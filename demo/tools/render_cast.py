#!/usr/bin/env python3
"""Render an asciinema v2 .cast into an H.264 clip with a title bar and captions.

    render_cast.py scene.json

scene.json keys:
  cast, out, title, fps (20), width/height (1920x1080), font_size (22),
  captions: [[regex_or_null, text], ...]  first entry (regex null) = initial caption;
            later entries switch the caption when stripped output matches regex
  holds:    [[regex, seconds], ...]  pause on the current screen before the
            first event matching regex (lets viewers read)
  max_spinner: seconds — cap long spinner-only waits (marked "sped up" on screen)
  tail: seconds to hold the final frame
  snapshots: [[regex_or_"end", seconds_after, path.png], ...]
"""
from __future__ import annotations

import json
import re
import subprocess
import sys

import pyte
from PIL import Image, ImageDraw, ImageFont

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07|\r")
SPINNER_HINTS = ("is writing code", "running tests in a fresh", "judge reviewing")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
SANS_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

BG = (13, 17, 23)
FG = (220, 223, 228)
PALETTE = {
    "black": (40, 44, 52), "red": (240, 90, 90), "green": (80, 220, 120), "brown": (230, 190, 80),
    "yellow": (230, 190, 80), "blue": (90, 150, 255), "magenta": (200, 120, 230), "cyan": (80, 200, 220),
    "white": (220, 223, 228), "brightblack": (110, 118, 129), "brightred": (255, 120, 120),
    "brightgreen": (120, 240, 150), "brightbrown": (255, 220, 110), "brightyellow": (255, 220, 110),
    "brightblue": (130, 180, 255), "brightmagenta": (230, 150, 255), "brightcyan": (120, 230, 240),
    "brightwhite": (255, 255, 255),
}
ACCENT = (118, 185, 0)  # NVIDIA-ish green
NEBIUS = (0, 190, 255)


def color(c: str, default):
    if c == "default":
        return default
    if c in PALETTE:
        return PALETTE[c]
    if re.fullmatch(r"[0-9a-fA-F]{6}", c):
        return tuple(int(c[i : i + 2], 16) for i in (0, 2, 4))
    return default


def strip(s: str) -> str:
    return ANSI.sub("", s)


