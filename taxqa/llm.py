"""Pluggable LLM providers, chosen in .env (LLM_PROVIDER, LLM_MODEL, LLM_API_KEY).

claude-cli runs the Claude Code CLI that is installed and logged in on the server (`claude -p`), so it
needs no API key. openai, anthropic and gemini call the vendors' HTTP APIs with LLM_API_KEY.
"""

import json
import subprocess
import tempfile
import threading
import time
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


def model_name() -> str:
    model = settings.llm_model or DEFAULT_MODELS.get(settings.llm_provider, "")
    if not model:
        raise LLMError(f"Set LLM_MODEL in .env for the {settings.llm_provider} provider")
    return model


def complete(system: str, prompt: str, max_tokens: int = 2000) -> Completion:
    provider = settings.llm_provider
    if provider not in PROVIDERS:
        raise LLMError(f"Unknown LLM_PROVIDER {provider!r}; expected one of {', '.join(PROVIDERS)}")
    if provider != "claude-cli" and not settings.llm_api_key:
        raise LLMError(f"Set LLM_API_KEY in .env for the {provider} provider")
    model = model_name()
    started = time.monotonic()
    if provider == "claude-cli":
        text, model = _claude_cli(system, prompt, model)
    else:
        text = _HTTP[provider](system, prompt, model, max_tokens)
    return Completion(text.strip(), model, int((time.monotonic() - started) * 1000))


# claude-cli. Each CLI process peaks at about 220 MB and the server has 2 GB of RAM, so calls run one
# at a time and a short queue is allowed to build up before new requests are turned away.
_cli_lock = threading.Lock()
_cli_waiting = 0
_cli_counter = threading.Lock()
# An empty working directory, so the CLI picks up no CLAUDE.md or project settings.
_CLI_CWD = Path(tempfile.gettempdir()) / "taxqa-claude-cli"


def _claude_cli(system: str, prompt: str, model: str) -> tuple[str, str]:
    global _cli_waiting
    with _cli_counter:
        if _cli_waiting >= CLI_MAX_WAITING:
            raise LLMBusy("Too many questions are queued; try again in a minute.")
        _cli_waiting += 1
    try:
        with _cli_lock:
            return _run_cli(system, prompt, model)
    finally:
        with _cli_counter:
            _cli_waiting -= 1


def _run_cli(system: str, prompt: str, model: str) -> tuple[str, str]:
    _CLI_CWD.mkdir(exist_ok=True)
    # No tools, no MCP servers, no user or project settings, nothing saved to disk. The prompt goes over
    # stdin: no argument length limit, and it does not show up in `ps`.
    args = [settings.claude_bin, "-p", "--output-format", "json", "--tools", "", "--no-session-persistence",
            "--setting-sources", "", "--strict-mcp-config", "--system-prompt", system, "--model", model]
    try:
        proc = subprocess.run(args, input=prompt, capture_output=True, text=True, timeout=CLI_TIMEOUT,
                              cwd=_CLI_CWD)
    except FileNotFoundError as e:
        raise LLMError(f"Could not start the Claude CLI ({settings.claude_bin}); set CLAUDE_BIN") from e
    except subprocess.TimeoutExpired as e:
        raise LLMError("The Claude CLI timed out") from e
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        detail = (proc.stderr or proc.stdout).strip()[:300] or "no output"
        raise LLMError(f"Claude CLI failed (exit {proc.returncode}): {detail}") from e
    if data.get("is_error") or data.get("subtype") != "success":
        raise LLMError(f"Claude CLI error: {str(data.get('result') or data.get('subtype'))[:300]}")
    used = next(iter(data.get("modelUsage") or {}), model)
    return str(data.get("result") or ""), used


def _post(url: str, headers: dict, body: dict) -> dict:
    try:
        res = httpx.post(url, headers=headers, json=body, timeout=HTTP_TIMEOUT)
    except httpx.HTTPError as e:
        raise LLMError(f"LLM request failed: {e}") from e
    try:
        data = res.json()
    except ValueError:
        data = {}
    if res.status_code >= 400:
        error = data.get("error") if isinstance(data, dict) else None
        message = error.get("message") if isinstance(error, dict) else None
        raise LLMError(message or f"LLM HTTP {res.status_code}")
    return data


# Temperature 0: answers must stick to the retrieved text, not vary between runs.
def _openai(system: str, prompt: str, model: str, max_tokens: int) -> str:
    data = _post(
        "https://api.openai.com/v1/chat/completions",
        {"authorization": f"Bearer {settings.llm_api_key}"},
        {"model": model, "max_tokens": max_tokens, "temperature": 0,
         "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]},
    )
    return data["choices"][0]["message"]["content"] or ""


def _anthropic(system: str, prompt: str, model: str, max_tokens: int) -> str:
    data = _post(
        "https://api.anthropic.com/v1/messages",
        {"x-api-key": settings.llm_api_key, "anthropic-version": "2023-06-01"},
        {"model": model, "max_tokens": max_tokens, "temperature": 0, "system": system,
         "messages": [{"role": "user", "content": prompt}]},
    )
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


def _gemini(system: str, prompt: str, model: str, max_tokens: int) -> str:
    # Key in a header rather than the query string, so it does not end up in access logs.
    data = _post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        {"x-goog-api-key": settings.llm_api_key},
        {"systemInstruction": {"parts": [{"text": system}]},
         "contents": [{"role": "user", "parts": [{"text": prompt}]}],
         "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0}},
    )
    candidates = data.get("candidates") or [{}]
    return "".join(p.get("text", "") for p in candidates[0].get("content", {}).get("parts", []))


_HTTP = {"openai": _openai, "anthropic": _anthropic, "gemini": _gemini}
