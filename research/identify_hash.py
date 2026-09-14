"""Identify the exact hash + selection rule the wasm PoW module enforces.

Ask the wasm for a solution at several difficulties, then check which hash
construction makes that exact `w` valid. No guessing: the wasm is the oracle.
"""
from __future__ import annotations

import hashlib
import struct
import wasmtime
from Crypto.Hash import keccak as _keccak

WASM = "wasm/sha3_wasm_bg.7b9ca65ddd.wasm"
CHALLENGE = "b5acb9c6b3dc2bcc9a1f0e2d3c4b5a69788796a5b4c3d2e1f00918273645546372"
SALT = "probe-salt"
EXPIRE = 1_800_000_000
PREFIX = f"{SALT}_{EXPIRE}_"


def lz(d: bytes) -> int:
    n = 0
    for b in d:
        if b == 0:
            n += 8
            continue
        n += 8 - b.bit_length()
        break
    return n


def keccak256(b: bytes) -> bytes:
    h = _keccak.new(digest_bits=256)
    h.update(b)
    return h.digest()


def sha3_256(b: bytes) -> bytes:
    return hashlib.sha3_256(b).digest()


CONSTRUCTIONS = {
    "keccak(prefix+w)": lambda w: keccak256((PREFIX + str(w)).encode()),
    "sha3(prefix+w)": lambda w: sha3_256((PREFIX + str(w)).encode()),
    "keccak(challenge+prefix+w)": lambda w: keccak256((CHALLENGE + PREFIX + str(w)).encode()),
    "sha3(challenge+prefix+w)": lambda w: sha3_256((CHALLENGE + PREFIX + str(w)).encode()),
    "keccak(challenge+w)": lambda w: keccak256((CHALLENGE + str(w)).encode()),
    "sha3(challenge+w)": lambda w: sha3_256((CHALLENGE + str(w)).encode()),
}


def main() -> None:
    engine = wasmtime.Engine()
    module = wasmtime.Module(engine, open(WASM, "rb").read())
    store = wasmtime.Store(engine)
    ex = wasmtime.Linker(engine).instantiate(store, module).exports(store)
    mem = ex["memory"]

    def write(b: bytes) -> tuple[int, int]:
        ptr = ex["__wbindgen_export_0"](store, len(b), 1)
        mem.write(store, b, ptr)
        return ptr, len(b)

    for difficulty in (1, 2, 4, 8, 12):
        cptr, clen = write(CHALLENGE.encode())
        pptr, plen = write(PREFIX.encode())
        retptr = ex["__wbindgen_add_to_stack_pointer"](store, -16)
        ex["wasm_solve"](store, retptr, cptr, clen, pptr, plen, float(difficulty))
        w = struct.unpack("<d", bytes(mem.read(store, retptr + 8, retptr + 16)))[0]
        w = int(w)
        print(f"\n== difficulty={difficulty} -> wasm w={w}")
        for name, fn in CONSTRUCTIONS.items():
            d = fn(w)
            print(f"   {name:30s} lz={lz(d):3d}  {d.hex()[:16]}")
        ex["__wbindgen_add_to_stack_pointer"](store, 16)


if __name__ == "__main__":
    main()
