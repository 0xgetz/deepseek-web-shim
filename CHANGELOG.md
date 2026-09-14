# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-09-14

### Added
- Pure-Python implementation of DeepSeek's `sha3` proof-of-work (23-round
  Keccak variant, rate 136, pad 0x06), verified byte for byte against DeepSeek's
  own wasm module as an oracle.
- Optional wasm backend via `wasmtime` (`DSW_WASM`, fetched with
  `scripts/fetch_wasm.py`; the module is not redistributed here).
- OpenAI-compatible server: `GET /healthz`, `GET /v1/models`,
  `POST /v1/chat/completions` with `stream=true|false`.
- Client for the web flow: `chat_session/create`, `create_pow_challenge`,
  local PoW, `chat/completion` SSE, cookie and proxy support.
- CLI: `--selftest`, `--serve`, `--session FILE`.
- `x-ds-pow-response` header encoding (base64 JSON of the challenge contract).
- Offline test suite: 51 tests, no network, wasm optional.
- Documentation: protocol notes and an intended-use / ethics note.

### Notes
- This is research tooling. It carries no credentials, creates no accounts and
  does not solve CAPTCHAs. Read `docs/intended-use.md` first.
