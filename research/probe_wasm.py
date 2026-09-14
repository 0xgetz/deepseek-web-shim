"""Probe the wasm PoW module empirically: find the real call contract.

Dumps the return region, tries candidate offsets, and verifies candidates in
pure Python so we learn the true semantics instead of guessing.
"""
from __future__ import annotations

import struct
import wasmtime

WASM = "wasm/sha3_wasm_bg.7b9ca65ddd.wasm"
CHALLENGE = "b5acb9c6b3dc2bcc9a1f0e2d3c4b5a69788796a5b4c3d2e1f00918273645546372"
SALT = "probe-salt"
EXPIRE = 1_800_000_000


def leading_zero_bits(d: bytes) -> int:
    n = 0
    for b in d:
        if b == 0:
            n += 8
            continue
        n += 8 - b.bit_length()
        break
    return n


def keccak(msg: bytes) -> bytes:
    from Crypto.Hash import keccak as k
    h = k.new(digest_bits=256)
    h.update(msg)
    return h.digest()


def main() -> None:
    engine = wasmtime.Engine()
    module = wasmtime.Module(engine, open(WASM, "rb").read())
    store = wasmtime.Store(engine)
    linker = wasmtime.Linker(engine)
    inst = linker.instantiate(store, module)
    ex = inst.exports(store)
    mem = ex["memory"]

    def write(b: bytes) -> tuple[int, int]:
        ptr = ex["__wbindgen_export_0"](store, len(b), 1)
        mem.write(store, b, ptr)
        return ptr, len(b)

    for difficulty in (1, 2, 3):
        print(f"\n===== difficulty={difficulty} =====")
        cptr, clen = write(CHALLENGE.encode())
        pptr, plen = write(f"{SALT}_{EXPIRE}_".encode())
        retptr = ex["__wbindgen_add_to_stack_pointer"](store, -16)
        try:
            retptr = ex["__wbindgen_add_to_stack_pointer"](store, 0)
        except Exception:
            pass
        raw = bytes(mem.read(store, retptr, retptr + 32))
        print("retptr:", hex(retptr), "pre-call:", raw.hex())
        dump = {}

        # Variant A: (retptr, cptr, clen, pptr, plen, difficulty)  [blog order]
        try:
            ex["wasm_solve"](store, retptr, cptr, clen, pptr, plen, float(difficulty))
            a = bytes(mem.read(store, retptr, retptr + 32))
            dump["A_retptr_c_p_diff"] = a.hex()
            print("A bytes:", a.hex())
            for off in (0, 8, 16):
                dump[f"A_i64@{off}"] = struct.unpack("<q", a[off:off + 8])[0]
                dump[f"A_f64@{off}"] = struct.unpack("<d", a[off:off + 8])[0]
        except Exception as exc:  # noqa: BLE001
            print("A failed:", exc)

        for k in sorted(dump):
            print(f"   {k} = {dump[k]}")

    # pure-python ground truth: what w satisfies a target, if policy is 'leading zeros'
    print("\n===== ground truth checks =====")
    prefix = f"{SALT}_{EXPIRE}_"
    for w in range(0, 5):
        h = keccak((prefix + str(w)).encode())
        print(f"w={w} keccak={h.hex()[:24]} lz_bits={leading_zero_bits(h)}")


if __name__ == "__main__":
    main()
