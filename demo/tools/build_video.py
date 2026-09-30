#!/usr/bin/env python3
"""Assemble demo/codeguard_demo.mp4 from slides, terminal recordings and a TTS voiceover.

Inputs : demo/raw/0*.cast (recorded with demo/tools/record.sh)
Tools  : ffmpeg, Pillow, pyte, piper-tts (+ voice model path in $PIPER_VOICE)
Outputs: demo/codeguard_demo.mp4, demo/screenshots/*.png, demo/raw/* (intermediates)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
import slides  # noqa: E402

RAW = ROOT / "demo/raw"
SHOTS = ROOT / "demo/screenshots"
OUT = ROOT / "demo/codeguard_demo.mp4"
FPS = 20
PY = sys.executable
PIPER = os.environ.get("PIPER_BIN", str(Path(sys.executable).parent / "piper"))
VOICE = os.environ.get("PIPER_VOICE", "")

REPAIR_LOG = [
    ('$ codeguard run "Write slugify(text: str) -> str that lowercases, replaces runs of ..."', "white"),
    ("───────────────────────────── attempt 1 ─────────────────────────────", "grey"),
    ("[3/4] Sandbox  Nebius Token Factory Sandbox (Contree) · image python:3.12-slim", "cyan"),
    ("      exit code: 1 · 2.6s · tests 2/3 passed", "red"),
    ("      FAIL  test_slugify_extra_hyphens", "red"),
    ('        assert slugify("Café-au-lait!!!") == "cafe-au-lait"   ->  AssertionError', "white"),
    ("      attempt 1: REJECT", "red"),
    ("# CodeGuard sends the rejection reasons + sandbox stderr back to Nemotron", "yellow"),
    ("────────────────────────── repair attempt 2 ──────────────────────────", "grey"),
    ("  13     normalized = unicodedata.normalize('NFKD', text)", "white"),
    ("  14     ascii_text = normalized.encode('ASCII', 'ignore').decode('ASCII')", "white"),
    ("      exit code: 0 · 2.6s · tests 3/3 passed", "green"),
    ("nemotron judge     ACCEPT  All static checks passed and the test suite executed successfully", "green"),
    ("ACCEPT  evidence-backed: tests passed in a Nebius sandbox (attempt 2, 2 sandbox runs)", "green"),
    ("(condensed excerpt of the terminal log; box borders, code listing and some lines omitted)", "grey"),
]

RUN_CAPS = [
    [None, "Live run: a plain-English coding task goes in."],
    [r"1/4\] Write", "Step 1 — NVIDIA Nemotron on Nebius Token Factory writes the function AND its own tests."],
    [r"2/4\] Preflight", "Step 2 — Static preflight: no eval/exec, subprocess, sockets or destructive os calls."],
    [r"3/4\] Sandbox", "Step 3 — The tests execute in a fresh Nebius Token Factory Sandbox (Contree SDK)."],
    [r"exit code:", "Observed evidence from the sandbox: exit code + per-test results."],
    [r"judge reviewing", "Step 4 — Deterministic gates, then a Nemotron judge that sees only the evidence (veto only)."],
    [r"ACCEPT  evidence", "ACCEPT — tests passed inside the sandbox. No accept without evidence."],
]

# (name, kind, source, narration, extra)
SEGMENTS = [
    ("01_title", "slide", slides.title_slide, None,
     "Nebius CodeGuard: a coding agent that has to prove its code before it ships. "
     "Built for the Nebius and NVIDIA Global AI Hackathon."),
    ("02_problem", "slide", slides.problem_slide, None,
     "AI coding agents write code confidently, but confidence is not evidence. "
     "Without isolated execution and hard gates, broken or unsafe patches slip through. "
     "CodeGuard makes the model prove every patch."),
    ("03_arch", "slide", slides.architecture_slide, None,
     "Here is how it works. NVIDIA Nemotron, served by Nebius Token Factory, writes a Python module with its own "
     "tests. A static preflight blocks dangerous code, like eval, subprocess, or network access, before anything "
     "runs. Clean code executes in a fresh Nebius Token Factory Sandbox, through the Contree SDK. Deterministic "
     "gates check the exit code and the test results, and a second Nemotron pass acts as an evidence only judge. "
     "It can veto, but never override the gates."),
    ("04_setup", "cast", "01_setup.cast",
     {"title": "Setup & offline tests",
      "captions": [[None, "Setup: pip install -r requirements.txt, copy .env.example to .env."],
                   [r"NEBIUS_PROJECT_ID", "codeguard doctor shows the config — secrets are never printed, only 'set'."],
                   [r"passed", "62 offline unit tests (gates, agent loop, harness, config) pass with pytest."]],
      "holds": [], "tail": 2.5,
      "snapshots": [["end", 0, "05_tests_and_doctor.png"]]},
     {0: "Setup is simple: install the requirements and copy the example env file.",
      1: "codeguard doctor confirms the configuration without ever printing secrets.",
      2: "And sixty two offline unit tests pass."}),
    ("05_run", "cast", "02_run.cast",
     {"title": "Live run: write → sandbox → gates → judge",
      "captions": RUN_CAPS,
      "holds": [[r"2/4\] Preflight", 1.0], [r"4/4\] Gates", 1.0]],
      "max_spinner": 2.5, "tail": 3,
      "snapshots": [["end", 0, "02_live_run_accept.png"]]},
     {0: "Now, a live run. We ask for a Roman numeral converter.",
      1: "Nemotron, on Token Factory, writes the function and three tests.",
      2: "The preflight scan is clean, so the code is allowed to run.",
      3: "It executes in a fresh Nebius sandbox.",
      4: "Exit code zero, and all three tests pass.",
      5: "The gates are green, and the judge reviews only the observed evidence.",
      6: "CodeGuard accepts."}),
    ("06_repair", "slide", lambda caption=None: slides.repair_slide(REPAIR_LOG, caption), None,
     "When tests fail, CodeGuard feeds the sandbox evidence back to Nemotron. In this earlier live run, "
     "the first draft mishandled an accented character. The repair attempt normalized the Unicode, "
     "and passed on the second sandbox run."),
    ("07_broken", "cast", "03_broken.cast",
     {"title": "Gate: failing tests are rejected",
      "captions": [[None, "A deliberately buggy module: add() returns a - b."],
                   [r"3/4\] Sandbox", "It runs in a Nebius sandbox — one test fails with an AssertionError."],
                   [r"REJECT", "REJECT — non-zero exit and failing tests. Evidence decides, not the model."]],
      "holds": [[r"4/4\] Gates", 1.0]], "tail": 2.5,
      "snapshots": [["end", 0, "03_reject_failing_tests.png"]]},
     {0: "Here is a deliberately buggy add function.",
      1: "It runs in the sandbox, and one test fails with an assertion error.",
      2: "Exit code one, so the gates reject it."}),
    ("08_insecure", "cast", "04_insecure.cast",
     {"title": "Gate: insecure code is blocked before execution",
      "captions": [[None, "An insecure calculator that uses eval() — its test would pass."],
                   [r"2/4\] Preflight", "The security preflight blocks eval() — the code is never sent to the sandbox."],
                   [r"REJECT", "REJECT — unsafe code never runs at all."]],
      "holds": [], "tail": 2.5,
      "snapshots": [["end", 0, "04_reject_insecure.png"]]},
     {0: "And this calculator uses eval. Its test would pass,",
      1: "but the security preflight blocks it, and the code is never even sent to the sandbox."}),
    ("09_impact", "slide", slides.impact_slide, None,
     "No accept without evidence. Nebius Token Factory gives us Nemotron inference and sandboxed execution "
     "on one platform, so agent-written code never runs on the developer's machine."),
    ("10_closing", "slide", slides.closing_slide, None,
     "Nebius CodeGuard. Open source under the MIT license, built with Nebius Token Factory and NVIDIA Nemotron. "
     "Thanks for watching."),
]

SLIDE_CAPTIONS = {
    "01_title": None,
    "02_problem": None,
    "03_arch": None,
    "06_repair": "Failing tests trigger a repair attempt with the sandbox evidence (real log excerpt).",
    "09_impact": None,
    "10_closing": None,
}


def run(cmd, **kw):
    subprocess.run(cmd, check=True, **kw)


def duration(path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]
    )
    return float(out)


def tts(text: str, path: Path) -> float:
    if not VOICE:
        raise SystemExit("set PIPER_VOICE to a piper .onnx voice model")
    run([PIPER, "-m", VOICE, "-f", str(path), "--length-scale", "1.0", "--sentence-silence", "0.25"],
        input=text.encode(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return duration(path)


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    parts = []
    for name, kind, src, extra, narration in SEGMENTS:
        lead, trail = 0.5, 0.9
        if isinstance(narration, str):
            narration = {0: narration}
        chunks = []  # (index, wav, dur)
        for i, text in sorted(narration.items()):
            wav = RAW / f"{name}_{i}.wav"
            chunks.append((i, wav, tts(text, wav)))
        if kind == "slide":
            png = RAW / f"{name}.png"
            src(caption=SLIDE_CAPTIONS.get(name)).save(png)
            a_total = sum(d for _, _, d in chunks) + 0.3 * (len(chunks) - 1)
            v_dur = a_total + lead + trail
            clip = RAW / f"{name}_v.mp4"
            run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(png), "-t", f"{v_dur:.2f}",
                 "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                 str(clip)])
            marks = {"0": 0.0}
        else:
            cfg = dict(extra)
            cfg["cast"] = str(RAW / src)
            clip = RAW / f"{name}_v.mp4"
            cfg["out"] = str(clip)
            cfg["fps"] = FPS
            cfg["snapshots"] = [[r, a, str(SHOTS / p)] for r, a, p in cfg.get("snapshots", [])]
            cfg["narration_durs"] = {str(i): d for i, _, d in chunks}
            cfg_path = RAW / f"{name}.json"
            cfg_path.write_text(json.dumps(cfg, indent=1))
            run([PY, str(Path(__file__).parent / "render_cast.py"), str(cfg_path)])
            v_dur = duration(clip)
            marks = json.loads(Path(str(clip) + ".marks.json").read_text())
        # place each narration chunk at its caption mark (never overlapping the previous chunk)
        placed, cursor = [], 0.0
        for i, wav, d in chunks:
            start = max(marks.get(str(i), cursor) + (lead if i == 0 else 0.15), cursor)
            placed.append((wav, start))
            cursor = start + d + 0.25
        a_dur = cursor
        total = max(v_dur, cursor + trail)
        seg = RAW / f"{name}_seg.mp4"
        pad = max(0.0, total - v_dur) + 0.1
        inputs, filt, labels = [], [], []
        for k, (wav, start) in enumerate(placed, start=1):
            inputs += ["-i", str(wav)]
            ms = int(start * 1000)
            filt.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}:all=1[a{k}]")
            labels.append(f"[a{k}]")
        filt.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0,apad[a]")
        filt.append(f"[0:v]tpad=stop_mode=clone:stop_duration={pad:.2f},fps={FPS},format=yuv420p[v]")
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(clip), *inputs, "-filter_complex", ";".join(filt),
             "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "medium",
             "-crf", "18", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", str(seg)])
        print(f"{name}: video {v_dur:.1f}s, voice {a_dur:.1f}s -> {total:.1f}s")
        parts.append(seg)
    lst = RAW / "concat.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c:v", "libx264",
         "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
         "-movflags", "+faststart", str(OUT)])
    # gallery images
    slides.architecture_slide().save(SHOTS / "01_title_architecture.png")
    print(f"{OUT}: {duration(OUT):.1f}s")


if __name__ == "__main__":
    main()
