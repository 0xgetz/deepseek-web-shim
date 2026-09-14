"""Configuration, read from the environment only. No secrets live in the tree.

    DSW_API_KEY    key clients must present as ``Authorization: Bearer <key>``
                   to this shim (unset = no auth, localhost use only)
    DSW_HOST/PORT  bind address of the shim server
    DSW_STATE_DIR  where the captured session lives (default ~/.deepseek-web-shim)
    DSW_WASM       path to DeepSeek's sha3 wasm module (optional, faster PoW)
    DS_TOKEN       DeepSeek bearer token captured from your own logged-in browser
    DS_PROXY       residential proxy for the outbound leg, e.g. http://user:pass@host:port
"""
from __future__ import annotations

import os
from pathlib import Path


def state_dir() -> Path:
    return Path(os.environ.get("DSW_STATE_DIR") or (Path.home() / ".deepseek-web-shim"))


def session_file() -> Path:
    return state_dir() / "session.json"
