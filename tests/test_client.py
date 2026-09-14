"""Client tests — offline. No request ever leaves this process."""
from __future__ import annotations

import json

import pytest

from deepseek_web_shim import config
from deepseek_web_shim.client import DeepSeekWeb


def test_headers_carry_a_bearer_token_when_one_is_set():
    c = DeepSeekWeb(token="tok-123")
    h = c._headers("/x")
    assert h["authorization"] == "Bearer tok-123"
    assert h["content-type"] == "application/json"
    assert h["x-client-platform"] == "web"


def test_headers_omit_authorization_when_anonymous():
    assert "authorization" not in DeepSeekWeb()._headers("/x")


def test_extra_headers_win_over_defaults():
    c = DeepSeekWeb(token="t")
    h = c._headers("/x", {"x-ds-pow-response": "abc"})
    assert h["x-ds-pow-response"] == "abc"


def test_device_id_is_stable_within_a_client():
    c = DeepSeekWeb()
    assert c.device_id == c.device_id
    assert len(c.device_id) == 36


def test_state_round_trips_token_and_cookies(tmp_path, monkeypatch):
    monkeypatch.setenv("DSW_STATE_DIR", str(tmp_path))
    a = DeepSeekWeb(token="tok-abc")
    a.s.cookies.set("aws-waf-token", "waf-1", domain=".deepseek.com")
    a.save_state()

    f = config.session_file()
    assert f.exists()
    assert (f.stat().st_mode & 0o777) == 0o600  # secret file, owner-only

    b = DeepSeekWeb()
    assert b.load_state() is True
    assert b.token == "tok-abc"
    assert b.s.cookies.get("aws-waf-token", domain=".deepseek.com") == "waf-1"


def test_load_state_is_false_when_nothing_was_captured(tmp_path, monkeypatch):
    monkeypatch.setenv("DSW_STATE_DIR", str(tmp_path / "empty"))
    assert DeepSeekWeb().load_state() is False


def test_cookies_can_be_injected_directly():
    c = DeepSeekWeb(token="t", cookies={"aws-waf-token": "w"})
    assert c.s.cookies.get("aws-waf-token", domain=".deepseek.com") == "w"


def test_proxy_is_applied_to_the_session():
    c = DeepSeekWeb(proxy="http://u:p@127.0.0.1:9999")
    assert c.s.proxies["https"] == "http://u:p@127.0.0.1:9999"


def test_waf_token_lookup_reads_the_jar():
    c = DeepSeekWeb()
    assert c._aws_waf_token() is None
    c.s.cookies.set("aws-waf-token", "v", domain=".deepseek.com")
    assert c._aws_waf_token() == "v"


def test_state_file_holds_no_unexpected_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("DSW_STATE_DIR", str(tmp_path))
    c = DeepSeekWeb(token="t")
    c.save_state()
    assert set(json.loads(config.session_file().read_text())) == {"token", "device_id", "cookies"}
