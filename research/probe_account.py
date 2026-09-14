"""Probe account/signup endpoints behind the WAF, and test whether a device
session can be established before login. Read-only recon: nothing is created.
"""
from __future__ import annotations

import json
import uuid

from curl_cffi import requests as r

BASE = "https://chat.deepseek.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def hdrs() -> dict:
    return {
        "accept": "*/*",
        "content-type": "application/json",
        "origin": BASE,
        "referer": f"{BASE}/",
        "user-agent": UA,
        "x-app-version": "20241129.1",
        "x-client-platform": "web",
        "x-client-version": "1.7.0",
        "x-client-locale": "en_US",
    }


def main() -> None:
    s = r.Session(impersonate="chrome131")
    print("warmup:", s.get(BASE, headers={"user-agent": UA}, timeout=30).status_code)
    print("cookies:", [c.name for c in s.cookies.jar])

    device = str(uuid.uuid4())
    probes = [
        ("POST", "/api/v0/users/create_session", {"device_id": device}),
        ("POST", "/api/v0/users/create_email_verification_code",
         {"email": "probe@example.com", "scene": "signup"}),
        ("POST", "/api/v0/users/login", {"email": "probe@example.com", "password": "x",
                                         "device_id": device}),
        ("GET", "/api/v0/users/current", None),
        ("GET", "/api/v0/chat_session/fetch_page", None),
    ]
    for method, path, body in probes:
        try:
            if method == "POST":
                resp = s.post(BASE + path, headers=hdrs(), json=body or {}, timeout=30)
            else:
                resp = s.get(BASE + path, headers=hdrs(), timeout=30)
            txt = resp.text[:260].replace("\n", " ")
            print(f"{method:4s} {path:48s} http={resp.status_code} {txt}")
        except Exception as exc:  # noqa: BLE001
            print(f"{method:4s} {path:48s} EXC {type(exc).__name__}: {str(exc)[:120]}")
    print("\nfinal cookies:", [c.name for c in s.cookies.jar])
    print(json.dumps({"waf_token_present": any("aws-waf" in c.name for c in s.cookies.jar)}))


if __name__ == "__main__":
    main()
