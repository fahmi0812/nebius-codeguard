"""CodeGuard agent loop: write -> preflight -> sandbox test -> gates -> judge.

The loop is written against small injectable callables (``llm`` and
``sandbox``) so it can be unit-tested without any network access.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .config import Settings, get_settings
from .gates import GateReport, TestSummary, decide, parse_test_summary, preflight
from .sandbox import RunResult

STRATEGY_SYSTEM = """You are CodeGuard strategy, a careful Python engineer.
Write ONE self-contained Python module for the user's task.
Rules:
- Standard library only. No file, network, subprocess or OS access. No eval/exec.
- Include at least three test functions named test_* that use plain assert
  statements (do NOT import pytest). Tests must be deterministic.
- Return ONLY the full module inside a single ```python code fence.
Do not claim tests passed — execution happens later in an isolated sandbox.
"""

REPAIR_TEMPLATE = """Your previous module was REJECTED by CodeGuard gates.

Task:
{task}

Rejection reasons:
{reasons}

Sandbox evidence (truncated):
exit_code={exit_code}
stdout:
{stdout}
stderr:
{stderr}

Previous module:
```python
{source}
```

Fix the module so every gate passes. Follow the same rules. Return ONLY the full
module in a single ```python code fence."""

JUDGE_SYSTEM = """You are CodeGuard judge. You only see observed sandbox evidence
(exit code, stdout, stderr) and the static gate results. Reply with ONLY a JSON object:
{"recommend_accept": bool, "risks": [str], "summary": str}
Do not invent evidence that was not provided. If the evidence does not show
passing tests, recommend_accept must be false.
"""

FENCE_RE = re.compile(r"```[ \t]*([A-Za-z0-9_+-]*)[ \t]*\n(.*?)```", re.DOTALL)
THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


# ---------------------------------------------------------------- pure helpers


def extract_code(raw: str) -> str:
    """Return the first fenced code block (preferring python), else the raw text."""
    text = THINK_RE.sub("", raw or "")
    blocks = FENCE_RE.findall(text)
    if blocks:
        for lang, body in blocks:
            if lang.lower() in ("python", "py", "python3"):
                return body.strip("\n").rstrip() + "\n"
        return blocks[0][1].strip("\n").rstrip() + "\n"
    return text.strip() + "\n" if text.strip() else ""


@dataclass
class JudgeVerdict:
    recommend_accept: bool | None
    risks: list[str] = field(default_factory=list)
    summary: str = ""
    raw: str = ""

    @property
    def parsed(self) -> bool:
        return self.recommend_accept is not None


def parse_judge(raw: str) -> JudgeVerdict:
    """Parse the judge's JSON (tolerates code fences / surrounding prose)."""
    text = THINK_RE.sub("", raw or "").strip()
    candidates = [text]
    for _, body in FENCE_RE.findall(text):
        candidates.append(body)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for cand in candidates:
        try:
            data = json.loads(cand)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and "recommend_accept" in data:
            rec = data.get("recommend_accept")
            if isinstance(rec, str):
                rec = rec.strip().lower() in ("true", "yes", "1")
            risks = data.get("risks") or []
            if not isinstance(risks, list):
                risks = [str(risks)]
            return JudgeVerdict(
                recommend_accept=bool(rec),
                risks=[str(r) for r in risks],
                summary=str(data.get("summary", "")),
                raw=raw,
            )
    return JudgeVerdict(recommend_accept=None, raw=raw, summary="judge reply was not valid JSON")


def build_evidence(run: RunResult, report: GateReport, limit: int = 2000) -> str:
    gates = "\n".join(f"- {name}: {'PASS' if ok else 'FAIL'} ({detail})" for name, ok, detail in report.checks)
    return (
        f"exit_code={run.exit_code}\n"
        f"stdout:\n{run.stdout[:limit]}\n"
        f"stderr:\n{run.stderr[:limit]}\n"
        f"static gates:\n{gates}\n"
    )


def final_decision(report: GateReport, judge: JudgeVerdict | None) -> tuple[bool, list[str]]:
    """Gates are mandatory; the judge can only veto (never upgrade a REJECT)."""
    reasons = list(report.reasons)
    if not report.accepted:
        return False, reasons
    if judge is not None and judge.recommend_accept is False:
        reasons.append("judge vetoed: " + (judge.summary or "recommend_accept=false"))
        return False, reasons
    return True, reasons


def repair_prompt(task: str, source: str, run: RunResult | None, reasons: list[str]) -> str:
    return REPAIR_TEMPLATE.format(
        task=task,
        reasons="\n".join(f"- {r}" for r in reasons) or "- (none)",
        exit_code=run.exit_code if run else None,
        stdout=(run.stdout if run else "")[-1500:],
        stderr=(run.stderr if run else "")[-1500:],
        source=source,
    )


# ---------------------------------------------------------------- pipeline


