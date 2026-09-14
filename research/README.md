# Research notes

These are the scripts that produced the conclusions the shipped code depends on.
They are kept because the reasoning is the point of the project, and because a
claim you cannot re-run is not a claim.

They are not part of the package and are not meant to be imported. Run them from
this directory with the project venv.

| Script | Question it answered |
| --- | --- |
| `inspect_wasm.py` | What does DeepSeek's wasm module export, and what does it import? |
| `probe_wasm.py` | What does `wasm_solve` actually take and return? (First two hypotheses were wrong.) |
| `identify_hash.py` | Is it SHA3-256 (NIST padding) or Keccak? (Neither, as it turned out.) |
| `probe2.py` | Does the module need a WASI host at instantiation? |
| `probe3.py` | What is the exact call order and the shape of the return struct? |
| `confirm_algo.py` | **The decisive test.** Plant a solution, ask both the wasm oracle and Python to find it, and check a random target is rejected. |
| `probe_account.py` | What does the signup endpoint require? (Answer: `turnstile_token`, `device_id`, `scenario`.) |
| `solver.py` | The first solver attempt, kept as the record of the wrong starting assumption. |

## What the sequence established

1. The module exports `wasm_solve`, an allocator and `memory`, and imports
   nothing, so no host shim is needed for this path.
2. The return value is a struct at a stack pointer: status `i32` at offset 0,
   answer `f64` at offset 8. Reading the wrong offset is why early attempts
   returned `0` for every challenge.
3. The hash is Keccak-f[1600], 23 rounds, `RC[0]` skipped, rate 136, pad `0x06`.
   Both SHA3-256 and stock Keccak-256 were ruled out by test, not by reading.
4. The challenge is a preimage target, not a leading-zeros target: the server
   digests a chosen answer and asks you to find it inside the difficulty bound.
5. The Python implementation and the wasm module agree byte for byte, which is
   what allows the shipped code to run without the module at all.

## On keeping the wrong turns

`solver.py` and the two failed hash hypotheses are here on purpose. A clean
write-up that presents the final answer as if it were the first guess is less
useful than the record of how the answer was pinned down, and it hides how
easily a plausible-looking wrong assumption survives until something tests it.
