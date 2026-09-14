"""Inspect the DeepSeek sha3 wasm module: exports + import requirements.

Run:  .venv/bin/python inspect_wasm.py wasm/sha3_wasm_bg.7b9ca65ddd.wasm
"""
import sys
import wasmtime

path = sys.argv[1] if len(sys.argv) > 1 else "wasm/sha3_wasm_bg.7b9ca65ddd.wasm"
data = open(path, "rb").read()
print("module bytes:", len(data))

engine = wasmtime.Engine()
module = wasmtime.Module(engine, data)

print("\n-- exports --")
for e in module.exports:
    print(f"  {e.name:28s} {e.type}")

print("\n-- imports --")
try:
    for i in module.imports:
        print(f"  {i.module}.{i.name:28s} {i.type}")
except Exception as exc:  # noqa: BLE001
    print("  (imports unavailable:", exc, ")")
