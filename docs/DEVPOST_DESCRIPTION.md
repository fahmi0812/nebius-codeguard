# Nebius CodeGuard — Devpost submission text

**Project name:** Nebius CodeGuard
**Tagline:** A coding agent that must prove its code in a Nebius sandbox before it ships.
**Track:** Coding and Agentic Engineering
**Hackathon:** Nebius × NVIDIA Global AI Hackathon
**Repository:** github.com/kuker24/nebius-codeguard *(placeholder — publish before submitting)*
**Demo video:** *(YouTube link — add after upload)*

---

## Inspiration

AI coding agents are fast and confident — and confidence is exactly the problem. We kept seeing agents announce
"all tests pass" for code that was never executed, or quietly reach for `eval` and shell calls to make something work.
Running that code on a developer laptop to find out is a security risk in itself. We wanted an agent whose default
answer is **"no"** until it can show real evidence, produced somewhere safe.

## What it does

Nebius CodeGuard takes a small coding task in plain English and:

1. **Writes** — NVIDIA Nemotron (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`), served by Nebius Token Factory, writes a
   self-contained Python module **and its own `test_*` functions**.
2. **Preflights** — an AST-based security and quality scan blocks `eval`/`exec`/`__import__`, `subprocess`, sockets,
   `pickle`, network libraries and destructive `os` calls, as well as syntax errors and missing tests.
   Blocked code is **never executed**.
3. **Executes** — clean code is uploaded to a **fresh Nebius Token Factory Sandbox** (Contree, `python:3.12-slim`)
   where a small harness runs every test and reports each result.
4. **Gates** — deterministic rules: the sandbox must have run, exit code must be `0`, every test must pass, scans must
   be clean.
5. **Judges** — a second Nemotron call sees **only the observed evidence** (exit code, stdout/stderr, gate results)
   and returns JSON. It can **veto** an accept but can **never override** a failed gate.
6. **Repairs** — if the gates reject, the rejection reasons and sandbox stderr go back to Nemotron for another attempt.

The result is a clear **ACCEPT** or **REJECT** with the reasons printed in the terminal (`codeguard run "<task>"`).
`codeguard check <file>` runs an existing module through the same preflight → sandbox → gates path.

In our live runs, Nemotron wrote a Roman-numeral converter that passed 3/3 tests in the sandbox and was accepted; a
`slugify` task failed one test in the sandbox on its first attempt (`"Café-au-lait!!!"`), and after receiving the
evidence Nemotron added Unicode normalisation and passed on attempt 2. A deliberately buggy `add` was rejected on
its failing test, and an `eval`-based calculator was rejected before it ever reached a sandbox.

## How we built it

- **Python 3.11+** CLI built with Typer and Rich.
- **Nebius Token Factory** OpenAI-compatible inference (`https://api.tokenfactory.nebius.com/v1`) through the
  official **OpenAI Python SDK**.
- **NVIDIA Nemotron** (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`) as both writer and evidence-only judge, with separate
  system prompts and temperatures.
- **Nebius Token Factory Sandboxes (Contree)** through **`contree-sdk` 0.3.6**:
  `ContreeSync()` → `images.use("python:3.12-slim")` → `run("python", ["run_tests.py"], files=..., cwd=...).wait()`,
  authenticated with the same Nebius API key and project ID.
- Gates are pure, deterministic Python (`ast` based) so they are easy to audit and unit-test; the agent loop takes
  injectable `llm` and `sandbox` callables, so the whole pipeline is covered by **62 offline pytest tests** using
  fakes, plus an optional `-m live` test that spawns a real sandbox.

## Challenges we ran into

- **Wiring the Sandboxes Beta.** Our first attempt used raw REST calls (image UUIDs and a heredoc shell hack to
  write files). Switching to the official `contree-sdk` pattern — images by tag and uploading files with
  `files=` — made execution reliable, but project-level Beta access came through only part-way into the hackathon.
- **Keeping the judge honest.** An LLM judge will happily "confirm" tests it never saw. We give it only observed
  evidence, ask for strict JSON, and make it veto-only: it can never turn a failed gate into an accept.
- **Strict but not silly security rules.** A substring check for `eval(` also flags `ast.literal_eval`. We moved to an
  AST-based policy that inspects actual calls and imports, with a substring fallback only for unparseable code.
- **Making evidence machine-readable.** A custom harness prints per-test `ok`/`FAIL` lines and a final
  `PASS n tests` / `FAILED f/t tests` summary with meaningful exit codes, so gates never have to guess.

## Accomplishments that we're proud of

- A working end-to-end loop on Nebius infrastructure: Nemotron writes → preflight → Token Factory Sandbox executes →
  gates → Nemotron judge, including an evidence-driven repair that fixed a real failing test.
- **No accept without evidence**, enforced in code rather than in a prompt.
- Unsafe code is rejected **before** execution; untrusted code runs only in a disposable sandbox, never locally.
- Clean, tested, MIT-licensed codebase with a readable CLI and secrets that are never printed.

## What we learned

- Separating the **generator** from an **evidence-only judge** — and giving the final word to deterministic gates —
  removes most "self-congratulating" false accepts.
- Sandboxes turn "should I run this?" into a non-question: every attempt gets a fresh environment in about 1–3
  seconds, which makes retry loops cheap.
- Small models like Nemotron 3 Nano are very capable at writing focused modules and tests when the contract is
  explicit (stdlib only, plain `assert`, single code fence).

## What's next for Nebius CodeGuard

- Parallel candidates using sandbox checkpoints/branches and picking the best-evidenced one.
- Coverage, property-based and mutation-testing gates so weak tests cannot pass.
- Multi-file repository patches (diffs applied to an existing project and its own test suite).
- A hosted CodeGuard API / CI integration.

## Built with

- Python
- Nebius Token Factory
- NVIDIA Nemotron (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`)
- Nebius Token Factory Sandboxes / Contree
- contree-sdk
- OpenAI Python SDK
- Typer, Rich, pytest *(supporting libraries)*

## Feedback on Nebius and NVIDIA tools (draft — edit before submitting)

- **Token Factory inference:** the OpenAI-compatible API meant zero custom client code; Nemotron 3 Nano responded
  quickly and followed the "single code fence" contract reliably.
- **Sandboxes (Beta):** the `contree-sdk` flow (`images.use(...).run(..., files=...)`) is simple and fast (~1–3 s per
  run). It would help to have the SDK path featured more prominently than raw REST in the docs, a self-serve way to
  see whether Beta access is enabled for a project (we hit `403 Insufficient permissions` until access was granted),
  and documented checkpoint/branch examples for agent loops.
- **Nemotron:** the model sometimes writes tests with subtle wrong expectations (e.g. Unicode edge cases); the sandbox
  evidence + repair loop handled this well.
