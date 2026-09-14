"""OpenAI-compatible shim in front of DeepSeek's web chat backend.

Drop-in for ``api.openai.com``:

    GET  /healthz
    GET  /v1/models
    POST /v1/chat/completions        (stream=true|false)

It holds **your own** DeepSeek web session — a bearer token you captured from
your own logged-in browser, in ``DS_TOKEN`` or ``~/.deepseek-web-shim/session.json``
— and translates OpenAI requests into the web flow:

    chat_session/create -> create_pow_challenge -> local PoW -> completion (SSE)

Run::

    DSW_API_KEY=local deepseek-web-shim --serve
    # then point a client at http://127.0.0.1:8712/v1

Boundary this project does not cross: it does not create accounts, does not
solve CAPTCHAs, and ships no credentials. See README "Intended use and caveats".
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from .client import DeepSeekWeb

MODELS = ["deepseek-web", "deepseek-web-reasoner", "deepseek-web-search"]
MODEL_MAP = {
    "deepseek-web": ("default", False, False),
    "deepseek-web-chat": ("default", False, False),
    "deepseek-web-reasoner": ("default", True, False),
    "deepseek-web-thinking": ("default", True, False),
    "deepseek-web-search": ("default", False, True),
}

# Thread one DeepSeek chat session per conversation key so multi-turn works.
_sessions: dict[str, str] = {}
_client: DeepSeekWeb | None = None

app = FastAPI(title="deepseek-web-shim", version="0.1.0")


def set_client(c: DeepSeekWeb | None) -> None:
    """Inject a client (tests use this to stay fully offline)."""
    global _client
    _client = c


def client() -> DeepSeekWeb:
    global _client
    if _client is not None:
        return _client
    token = os.environ.get("DS_TOKEN")
    proxy = os.environ.get("DS_PROXY")
    c = DeepSeekWeb(token=token or None, proxy=proxy)
    if not token:
        c.load_state()  # session captured earlier via `--session FILE`
    _client = c
    return c


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _auth(authorization: str | None) -> None:
    """Bearer guard.

    ``DSW_API_KEY`` is the key clients must present. Leaving it unset runs with
    no auth, which is only safe on loopback, so that combination requires an
    explicit ``DSW_ALLOW_NO_AUTH=1``: one environment variable is a thin thing
    to stand between a captured DeepSeek session and everyone who can reach the
    port, and this default should not depend on a human reading a comment.
    """
    want = os.environ.get("DSW_API_KEY")
    if not want:
        if not _truthy("DSW_ALLOW_NO_AUTH"):
            raise HTTPException(
                status_code=503,
                detail={
                    "error": {
                        "message": (
                            "no DSW_API_KEY set; this shim proxies your own DeepSeek session. "
                            "Set DSW_API_KEY=<any secret> and send it as "
                            "'Authorization: Bearer <secret>', or set DSW_ALLOW_NO_AUTH=1 if you "
                            "really want an unauthenticated port."
                        ),
                        "type": "not_configured",
                    }
                },
            )
        return
    if authorization != f"Bearer {want}":
        raise HTTPException(status_code=401, detail={"error": {"message": "invalid api key"}})


def _session_key(messages: list[dict[str, Any]]) -> str:
    """Stable per-conversation key: the system prompt plus the opening user turn."""
    parts = []
    for m in messages:
        if m.get("role") in ("system", "user"):
            content = m.get("content")
            if isinstance(content, list):  # OpenAI content-parts form
                content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
            parts.append(str(content))
            if m.get("role") == "user":
                break
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "\n".join(parts)[:2000]))


def _flatten(messages: list[dict[str, Any]]) -> str:
    """DeepSeek web takes a single prompt; fold the whole thread into it."""
    parts = []
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        if isinstance(content, list):  # OpenAI content-parts form
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        if role == "system":
            parts.append(f"[system]\n{content}")
        elif role == "user":
            parts.append(str(content))
        elif role == "assistant":
            parts.append(f"[assistant]\n{content}")
        elif role == "tool":
            parts.append(f"[tool result]\n{content}")
    return "\n\n".join(parts).strip()


def _collect(fragment: dict[str, Any]) -> str:
    """Pull text out of one DeepSeek SSE chunk."""
    if not isinstance(fragment, dict):
        return ""
    cur: Any = fragment
    for key in ("content",):
        cur = cur.get(key) if isinstance(cur, dict) else None
    if isinstance(cur, str):
        return cur
    # thinking fragments arrive with type=THINKING
    if fragment.get("type") == "THINKING" and isinstance(fragment.get("content"), str):
        return fragment["content"]
    return ""


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    c = client()
    return {"ok": True, "pow_backend": c.pow.backend, "authenticated": bool(c.token)}


@app.get("/v1/models")
def models(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    return {
        "object": "list",
        "data": [
            {"id": m, "object": "model", "created": int(time.time()), "owned_by": "deepseek-web"}
            for m in MODELS
        ],
    }


def _resolve(body: dict[str, Any], model: str) -> tuple[DeepSeekWeb, str]:
    """Map a request to (client, chat session id), creating the session on first use.

    Failures here are reported as clean JSON, never as an HTML 500: an
    unauthenticated shim and an upstream rejection are both ordinary states
    for this tool, and the client deserves to be told which one happened.
    """
    c = client()
    if not c.token:
        raise HTTPException(status_code=401, detail={"error": {
            "message": "no DeepSeek session captured — run `deepseek-web-shim "
                       "--session <file>` with a token from your own logged-in "
                       "browser, or set DS_TOKEN",
            "type": "not_authenticated",
        }})
    key = _session_key(body.get("messages") or [])
    sid = _sessions.get(key)
    if sid is None:
        try:
            sid = c.get_session_id()
        except Exception as exc:  # noqa: BLE001 — upstream refusal is a normal state here
            raise HTTPException(status_code=502, detail={"error": {
                "message": f"DeepSeek refused chat_session/create: {exc}",
                "type": "upstream_error",
            }})
        _sessions[key] = sid
    return c, sid


def _stream(body: dict[str, Any], model: str, created: int) -> StreamingResponse:
    c, sid = _resolve(body, model)
    model_type, thinking, search = MODEL_MAP.get(model, ("default", False, False))
    prompt = _flatten(body["messages"])
    rid = f"chatcmpl-{uuid.uuid4().hex[:24]}"

    def gen():
        try:
            for frag in c.completion(prompt, sid, model_type=model_type,
                                     thinking=thinking, search=search):
                text = _collect(frag)
                if not text:
                    continue
                yield "data: " + json.dumps({
                    "id": rid, "object": "chat.completion.chunk", "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
                }) + "\n\n"
            yield "data: " + json.dumps({
                "id": rid, "object": "chat.completion.chunk", "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }) + "\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:  # noqa: BLE001 — surface upstream errors as SSE, never crash the stream
            yield "data: " + json.dumps({"error": {"message": str(exc)[:500]}}) + "\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/v1/chat/completions")
async def chat(request: Request, authorization: str | None = Header(default=None)):
    _auth(authorization)
    body = await request.json()
    if not isinstance(body.get("messages"), list) or not body["messages"]:
        raise HTTPException(status_code=400, detail={"error": {"message": "messages[] is required"}})
    model = body.get("model", "deepseek-web")
    created = int(time.time())
    if body.get("stream"):
        return _stream(body, model, created)

    c, sid = _resolve(body, model)
    model_type, thinking, search = MODEL_MAP.get(model, ("default", False, False))
    try:
        parts = []
        for frag in c.completion(_flatten(body["messages"]), sid, model_type=model_type,
                                 thinking=thinking, search=search):
            parts.append(_collect(frag))
    except Exception as exc:  # noqa: BLE001 — report upstream failure as JSON, not a stack trace
        raise HTTPException(status_code=502, detail={"error": {
            "message": f"DeepSeek completion failed: {exc}", "type": "upstream_error",
        }})
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": "".join(parts)},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
