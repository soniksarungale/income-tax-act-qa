"""Pluggable LLM providers, chosen in .env (LLM_PROVIDER, LLM_MODEL, LLM_API_KEY).

claude-cli runs the Claude Code CLI that is installed and logged in on the server (`claude -p`), so it
needs no API key. openai, anthropic and gemini call the vendors' HTTP APIs with LLM_API_KEY.
"""

import json
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx

from taxqa.config import settings

PROVIDERS = ("claude-cli", "openai", "anthropic", "gemini")
# Only where the alias is stable. OpenAI and Gemini model names change often, so LLM_MODEL is required.
DEFAULT_MODELS = {"claude-cli": "sonnet", "anthropic": "claude-sonnet-5-5"}
CLI_TIMEOUT = 180
HTTP_TIMEOUT = 90
CLI_MAX_WAITING = 8


class LLMError(RuntimeError):
    pass


class LLMBusy(LLMError):
    pass


@dataclass
class Completion:
    text: str
    model: str
    ms: int


class Stream:
    """Text from the model as it is generated. Iterate it once for the pieces; afterwards .text, .model
    and .ms hold the whole reply, the model that produced it and the time taken."""

    def __init__(self, pieces: Callable[[dict], Iterator[str]], model: str):
        self._pieces = pieces
        self.text, self.model, self.ms = "", model, 0

    def __iter__(self) -> Iterator[str]:
        started = time.monotonic()
        meta: dict = {}
        parts = []
        for piece in self._pieces(meta):
            if piece:
                parts.append(piece)
                yield piece
        # The CLI also reports the full reply at the end; prefer it over the joined pieces.
        self.text = (meta.get("text") or "".join(parts)).strip()
        self.model = meta.get("model") or self.model
        self.ms = int((time.monotonic() - started) * 1000)


def model_name() -> str:
    model = settings.llm_model or DEFAULT_MODELS.get(settings.llm_provider, "")
    if not model:
        raise LLMError(f"Set LLM_MODEL in .env for the {settings.llm_provider} provider")
    return model


def stream(system: str, prompt: str, max_tokens: int = 2000) -> Stream:
    """Configuration errors are raised here; errors from the model are raised while iterating."""
    provider = settings.llm_provider
    if provider not in PROVIDERS:
        raise LLMError(f"Unknown LLM_PROVIDER {provider!r}; expected one of {', '.join(PROVIDERS)}")
    if provider != "claude-cli" and not settings.llm_api_key:
        raise LLMError(f"Set LLM_API_KEY in .env for the {provider} provider")
    model = model_name()
    if provider == "claude-cli":
        return Stream(lambda meta: _claude_cli(system, prompt, model, meta), model)
    return Stream(lambda meta: _HTTP[provider](system, prompt, model, max_tokens, meta), model)


def complete(system: str, prompt: str, max_tokens: int = 2000) -> Completion:
    s = stream(system, prompt, max_tokens)
    for _ in s:
        pass
    return Completion(s.text, s.model, s.ms)


# claude-cli. Each CLI process peaks at about 220 MB and the server has 2 GB of RAM, so calls run one
# at a time and a short queue is allowed to build up before new requests are turned away. The lock is
# held while the reply streams, and released when the stream ends or is abandoned.
_cli_lock = threading.Lock()
_cli_waiting = 0
_cli_counter = threading.Lock()
# An empty working directory, so the CLI picks up no CLAUDE.md or project settings.
_CLI_CWD = Path(tempfile.gettempdir()) / "taxqa-claude-cli"


def _claude_cli(system: str, prompt: str, model: str, meta: dict) -> Iterator[str]:
    global _cli_waiting
    with _cli_counter:
        if _cli_waiting >= CLI_MAX_WAITING:
            raise LLMBusy("Too many questions are queued; try again in a minute.")
        _cli_waiting += 1
    try:
        with _cli_lock:
            yield from _run_cli(system, prompt, model, meta)
    finally:
        with _cli_counter:
            _cli_waiting -= 1