class SandboxLike(Protocol):
    def run_write_test(self, *, source: str) -> RunResult: ...


LLMFn = Callable[[str, str, bool], str]
"""llm(system, user, is_judge) -> text"""

EventFn = Callable[[str, dict], None]


@dataclass
class Attempt:
    number: int
    source: str
    preflight: list[str]
    run: RunResult | None
    tests: TestSummary | None
    report: GateReport
    judge: JudgeVerdict | None
    accepted: bool
    reasons: list[str]


@dataclass
class PipelineResult:
    task: str
    attempts: list[Attempt]

    @property
    def accepted(self) -> bool:
        return bool(self.attempts) and self.attempts[-1].accepted

    @property
    def final(self) -> Attempt | None:
        return self.attempts[-1] if self.attempts else None

    @property
    def sandbox_runs(self) -> int:
        return sum(1 for a in self.attempts if a.run is not None)


def _noop(_event: str, _data: dict) -> None:
    return None


def evaluate_source(
    source: str,
    *,
    sandbox: SandboxLike,
    llm: LLMFn | None = None,
    use_judge: bool = True,
    number: int = 1,
    on_event: EventFn = _noop,
    min_tests: int = 1,
) -> Attempt:
    """Preflight -> sandbox -> gates -> (judge) for one candidate module."""
    pre = preflight(source, min_tests=min_tests)
    on_event("preflight", {"findings": pre})
    run: RunResult | None = None
    tests: TestSummary | None = None
    if pre:
        # Never ship statically-rejected code to execution.
        report = decide(exit_code=None, source=source, test_ok=False, min_tests=min_tests)
        report.reasons = [
            r for r in report.reasons if r not in ("no exit code (sandbox did not run)", "tests failed")
        ]
        report.reasons.append("sandbox skipped: preflight failed")
        report.checks = [
            (name, ok, "skipped (preflight failed)") if name in ("sandbox exit code", "tests passed") else (name, ok, d)
            for name, ok, d in report.checks
        ]
        on_event("gates", {"report": report})
        return Attempt(number, source, pre, None, None, report, None, False, report.reasons)

    on_event("sandbox_start", {})
    run = sandbox.run_write_test(source=source)
    tests = parse_test_summary(run.exit_code, run.stdout)
    on_event("sandbox_done", {"run": run, "tests": tests})

    report = decide(exit_code=run.exit_code, source=source, test_ok=tests.ok, min_tests=min_tests)
    on_event("gates", {"report": report})

    judge: JudgeVerdict | None = None
    if report.accepted and use_judge and llm is not None:
        on_event("judge_start", {})
        judge = parse_judge(llm(JUDGE_SYSTEM, build_evidence(run, report), True))
        on_event("judge_done", {"judge": judge})

    accepted, reasons = final_decision(report, judge)
    return Attempt(number, source, pre, run, tests, report, judge, accepted, reasons)


def run_pipeline(
    task: str,
    *,
    llm: LLMFn,
    sandbox: SandboxLike,
    attempts: int = 2,
    use_judge: bool = True,
    on_event: EventFn = _noop,
    min_tests: int = 1,
) -> PipelineResult:
    """Nemotron writes code+tests; retry with evidence if the gates reject it."""
    result = PipelineResult(task=task, attempts=[])
    prompt = task
    for n in range(1, max(1, attempts) + 1):
        on_event("write_start", {"attempt": n, "repair": n > 1})
        source = extract_code(llm(STRATEGY_SYSTEM, prompt, False))
        on_event("write_done", {"attempt": n, "source": source})
        att = evaluate_source(
            source,
            sandbox=sandbox,
            llm=llm,
            use_judge=use_judge,
            number=n,
            on_event=on_event,
            min_tests=min_tests,
        )
        result.attempts.append(att)
        on_event("attempt_done", {"attempt": att})
        if att.accepted:
            break
        prompt = repair_prompt(task, source, att.run, att.reasons)
    return result


# ---------------------------------------------------------------- live wiring


def make_llm(settings: Settings) -> LLMFn:
    from .llm import chat

    def _llm(system: str, user: str, is_judge: bool) -> str:
        if is_judge:
            return chat(settings, system=system, user=user, model=settings.nemotron_judge_model, temperature=0.1)
        return chat(settings, system=system, user=user, temperature=0.3)

    return _llm


def propose_patch(task: str, settings: Settings | None = None) -> str:
    """Single Nemotron call returning the extracted module (used by smoke test)."""
    settings = settings or get_settings()
    return extract_code(make_llm(settings)(STRATEGY_SYSTEM, task, False))


def judge_evidence(evidence: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return make_llm(settings)(JUDGE_SYSTEM, evidence, True)


def local_gate_demo(source: str, exit_code: int = 0, test_ok: bool = True) -> dict:
    report = decide(exit_code=exit_code, source=source, test_ok=test_ok)
    return {"accepted": report.accepted, "reasons": report.reasons}
