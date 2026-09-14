"""DeepSeek proof-of-work solver, pure-Python driver over DeepSeek's own sha3 wasm.

The web client ships `sha3_wasm_bg.<hash>.wasm` and calls its exported
`wasm_solve` to find `w` such that Keccak256(f"{salt}_{expire_at}_{w}") meets the
challenge target for the given difficulty. We load the same module with wasmtime
and reproduce that call, so the algorithm can never drift from the server's.

Usage:
    .venv/bin/python solver.py --selftest
"""
from __future__ import annotations

import argparse
import json
import random
import sys

import wasmtime

DEFAULT_WASM = "wasm/sha3_wasm_bg.7b9ca65ddd.wasm"


class DeepSeekHash:
    """Thin driver over the wasm PoW module (no WASI; the module imports nothing)."""

    def __init__(self, wasm_path: str = DEFAULT_WASM) -> None:
        self._engine = wasmtime.Engine()
        module = wasmtime.Module(self._engine, open(wasm_path, "rb").read())
        self._store = wasmtime.Store(self._engine)
        linker = wasmtime.Linker(self._engine)
        self._instance = linker.instantiate(self._store, module)
        self._exports = self._instance.exports(self._store)
        self._memory = self._exports["memory"]

    # -- memory plumbing ---------------------------------------------------
    def _write(self, data: bytes) -> tuple[int, int]:
        """Copy `data` into wasm memory via the wbindgen allocator."""
        alloc = self._exports["__wbindgen_export_0"]
        ptr = alloc(self._store, len(data), 1)
        buf = self._memory.read(self._store, ptr, ptr + len(data))
        self._memory.write(self._store, bytes(data), ptr)
        del buf
        return ptr, len(data)

    def _retptr(self) -> int:
        """8-byte return slot for the value the wasm solver hands back."""
        return self._exports["__wbindgen_add_to_stack_pointer"](self._store, -16)

    def _read_f64(self, retptr: int) -> float:
        raw = self._memory.read(self._store, retptr + 8, retptr + 16)
        return float(__import__("struct").unpack("<d", bytes(raw))[0])

    # -- public api --------------------------------------------------------
    def calculate_hash(
        self,
        algorithm: str,
        challenge: str,
        salt: str,
        difficulty: int,
        expire_at: int,
    ) -> int:
        prefix = f"{salt}_{expire_at}_".encode()
        challenge_b = challenge.encode()

        cptr, clen = self._write(challenge_b)
        pptr, plen = self._write(prefix)
        retptr = self._retptr()
        try:
            solve = self._exports["wasm_solve"]
            solve(
                self._store,
                retptr,
                cptr,
                clen,
                pptr,
                plen,
                float(difficulty),
            )
            return int(self._read_f64(retptr))
        finally:
            self._exports["__wbindgen_add_to_stack_pointer"](self._store, 16)

    def solve_pow(self, challenge: str, salt: str, difficulty: int, expire_at: int) -> int:
        return self.calculate_hash("sha3", challenge, salt, difficulty, expire_at)


# ---------------------------------------------------------------------------
def _keccak256_hex(msg: bytes) -> bytes:
    """Keccak-256 (pre-NIST padding), matching the browser's sha3 usage."""
    try:
        from Crypto.Hash import keccak  # pycryptodome
    except ImportError:  # pragma: no cover
        return _keccak256_hex_pure(msg)
    h = keccak.new(digest_bits=256)
    h.update(msg)
    return h.digest()


def _keccak256_hex_pure(msg: bytes) -> bytes:  # pragma: no cover
    """Fallback Keccak-256 (no dependencies). Slow but exact."""
    RC = [
        0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
        0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
        0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
        0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
        0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
        0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
    ]
    R = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61],
         [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]
    MASK = (1 << 64) - 1

    def rol(x, n):
        n %= 64
        return ((x << n) | (x >> (64 - n))) & MASK

    rate = 136
    st = [0] * 25
    pad = bytearray(msg) + b"\x01"
    while len(pad) % rate != 0:
        pad += b"\x00"
    pad[-1] ^= 0x80

    for off in range(0, len(pad), rate):
        blk = pad[off:off + rate]
        for i in range(rate // 8):
            st[i] ^= int.from_bytes(blk[i * 8:(i + 1) * 8], "little")
        for rnd in range(24):
            C = [st[x] ^ st[x + 5] ^ st[x + 10] ^ st[x + 15] ^ st[x + 20] for x in range(5)]
            D = [C[(x - 1) % 5] ^ rol(C[(x + 1) % 5], 1) for x in range(5)]
            for x in range(5):
                for y in range(5):
                    st[x + 5 * y] ^= D[x]
            B = [0] * 25
            for x in range(5):
                for y in range(5):
                    B[y + 5 * ((2 * x + 3 * y) % 5)] = rol(st[x + 5 * y], R[x][y])
            for x in range(5):
                for y in range(5):
                    st[x + 5 * y] = B[x + 5 * y] ^ ((~B[(x + 1) % 5 + 5 * y]) & B[(x + 2) % 5 + 5 * y] & MASK)
            st[0] ^= RC[rnd]
    return (st[0] | (st[1] << 64)).to_bytes(32, "little") if False else \
        b"".join(st[i].to_bytes(8, "little") for i in range(4))[:32]


def _leading_zero_bits(digest: bytes) -> int:
    bits = 0
    for b in digest:
        if b == 0:
            bits += 8
            continue
        bits += 8 - b.bit_length()
        break
    return bits


def selftest(wasm_path: str) -> int:
    """Solve a locally generated challenge and verify the hash ourselves."""
    h = DeepSeekHash(wasm_path)
    rng = random.Random(1337)
    challenge = "".join(rng.choice("0123456789abcdef") for _ in range(64))
    salt = "selftest-salt"
    expire_at = 1_800_000_000
    difficulty = 3
    w = h.solve_pow(challenge, salt, difficulty, expire_at)
    prefix = f"{salt}_{expire_at}_"
    digest = _keccak256_hex((prefix + str(w)).encode())
    bits = _leading_zero_bits(digest)
    ok = bits >= difficulty
    print(json.dumps({
        "challenge_prefix": challenge[:16],
        "difficulty": difficulty,
        "solution_w": w,
        "keccak256": digest.hex(),
        "leading_zero_bits": bits,
        "meets_target": ok,
    }, indent=2))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="DeepSeek web PoW solver")
    ap.add_argument("--wasm", default=DEFAULT_WASM)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--challenge")
    ap.add_argument("--salt")
    ap.add_argument("--difficulty", type=int)
    ap.add_argument("--expire-at", type=int)
    a = ap.parse_args()

    if a.selftest:
        return selftest(a.wasm)
    if not (a.challenge and a.salt and a.difficulty and a.expire_at):
        ap.error("need --challenge --salt --difficulty --expire-at (or --selftest)")
    h = DeepSeekHash(a.wasm)
    w = h.solve_pow(a.challenge, a.salt, a.difficulty, a.expire_at)
    print(json.dumps({"w": w, "prefix": f"{a.salt}_{a.expire_at}_"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
