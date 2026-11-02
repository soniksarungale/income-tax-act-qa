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


def fake_run(stdout, returncode=0, seen=None):
    def run(args, **kwargs):
        if seen is not None:
            seen.update(args=args, **kwargs)
        return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr="")
    return run


def test_claude_cli_sends_prompt_on_stdin_with_tools_disabled(provider, monkeypatch):
    provider("claude-cli", key="")
    seen = {}
    out = json.dumps({"subtype": "success", "result": " hello ", "modelUsage": {"claude-x": {}}})
    monkeypatch.setattr(subprocess, "run", fake_run(out, seen=seen))
    result = llm.complete("system text", "the question")
    assert (result.text, result.model) == ("hello", "claude-x")
    assert seen["input"] == "the question"
    args = seen["args"]
    assert args[args.index("--tools") + 1] == ""
    assert args[args.index("--setting-sources") + 1] == ""
    assert "--strict-mcp-config" in args and "--no-session-persistence" in args
    assert args[args.index("--model") + 1] == "sonnet"


def test_claude_cli_errors_are_reported(provider, monkeypatch):
    provider("claude-cli", key="")
    monkeypatch.setattr(subprocess, "run", fake_run(json.dumps({"is_error": True, "result": "not logged in"})))
    with pytest.raises(llm.LLMError, match="not logged in"):
        llm.complete("s", "p")
    monkeypatch.setattr(subprocess, "run", fake_run("garbage", returncode=1))
    with pytest.raises(llm.LLMError, match="exit 1"):
        llm.complete("s", "p")


def test_claude_cli_runs_one_call_at_a_time(provider, monkeypatch):
    provider("claude-cli", key="")
    active, peak, lock = 0, 0, threading.Lock()
    out = json.dumps({"subtype": "success", "result": "ok"})

    def run(args, **kwargs):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        threading.Event().wait(0.05)
        with lock:
            active -= 1
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")

    monkeypatch.setattr(subprocess, "run", run)
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


@pytest.mark.parametrize("name,model,response,expected_url", [
    ("openai", "gpt-test", {"choices": [{"message": {"content": "answer"}}]},
     "https://api.openai.com/v1/chat/completions"),
    ("anthropic", "", {"content": [{"type": "text", "text": "answer"}]},
     "https://api.anthropic.com/v1/messages"),
    ("gemini", "gemini-test", {"candidates": [{"content": {"parts": [{"text": "answer"}]}}]},
     "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent"),
])
def test_http_providers(provider, monkeypatch, name, model, response, expected_url):
    provider(name, model=model)
    seen = {}

    def post(url, headers, json, timeout):
        seen.update(url=url, headers=headers, body=json)
        return httpx.Response(200, json=response)

    monkeypatch.setattr(httpx, "post", post)
    assert llm.complete("system text", "the question").text == "answer"
    assert seen["url"] == expected_url
    assert "test-key" in " ".join(seen["headers"].values())
    assert "key=" not in seen["url"]
    body = seen["body"]
    assert (body["generationConfig"] if name == "gemini" else body)["temperature"] == 0


def test_http_error_message_is_passed_on(provider, monkeypatch):
    provider("anthropic")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(401, json={"error": {"message": "invalid x-api-key"}}))
    with pytest.raises(llm.LLMError, match="invalid x-api-key"):
        llm.complete("s", "p")
