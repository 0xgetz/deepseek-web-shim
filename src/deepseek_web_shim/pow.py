"""DeepSeek web PoW — solver for the `sha3` challenge.

Reverse-engineered, then verified against DeepSeek's own wasm module as an
oracle (see research/confirm_algo.py for the decisive test).

Contract:

    prefix = f"{salt}_{expire_at}_"                 # NOTE the trailing underscore
    find w in [0, difficulty] such that
        H(prefix + str(w)) == challenge             # challenge = 64 hex chars

    H = Keccak-f[1600] with 23 rounds (round constant 0 skipped),
        rate 136, pad 0x06, 32-byte output.

Stock Keccak-256 (24 rounds) does NOT verify. It is a *preimage match*, not a
leading-zeros target: the challenge is the digest of the answer, so the search
space is the difficulty bound.

The digest is sent back base64'd in a header:

    x-ds-pow-response: base64(json({algorithm, challenge, salt, answer,
                                    signature, target_path}))

Two backends implement H and MUST agree byte for byte:

  * ``pure`` — the Python implementation in this module, no dependencies.
  * ``wasm`` — DeepSeek's own module, when you supply it (``DSW_WASM``).
    Verified: planted ``w=7`` solved exactly, random target rejected, and the
    two backends produce identical digests.

Backend choice is never a correctness question, only a speed one.
"""
from __future__ import annotations

import base64
import json
import os
import struct
from pathlib import Path

__all__ = [
    "deepseek_sha3",
    "pow_prefix",
    "solve_pure",
    "WasmPow",
    "PowSolver",
]

# --- the hash ---------------------------------------------------------------

_RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]
_ROUNDS = _RC[1:24]  # 23 rounds: RC[0] is skipped in this variant
_ROT = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61],
        [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]
_M = (1 << 64) - 1
_RATE = 136
_OUT = 32


def _rol(x: int, n: int) -> int:
    n %= 64
    return ((x << n) | (x >> (64 - n))) & _M