def _run_cli(system: str, prompt: str, model: str, meta: dict) -> Iterator[str]:
    _CLI_CWD.mkdir(exist_ok=True)
    # No tools, no MCP servers, no user or project settings, nothing saved to disk. The prompt goes over
    # stdin: no argument length limit, and it does not show up in `ps`. stream-json with partial
    # messages emits each piece of text as the model writes it.
    args = [settings.claude_bin, "-p", "--output-format", "stream-json", "--include-partial-messages",
            "--verbose", "--tools", "", "--no-session-persistence", "--setting-sources", "",
            "--strict-mcp-config", "--system-prompt", system, "--model", model]
    # stderr goes to a file: a pipe nobody reads could fill up and stall the CLI.
    with tempfile.TemporaryFile() as err:
        try:
            proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err,
                                    text=True, cwd=_CLI_CWD)
        except FileNotFoundError as e:
            raise LLMError(f"Could not start the Claude CLI ({settings.claude_bin}); set CLAUDE_BIN") from e
        timed_out = threading.Event()

        def kill():
            timed_out.set()
            proc.kill()

        timer = threading.Timer(CLI_TIMEOUT, kill)
        timer.start()
        result = None
        try:
            try:
                proc.stdin.write(prompt)
                proc.stdin.close()
            except OSError:
                pass  # the CLI exited early; its error is read below
            for line in proc.stdout:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("type") == "stream_event":
                    inner = event.get("event") or {}
                    delta = inner.get("delta") or {}
                    if inner.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                        yield delta.get("text", "")
                elif event.get("type") == "result":
                    result = event
            proc.wait()
        finally:
            # Also runs when the reader stops early (the visitor closed the page): stop the CLI.
            timer.cancel()
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        if timed_out.is_set():
            raise LLMError("The Claude CLI timed out")
        if result is None:
            err.seek(0)
            detail = err.read().decode(errors="replace").strip()[:300] or "no output"
            raise LLMError(f"Claude CLI failed (exit {proc.returncode}): {detail}")
    if result.get("is_error") or result.get("subtype") != "success":
        raise LLMError(f"Claude CLI error: {str(result.get('result') or result.get('subtype'))[:300]}")
    meta["text"] = str(result.get("result") or "")
    meta["model"] = next(iter(result.get("modelUsage") or {}), model)


def _events(url: str, headers: dict, body: dict) -> Iterator[dict]:
    """POST and read the server-sent events of a streamed reply, one JSON object per data line."""
    try:
        with httpx.stream("POST", url, headers=headers, json=body, timeout=HTTP_TIMEOUT) as res:
            if res.status_code >= 400:
                res.read()
                try:
                    data = res.json()
                except ValueError:
                    data = {}
                # Gemini sends a list with one error object.
                data = data[0] if isinstance(data, list) and data else data
                error = data.get("error") if isinstance(data, dict) else None
                message = error.get("message") if isinstance(error, dict) else None
                raise LLMError(message or f"LLM HTTP {res.status_code}")
            for line in res.iter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    yield json.loads(payload)
                except ValueError:
                    continue
    except httpx.HTTPError as e:
        raise LLMError(f"LLM request failed: {e}") from e


# Temperature 0: answers must stick to the retrieved text, not vary between runs.
def _openai(system: str, prompt: str, model: str, max_tokens: int, meta: dict) -> Iterator[str]:
    body = {"model": model, "max_tokens": max_tokens, "temperature": 0, "stream": True,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
    for data in _events("https://api.openai.com/v1/chat/completions",
                        {"authorization": f"Bearer {settings.llm_api_key}"}, body):
        meta["model"] = data.get("model") or model
        for choice in data.get("choices") or []:
            yield (choice.get("delta") or {}).get("content") or ""


def _anthropic(system: str, prompt: str, model: str, max_tokens: int, meta: dict) -> Iterator[str]:
    body = {"model": model, "max_tokens": max_tokens, "temperature": 0, "stream": True, "system": system,
            "messages": [{"role": "user", "content": prompt}]}
    for data in _events("https://api.anthropic.com/v1/messages",
                        {"x-api-key": settings.llm_api_key, "anthropic-version": "2023-06-01"}, body):
        kind = data.get("type")
        if kind == "message_start":
            meta["model"] = (data.get("message") or {}).get("model") or model
        elif kind == "content_block_delta" and (data.get("delta") or {}).get("type") == "text_delta":
            yield data["delta"].get("text", "")
        elif kind == "error":
            raise LLMError((data.get("error") or {}).get("message") or "Anthropic stream error")


def _gemini(system: str, prompt: str, model: str, max_tokens: int, meta: dict) -> Iterator[str]:
    # Key in a header rather than the query string, so it does not end up in access logs.
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0}}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse"
    for data in _events(url, {"x-goog-api-key": settings.llm_api_key}, body):
        for candidate in (data.get("candidates") or [])[:1]:
            for part in (candidate.get("content") or {}).get("parts") or []:
                yield part.get("text", "")


_HTTP = {"openai": _openai, "anthropic": _anthropic, "gemini": _gemini}
