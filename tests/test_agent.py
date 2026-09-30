import json

from codeguard.agent import (
    JUDGE_SYSTEM,
    STRATEGY_SYSTEM,
    build_evidence,
    evaluate_source,
    extract_code,
    final_decision,
    parse_judge,
    repair_prompt,
    run_pipeline,
)
from codeguard.gates import GateReport, decide
from codeguard.sandbox import RunResult

GOOD = "def add(a, b):\n    return a + b\n\ndef test_add():\n    assert add(1, 2) == 3\n"
BAD = "def add(a, b):\n    return a - b\n\ndef test_add():\n    assert add(1, 2) == 3\n"
EVIL = "def calc(s):\n    return eval(s)\n\ndef test_calc():\n    assert calc('1+1') == 2\n"


def fence(code, lang="python"):
    return f"Here you go:\n```{lang}\n{code}```\nDone."


# ------------------------------------------------------------------ extract_code


def test_extract_code_python_fence():
    assert extract_code(fence(GOOD)) == GOOD


def test_extract_code_prefers_python_block():
    raw = "```text\nnot code\n```\n```py\nx = 1\n```"
    assert extract_code(raw) == "x = 1\n"


def test_extract_code_unlabelled_fence_and_think_tags():
    raw = "<think>\n```python\nwrong = 1\n```\n</think>\n```\nright = 2\n```"
    assert extract_code(raw) == "right = 2\n"


def test_extract_code_without_fence_returns_text():
    assert extract_code("  x = 1  ") == "x = 1\n"
    assert extract_code("") == ""


# ------------------------------------------------------------------ judge parsing


def test_parse_judge_plain_json():
    j = parse_judge(json.dumps({"recommend_accept": True, "risks": [], "summary": "4 tests passed"}))
    assert j.parsed and j.recommend_accept is True and j.summary == "4 tests passed"


def test_parse_judge_fenced_and_prose():
    raw = 'Verdict below.\n```json\n{"recommend_accept": false, "risks": "flaky", "summary": "no"}\n```'
    j = parse_judge(raw)
    assert j.recommend_accept is False
    assert j.risks == ["flaky"]


def test_parse_judge_string_boolean():
    assert parse_judge('{"recommend_accept": "true"}').recommend_accept is True


def test_parse_judge_garbage():
    j = parse_judge("I think it is fine!")
    assert j.recommend_accept is None and not j.parsed


# ------------------------------------------------------------------ final decision


def test_final_decision_gate_reject_cannot_be_overridden_by_judge():
    report = GateReport(accepted=False, reasons=["tests failed"])
    ok, reasons = final_decision(report, parse_judge('{"recommend_accept": true}'))
    assert not ok and reasons == ["tests failed"]


def test_final_decision_judge_can_veto():
    report = GateReport(accepted=True, reasons=[])
    ok, reasons = final_decision(report, parse_judge('{"recommend_accept": false, "summary": "suspicious"}'))
    assert not ok and reasons == ["judge vetoed: suspicious"]


def test_final_decision_unparseable_judge_is_advisory():
    report = GateReport(accepted=True, reasons=[])
    assert final_decision(report, parse_judge("???")) == (True, [])
    assert final_decision(report, None) == (True, [])


def test_build_evidence_contains_observed_data_only():
    run = RunResult(exit_code=0, stdout="PASS 1 tests\n", stderr="")
    ev = build_evidence(run, decide(exit_code=0, source=GOOD, test_ok=True))
    assert "exit_code=0" in ev and "PASS 1 tests" in ev and "security scan: PASS" in ev


def test_repair_prompt_includes_reasons_and_source():
    run = RunResult(exit_code=1, stdout="FAILED 1/1 tests", stderr="AssertionError")
    p = repair_prompt("write add", BAD, run, ["tests failed"])
    assert "write add" in p and "- tests failed" in p and "AssertionError" in p and "a - b" in p


def test_prompts_forbid_claiming_success():
    assert "sandbox" in STRATEGY_SYSTEM.lower()
    assert "do not invent evidence" in JUDGE_SYSTEM.lower()


# ------------------------------------------------------------------ pipeline with fakes


class FakeSandbox:
    """Executes nothing; decides pass/fail from the source text."""

    def __init__(self):
        self.calls = []

    def run_write_test(self, *, source):
        self.calls.append(source)
        if "a - b" in source:
            return RunResult(exit_code=1, stdout="FAIL  test_add\nFAILED 1/1 tests\n", stderr="AssertionError")
        return RunResult(exit_code=0, stdout="ok    test_add\nPASS 1 tests\n", stderr="")


class FakeLLM:
    def __init__(self, sources, judge='{"recommend_accept": true, "risks": [], "summary": "ok"}'):
        self.sources = list(sources)
        self.judge = judge
        self.prompts = []

    def __call__(self, system, user, is_judge):
        self.prompts.append((system, user, is_judge))
        if is_judge:
            return self.judge
        return fence(self.sources.pop(0))


def test_pipeline_accepts_good_code_first_try():
    llm, sb = FakeLLM([GOOD]), FakeSandbox()
    events = []
    res = run_pipeline("write add", llm=llm, sandbox=sb, on_event=lambda e, d: events.append(e))
    assert res.accepted and len(res.attempts) == 1 and res.sandbox_runs == 1
    assert res.final.judge.recommend_accept is True
    assert events[:3] == ["write_start", "write_done", "preflight"]
    assert "judge_done" in events


def test_pipeline_repairs_after_failing_tests():
    llm, sb = FakeLLM([BAD, GOOD]), FakeSandbox()
    res = run_pipeline("write add", llm=llm, sandbox=sb, attempts=2)
    assert res.accepted
    assert [a.accepted for a in res.attempts] == [False, True]
    repair_user_msg = llm.prompts[1][1]
    assert "REJECTED" in repair_user_msg and "AssertionError" in repair_user_msg


def test_pipeline_rejects_after_exhausting_attempts():
    res = run_pipeline("write add", llm=FakeLLM([BAD, BAD]), sandbox=FakeSandbox(), attempts=2)
    assert not res.accepted
    assert res.final.reasons == ["non-zero exit: 1", "tests failed"]


def test_insecure_code_never_reaches_sandbox():
    sb = FakeSandbox()
    res = run_pipeline("calc", llm=FakeLLM([EVIL]), sandbox=sb, attempts=1)
    assert not res.accepted
    assert sb.calls == []
    assert res.final.run is None
    assert any("eval" in r for r in res.final.reasons)
    assert "sandbox skipped: preflight failed" in res.final.reasons


def test_judge_veto_rejects_even_when_gates_pass():
    llm = FakeLLM([GOOD], judge='{"recommend_accept": false, "summary": "tests are trivial"}')
    res = run_pipeline("write add", llm=llm, sandbox=FakeSandbox(), attempts=1)
    assert not res.accepted
    assert res.final.reasons == ["judge vetoed: tests are trivial"]


def test_no_judge_mode_skips_judge_call():
    llm = FakeLLM([GOOD])
    res = run_pipeline("write add", llm=llm, sandbox=FakeSandbox(), use_judge=False)
    assert res.accepted and res.final.judge is None
    assert all(not is_judge for _, _, is_judge in llm.prompts)


def test_judge_not_called_when_gates_reject():
    llm = FakeLLM([BAD])
    run_pipeline("write add", llm=llm, sandbox=FakeSandbox(), attempts=1)
    assert all(not is_judge for _, _, is_judge in llm.prompts)


def test_evaluate_source_without_llm():
    att = evaluate_source(GOOD, sandbox=FakeSandbox(), llm=None)
    assert att.accepted and att.judge is None
