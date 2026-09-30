#!/usr/bin/env python3
"""Render the static slides (title, problem, architecture, repair loop, impact, closing)."""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
BG = (8, 10, 14)
PANEL = (18, 22, 30)
WHITE = (245, 247, 250)
GREY = (160, 170, 182)
GREEN = (118, 185, 0)  # NVIDIA green
BLUE = (0, 190, 255)  # Nebius-ish cyan
RED = (240, 90, 90)
YELLOW = (255, 200, 80)
INTER = "/usr/share/fonts/truetype/sand-box/google/Inter/Inter-VariableFont_opsz,wght.ttf"
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"


def font(size, weight=400):
    try:
        f = ImageFont.truetype(INTER, size)
        f.set_variation_by_axes([min(32, max(14, size)), weight])
        return f
    except Exception:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)


def base(title=None, caption=None):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # subtle gradient band
    for i in range(H):
        c = int(8 + 10 * (i / H))
        d.line([(0, i), (W, i)], fill=(c - 2, c, c + 6))
    d.rectangle([0, 0, W, 8], fill=GREEN)
    if title:
        d.text((110, 90), title, font=font(64, 800), fill=WHITE)
        d.rectangle([110, 180, 250, 186], fill=BLUE)
    if caption:
        y0 = H - 150
        d.rectangle([0, y0, W, H], fill=PANEL)
        d.rectangle([0, y0, 10, H], fill=BLUE)
        f = font(34, 400)
        lines = wrap(d, caption, f, W - 120)
        ty = y0 + (150 - len(lines) * 44) / 2
        for ln in lines[:3]:
            d.text((60, ty), ln, font=f, fill=WHITE)
            ty += 44
    return img, d


def wrap(d, text, f, width):
    out, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= width:
            cur = t
        else:
            out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out


def center(d, y, text, f, fill):
    d.text(((W - d.textlength(text, font=f)) / 2, y), text, font=f, fill=fill)


def box(d, xy, title, sub=None, color=BLUE, fill=PANEL, tsize=30, ssize=22):
    x0, y0, x1, y1 = xy
    d.rounded_rectangle(xy, radius=18, fill=fill, outline=color, width=4)
    ft, fs = font(tsize, 700), font(ssize, 400)
    lines = [(title, ft, WHITE)] + [(s, fs, GREY) for s in (sub or [])]
    total = sum((tsize + 10) if f is ft else (ssize + 8) for _, f, _ in lines)
    y = y0 + (y1 - y0 - total) / 2
    for text, f, c in lines:
        d.text((x0 + (x1 - x0 - d.textlength(text, font=f)) / 2, y), text, font=f, fill=c)
        y += (tsize + 10) if f is ft else (ssize + 8)


def arrow(d, p0, p1, color=GREY, width=5, label=None, lpos=None, lcolor=None):
    import math

    d.line([p0, p1], fill=color, width=width)
    ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    s = 18
    a = (p1[0] - s * math.cos(ang - 0.45), p1[1] - s * math.sin(ang - 0.45))
    b = (p1[0] - s * math.cos(ang + 0.45), p1[1] - s * math.sin(ang + 0.45))
    d.polygon([p1, a, b], fill=color)
    if label:
        f = font(22, 600)
        x, y = lpos or ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
        d.text((x, y), label, font=f, fill=lcolor or color)


def title_slide(caption=None):
    img, d = base(caption=caption)
    center(d, 270, "Nebius CodeGuard", font(120, 800), WHITE)
    center(d, 420, "A coding agent that must prove its code before it ships", font(44, 500), GREY)
    tags = [("NVIDIA Nemotron", GREEN), ("Nebius Token Factory", BLUE), ("Token Factory Sandboxes", BLUE)]
    f = font(30, 700)
    widths = [d.textlength(t, font=f) + 60 for t, _ in tags]
    x = (W - sum(widths) - 30 * (len(tags) - 1)) / 2
    for (t, c), w in zip(tags, widths):
        d.rounded_rectangle([x, 540, x + w, 600], radius=30, outline=c, width=3)
        d.text((x + 30, 552), t, font=f, fill=c)
        x += w + 30
    center(d, 690, "Nebius × NVIDIA Global AI Hackathon  ·  Track: Coding and Agentic Engineering", font(30, 400), GREY)
    return img


def problem_slide(caption=None):
    img, d = base("The problem", caption)
    items = [
        (RED, "Coding agents write code confidently — confidence is not evidence."),
        (RED, "Untested or unsafe patches (eval, shell calls, network access) slip through."),
        (RED, "Running model-written code on a developer laptop is a security risk."),
        (GREEN, "CodeGuard: the model must prove every patch in an isolated sandbox,"),
        (GREEN, "and hard, deterministic gates decide — not the model's own claims."),
    ]
    y = 260
    for c, t in items:
        d.ellipse([130, y + 14, 152, y + 36], fill=c)
        d.text((180, y), t, font=font(40, 500), fill=WHITE)
        y += 100 if c is RED else 80
        if c is RED and items.index((c, t)) == 2:
            y += 30
    return img


