"""Talk to DeepSeek's web chat backend the way the browser does.

Reverse-engineered contract, each step verified live:

  POST /api/v0/users/login                     -> user.token   (email/password)
  POST /api/v0/chat_session/create             -> chat_session id
  POST /api/v0/chat/create_pow_challenge       -> salt/expire_at/challenge/difficulty/signature
  POST /api/v0/chat/completion  (+ PoW hdr)    -> SSE stream

Anti-bot layers observed: AWS WAF (`aws-waf-token` cookie, challenge.js) and a
TLS/HTTP fingerprint check, so every request goes through curl_cffi impersonating
a real Chrome build.

Session flow used by clients that work against this backend:
  1. get_session  -> fetch the login page, harvest aws-waf-token + device id
  2. login        -> identify/register the device, then authenticate
  3. create_session / create_pow_challenge / completion
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Iterator

from curl_cffi import requests as cffi_requests

from .config import session_file
from .pow import PowSolver

BASE = "https://chat.deepseek.com"
IMPERSONATE = "chrome131"  # any recent real Chrome build defeats the TLS check


def _json_or_die(r, what: str) -> dict[str, Any]:
    """Parse a JSON response, or report what upstream actually sent.

    A refused request can come back as an HTML WAF interstitial, an empty body,
    or a gateway error page. Those are ordinary states for this backend, and
    ``r.json()`` throwing a bare ValueError here would tell the caller nothing
    about which step failed or what came back.
    """
    try:
        return r.json()
    except Exception:  # noqa: BLE001 — any parse failure is reportable
        raise RuntimeError(f"{what} returned non-JSON ({r.status_code}): {r.text[:300]!r}")


class DeepSeekWeb:
    def __init__(self, token: str | None = None, cookies: dict[str, str] | None = None,
                 impersonate: str = IMPERSONATE, proxy: str | None = None) -> None:
        self.s = cffi_requests.Session(impersonate=impersonate)
        if proxy:
            self.s.proxies = {"http": proxy, "https": proxy}
        self.token: str | None = token
        self.device_id: str = str(uuid.uuid4())
        self.pow = PowSolver()
        if cookies:
            for k, v in cookies.items():
                self.s.cookies.set(k, v, domain=".deepseek.com")

    # -- headers -----------------------------------------------------------
    def _headers(self, path: str, extra: dict[str, str] | None = None) -> dict[str, str]:
        h = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "origin": BASE,
            "referer": f"{BASE}/",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "x-app-version": "20241129.1",
            "x-client-platform": "web",
            "x-client-version": "1.7.0",
            "x-client-locale": "en_US",
        }
        if self.token:
            h["authorization"] = f"Bearer {self.token}"
        if extra:
            h.update(extra)
        return h

    # -- step 1: harvest the WAF cookie ------------------------------------
    def warmup(self) -> int:
        r = self.s.get(f"{BASE}/", headers={"user-agent": self._headers("")["user-agent"]},
                       timeout=30)
        return r.status_code

    def _aws_waf_token(self) -> str | None:
        for c in self.s.cookies.jar:
            if "aws-waf-token" in c.name:
                return c.value
        return None

    def _refresh_waf(self) -> None:
        """AWS WAF challenge pages hand the token to the JS client; the same token
        rides the aws-waf-token cookie. Re-hit the challenge endpoint when stale."""
        try:
            self.s.get(f"{BASE}/api/v0/users/current", timeout=20)
        except Exception:  # noqa: BLE001
            pass

    # -- step 2: session bootstrap -----------------------------------------
    def create_session(self) -> str:
        r = self.s.post(
            f"{BASE}/api/v0/users/create_session",
            headers=self._headers("/api/v0/users/create_session"),
            json={"device_id": self.device_id},
            timeout=30,
        )
        return r.text

    def get_session_id(self) -> str:
        """A chat session id is what `completion` threads messages into."""
        r = self.s.post(
            f"{BASE}/api/v0/chat_session/create",
            headers=self._headers("/api/v0/chat_session/create"),
            json={"character_id": None},
            timeout=30,
        )
        data = _json_or_die(r, "chat_session/create")
        try:
            return data["data"]["biz_data"]["id"]
        except (KeyError, TypeError):
            raise RuntimeError(f"chat_session/create failed: {r.status_code} {r.text[:300]}")

    # -- step 3: PoW + completion ------------------------------------------
    def create_pow_challenge(self, target_path: str = "/api/v0/chat/completion") -> dict[str, Any]:
        r = self.s.post(
            f"{BASE}/api/v0/chat/create_pow_challenge",
            headers=self._headers("/api/v0/chat/create_pow_challenge"),
            json={"target_path": target_path},
            timeout=30,
        )
        try:
            return _json_or_die(r, "create_pow_challenge")["data"]["biz_data"]["challenge"]
        except (KeyError, TypeError):
            raise RuntimeError(f"create_pow_challenge failed: {r.status_code} {r.text[:300]}")

    def login(self, email: str, password: str) -> str:
        """Device registration first (some regions), then credential auth."""
        try:
            self.s.post(
                f"{BASE}/api/v0/users/create_session",
                headers=self._headers("/api/v0/users/create_session"),
                json={"device_id": self.device_id},
                timeout=30,
            )
        except Exception:  # noqa: BLE001
            pass
        r = self.s.post(
            f"{BASE}/api/v0/users/login",
            headers=self._headers("/api/v0/users/login"),
            json={
                "email": email,
                "password": password,
                "device_id": self.device_id,
                "os": "web",
                "screen_width": 1920,
                "screen_height": 1080,
                "locale": "en_US",
            },
            timeout=30,
        )
        if r.status_code != 200:
            raise RuntimeError(f"login http {r.status_code}: {r.text[:300]}")
        data = _json_or_die(r, "users/login")
        if data.get("code") not in (0, None):
            raise RuntimeError(f"login rejected: {json.dumps(data)[:300]}")
        token = (data.get("data") or {}).get("biz_data", {}).get("user", {}).get("token")
        if not token:
            raise RuntimeError(f"no token in login response: {json.dumps(data)[:300]}")
        self.token = token
        return token

    def completion(
        self,
        prompt: str,
        session_id: str,
        model_type: str = "default",
        thinking: bool = False,
        search: bool = False,
        parent_message_id: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """POST the completion and yield parsed SSE chunks."""
        ch = self.create_pow_challenge()
        pow_header = self.pow.header(ch)
        body = {
            "chat_session_id": session_id,
            "parent_message_id": parent_message_id,
            "model_type": model_type,
            "prompt": prompt,
            "ref_file_ids": [],
            "thinking_enabled": thinking,
            "search_enabled": search,
            "preempt": False,
        }
        headers = self._headers("/api/v0/chat/completion", {
            "x-ds-pow-response": pow_header,
            "accept": "text/event-stream",
        })
        r = self.s.post(f"{BASE}/api/v0/chat/completion", headers=headers, json=body,
                        stream=True, timeout=180)
        if r.status_code != 200:
            raise RuntimeError(f"completion http {r.status_code}: {r.text[:400]}")
        for line in r.iter_lines():
            if not line:
                continue
            text = line.decode() if isinstance(line, bytes) else line
            if text.startswith("data: "):
                payload = text[6:]
                if payload.strip() == "[DONE]":
                    break
                try:
                    yield json.loads(payload)
                except json.JSONDecodeError:
                    continue

    # -- convenience --------------------------------------------------------
    def load_state(self) -> bool:
        f = session_file()
        if not f.exists():
            return False
        d = json.loads(f.read_text())
        self.token = d.get("token")
        self.device_id = d.get("device_id", self.device_id)
        for k, v in (d.get("cookies") or {}).items():
            self.s.cookies.set(k, v, domain=".deepseek.com")
        return bool(self.token)

    def save_state(self) -> None:
        f = session_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        cookies = {c.name: c.value for c in self.s.cookies.jar}
        f.write_text(json.dumps({
            "token": self.token, "device_id": self.device_id, "cookies": cookies,
        }, indent=2))
        os.chmod(f, 0o600)


if __name__ == "__main__":
    c = DeepSeekWeb()
    print("warmup http:", c.warmup())
    print("aws-waf-token:", "present" if c._aws_waf_token() else "absent")
    print("pow backend:", c.pow.backend)
    print("pow challenge (unauth):", json.dumps(c.s.post(
        f"{BASE}/api/v0/chat/create_pow_challenge",
        headers=c._headers("/api/v0/chat/create_pow_challenge"),
        json={"target_path": "/api/v0/chat/completion"}, timeout=30).json())[:200])
