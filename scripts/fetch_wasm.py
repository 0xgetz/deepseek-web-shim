#!/usr/bin/env python3
"""Fetch DeepSeek's sha3 wasm module into ./wasm/sha3_wasm_bg.wasm (optional).

The module is DeepSeek's own artifact, so this project does not redistribute it.
It is only useful as a *speed* backend and as an oracle: the pure-Python
implementation in ``deepseek_web_shim.pow`` is verified to produce identical
digests. Fetch it yourself if you want the wasm path:

    python scripts/fetch_wasm.py
    DSW_WASM=wasm/sha3_wasm_bg.wasm deepseek-web-shim --selftest

Try, in order: the chat.deepseek.com asset (may be WAF-gated), then public
mirrors that ship the same build.
"""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

# same build, sha256 recorded here so you can tell if a mirror served something else
KNOWN_SHA256 = "b3fca8cc072c1defbd60c02266a8e48bd307a1804aaff4314900aea720e72f7d"

SOURCES = [
    "https://chat.deepseek.com/sha3_wasm_bg.7b9ca65ddd.wasm",
    "https://raw.githubusercontent.com/KTS-o7/freeseek-proxy/main/sha3_wasm_bg.7b9ca65ddd.wasm",
    "https://raw.githubusercontent.com/KTS-o7/freeseek-proxy/main/wasm/sha3_wasm_bg.7b9ca65ddd.wasm",
]

DEST = Path(__file__).resolve().parent.parent / "wasm" / "sha3_wasm_bg.wasm"


def main() -> int:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    for url in SOURCES:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
                data = r.read()
        except Exception as exc:  # noqa: BLE001
            print(f"  miss {url}: {type(exc).__name__}", file=sys.stderr)
            continue
        if len(data) < 1000:
            print(f"  miss {url}: {len(data)} bytes (WAF interstitial?)", file=sys.stderr)
            continue
        got = hashlib.sha256(data).hexdigest()
        DEST.write_bytes(data)
        ok = "MATCHES" if got == KNOWN_SHA256 else "DIFFERS from"
        print(f"saved {len(data)} bytes to {DEST}\nsha256 {got} ({ok} known build)")
        return 0
    print("could not fetch the module from any source — the pure backend still works", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
