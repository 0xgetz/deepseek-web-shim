"""Probe: WASI vs no-WASI, status field semantics, realistic difficulty values."""
from __future__ import annotations

import struct
import wasmtime

WASM = "wasm/sha3_wasm_bg.7b9ca65ddd.wasm"
CHALLENGE = "b5acb9c6b3dc2bcc9a1f0e2d3c4b5a69788796a5b4c3d2e1f00918273645546372"
SALT = "probe-salt"
EXPIRE = 1_800_000_000
PREFIX = f"{SALT}_{EXPIRE}_"


def run(use_wasi: bool, difficulty, challenge=CHALLENGE):
    engine = wasmtime.Engine()
    module = wasmtime.Module(engine, open(WASM, "rb").read())
    store = wasmtime.Store(engine)
    linker = wasmtime.Linker(engine)
    if use_wasi:
        try:
            linker.define_wasi()
        except Exception as exc:  # noqa: BLE001
            return f"define_wasi failed: {exc}"
    try:
        inst = linker.instantiate(store, module)
    except Exception as exc:  # noqa: BLE001
        return f"instantiate failed: {exc}"
    ex = inst.exports(store)
    mem = ex["memory"]

    def write(b: bytes):
        ptr = ex["__wbindgen_export_0"](store, len(b), 1)
        mem.write(store, b, ptr)
        return ptr, len(b)

    retptr = ex["__wbindgen_add_to_stack_pointer"](store, -16)
    try:
        cptr, clen = write(challenge.encode())
        pptr, plen = write(PREFIX.encode())
        try:
            ex["wasm_solve"](store, retptr, cptr, clen, pptr, plen, float(difficulty))
        except Exception as exc:  # noqa: BLE001
            return f"wasm_solve trap: {type(exc).__name__}: {str(exc)[:120]}"
        raw = bytes(mem.read(store, retptr, retptr + 24))
        status = struct.unpack("<i", raw[0:4])[0]
        val = struct.unpack("<d", raw[8:16])[0]
        return f"status={status} answer={int(val)} raw={raw.hex()}"
    finally:
        ex["__wbindgen_add_to_stack_pointer"](store, 16)


def main() -> None:
    for use_wasi in (False, True):
        print(f"\n########## use_wasi={use_wasi}")
        for diff in (1, 3, 144000, 144000.0, 8):
            r = run(use_wasi, diff)
            print(f"  difficulty={diff!r:>10} -> {r}")
        # short challenge (32 hex chars, like real server)
        r = run(use_wasi, 144000, challenge="a" * 32)
        print(f"  short-challenge 32 -> {r}")


if __name__ == "__main__":
    main()