def deepseek_sha3(data: bytes) -> bytes:
    """32-byte Keccak variant used by DeepSeek's PoW (23 rounds, RC[0] skipped)."""
    st = [0] * 25
    buf = bytearray(data) + b"\x06"
    while len(buf) % _RATE != 0:
        buf += b"\x00"
    buf[-1] ^= 0x80

    for off in range(0, len(buf), _RATE):
        blk = buf[off:off + _RATE]
        for i in range(_RATE // 8):
            st[i] ^= int.from_bytes(blk[i * 8:(i + 1) * 8], "little")
        for rc in _ROUNDS:
            c = [st[x] ^ st[x + 5] ^ st[x + 10] ^ st[x + 15] ^ st[x + 20] for x in range(5)]
            d = [c[(x - 1) % 5] ^ _rol(c[(x + 1) % 5], 1) for x in range(5)]
            for x in range(5):
                for y in range(5):
                    st[x + 5 * y] ^= d[x]
            b = [0] * 25
            for x in range(5):
                for y in range(5):
                    b[y + 5 * ((2 * x + 3 * y) % 5)] = _rol(st[x + 5 * y], _ROT[x][y])
            for x in range(5):
                for y in range(5):
                    st[x + 5 * y] = b[x + 5 * y] ^ (
                        (~b[(x + 1) % 5 + 5 * y]) & b[(x + 2) % 5 + 5 * y] & _M
                    )
            st[0] ^= rc
    return b"".join(st[i].to_bytes(8, "little") for i in range(_OUT // 8))


# --- the search -------------------------------------------------------------


def pow_prefix(salt: str, expire_at: int) -> str:
    """The exact string the answer is appended to. One definition, three callers.

    (An earlier revision built this inline in two places and the fallback path
    silently dropped the trailing underscore, which made the pure backend fail
    on every challenge. Keep this as the single source of truth.)
    """
    return f"{salt}_{expire_at}_"


def solve_pure(prefix: str, target: bytes, difficulty: int) -> int | None:
    """Brute force ``w`` in ``[0, difficulty]`` and return the preimage.

    ``prefix`` must already be the full :func:`pow_prefix` value.
    """
    pb = prefix.encode()
    for w in range(difficulty + 1):
        if deepseek_sha3(pb + str(w).encode()) == target:
            return w
    return None


class WasmPow:
    """Drive DeepSeek's own wasm module — the same code the browser runs.

    Passing an oracle that is not ours is the point: it is what makes the
    Python implementation in this file a *verified* reimplementation rather
    than a guess.
    """

    def __init__(self, wasm_path: str | Path) -> None:
        import wasmtime

        self._wasmtime = wasmtime
        engine = wasmtime.Engine()
        module = wasmtime.Module(engine, Path(wasm_path).read_bytes())
        self._store = wasmtime.Store(engine)
        linker = wasmtime.Linker(engine)
        linker.define_wasi()  # module imports nothing, but mirrors the proven driver
        self._ex = linker.instantiate(self._store, module).exports(self._store)
        self._mem = self._ex["memory"]

    def _write(self, text: str) -> tuple[int, int]:
        b = text.encode()
        ptr = self._ex["__wbindgen_export_0"](self._store, len(b), 1)
        self._mem.write(self._store, b, ptr)
        return ptr, len(b)

    def solve(self, challenge: str, salt: str, difficulty: float, expire_at: int) -> int | None:
        prefix = pow_prefix(salt, expire_at)
        retptr = self._ex["__wbindgen_add_to_stack_pointer"](self._store, -16)
        try:
            cptr, clen = self._write(challenge)
            pptr, plen = self._write(prefix)
            self._ex["wasm_solve"](
                self._store, retptr, cptr, clen, pptr, plen, float(difficulty)
            )
            raw = bytes(self._mem.read(self._store, retptr, retptr + 16))
            status = struct.unpack("<i", raw[0:4])[0]
            if status == 0:
                return None
            return int(struct.unpack("<d", raw[8:16])[0])
        finally:
            self._ex["__wbindgen_add_to_stack_pointer"](self._store, 16)


def _find_wasm() -> str | None:
    """DeepSeek's wasm module is NOT redistributed with this project.

    Point ``DSW_WASM`` at a copy you obtained yourself (see
    ``scripts/fetch_wasm.py``), or drop it at ``wasm/sha3_wasm_bg.wasm``.
    Without it the pure-Python backend runs — same digests, slower.
    """
    for cand in (
        os.environ.get("DSW_WASM"),
        str(Path.cwd() / "wasm" / "sha3_wasm_bg.wasm"),
        str(Path(__file__).resolve().parent.parent.parent / "wasm" / "sha3_wasm_bg.wasm"),
    ):
        if cand and Path(cand).exists():
            return cand
    return None


class PowSolver:
    """Facade: wasm when you supply it (exact, fast), pure Python otherwise.

    Both backends are verified to produce identical digests, so falling back
    changes latency only, never correctness.
    """

    def __init__(self, wasm_path: str | Path | None = None) -> None:
        self._wasm: WasmPow | None = None
        path = str(wasm_path) if wasm_path else _find_wasm()
        if path:
            try:
                self._wasm = WasmPow(path)
            except Exception:  # noqa: BLE001 — wasmtime missing or module rejected
                self._wasm = None

    @property
    def backend(self) -> str:
        return "wasm" if self._wasm else "pure"

    def answer(self, challenge: dict) -> int:
        alg = challenge.get("algorithm", "sha3")
        if alg != "sha3":
            raise ValueError(f"unsupported PoW algorithm: {alg!r}")
        ch = challenge["challenge"]
        salt = challenge["salt"]
        diff = int(challenge["difficulty"])
        expire = int(challenge["expire_at"])

        if self._wasm is not None:
            w = self._wasm.solve(ch, salt, diff, expire)
        else:
            w = solve_pure(pow_prefix(salt, expire), bytes.fromhex(ch), diff)
        if w is None:
            raise RuntimeError(
                f"PoW not solved within difficulty bound ({diff}) — "
                "challenge and salt may be stale"
            )
        return w

    def header(self, challenge: dict) -> str:
        """Build the ``x-ds-pow-response`` header value."""
        for key in ("algorithm", "challenge", "salt", "signature", "target_path"):
            if key not in challenge:
                raise ValueError(f"challenge is missing {key!r}")
        payload = {
            "algorithm": challenge["algorithm"],
            "challenge": challenge["challenge"],
            "salt": challenge["salt"],
            "answer": self.answer(challenge),
            "signature": challenge["signature"],
            "target_path": challenge["target_path"],
        }
        return base64.b64encode(json.dumps(payload).encode()).decode()


def _selftest() -> dict:
    """Plant a solution and confirm every available backend finds it."""
    salt, expire, planted, diff = "check-salt", 1_800_000_000, 11, 300
    prefix = pow_prefix(salt, expire)
    target = deepseek_sha3((prefix + str(planted)).encode())
    s = PowSolver()
    out = {
        "backend": s.backend,
        "planted": planted,
        "pure_answer": solve_pure(prefix, target, diff),
    }
    if s._wasm is not None:
        out["wasm_answer"] = s._wasm.solve(target.hex(), salt, diff, expire)
    out["match"] = all(
        out[k] == planted for k in ("pure_answer", "wasm_answer") if k in out
    )
    return out


if __name__ == "__main__":
    print(json.dumps(_selftest(), indent=2))
