"""Decisive test: what hash does DeepSeek's wasm PoW actually invert?

Hypothesis from the Go reverse-engineering: find w in [0, difficulty] such that
    H(prefix + str(w)) == target
where prefix = f"{salt}_{expire_at}_" and target is the 64-hex `challenge` field.

We compute targets with two candidate hash variants, then ask the wasm to invert
them. Whichever target the wasm can solve IS the real algorithm.
"""
from __future__ import annotations

import struct
import wasmtime

WASM = "wasm/sha3_wasm_bg.7b9ca65ddd.wasm"
SALT = "probe-salt"
EXPIRE = 1_800_000_000
PREFIX = f"{SALT}_{EXPIRE}_"

RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]
ROT = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61],
       [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]
M = (1 << 64) - 1


def rol(x, n):
    n %= 64
    return ((x << n) | (x >> (64 - n))) & M


def keccak(data: bytes, rounds, pad=0x06, rate=136) -> bytes:
    st = [0] * 25
    buf = bytearray(data) + bytes([pad])
    while len(buf) % rate != 0:
        buf += b"\x00"
    buf[-1] ^= 0x80
    for off in range(0, len(buf), rate):
        blk = buf[off:off + rate]
        for i in range(rate // 8):
            st[i] ^= int.from_bytes(blk[i * 8:(i + 1) * 8], "little")
        for rc in rounds:
            C = [st[x] ^ st[x + 5] ^ st[x + 10] ^ st[x + 15] ^ st[x + 20] for x in range(5)]
            D = [C[(x - 1) % 5] ^ rol(C[(x + 1) % 5], 1) for x in range(5)]
            for x in range(5):
                for y in range(5):
                    st[x + 5 * y] ^= D[x]
            B = [0] * 25
            for x in range(5):
                for y in range(5):
                    B[y + 5 * ((2 * x + 3 * y) % 5)] = rol(st[x + 5 * y], ROT[x][y])
            for x in range(5):
                for y in range(5):
                    st[x + 5 * y] = B[x + 5 * y] ^ ((~B[(x + 1) % 5 + 5 * y]) & B[(x + 2) % 5 + 5 * y] & M)
            st[0] ^= rc
    return b"".join(st[i].to_bytes(8, "little") for i in range(4))


VARIANTS = {
    "keccak24_std": lambda d: keccak(d, RC),
    "keccak23_skipRC0": lambda d: keccak(d, RC[1:24]),
}


def wasm_solve(target_hex: str, difficulty: float) -> tuple[int, int]:
    engine = wasmtime.Engine()
    module = wasmtime.Module(engine, open(WASM, "rb").read())
    store = wasmtime.Store(engine)
    linker = wasmtime.Linker(engine)
    linker.define_wasi()
    ex = linker.instantiate(store, module).exports(store)
    mem = ex["memory"]

    def write(s: str):
        b = s.encode()
        ptr = ex["__wbindgen_export_0"](store, len(b), 1)
        mem.write(store, b, ptr)
        return ptr, len(b)

    retptr = ex["__wbindgen_add_to_stack_pointer"](store, -16)
    try:
        cptr, clen = write(target_hex)
        pptr, plen = write(PREFIX)
        ex["wasm_solve"](store, retptr, cptr, clen, pptr, plen, float(difficulty))
        raw = bytes(mem.read(store, retptr, retptr + 16))
        status = struct.unpack("<i", raw[0:4])[0]
        ans = int(struct.unpack("<d", raw[8:16])[0])
        return status, ans
    finally:
        ex["__wbindgen_add_to_stack_pointer"](store, 16)


def main() -> None:
    truth_w = 7
    msg = (PREFIX + str(truth_w)).encode()
    print(f"prefix={PREFIX!r}  planted solution w={truth_w}\n")

    for name, fn in VARIANTS.items():
        target = fn(msg).hex()
        status, ans = wasm_solve(target, 200)
        verdict = "SOLVED -> algorithm CONFIRMED" if (status != 0 and ans == truth_w) else "no"
        print(f"{name:20s} target={target[:24]}...  wasm status={status} answer={ans}   {verdict}\n")

    # negative control: random target must NOT solve
    status, ans = wasm_solve("ab" * 32, 200)
    print(f"{'negative control':20s} random target            wasm status={status} answer={ans}")


if __name__ == "__main__":
    main()