def wrap(draw, text, font, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


class Renderer:
    def __init__(self, cfg, cols, rows):
        self.W, self.H = cfg.get("width", 1920), cfg.get("height", 1080)
        fs = cfg.get("font_size", 21)
        self.font = ImageFont.truetype(FONT, fs)
        self.font_b = ImageFont.truetype(FONT_B, fs)
        self.cw = self.font.getlength("M")
        self.lh = int(fs * 1.25)
        self.cols, self.rows = cols, rows
        self.top, self.bottom = 76, 150
        term_w, term_h = self.cw * cols, self.lh * rows
        self.ox = int((self.W - term_w) / 2)
        self.oy = self.top + int((self.H - self.top - self.bottom - term_h) / 2)
        self.title = cfg.get("title", "")
        self.cap_font = ImageFont.truetype(SANS, 34)
        self.title_font = ImageFont.truetype(SANS_B, 28)
        self.small = ImageFont.truetype(SANS, 22)

    def frame(self, screen, caption, sped_up=False):
        img = Image.new("RGB", (self.W, self.H), (8, 10, 14))
        d = ImageDraw.Draw(img)
        # top bar
        d.rectangle([0, 0, self.W, self.top], fill=(18, 22, 30))
        d.rectangle([0, self.top - 3, self.W, self.top], fill=ACCENT)
        d.text((40, 22), "Nebius CodeGuard", font=self.title_font, fill=(255, 255, 255))
        d.text((345, 26), "·  " + self.title, font=self.small, fill=(170, 180, 190))
        right = "live terminal recording" + ("   ⏩ model wait sped up" if sped_up else "")
        d.text((self.W - 40 - d.textlength(right, font=self.small), 26), right, font=self.small,
               fill=(255, 200, 80) if sped_up else (120, 130, 140))
        # terminal
        pad = 18
        d.rounded_rectangle([self.ox - pad, self.oy - pad, self.ox + self.cw * self.cols + pad,
                             self.oy + self.lh * self.rows + pad], radius=14, fill=BG, outline=(40, 48, 60))
        cells = []
        for y in range(self.rows):
            line = screen.buffer[y]
            for x in range(self.cols):
                ch = line[x]
                fg, bg = color(ch.fg, FG), color(ch.bg, None)
                if ch.reverse:
                    fg, bg = (bg or BG), fg
                px, py = self.ox + x * self.cw, self.oy + y * self.lh
                if bg is not None:
                    d.rectangle([px, py, px + self.cw + 1, py + self.lh], fill=bg)
                if ch.data and ch.data != " ":
                    cells.append((px, py, ch.data, ch.bold, fg))
        for px, py, data, bold, fg in cells:
            d.text((px, py + 1), data, font=self.font_b if bold else self.font, fill=fg)
        if not screen.cursor.hidden:
            cx, cy = self.ox + screen.cursor.x * self.cw, self.oy + screen.cursor.y * self.lh
            d.rectangle([cx, cy + 3, cx + self.cw, cy + self.lh - 1], fill=(200, 200, 200))
        # caption
        y0 = self.H - self.bottom
        d.rectangle([0, y0, self.W, self.H], fill=(18, 22, 30))
        d.rectangle([0, y0, 10, self.H], fill=NEBIUS)
        lines = wrap(d, caption or "", self.cap_font, self.W - 120)[:3]
        ty = y0 + (self.bottom - len(lines) * 44) / 2
        for ln in lines:
            d.text((60, ty), ln, font=self.cap_font, fill=(255, 255, 255))
            ty += 44
        return img


def main(cfg_path):
    cfg = json.load(open(cfg_path))
    lines = open(cfg["cast"], encoding="utf-8").read().splitlines()
    header = json.loads(lines[0])
    events = [json.loads(ln) for ln in lines[1:] if ln.strip()]
    events = [(t, d) for t, typ, d in events if typ == "o"]
    cols, rows = header["width"], header["height"]
    fps = cfg.get("fps", 20)

    caps = cfg.get("captions", [[None, ""]])
    cap_rules = [(re.compile(r), c) for r, c in caps[1:]]
    caption = caps[0][1]
    narr = {int(k): v for k, v in cfg.get("narration_durs", {}).items()}
    marks = {"0": 0.0}
    narr_end = 0.5 + narr.get(0, 0.0) + 0.25 if narr else 0.0

    # --- retime: cap spinner stretches, insert holds, sync to narration
    holds = [(re.compile(r), s) for r, s in cfg.get("holds", [])]
    used_holds = set()
    max_spin = cfg.get("max_spinner", 2.5)
    timeline, shift, prev_t, spin_run = [], 0.0, 0.0, 0.0
    sped_ranges = []
    for t, data in events:
        text = strip(data)
        gap = t - prev_t
        prev_t = t
        is_spin = any(h in text for h in SPINNER_HINTS) and len(text) < 300
        if is_spin:
            if spin_run + gap > max_spin:
                allowed = max(0.0, max_spin - spin_run)
                shift -= gap - allowed
                if allowed < gap:
                    sped_ranges.append(t + shift)
                spin_run = max_spin
            else:
                spin_run += gap
        else:
            spin_run = 0.0
        for i, (rx, secs) in enumerate(holds):
            if i not in used_holds and rx.search(text):
                used_holds.add(i)
                shift += secs
        # keep the voiceover in sync: a caption (and its narration chunk) may not
        # start before the previous narration chunk has finished
        for ci, (rx, _c) in enumerate(cap_rules, start=1):
            if str(ci) not in marks and rx.search(text):
                T = t + shift
                if ci in narr and T < narr_end:
                    shift += narr_end - T
                    T = narr_end
                marks[str(ci)] = T
                if ci in narr:
                    narr_end = T + 0.15 + narr[ci] + 0.25
        timeline.append((t + shift, data, text))

    snaps = cfg.get("snapshots", [])
    snap_rules = [(r, after, p) for r, after, p in snaps if r != "end"]
    snap_end = [(after, p) for r, after, p in snaps if r == "end"]
    pending_snaps = []

    screen = pyte.Screen(cols, rows)
    stream = pyte.ByteStream(screen)
    rend = Renderer(cfg, cols, rows)
    end_t = max((timeline[-1][0] if timeline else 0), narr_end) + cfg.get("tail", 2.0)
    min_d = cfg.get("min_duration", 0)
    end_t = max(end_t, min_d)
    nframes = int(end_t * fps) + 1
    W, H = rend.W, rend.H
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-r", str(fps), cfg["out"]], stdin=subprocess.PIPE)
    idx, last_bytes, dirty = 0, None, True
    last_img = None
    for f in range(nframes):
        now = f / fps
        while idx < len(timeline) and timeline[idx][0] <= now:
            _, data, text = timeline[idx]
            stream.feed(data.encode("utf-8"))
            for rx, c in cap_rules:
                if rx.search(text):
                    caption = c
            for r, after, p in snap_rules:
                if re.search(r, text) and p not in [q for _, q in pending_snaps]:
                    pending_snaps.append((now + after, p))
            idx += 1
            dirty = True
        sped = any(abs(now - s) < 1.2 for s in sped_ranges)
        key = (caption, sped)
        if dirty or last_bytes is None or key != getattr(main, "_k", None):
            main._k = key
            last_img = rend.frame(screen, caption, sped)
            last_bytes = last_img.tobytes()
            dirty = False
        for due, p in list(pending_snaps):
            if now >= due:
                last_img.save(p)
                pending_snaps.remove((due, p))
                snap_rules = [s for s in snap_rules if s[2] != p]
        ff.stdin.write(last_bytes)
    for after, p in snap_end:
        last_img.save(p)
    ff.stdin.close()
    ff.wait()
    with open(cfg["out"] + ".marks.json", "w") as fh:
        json.dump(marks, fh)
    print(f"{cfg['out']}: {end_t:.1f}s, {nframes} frames")


if __name__ == "__main__":
    main(sys.argv[1])
