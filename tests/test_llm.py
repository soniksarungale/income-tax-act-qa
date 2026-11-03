import contextlib
import io
import json
import subprocess
import threading

import httpx
import pytest

from taxqa import llm
from taxqa.config import settings


@pytest.fixture
def provider(monkeypatch):
    def use(name, key="test-key", model=""):
        monkeypatch.setattr(settings, "llm_provider", name)
        monkeypatch.setattr(settings, "llm_api_key", key)
        monkeypatch.setattr(settings, "llm_model", model)
    return use


def cli_output(text="hello", model="claude-x", pieces=None, result=None):
    lines = [{"type": "system", "subtype": "init"}]
    for piece in pieces or [text]:
        lines.append({"type": "stream_event",
                      "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": piece}}})
    lines.append(result or {"type": "result", "subtype": "success", "result": text, "modelUsage": {model: {}}})
    return "".join(json.dumps(line) + "\n" for line in lines)


class FakePopen:
    """Stands in for the CLI process: records how it was started and replays canned stdout."""

    def __init__(self, stdout, returncode=0, seen=None, delay=0.0):
        self.stdout_text, self.code, self.seen, self.delay = stdout, returncode, seen, delay

    def __call__(self, args, **kwargs):
        if self.seen is not None:
            self.seen.update(args=args, **kwargs)
        self.args, self.returncode = args, None
        self.stdin = io.StringIO()
        if self.seen is not None:
            self.seen["stdin"] = self.stdin
        self.stdin.close = lambda: self.seen is not None and self.seen.update(input=self.stdin.getvalue())
        if self.delay:
            threading.Event().wait(self.delay)
        self.stdout = io.StringIO(self.stdout_text)
        return self

    def wait(self):
        self.returncode = self.code
        return self.code

    def poll(self):
        return self.returncode

    def kill(self):
        self.returncode = -9


def test_claude_cli_sends_prompt_on_stdin_with_tools_disabled(provider, monkeypatch):
    provider("claude-cli", key="")
    seen = {}
    monkeypatch.setattr(subprocess, "Popen", FakePopen(cli_output(" hello "), seen=seen))
    result = llm.complete("system text", "the question")
    assert (result.text, result.model) == ("hello", "claude-x")
    assert seen["input"] == "the question"
    args = seen["args"]
    assert args[args.index("--tools") + 1] == ""
    assert args[args.index("--setting-sources") + 1] == ""
    assert "--strict-mcp-config" in args and "--no-session-persistence" in args
    assert args[args.index("--model") + 1] == "sonnet"
    assert args[args.index("--output-format") + 1] == "stream-json" and "--include-partial-messages" in args


def test_claude_cli_streams_text_pieces(provider, monkeypatch):
    provider("claude-cli", key="")
    monkeypatch.setattr(subprocess, "Popen", FakePopen(cli_output("one two", pieces=["one", " two"])))
    s = llm.stream("s", "p")
    assert list(s) == ["one", " two"]
    assert (s.text, s.model) == ("one two", "claude-x")


def test_claude_cli_errors_are_reported(provider, monkeypatch):
    provider("claude-cli", key="")
    error = {"type": "result", "subtype": "error", "is_error": True, "result": "not logged in"}
    monkeypatch.setattr(subprocess, "Popen", FakePopen(cli_output(pieces=[""], result=error)))
    with pytest.raises(llm.LLMError, match="not logged in"):
        llm.complete("s", "p")
    monkeypatch.setattr(subprocess, "Popen", FakePopen("garbage", returncode=1))
    with pytest.raises(llm.LLMError, match="exit 1"):
        llm.complete("s", "p")


def test_claude_cli_runs_one_call_at_a_time(provider, monkeypatch):
    provider("claude-cli", key="")
    active, peak, lock = 0, 0, threading.Lock()

    class Counting(FakePopen):
        def __call__(self, args, **kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            threading.Event().wait(0.05)
            return FakePopen.__call__(self, args, **kwargs)

        def wait(self):
            nonlocal active
            with lock:
                active -= 1
            return FakePopen.wait(self)

    def popen(args, **kwargs):
        return Counting(cli_output("ok"))(args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", popen)
    threads = [threading.Thread(target=llm.complete, args=("s", "p")) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak == 1


def test_claude_cli_turns_away_requests_when_the_queue_is_full(provider, monkeypatch):
    provider("claude-cli", key="")
    monkeypatch.setattr(llm, "_cli_waiting", llm.CLI_MAX_WAITING)
    with pytest.raises(llm.LLMBusy):
        llm.complete("s", "p")


def test_http_providers_need_a_key_and_openai_gemini_need_a_model(provider):
    provider("openai", key="")
    with pytest.raises(llm.LLMError, match="LLM_API_KEY"):
        llm.complete("s", "p")
    provider("gemini")
    with pytest.raises(llm.LLMError, match="LLM_MODEL"):
        llm.complete("s", "p")
    provider("mistral")
    with pytest.raises(llm.LLMError, match="Unknown LLM_PROVIDER"):
        llm.complete("s", "p")


def sse(*events):
    return "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"


@pytest.mark.parametrize("name,model,body,expected_url", [
    ("openai", "gpt-test",
     sse({"model": "gpt-test", "choices": [{"delta": {"content": "ans"}}]},
         {"model": "gpt-test", "choices": [{"delta": {"content": "wer"}}]}),
     "https://api.openai.com/v1/chat/completions"),
    ("anthropic", "",
     sse({"type": "message_start", "message": {"model": "claude-sonnet-5-5"}},
         {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "ans"}},
         {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "wer"}},
         {"type": "message_stop"}),
     "https://api.anthropic.com/v1/messages"),
    ("gemini", "gemini-test",
     sse({"candidates": [{"content": {"parts": [{"text": "ans"}]}}]},
         {"candidates": [{"content": {"parts": [{"text": "wer"}]}}]}),
     "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:streamGenerateContent?alt=sse"),
])
def test_http_providers(provider, monkeypatch, name, model, body, expected_url):
    provider(name, model=model)
    seen = {}

    @contextlib.contextmanager
    def stream(method, url, headers, json, timeout):
        seen.update(url=url, headers=headers, body=json)
        yield httpx.Response(200, text=body)

    monkeypatch.setattr(httpx, "stream", stream)
    s = llm.stream("system text", "the question")
    assert list(s) == ["ans", "wer"] and s.text == "answer"
    assert seen["url"] == expected_url
    assert "test-key" in " ".join(seen["headers"].values())
    assert "key=" not in seen["url"]
    sent = seen["body"]
    assert (sent["generationConfig"] if name == "gemini" else sent)["temperature"] == 0


def test_http_error_message_is_passed_on(provider, monkeypatch):
    provider("anthropic")

    @contextlib.contextmanager
    def stream(*args, **kwargs):
        yield httpx.Response(401, json={"error": {"message": "invalid x-api-key"}})

    monkeypatch.setattr(httpx, "stream", stream)
    with pytest.raises(llm.LLMError, match="invalid x-api-key"):
        llm.complete("s", "p")
