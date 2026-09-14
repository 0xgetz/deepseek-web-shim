"""CLI entry points.

    python -m deepseek_web_shim --selftest     # verify the PoW backends
    python -m deepseek_web_shim --serve        # run the OpenAI-compatible shim
    python -m deepseek_web_shim --session FILE # capture a session token from a file
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .config import session_file, state_dir


def _serve(host: str, port: int) -> int:
    import uvicorn

    from .server import app

    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


def _session(path: str) -> int:
    """Persist a captured session token (JSON, or a raw ``Bearer ...`` string)."""
    from .client import DeepSeekWeb

    raw = open(path).read().strip()
    token = raw
    cookies: dict[str, str] = {}
    if raw.startswith("{"):
        data = json.loads(raw)
        token = (data.get("token") or "").removeprefix("Bearer ").strip()
        cookies = data.get("cookies") or {}
    else:
        token = raw.removeprefix("Bearer ").strip()
    if not token:
        print("no token found in that file", file=sys.stderr)
        return 1

    c = DeepSeekWeb(token=token, cookies=cookies)
    c.save_state()
    f = session_file()
    print(json.dumps({"saved": str(f), "token_len": len(token),
                      "cookies": len(cookies), "state_dir": str(state_dir())}))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="deepseek-web-shim", description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--selftest", action="store_true", help="verify the PoW backends")
    g.add_argument("--serve", action="store_true", help="run the shim server")
    g.add_argument("--session", metavar="FILE", help="store a captured session token")
    p.add_argument("--host", default=os.environ.get("DSW_HOST", "127.0.0.1"))
    p.add_argument("--port", type=int, default=int(os.environ.get("DSW_PORT", "8712")))
    args = p.parse_args(argv)

    if args.session:
        return _session(args.session)
    if args.serve:
        return _serve(args.host, args.port)

    from .pow import _selftest

    print(json.dumps(_selftest(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
