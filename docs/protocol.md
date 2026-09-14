# Protocol notes

Everything here was derived from observed network traffic and from DeepSeek's own
client artifacts, and every claim was checked against a live response or against
their wasm module. Where something is a guess it says so.

Last verified: 2026-09-14 against `chat.deepseek.com` as served to a Chrome
client. Upstream may change any of this at any time; the shim fails loudly when
it does.

## Endpoints used

| Step | Endpoint | Purpose |
| --- | --- | --- |
| bootstrap | `GET /` | collects the `aws-waf-token` cookie |
| device | `POST /api/v0/users/create_session` | registers a `device_id` |
| session | `POST /api/v0/chat_session/create` | returns a chat session id |
| challenge | `POST /api/v0/chat/create_pow_challenge` | returns the proof-of-work challenge |
| completion | `POST /api/v0/chat/completion` | SSE stream, requires the PoW header |

All requests carry the browser-ish header set in `client.py` (`x-client-platform:
web`, `x-client-version`, `x-app-version`, `origin`, `referer`) and ride a
`curl_cffi` session impersonating a recent Chrome build, because the site also
fingerprints the TLS handshake.

## The proof of work

`create_pow_challenge` returns:

```json
{
  "algorithm": "sha3",
  "challenge": "<64 hex chars>",
  "salt": "<string>",
  "difficulty": 100000,
  "expire_at": 1800000000,
  "signature": "<string>",
  "target_path": "/api/v0/chat/completion"
}
```

The task is a **preimage match**, not a leading-zeros target:

```
prefix = f"{salt}_{expire_at}_"          # note the trailing underscore
find w in [0, difficulty] such that
    H(prefix + str(w)) == bytes.fromhex(challenge)
```

So `challenge` is the digest of the answer, and `difficulty` is the size of the
search space. A server picks the answer first and publishes its digest.

## The hash

`H` is not stock SHA3-256 and not stock Keccak-256. It is a Keccak-f[1600]
variant with **23 rounds**: the round constants are the standard 24, with
`RC[0]` skipped, so the permutation runs over `RC[1..23]`. Rate 136, padding
`0x06`, 32-byte output.

Stock Keccak-256 with 24 rounds does not verify against their challenges. The
23-round variant does, and it reproduces DeepSeek's wasm output byte for byte.

`research/confirm_algo.py` is the decisive test: it plants a solution into a
synthetic challenge and checks that both the wasm oracle and the Python
implementation find it, while a random target is rejected on both.

## The answer header

The answer travels base64-encoded in `x-ds-pow-response`:

```json
{
  "algorithm": "sha3",
  "challenge": "<same hex as the challenge>",
  "salt": "<same salt>",
  "answer": 12345,
  "signature": "<same signature>",
  "target_path": "/api/v0/chat/completion"
}
```

Nothing in the payload is signed by the client; it is a transport encoding. The
`signature` field is echoed from the challenge.

## The completion request

```json
{
  "chat_session_id": "<session id>",
  "parent_message_id": null,
  "model_type": "default",
  "prompt": "<the whole conversation folded into one string>",
  "ref_file_ids": [],
  "thinking_enabled": false,
  "search_enabled": false,
  "preempt": false
}
```

Notes:

- The web API takes a single prompt string, so the shim folds `messages[]` into
  one text block with `[system]`, `[assistant]` and `[tool result]` markers.
- `thinking_enabled` selects the reasoning variant, `search_enabled` the web
  search variant; they are the only model knob the web endpoint exposes, which
  is why `/v1/models` maps three names onto two booleans.
- The response is `text/event-stream`. Fragments with `type: "THINKING"` carry
  reasoning text and are surfaced the same way as content.

## Anti-bot layers observed

1. **AWS WAF**, via an `aws-waf-token` cookie obtained from the site itself.
   Requests without a plausible token are refused.
2. **TLS / HTTP fingerprinting**, which is why the client uses `curl_cffi` with
   Chrome impersonation instead of a plain HTTP library.
3. **The proof of work** above, which exists to make automated request volume
   expensive.

None of these is a vulnerability. They are controls working as intended, and
this project treats them that way: it solves the PoW because a browser does
the same work, and it never attempts to defeat the CAPTCHA on the signup and
login flows (`turnstile_token`, `device_id` and `scenario` are required, and the
token is issued to a real browser session).

## Rate and account limits still apply

Solving the PoW does not grant anything: the shim runs on **your** session, so
your account's limits, and your account's exposure to enforcement, are the ones
in play. See `intended-use.md`.
