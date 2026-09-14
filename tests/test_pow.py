"""PoW tests — offline. No network, no wasm required."""
from __future__ import annotations

import base64
import json

import pytest

from deepseek_web_shim.pow import (
    PowSolver,
    deepseek_sha3,
    pow_prefix,
    solve_pure,
)

# Frozen vectors. If these change, the hash changed — that is a breaking event,
# not a test to update casually. Cross-checked against DeepSeek's wasm oracle.
VECTORS = {
    b"": "e594808bc5b7151ac160c6d39a02e0a8e261ed588578403099e3561dc40c26b3",
    b"abc": "f841106c601ce9be9bc38525e90d4178d47f21dd8eb9f238fc55ffaa4ca94506",
    b"t_1800000000_11": "bed876e1c000efd69019eba5b4dd1ce74fb5b1013c9fa55556a7d5c4939d94df",
    b"x" * 136: "9c8a9eefd990d3073104fa5a3dd2d090681086778caccfa5b9af53b859752a99",
    b"y" * 137: "cfdc4d66c8c7d30780413becbc233ae30772278e6d2bcf85d661a2c433ad3ce9",
}


@pytest.mark.parametrize("data,expected", VECTORS.items(), ids=[repr(k[:12]) for k in VECTORS])
def test_known_answer_vectors(data, expected):
    assert deepseek_sha3(data).hex() == expected


def test_digest_is_32_bytes():
    assert len(deepseek_sha3(b"anything")) == 32


def test_hash_is_deterministic_and_collision_free_on_samples():
    seen = {deepseek_sha3(f"msg-{i}".encode()) for i in range(200)}
    assert len(seen) == 200


def test_pow_prefix_keeps_the_trailing_underscore():
    """Regression: the pure backend once dropped this and failed every challenge."""
    assert pow_prefix("AbC-123", 1_800_000_000) == "AbC-123_1800000000_"
    assert pow_prefix("s", 1).endswith("_")


def test_solve_pure_finds_the_planted_preimage():
    salt, expire, planted, diff = "s", 1_800_000_000, 11, 300
    prefix = pow_prefix(salt, expire)
    target = deepseek_sha3((prefix + str(planted)).encode())
    assert solve_pure(prefix, target, diff) == planted


def test_solve_pure_returns_none_when_out_of_range():
    salt, expire, planted = "s", 1_800_000_000, 500
    prefix = pow_prefix(salt, expire)
    target = deepseek_sha3((prefix + str(planted)).encode())
    assert solve_pure(prefix, target, 100) is None


def test_solve_pure_handles_zero_answer():
    prefix = pow_prefix("zero", 1)
    target = deepseek_sha3((prefix + "0").encode())
    assert solve_pure(prefix, target, 10) == 0


def _challenge(planted: int, diff: int = 500) -> dict:
    salt, expire = "challsalt", 1_800_000_000
    target = deepseek_sha3((pow_prefix(salt, expire) + str(planted)).encode())
    return {
        "algorithm": "sha3", "challenge": target.hex(), "salt": salt,
        "difficulty": diff, "expire_at": expire, "signature": "sig-abc",
        "target_path": "/api/v0/chat/completion",
    }


def test_answers_via_whichever_backend_is_available(monkeypatch, tmp_path):
    # force the pure path even if a fetched module sits in the working tree
    monkeypatch.setenv("DSW_POW_BACKEND", "pure")
    monkeypatch.chdir(tmp_path)
    s = PowSolver()
    assert s.backend == "pure"
    assert s.answer(_challenge(42)) == 42


def test_pow_backend_pure_overrides_a_present_wasm_module(monkeypatch, tmp_path):
    """A fetched module must not defeat the pin: --selftest has to stay reproducible."""
    fake = tmp_path / "wasm" / "sha3_wasm_bg.wasm"
    fake.parent.mkdir(parents=True)
    fake.write_bytes(b"not really wasm")
    monkeypatch.setenv("DSW_WASM", str(fake))
    monkeypatch.setenv("DSW_POW_BACKEND", "pure")
    assert PowSolver().backend == "pure"
    monkeypatch.delenv("DSW_POW_BACKEND")
    # without the pin the module is attempted (and rejected here, so it falls back)
    assert PowSolver().backend == "pure"


def test_both_backends_agree_when_wasm_is_available():
    """Opt-in: only runs when you have fetched the module (scripts/fetch_wasm.py)."""
    s = PowSolver()
    if s.backend != "wasm":
        pytest.skip("wasm module not present; pure backend covered above")
    ch = _challenge(11)
    assert s._wasm.solve(ch["challenge"], ch["salt"], 300, ch["expire_at"]) == 11
    assert s.answer(ch) == 11


def test_unsupported_algorithm_is_rejected():
    ch = _challenge(1)
    ch["algorithm"] = "md5"
    with pytest.raises(ValueError, match="unsupported PoW algorithm"):
        PowSolver().answer(ch)


def test_header_round_trips_all_contract_fields():
    ch = _challenge(7)
    h = PowSolver().header(ch)
    payload = json.loads(base64.b64decode(h))
    assert payload == {
        "algorithm": "sha3", "challenge": ch["challenge"], "salt": ch["salt"],
        "answer": 7, "signature": ch["signature"], "target_path": ch["target_path"],
    }


def test_header_rejects_incomplete_challenge():
    with pytest.raises(ValueError, match="target_path"):
        PowSolver().header({"algorithm": "sha3", "challenge": "ab", "salt": "s",
                            "difficulty": 5, "expire_at": 1, "signature": "x"})


def test_solver_fails_loudly_when_it_cannot_solve():
    ch = _challenge(1000, diff=1200)
    ch["difficulty"] = 5
    with pytest.raises(RuntimeError, match="not solved within difficulty bound"):
        PowSolver().answer(ch)
