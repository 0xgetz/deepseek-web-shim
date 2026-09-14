# Contributing

Thanks for looking at this. It is research tooling, so the bar is "does it tell
the truth and does it stay honest about what it is".

## Ground rules

This project exists to document and study how a web chat client's
proof-of-work and session flow work. Contributions that turn it into something
else will be declined:

- No credential harvesting, no bundled tokens, no "free API" wrappers that
  hide whose account is being used.
- No account creation, no CAPTCHA solving, no anti-bot bypass helpers.
- No claims of vulnerability where the code is simply behaving as designed.

If you have a security concern about a third party, report it to that third
party, not here.

## Getting set up

```bash
git clone https://github.com/0xgetz/deepseek-web-shim
cd deepseek-web-shim
uv venv && uv pip install -e ".[dev]"
PYTHONPATH=src python -m pytest tests/ -q      # must be green
PYTHONPATH=src python -m deepseek_web_shim --selftest
```

## What a good change looks like

1. **Tests first.** Every behaviour change comes with a test that fails before
   it and passes after. Tests must run fully offline: inject clients, never hit
   a real endpoint.
2. **Verified against the oracle.** Anything touching the hash or the search
   must be checked against a known-answer vector, and against DeepSeek's wasm
   module when you have it (`scripts/fetch_wasm.py`, then
   `python -m pytest tests/test_pow.py`).
3. **Fail loud and clean.** API errors are JSON with a `type`, never a stack
   trace or an HTML page. Missing session, upstream refusal and bad input are
   distinct, named states.
4. **No secrets in the tree.** Run before committing:

   ```bash
   git grep --cached -nE "(sk-|ghp_|Bearer )[A-Za-z0-9._-]{16,}"
   ```

5. **Docs in the same PR.** If you change the protocol contract or an env var,
   update `docs/protocol.md` and the READMEs (EN, ID, 中文).

## Reporting a problem

Open an issue with: what you ran, what you expected, what happened, and the
exact output. If the answer is "upstream changed their protocol", that is a
useful issue on its own; include the response body so the contract can be
updated.