def architecture_slide(caption=None):
    img, d = base("How CodeGuard works", caption)
    y0, y1 = 300, 470
    xs = [(90, 390), (470, 790), (870, 1170), (1250, 1550), (1600, 1860)]
    box(d, (xs[0][0], y0, xs[0][1], y1), "1 · Write", ["NVIDIA Nemotron", "via Nebius Token Factory", "(OpenAI-compatible API)"], GREEN)
    box(d, (xs[1][0], y0, xs[1][1], y1), "2 · Preflight", ["AST security scan:", "eval / exec / subprocess /", "network / os.system …"], YELLOW)
    box(d, (xs[2][0], y0, xs[2][1], y1), "3 · Sandbox", ["Nebius Token Factory", "Sandbox (Contree SDK)", "python:3.12-slim, fresh"], BLUE)
    box(d, (xs[3][0], y0, xs[3][1], y1), "4 · Gates", ["exit code == 0", "every test_* passed", "security + quality"], BLUE)
    box(d, (xs[4][0], y0, xs[4][1], y1), "Judge", ["Nemotron sees only", "observed evidence", "(veto only)"], GREEN, tsize=30)
    for i in range(4):
        arrow(d, (xs[i][1] + 8, (y0 + y1) / 2), (xs[i + 1][0] - 8, (y0 + y1) / 2), GREY)
    # outcomes
    box(d, (1560, 610, 1860, 720), "ACCEPT", ["tests passed + gates green"], GREEN, fill=(14, 30, 14), tsize=34)
    arrow(d, (1730, y1 + 8), (1730, 602), GREEN)
    box(d, (500, 610, 800, 720), "REJECT", ["never sent to sandbox"], RED, fill=(34, 14, 14), tsize=34)
    arrow(d, (630, y1 + 8), (630, 602), RED, label="blocked", lpos=(645, 520))
    # repair loop
    d.line([(1400, y1 + 8), (1400, 800), (240, 800), (240, y1 + 8)], fill=YELLOW, width=5)
    arrow(d, (240, 805), (240, y1 + 10), YELLOW)
    d.text((560, 812), "tests fail → sandbox evidence fed back to Nemotron → repair attempt (--attempts, default 2)", font=font(26, 600), fill=YELLOW)
    d.text((110, 215), "Evidence-first: no ACCEPT without passing tests observed in a Nebius sandbox.", font=font(32, 500), fill=GREY)
    return img


def repair_slide(log_lines, caption=None):
    img, d = base("Repair loop — real output from a live run (30 Sep 2026)", caption)
    fm, fb = ImageFont.truetype(MONO, 25), ImageFont.truetype(MONO_B, 25)
    x0, y0 = 110, 230
    d.rounded_rectangle([x0 - 20, y0 - 20, W - 90, y0 + 30 * len(log_lines) + 20], radius=14, fill=(13, 17, 23), outline=(40, 48, 60))
    y = y0
    for text, style in log_lines:
        c = {"red": RED, "green": (80, 220, 120), "cyan": (80, 200, 220), "grey": GREY, "yellow": YELLOW}.get(style, WHITE)
        d.text((x0, y), text, font=fb if style in ("red", "green", "cyan") else fm, fill=c)
        y += 30
    return img


def impact_slide(caption=None):
    img, d = base("Why it matters", caption)
    rows = [
        (GREEN, "No accept without evidence", "Gates are deterministic; the LLM judge can veto but never override them."),
        (BLUE, "Untrusted code never runs locally", "Every candidate executes in a disposable Token Factory Sandbox."),
        (YELLOW, "Unsafe code never runs at all", "Static preflight blocks eval, subprocess, sockets and destructive os calls."),
        (GREEN, "One platform", "Nemotron inference + Sandboxes on Nebius Token Factory with one API key."),
    ]
    y = 250
    for c, h, s in rows:
        d.rounded_rectangle([110, y, 130, y + 110], radius=8, fill=c)
        d.text((170, y + 4), h, font=font(42, 700), fill=WHITE)
        d.text((170, y + 62), s, font=font(30, 400), fill=GREY)
        y += 150
    return img


def closing_slide(caption=None):
    img, d = base(caption=caption)
    center(d, 250, "Nebius CodeGuard", font(100, 800), WHITE)
    center(d, 390, "github.com/kuker24/nebius-codeguard", font(50, 600), BLUE)
    center(d, 480, "Open source · MIT License", font(36, 400), GREY)
    center(d, 600, "Built with Nebius Token Factory + NVIDIA Nemotron", font(40, 700), GREEN)
    center(d, 660, "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B  ·  Token Factory Sandboxes (Contree SDK)", font(28, 400), GREY)
    center(d, 760, "Nebius × NVIDIA Global AI Hackathon  ·  Coding and Agentic Engineering", font(30, 400), GREY)
    return img


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "demo/raw")
    out.mkdir(parents=True, exist_ok=True)
    title_slide().save(out / "slide_title.png")
    architecture_slide().save(out / "slide_arch.png")
    problem_slide().save(out / "slide_problem.png")
    impact_slide().save(out / "slide_impact.png")
    closing_slide().save(out / "slide_closing.png")
    print("ok")
