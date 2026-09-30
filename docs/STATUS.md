# Engineering status — Nebius CodeGuard (30 Sep 2026, WIB)

## Verified live on 30 Sep 2026

| Check | Result |
|---|---|
| Nemotron chat via Token Factory (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`) | OK |
| Sandbox spawn via `contree-sdk` 0.3.6 (`python:3.12-slim`) | exit 0, ~1–3 s |
| `scripts/smoke_test.py` (write → sandbox → gates → judge) | `PASS 4 tests`, gates ACCEPT, judge `recommend_accept: true` |
| `codeguard run` — slugify | attempt 1 REJECT (1/3 tests failed in sandbox) → repair → attempt 2 ACCEPT (3/3) |
| `codeguard run` — roman_to_int | attempt 1 ACCEPT (3/3), judge ACCEPT |
| `codeguard check examples/broken_add.py` | REJECT (`non-zero exit: 1`, `tests failed`) |
| `codeguard check examples/insecure_eval.py` | REJECT in preflight (`blocked call: eval()`), sandbox not used |
| `pytest -q` | 62 passed, 1 deselected (live) |

## Components

- `sandbox.py` — official SDK pattern: `ContreeSync()` → `images.use(image)` → `run(cmd, args, files, cwd).wait()`.
- `gates.py` — AST security scan, quality scan, harness summary parsing, decision.
- `agent.py` — pipeline with injectable LLM/sandbox, repair loop, evidence-only judge (veto only).
- `cli.py` — `run`, `check`, `scan`, `doctor`, `version`.

## Known limitations

See README → Limitations.
