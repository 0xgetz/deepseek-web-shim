#!/usr/bin/env python3
"""Fetch DeepSeek's sha3 wasm module into ./wasm/sha3_wasm_bg.wasm (optional).

The module is DeepSeek's own artifact, so this project does not redistribute it.
It is only useful as a *speed* backend and as an oracle: the pure-Python
implementation in ``deepseek_web_shim.pow`` is verified to produce identical
digests. Fetch it yourself if you want the wasm path:

    python scripts/fetch_wasm.py
    python scripts/fetch_wasm.py --file ~/Downloads/sha3_wasm_bg.7b9ca65ddd.wasm
    DSW_WASM=wasm/sha3_wasm_bg.wasm deepseek-web-shim --selftest

The first source is the site itself and is usually WAF-gated; the mirrors after
it ship the same build. A mirror that stores the file through Git LFS hands back
a 130-byte text pointer over the raw URL, so the pointer is detected and the
real bytes are pulled from the LFS media endpoint instead.

Every candidate is checked against a recorded sha256, so you can tell whether a
mirror served the build this project was verified against or something else.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

# Same build this project's digests were pinned against, so a mirror that serves
# something else is reported rather than silently trusted.
KNOWN_SHA256 = "b3fca8cc072c1defbd60c02266a8e48bd307a1804aaff4314900aea720e72f7d"

# Git LFS v1 pointer, handed back instead of the artifact when a mirror tracks
# the file with LFS and the raw URL is used.
LFS_MAGIC = b"version https://git-lfs.github.com/spec/v1"

SOURCES = [
    "https://chat.deepseek.com/sha3_wasm_bg.7b9ca65ddd.wasm",
    "https://raw.githubusercontent.com/baixueaik/Deepseek2API/4940d46e224b169759bf4918800ad3c4e5faabc9/sha3_wasm_bg.7b9ca65ddd.wasm",
    "https://raw.githubusercontent.com/KTS-o7/freeseek-proxy/main/sha3_wasm_bg.7b9ca65ddd.wasm",
]

DEST = Path(__file__).resolve().parent.parent / "wasm" / "sha3_wasm_bg.wasm"
UA = {"User-Agent": "Mozilla/5.0"}


def _get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers=UA)  # noqa: S310
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return r.read()


def _lfs_media_url(raw_url: str) -> str | None:
    """raw.githubusercontent.com/x/y/z -> media.githubusercontent.com/media/x/y/z"""
    marker = "raw.githubusercontent.com/"
    if marker not in raw_url:
        return None
    return raw_url.replace(marker, "media.githubusercontent.com/media/", 1)


def _fetch(url: str) -> bytes | None:
    """Return the artifact bytes for one source, resolving an LFS pointer if needed."""
    try:
        data = _get(url)
    except Exception as exc:  # noqa: BLE001
        print(f"  miss {url}: {type(exc).__name__}", file=sys.stderr)
        return None

    if data.startswith(LFS_MAGIC):
        media = _lfs_media_url(url)
        if not media:
            print(f"  miss {url}: Git LFS pointer and no media URL derivable", file=sys.stderr)
            return None
        print(f"  note {url}: Git LFS pointer, following media endpoint", file=sys.stderr)
        try:
            data = _get(media, timeout=60)
        except Exception as exc:  # noqa: BLE001
            print(f"  miss {media}: {type(exc).__name__}", file=sys.stderr)
            return None

    # The site answers an interstitial (not the module) when the WAF is in the way.
    if len(data) < 1000:
        print(f"  miss {url}: {len(data)} bytes (WAF interstitial?)", file=sys.stderr)
        return None
    return data


def _report(data: bytes, origin: str) -> int:
    got = hashlib.sha256(data).hexdigest()
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_bytes(data)
    verdict = "MATCHES" if got == KNOWN_SHA256 else "DIFFERS from"
    print(f"saved {len(data)} bytes to {DEST}\nfrom  {origin}\nsha256 {got} ({verdict} known build)")
    return 0 if got == KNOWN_SHA256 else 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--file",
        type=Path,
        help="use a wasm file you already have (for example the one your browser downloaded)",
    )
    args = ap.parse_args(argv)

    if args.file:
        if not args.file.is_file():
            print(f"no such file: {args.file}", file=sys.stderr)
            return 1
        return _report(args.file.read_bytes(), str(args.file))

    for url in SOURCES:
        data = _fetch(url)
        if data is not None:
            return _report(data, url)

    print(
        "could not fetch the module from any source - the pure backend still works",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
