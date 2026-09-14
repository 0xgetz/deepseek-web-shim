"""Server tests — offline, via an injected fake DeepSeek client (no network)."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from deepseek_web_shim import server


class FakePow:
    backend = "fake"


class FakeDeepSeek:
    """Mimics DeepSeekWeb's surface. Records calls so tests can assert on the flow."""

    def __init__(self, chunks=("Hello", " ", "world")):
        self.pow = FakePow()
        self.token = "fake-token"
        self.chunks = chunks
        self.session_calls = 0
        self.completions: list[dict] = []

    def get_session_id(self) -> str:
        self.session_calls += 1
        return f"session-{self.session_calls}"

    def completion(self, prompt, session_id, model_type="default", thinking=False, search=False,
                   parent_message_id=None):
        self.completions.append({
            "prompt": prompt, "session_id": session_id, "model_type": model_type,
            "thinking": thinking, "search": search,
        })
        for c in self.chunks:
            yield {"content": c}


@pytest.fixture()
def fake(monkeypatch):
    f = FakeDeepSeek()
    monkeypatch.setenv("DSW_API_KEY", "test-key")
    server.set_client(f)
    server._sessions.clear()
    yield f
    server.set_client(None)
    server._sessions.clear()


@pytest.fixture()
def http():
    return TestClient(server.app)


def _body(stream=False, model="deepseek-web", user="hi", system=None):
    msgs = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": user}
    ]
    return {"model": model, "messages": msgs, "stream": stream}


# --- auth ------------------------------------------------------------------


def test_models_requires_the_configured_key(fake, http):
    assert http.get("/v1/models").status_code == 401
    assert http.get("/v1/models", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert http.get("/v1/models", headers={"Authorization": "Bearer test-key"}).status_code == 200


def test_chat_requires_the_configured_key(fake, http):
    r = http.post("/v1/chat/completions", json=_body())
    assert r.status_code == 401


def test_missing_key_is_not_configured_rather_than_open(fake, http, monkeypatch):
    """No DSW_API_KEY and no explicit opt-in must refuse, not quietly serve."""
    monkeypatch.delenv("DSW_API_KEY", raising=False)
    monkeypatch.delenv("DSW_ALLOW_NO_AUTH", raising=False)
    r = http.get("/v1/models")
    assert r.status_code == 503
    assert r.json()["detail"]["error"]["type"] == "not_configured"
    assert "DSW_API_KEY" in r.json()["detail"]["error"]["message"]


def test_auth_is_off_only_with_an_explicit_opt_in(fake, http, monkeypatch):
    monkeypatch.delenv("DSW_API_KEY", raising=False)
    monkeypatch.setenv("DSW_ALLOW_NO_AUTH", "1")
    assert http.get("/v1/models").status_code == 200


def test_healthz_stays_open_so_you_can_see_whats_wrong(fake, http, monkeypatch):
    """healthz is the diagnostic: it must answer even when the port is unconfigured."""
    monkeypatch.delenv("DSW_API_KEY", raising=False)
    monkeypatch.delenv("DSW_ALLOW_NO_AUTH", raising=False)
    assert http.get("/healthz").status_code == 200


# --- health & models -------------------------------------------------------


def test_healthz_reports_backend_and_auth_state(fake, http):
    r = http.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "pow_backend": "fake", "authenticated": True}


def test_models_lists_the_three_web_variants(fake, http):
    data = http.get("/v1/models", headers={"Authorization": "Bearer test-key"}).json()
    assert data["object"] == "list"
    assert [m["id"] for m in data["data"]] == [
        "deepseek-web", "deepseek-web-reasoner", "deepseek-web-search",
    ]
    assert all(m["object"] == "model" for m in data["data"])


# --- chat ------------------------------------------------------------------


def test_non_streaming_chat_concatenates_fragments(fake, http):
    r = http.post("/v1/chat/completions", json=_body(),
                  headers={"Authorization": "Bearer test-key"})
    assert r.status_code == 200
    data = r.json()
    assert data["object"] == "chat.completion"
    assert data["choices"][0]["message"] == {"role": "assistant", "content": "Hello world"}
    assert data["choices"][0]["finish_reason"] == "stop"
    assert data["usage"]["total_tokens"] == 0


