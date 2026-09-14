<div align="center">
  <img src="assets/logo.png" alt="deepseek-web-shim logo" width="128" height="128">
  <h1>deepseek-web-shim</h1>
  <p>An OpenAI-compatible local server in front of DeepSeek's web chat.<br>
  The proof-of-work is reimplemented in Python and verified against the vendor's own wasm module.</p>
  <p>
    <a href="https://github.com/0xgetz/deepseek-web-shim/releases"><img src="https://img.shields.io/github/v/release/0xgetz/deepseek-web-shim?style=flat-square" alt="release"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-3fb950?style=flat-square" alt="MIT license"></a>
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.9%2B-blue?style=flat-square" alt="Python 3.9+"></a>
    <a href="tests"><img src="https://img.shields.io/badge/tests-74%20offline-2ea44f?style=flat-square" alt="74 offline tests"></a>
  </p>
  <p>
    <strong>English</strong> ·
    <a href="README.id.md">Bahasa Indonesia</a> ·
    <a href="README.zh-CN.md">简体中文</a> ·
    <a href="README.ja.md">日本語</a> ·
    <a href="README.ko.md">한국어</a>
  </p>
</div>

---

## What this is

A research tool that speaks the same protocol `chat.deepseek.com` speaks, from
Python, and exposes it as an OpenAI-compatible endpoint:

```bash
export DSW_API_KEY=local   # any value; it guards your own local port
curl http://127.0.0.1:8712/v1/chat/completions \
  -H "Authorization: Bearer local" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-web","messages":[{"role":"user","content":"hi"}]}'
```

Two parts are worth reading even if you never run the server:

1. **The proof-of-work, verified.** DeepSeek's challenge is not a leading-zeros
   puzzle and its hash is not stock SHA3 or stock Keccak. It is Keccak-f[1600]
   with **23 rounds** (round constant 0 skipped), rate 136, pad `0x06`, and the
   challenge is a **preimage target**: the server picks an answer, digests it,
   and asks you to find the preimage inside the difficulty bound. See
   [`docs/protocol.md`](docs/protocol.md).
2. **A testable client.** The Python hash reproduces the output of DeepSeek's
   own wasm module byte for byte, which is what lets the shim run without
   shipping their binary at all. The research scripts that pinned this down,
   including the two wrong hypotheses, are in [`research/`](research/README.md).

## Install

```bash
git clone https://github.com/0xgetz/deepseek-web-shim
cd deepseek-web-shim
uv venv && uv pip install -e ".[dev]"
```

## Capture a session

The shim runs on **your own** session. Open `chat.deepseek.com` in your browser,
log in, then in DevTools open Network, send any message, click the `completion`
request and copy the `authorization` header value.

```bash
echo 'Bearer <paste your token here>' > /tmp/tok.txt
PYTHONPATH=src python -m deepseek_web_shim --session /tmp/tok.txt
# {"saved": "...", "token_len": ..., "cookies": 0, ...}
rm /tmp/tok.txt        # the token now lives in ~/.deepseek-web-shim/session.json (mode 0600)
```

## Run

```bash
PYTHONPATH=src DSW_API_KEY=local python -m deepseek_web_shim --serve
# GET  /healthz              -> {"ok":true,"pow_backend":"pure","authenticated":true}
# GET  /v1/models            -> deepseek-web, deepseek-web-reasoner, deepseek-web-search
# POST /v1/chat/completions  -> OpenAI schema, stream=true|false
```

Point any OpenAI-compatible client at `http://127.0.0.1:8712/v1`.

| Model name | What it maps to |
| --- | --- |
| `deepseek-web` | the default web model |
| `deepseek-web-reasoner` | `thinking_enabled: true` |
| `deepseek-web-search` | `search_enabled: true` |

## Verify it yourself

```bash
PYTHONPATH=src python -m pytest tests/ -q          # 73 passed, 1 skipped, 0 failed
PYTHONPATH=src python -m deepseek_web_shim --selftest
# {"backend":"pure","planted":11,"pure_answer":11,"match":true}
```

The suite is fully offline: no test touches the network. `test_pow.py` pins the
hash to frozen known-answer vectors, and `test_server.py` drives the real ASGI
app against an injected fake upstream.

To cross-check the Python hash against DeepSeek's wasm oracle, fetch the module
yourself (it is **not** redistributed here) and rerun:

```bash
python scripts/fetch_wasm.py                       # records the sha256 it gets
python scripts/fetch_wasm.py --file ~/Downloads/sha3_wasm_bg.7b9ca65ddd.wasm   # or use a copy you already have
PYTHONPATH=src DSW_WASM=wasm/sha3_wasm_bg.wasm python -m pytest tests/test_pow.py
```

## Fast vs slow PoW

| Backend | Speed | Needs |
| --- | --- | --- |
| `wasm` | fast | DeepSeek's wasm module, fetched by you (`DSW_WASM=`) |
| `pure` | roughly 1.9k hashes/s | nothing, it is the code in this repo |

Both produce **identical digests**, so the choice is latency only. `--selftest`
prints which one is active.

## Configuration

All via environment, never committed. See [`.env.example`](.env.example).

| Variable | Meaning |
| --- | --- |
| `DSW_API_KEY` | key clients must present; required, because this port fronts your own session |
| `DSW_ALLOW_NO_AUTH` | set to `1` to run deliberately without a key, loopback only |
| `DSW_HOST` / `DSW_PORT` | bind address, default `127.0.0.1:8712` |
| `DS_TOKEN` | DeepSeek bearer token, alternative to `--session` |
| `DSW_STATE_DIR` | where the captured session is stored |
| `DSW_WASM` | path to the optional wasm module |
| `DSW_POW_BACKEND` | set to `pure` to force the pure-Python backend even when a module is present |
| `DS_PROXY` | residential proxy for the outbound leg, if your IP is refused |

## Read this before using it

This is research tooling, not an access trick. It ships **no credentials**, it
never creates accounts, and it does not solve CAPTCHAs. It runs on your session,
so your account's limits and your account's exposure apply. Automated access to
a web interface may violate that service's terms; that is your call and your
risk. Full text: [`docs/intended-use.md`](docs/intended-use.md).

It parses an undocumented protocol, so it will break when upstream changes. When
that happens it is designed to fail loudly with named JSON errors
(`not_authenticated`, `upstream_error`) rather than quietly returning the wrong
answer. A silent wrong answer would be a bug worth reporting.

If you want stable access, use the official API. It is documented, supported,
and removes every caveat on this page.

## Layout

```
src/deepseek_web_shim/   pow.py (verified hash + search), client.py (web flow),
                         server.py (OpenAI shim), config.py, __main__.py (CLI)
tests/                   74 offline tests
research/                the scripts behind the conclusions, wrong turns included
docs/                    protocol.md, intended-use.md
scripts/fetch_wasm.py    optional wasm fetcher, prints the sha256
```

## License

MIT. See [LICENSE](LICENSE).
