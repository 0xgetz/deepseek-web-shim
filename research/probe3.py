"""Match the proven call order exactly, and dump true wasm function signatures."""
from __future__ import annotations

import struct
import wasmtime

WASM = "wasm/sha3_wasm_bg.7b9ca65ddd.wasm"


def dump_signatures() -> None:
    engine = wasmtime.Engine()
    module = wasmtime.Module(engine, open(WASM, "rb").read())
    print("== export signatures ==")
    for e in module.exports:
        t = e.type
        try:
            print(f"  {e.name:30s} params={[str(p) for p in t.params]} results={[str(r) for r in t.results]}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {e.name:30s} <{exc}>")
    print("imports:", [f"{i.module}.{i.name}" for i in module.imports])
    print()


def solve_reference_order(challenge: str, salt: str, expire_at: int, difficulty: float,
                          retptr_first: bool = True, use_wasi: bool = True):
    """Mirror freeseek's driver: retptr first, then write strings, then wasm_solve."""
    engine = wasmtime.Engine()
    module = wasmtime.Module(engine, open(WASM, "rb").read())
    store = wasmtime.Store(engine)
    linker = wasmtime.Linker(engine)
    if use_wasi:
        linker.define_wasi()
    inst = linker.instantiate(store, module)
    ex = inst.exports(store)
    mem = ex["memory"]

    def write(s: str):
        b = s.encode("utf-8")
        ptr = ex["__wbindgen_export_0"](store, len(b), 1)
        mem.write(store, b, ptr)
        return ptr, len(b)

    prefix = f"{salt}_{expire_at}_"
    if retptr_first:
        retptr = ex["__wbindgen_add_to_stack_pointer"](store, -16)
    else:
        cptr, clen = write(challenge)
        pptr, plen = write(prefix)
        retptr = ex["__wbindgen_add_to_stack_pointer"](store, -16)

    try:
        if retptr_first:
            cptr, clen = write(challenge)
            pptr, plen = write(prefix)
        ex["wasm_solve"](store, retptr, cptr, clen, pptr, plen, float(difficulty))
        raw = bytes(mem.read(store, retptr, retptr + 16))
        status = struct.unpack("<i", raw[0:4])[0]
        answer = int(struct.unpack("<d", raw[8:16])[0])
        return status, answer, raw.hex()
    finally:
        ex["__wbindgen_add_to_stack_pointer"](store, 16)


def main() -> None:
    dump_signatures()

    ch64 = "b5acb9c6b3dc2bcc9a1f0e2d3c4b5a69788796a5b4c3d2e1f00918273645546372"
    for retptr_first in (False, True):
        for use_wasi in (False, True):
            print(f"\n#### retptr_first={retptr_first} use_wasi={use_wasi}")
            for diff in (1.0, 8.0, 144000.0):
                try:
                    s, a, raw = solve_reference_order(ch64, "probe-salt", 1_800_000_000, diff,
                                                      retptr_first, use_wasi)
                    print(f"   diff={diff:<10} status={s} answer={a} raw={raw}")
                except Exception as exc:  # noqa: BLE001
                    print(f"   diff={diff:<10} EXC {type(exc).__name__}: {str(exc)[:90]}")


if __name__ == "__main__":
    main()