def test_streaming_chat_emits_openai_sse_frames(fake, http):
    r = http.post("/v1/chat/completions", json=_body(stream=True),
                  headers={"Authorization": "Bearer test-key"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    lines = [ln for ln in r.text.split("\n\n") if ln.strip()]
    assert lines[-1] == "data: [DONE]"
    deltas = [json.loads(ln[6:]) for ln in lines[:-1]]
    assert "".join(d["choices"][0]["delta"].get("content", "") for d in deltas) == "Hello world"
    assert deltas[-1]["choices"][0]["finish_reason"] == "stop"


def test_model_variants_map_to_deepseek_flags(fake, http):
    hdr = {"Authorization": "Bearer test-key"}
    http.post("/v1/chat/completions", json=_body(model="deepseek-web-reasoner"), headers=hdr)
    assert fake.completions[-1]["thinking"] is True
    assert fake.completions[-1]["search"] is False

    http.post("/v1/chat/completions", json=_body(model="deepseek-web-search"), headers=hdr)
    assert fake.completions[-1]["thinking"] is False
    assert fake.completions[-1]["search"] is True

    http.post("/v1/chat/completions", json=_body(model="unknown-model"), headers=hdr)
    assert fake.completions[-1]["model_type"] == "default"


def test_unknown_extra_fields_are_ignored(fake, http):
    body = _body()
    body.update({"temperature": 0.2, "max_tokens": 10, "tools": [{"type": "function"}]})
    r = http.post("/v1/chat/completions", json=body, headers={"Authorization": "Bearer test-key"})
    assert r.status_code == 200


def test_missing_or_empty_messages_is_a_clean_400(fake, http):
    hdr = {"Authorization": "Bearer test-key"}
    assert http.post("/v1/chat/completions", json={"model": "deepseek-web"}, headers=hdr).status_code == 400
    assert http.post("/v1/chat/completions", json={"messages": []}, headers=hdr).status_code == 400


# --- conversation threading ------------------------------------------------
# The shim is stateless: a conversation is identified by the system prompt plus
# the *first* user message. An OpenAI client resends the whole history each
# turn, so the opening turn stays put and the DeepSeek session is reused —
# that is what makes multi-turn work without any server-side conversation store.


def test_same_conversation_reuses_one_deepseek_session(fake, http):
    hdr = {"Authorization": "Bearer test-key"}
    first = {"role": "user", "content": "first question"}
    http.post("/v1/chat/completions", json={"model": "deepseek-web", "messages": [first]},
              headers=hdr)
    # second turn: client resends history, so the opening message is unchanged
    http.post("/v1/chat/completions", json={"model": "deepseek-web", "messages": [
        first, {"role": "assistant", "content": "answer"}, {"role": "user", "content": "follow up"},
    ]}, headers=hdr)
    assert fake.session_calls == 1
    assert fake.completions[0]["session_id"] == fake.completions[1]["session_id"]


def test_different_conversations_get_separate_sessions(fake, http):
    hdr = {"Authorization": "Bearer test-key"}
    http.post("/v1/chat/completions", json=_body(user="question A"), headers=hdr)
    http.post("/v1/chat/completions", json=_body(user="question B"), headers=hdr)
    assert fake.session_calls == 2
    assert fake.completions[0]["session_id"] != fake.completions[1]["session_id"]


def test_same_opening_turn_but_different_system_prompt_is_a_new_session(fake, http):
    hdr = {"Authorization": "Bearer test-key"}
    http.post("/v1/chat/completions", json=_body(user="hi", system="persona A"), headers=hdr)
    http.post("/v1/chat/completions", json=_body(user="hi", system="persona B"), headers=hdr)
    assert fake.session_calls == 2


# --- prompt flattening -----------------------------------------------------


def test_flatten_keeps_every_role_and_folds_content_parts():
    msgs = [
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": [{"type": "text", "text": "part one "},
                                     {"type": "image_url", "image_url": {"url": "x"}},
                                     {"type": "text", "text": "part two"}]},
        {"role": "assistant", "content": "ok"},
        {"role": "tool", "content": "result"},
    ]
    out = server._flatten(msgs)
    assert "[system]\nbe terse" in out
    assert "part one part two" in out
    assert "[assistant]\nok" in out
    assert "[tool result]\nresult" in out


def test_collect_handles_junk_without_raising():
    assert server._collect({"content": "x"}) == "x"
    assert server._collect({"type": "THINKING", "content": "hmm"}) == "hmm"
    assert server._collect({"unexpected": 1}) == ""
    assert server._collect(None) == ""


# --- upstream failure ------------------------------------------------------


def test_upstream_error_surfaces_as_sse_and_still_closes(fake, http, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("upstream exploded")
        yield  # pragma: no cover

    monkeypatch.setattr(fake, "completion", boom)
    r = http.post("/v1/chat/completions", json=_body(stream=True),
                  headers={"Authorization": "Bearer test-key"})
    assert r.status_code == 200
    assert "upstream exploded" in r.text
    assert r.text.rstrip().endswith("data: [DONE]")


def test_upstream_error_in_non_streaming_mode_is_a_502_json(fake, http, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("upstream exploded")
        yield  # pragma: no cover

    monkeypatch.setattr(fake, "completion", boom)
    r = http.post("/v1/chat/completions", json=_body(),
                  headers={"Authorization": "Bearer test-key"})
    assert r.status_code == 502
    assert r.json()["detail"]["error"]["type"] == "upstream_error"
    assert "upstream exploded" in r.json()["detail"]["error"]["message"]


# --- honest failure states -------------------------------------------------


def test_missing_session_is_a_401_json_not_an_html_500(fake, http):
    """Regression: an unauthenticated shim used to answer 'Internal Server Error'."""
    fake.token = None
    r = http.post("/v1/chat/completions", json=_body(),
                  headers={"Authorization": "Bearer test-key"})
    assert r.status_code == 401
    detail = r.json()["detail"]["error"]
    assert detail["type"] == "not_authenticated"
    assert "--session" in detail["message"]
    assert "<html" not in r.text


def test_upstream_rejection_of_session_create_is_a_502_json(fake, http, monkeypatch):
    def boom():
        raise RuntimeError("chat_session/create failed: 401 {\"code\":1}")

    monkeypatch.setattr(fake, "get_session_id", boom)
    r = http.post("/v1/chat/completions", json=_body(),
                  headers={"Authorization": "Bearer test-key"})
    assert r.status_code == 502
    assert r.json()["detail"]["error"]["type"] == "upstream_error"


def test_healthz_tells_the_truth_when_there_is_no_session(fake, http):
    fake.token = None
    assert http.get("/healthz").json()["authenticated"] is False
