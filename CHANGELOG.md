# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] - 2026-09-14

### Fixed
- `scripts/fetch_wasm.py` pointed at mirrors that had gone away, so the optional
  wasm path could not be fetched at all. It now follows a Git LFS pointer when a
  mirror stores the module through LFS (a raw URL returns a 130-byte text
  pointer, not the artifact), and it gained `--file` so an existing copy works
  with no network.
- The documented way to pin the backend, `DSW_WASM=<a path that does not exist>`,
  stopped working once a fetched module sat in `wasm/`: auto-discovery found it
  and the "pure backend" command silently ran wasm instead. Added
  `DSW_POW_BACKEND=pure` and switched the suite to it.

### Changed
- Running without `DSW_API_KEY` now refuses with `503 not_configured` instead of
  serving unauthenticated. A local port that proxies your own DeepSeek session
  should not be open because a comment said "localhost only". Set
  `DSW_ALLOW_NO_AUTH=1` to opt out deliberately. `/healthz` stays open so you can
  still see what is wrong.
- Fetched module now reports whether it MATCHES or DIFFERS from the build this
  project's digests were pinned against, and exits non-zero when it differs.
- Test suite: 54 tests. Both backends are covered whether or not the module is
  present.

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
- Offline test suite: 54 tests, no network, wasm optional.
- Documentation: protocol notes and an intended-use / ethics note.

### Notes
- This is research tooling. It carries no credentials, creates no accounts and
  does not solve CAPTCHAs. Read `docs/intended-use.md` first.
