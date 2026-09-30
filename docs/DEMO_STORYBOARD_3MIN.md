# Demo video — Nebius CodeGuard (≤ 3 minutes)

**Output:** `demo/codeguard_demo.mp4` — 1920×1080, H.264 + AAC, ~2:45, English voiceover (offline Piper TTS,
`en_US-lessac-medium`) and on-screen English captions. All terminal footage is real `asciinema` recordings of live
runs; only long model-wait spinners are shortened (marked "⏩ model wait sped up" on screen).

| # | Segment | Visual | Narration (summary) |
|---|---------|--------|---------------------|
| 1 | Title | Title card, Nemotron / Token Factory / Sandboxes tags | What CodeGuard is |
| 2 | Problem | Problem bullets | Confidence ≠ evidence; unsafe patches slip through |
| 3 | Architecture | Write → Preflight → Sandbox → Gates → Judge, repair loop | How each Nebius/NVIDIA piece is used |
| 4 | Setup | `codeguard doctor` (secrets shown only as "set"), `pytest -q` | Setup + 62 offline tests |
| 5 | Live run | `codeguard run 'Write roman_to_int…'` → sandbox 3/3 → gates → judge → ACCEPT | Live write/run/test/accept |
| 6 | Repair loop | Condensed real log: slugify attempt 1 REJECT → attempt 2 ACCEPT | Evidence fed back to Nemotron |
| 7 | Failing test | `codeguard check examples/broken_add.py` → REJECT | Evidence decides |
| 8 | Insecure | `codeguard check examples/insecure_eval.py` → REJECT before execution | Unsafe code never runs |
| 9 | Impact | Four "why it matters" rows | No accept without evidence; one platform |
| 10 | Closing | Repo URL placeholder, MIT, "Built with Nebius Token Factory + NVIDIA Nemotron" | Thanks |

## Regenerate

```bash
pip install asciinema pyte pillow piper-tts           # separate tools venv recommended
# download a Piper voice, e.g. en_US-lessac-medium.onnx (+ .json) from huggingface.co/rhasspy/piper-voices
demo/tools/record.sh all          # re-records terminal scenes (spawns ~2 sandboxes); writes demo/raw/*.cast
PIPER_VOICE=/path/en_US-lessac-medium.onnx python demo/tools/build_video.py
```

`demo/raw/` and the rendered `.mp4` are git-ignored; screenshots in `demo/screenshots/` are committed.

## Upload checklist
- [ ] Watch once end-to-end (audio level, captions)
- [ ] Upload to YouTube (public or unlisted), title "Nebius CodeGuard — Nebius × NVIDIA Global AI Hackathon"
- [ ] Replace repo placeholder if the final URL differs from `github.com/kuker24/nebius-codeguard`
