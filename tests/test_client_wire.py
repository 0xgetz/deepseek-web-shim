"""Client tests driven through a fake transport.

No request leaves this process, but every request the client makes is now
inspected: the deepseek_web_shim.client HTTP layer runs for real against a
stand-in session. Before this file the client was only unit tested by calling
its pure helpers, which meant the wire contract (headers, body shape, SSE
parsing, error paths) was never exercised at all.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from deepseek_web_shim import client as client_mod
from deepseek_web_shim.client import DeepSeekWeb
from deepseek_web_shim.pow import deepseek_sha3, pow_prefix


# --- fake transport --------------------------------------------------------


class FakeCookies:
    def __init__(self, jar=None):
        self.jar = list(jar or [])

    class _C:
        def __init__(self, name, value):
            self.name, self.value = name, value

    def set(self, name, value, domain=None):
        self.jar.append(self._C(name, value))

    def get(self, name, domain=None):
        for c in self.jar:
            if c.name == name:
                return c.value
        return None


class FakeResponse:
    def __init__(self, status_code=200, json_body=None, text="", lines=()):
        self.status_code = status_code
        self._json = json_body
        self.text = text if text else json.dumps(json_body) if json_body else ""
        self._lines = list(lines)

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json

    def iter_lines(self):
        yield from self._lines


class FakeSession:
    """Records every call so tests can assert on the exact wire contract."""

    def __init__(self, impersonate=None, script=None):
        self.impersonate = impersonate
        self.proxies = {}
        self.cookies = FakeCookies()
        self.calls: list[dict] = []
        self._script = script or {}

    def _respond(self, key, method, url, kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        for prefix, resp in self._script.items():
            if prefix in url and (resp is not None):
                return resp() if callable(resp) else resp
        return FakeResponse(200, {"data": {"biz_data": {"id": "default-session",
                                                        "challenge": {}, "user": {}}}})

    def get(self, url, **kwargs):
        return self._respond("GET", "GET", url, kwargs)

    def post(self, url, **kwargs):
        return self._respond("POST", "POST", url, kwargs)


@pytest.fixture()
def wire(monkeypatch):
    """Install a fake session and hand back (client, session)."""
    holder = {}

    def factory(impersonate=None):
        s = FakeSession(impersonate=impersonate, script=holder.get("script", {}))
        holder["session"] = s
        return s

    monkeypatch.setattr(client_mod.cffi_requests, "Session", factory)
    monkeypatch.setenv("DSW_POW_BACKEND", "pure")  # no wasm needed for these

    def make(**kw):
        holder["script"] = kw.pop("script", {})
        c = DeepSeekWeb(**kw)
        return c, holder["session"]

    make.holder = holder
    return make


SALT, EXPIRE, ANSWER = "s", 1_800_000_000, 7


def _challenge(planted=ANSWER):
    """A synthetic challenge with a known solution, so the client's real PoW
    path runs end to end instead of hitting the difficulty bound."""
    prefix = pow_prefix(SALT, EXPIRE)
    target = deepseek_sha3((prefix + str(planted)).encode()).hex()
    return {"algorithm": "sha3", "challenge": target, "salt": SALT,
            "expire_at": EXPIRE, "difficulty": 300, "signature": "sig",
            "target_path": "/api/v0/chat/completion"}


# --- the wire contract -----------------------------------------------------


def test_every_request_carries_the_browser_identity_headers(wire):
    """The TLS/HTTP fingerprint check is why these headers exist; a dropped one
    is what makes the whole shim stop working."""
    c, s = wire(token="tok-1")
    c.get_session_id()
    sent = s.calls[-1]["headers"]
    assert sent["x-client-platform"] == "web"
    assert sent["x-client-version"] == "1.7.0"
    assert sent["x-app-version"] == "20241129.1"
    assert sent["x-client-locale"] == "en_US"
    assert sent["origin"] == client_mod.BASE
    assert sent["authorization"] == "Bearer tok-1"
    assert "Chrome/131" in sent["user-agent"]


def test_session_is_created_with_impersonation_not_a_plain_httpx_session(wire):
    """Plain HTTP libraries get fingerprinted and refused, so the impersonation
    profile is load-bearing, not cosmetic."""
    c, s = wire()
    assert s.impersonate == client_mod.IMPERSONATE


def test_warmup_hits_the_root_to_harvest_the_waf_cookie(wire):
    c, s = wire()
    assert c.warmup() == 200
    assert s.calls[-1]["method"] == "GET"
    assert s.calls[-1]["url"] == f"{client_mod.BASE}/"
    assert "user-agent" in s.calls[-1]["headers"]


# --- challenge + session id ------------------------------------------------


def test_get_session_id_reads_biz_data_id(wire):
    c, s = wire(script={"chat_session/create": FakeResponse(
        200, {"data": {"biz_data": {"id": "chat-xyz"}}})})
    assert c.get_session_id() == "chat-xyz"
    assert s.calls[-1]["json"] == {"character_id": None}


def test_get_session_id_error_names_the_status_and_body(wire):
    c, s = wire(script={"chat_session/create": FakeResponse(
        401, {"code": 1}, text='{"code":1,"msg":"unauthorized"}')})
    with pytest.raises(RuntimeError, match="chat_session/create failed: 401"):
        c.get_session_id()


def test_create_pow_challenge_unwraps_biz_data_challenge(wire):
    ch = _challenge()
    c, s = wire(script={"create_pow_challenge": FakeResponse(
        200, {"data": {"biz_data": {"challenge": ch}}})})
    assert c.create_pow_challenge() == ch
    assert s.calls[-1]["json"] == {"target_path": "/api/v0/chat/completion"}


def test_create_pow_challenge_error_is_reported_not_swallowed(wire):
    """A WAF page here is the common real outcome, so the error must name the
    step and include what came back."""
    c, s = wire(script={"create_pow_challenge": FakeResponse(
        403, None, text="<html>waf</html>")})
    with pytest.raises(RuntimeError, match=r"create_pow_challenge.*403") as ei:
        c.create_pow_challenge()
    assert "<html>waf</html>" in str(ei.value)


# --- login -----------------------------------------------------------------


def test_login_registers_the_device_then_authenticates(wire):
    c, s = wire(script={"users/login": FakeResponse(
        200, {"code": 0, "data": {"biz_data": {"user": {"token": "tok-live"}}}})})
    assert c.login("a@b.c", "pw") == "tok-live"
    assert c.token == "tok-live"
    urls = [call["url"] for call in s.calls]
    assert urls[0].endswith("/api/v0/users/create_session")
    assert urls[-1].endswith("/api/v0/users/login")
    body = s.calls[-1]["json"]
    assert body["email"] == "a@b.c" and body["password"] == "pw"
    assert body["device_id"] == c.device_id and body["os"] == "web"


def test_login_rejects_a_nonzero_business_code(wire):
    c, s = wire(script={"users/login": FakeResponse(
        200, {"code": 40003, "msg": "wrong password"})})
    with pytest.raises(RuntimeError, match="login rejected"):
        c.login("a@b.c", "nope")


def test_login_rejects_a_response_with_no_token(wire):
    c, s = wire(script={"users/login": FakeResponse(
        200, {"code": 0, "data": {"biz_data": {"user": {}}}})})
    with pytest.raises(RuntimeError, match="no token"):
        c.login("a@b.c", "pw")


def test_login_surfaces_an_http_error(wire):
    c, s = wire(script={"users/login": FakeResponse(429, None, text="slow down")})
    with pytest.raises(RuntimeError, match="login http 429"):
        c.login("a@b.c", "pw")


# --- completion ------------------------------------------------------------


def test_completion_fetches_a_challenge_then_sends_the_pow_header(wire):
    """The PoW header is what the upstream checks; it must be base64 JSON and
    must carry the fields the challenge came with."""
    import base64

    ch = _challenge()
    c, s = wire(script={
        "create_pow_challenge": FakeResponse(200, {"data": {"biz_data": {"challenge": ch}}}),
        "completion": FakeResponse(200, lines=[b'data: {"content":"hi"}', b"data: [DONE]"]),
    })
    out = list(c.completion("hello", "sess-1"))
    assert out == [{"content": "hi"}]
    sent = s.calls[-1]
    hdr = json.loads(base64.b64decode(sent["headers"]["x-ds-pow-response"]))
    assert hdr["algorithm"] == "sha3" and hdr["challenge"] == ch["challenge"]
    assert hdr["salt"] == ch["salt"] and hdr["signature"] == ch["signature"]
    assert sent["headers"]["accept"] == "text/event-stream"
    assert sent["stream"] is True


def test_completion_body_matches_the_documented_contract(wire):
    ch = _challenge()
    c, s = wire(script={
        "create_pow_challenge": FakeResponse(200, {"data": {"biz_data": {"challenge": ch}}}),
        "completion": FakeResponse(200, lines=[b"data: [DONE]"]),
    })
    list(c.completion("hello", "sess-1", model_type="default", thinking=True, search=True))
    body = s.calls[-1]["json"]
    assert body == {
        "chat_session_id": "sess-1", "parent_message_id": None, "model_type": "default",
        "prompt": "hello", "ref_file_ids": [], "thinking_enabled": True,
        "search_enabled": True, "preempt": False,
    }


def test_completion_parses_sse_and_stops_at_done(wire):
    ch = _challenge()
    lines = [b'data: {"content":"a"}', b"", b'data: {"content":"b"}',
             b"data: [DONE]", b'data: {"content":"never"}']
    c, s = wire(script={
        "create_pow_challenge": FakeResponse(200, {"data": {"biz_data": {"challenge": ch}}}),
        "completion": FakeResponse(200, lines=lines),
    })
    assert [x["content"] for x in c.completion("hi", "s")] == ["a", "b"]


def test_completion_skips_malformed_sse_lines_instead_of_dying(wire):
    """A half-line or a keepalive must not kill a stream that is otherwise fine."""
    ch = _challenge()
    lines = [b"data: {not json", b": keepalive", b"event: ping",
             b'data: {"content":"ok"}', b"data: [DONE]"]
    c, s = wire(script={
        "create_pow_challenge": FakeResponse(200, {"data": {"biz_data": {"challenge": ch}}}),
        "completion": FakeResponse(200, lines=lines),
    })
    assert [x["content"] for x in c.completion("hi", "s")] == ["ok"]


def test_completion_raises_with_the_status_when_upstream_refuses(wire):
    ch = _challenge()
    c, s = wire(script={
        "create_pow_challenge": FakeResponse(200, {"data": {"biz_data": {"challenge": ch}}}),
        "completion": FakeResponse(429, None, text="rate limited"),
    })
    with pytest.raises(RuntimeError, match="completion http 429"):
        list(c.completion("hi", "s"))


def test_completion_without_a_usable_challenge_fails_before_posting(wire):
    """A missing/blank challenge must fail loudly, not send a bogus PoW header."""
    c, s = wire(script={"create_pow_challenge": FakeResponse(200, {"data": {}})})
    with pytest.raises(RuntimeError, match="create_pow_challenge failed"):
        list(c.completion("hi", "s"))
    assert all("chat/completion" not in call["url"] for call in s.calls)


def test_a_non_json_response_is_reported_by_name_not_as_a_bare_valueerror(wire):
    """Upstream answers a refused request with an HTML WAF page. That must come
    back as a named RuntimeError that says which step failed."""
    c, s = wire(script={"chat_session/create": FakeResponse(
        403, None, text="<html><body>AWS WAF challenge</body></html>")})
    with pytest.raises(RuntimeError, match="chat_session/create returned non-JSON"):
        c.get_session_id()


def test_login_surfaces_a_gateway_error_with_its_body(wire):
    """Status is checked before parsing, so a 502 is reported as a 502 and the
    body is included: that is what tells you it was a gateway page, not a
    credential rejection."""
    c, s = wire(script={"users/login": FakeResponse(502, None, text="<html>bad gateway</html>")})
    with pytest.raises(RuntimeError, match=r"login http 502") as ei:
        c.login("a@b.c", "pw")
    assert "bad gateway" in str(ei.value)
