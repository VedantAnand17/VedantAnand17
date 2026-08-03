#!/usr/bin/env python3
"""Render assets/x402-handshake.gif, the terminal animation in the README.

The GIF is generated from scratch here rather than downloaded, so the repo owns
it outright (CC0-1.0, see assets/LICENSE). The previous README hotlinked a GIF
from a third-party site that later deleted it, which broke the profile.

Usage:  python3 assets/make-hero-gif.py        # needs Pillow + ffmpeg
        python3 assets/make-hero-gif.py --check # self-check, writes nothing
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "x402-handshake.gif"
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
FPS = 20

W, H = 680, 252
PAD_X, TITLEBAR_H, BODY_TOP = 22, 34, 20
FONT_SIZE, LINE_H = 16, 26

CANVAS = "#0d1117"
CHROME = "#161b22"
BORDER = "#30363d"
FG = "#c9d1d9"
DIM = "#8b949e"
GREEN = "#3fb950"
AMBER = "#d29922"
BLUE = "#58a6ff"
RED = "#f85149"
CURSOR = "#58a6ff"

# Each line is a list of (text, colour) segments. `typed` lines animate
# character by character; the rest are command output and appear at once.
LINES = [
    (True, [("$ ", GREEN), ("curl -i https://api.merchant.dev/v1/invoice", FG)]),
    (False, [("HTTP/1.1 ", DIM), ("402 Payment Required", AMBER)]),
    (False, [("x402  ", BLUE), ("0.01 USDC \u00b7 base \u00b7 pay-to 0x9f\u20264b2", DIM)]),
    (False, [("", FG)]),
    (True, [("$ ", GREEN), ("agent pay --auto", FG)]),
    (False, [("\u2713 quote signed   \u2713 settled on-chain   1.2s", GREEN)]),
    (False, [("HTTP/1.1 ", DIM), ("200 OK", GREEN)]),
]


def load_fonts():
    regular = FONT_DIR / "DejaVuSansMono.ttf"
    bold = FONT_DIR / "DejaVuSansMono-Bold.ttf"
    if not regular.exists():
        sys.exit(f"missing font: {regular}")
    return (
        ImageFont.truetype(str(regular), FONT_SIZE),
        ImageFont.truetype(str(bold), FONT_SIZE - 3),
    )


def draw_frame(font, title_font, visible, cursor_on):
    """visible: list of per-line character counts (None = line fully hidden)."""
    im = Image.new("RGB", (W, H), CANVAS)
    d = ImageDraw.Draw(im)

    # Square-cornered window chrome. Sharp edges are the point here.
    d.rectangle([0, 0, W - 1, TITLEBAR_H], fill=CHROME)
    d.line([0, TITLEBAR_H, W, TITLEBAR_H], fill=BORDER)
    d.rectangle([0, 0, W - 1, H - 1], outline=BORDER)
    for i, colour in enumerate((RED, AMBER, GREEN)):
        x = PAD_X + i * 18
        d.rectangle([x, TITLEBAR_H // 2 - 5, x + 9, TITLEBAR_H // 2 + 4], fill=colour)
    d.text((PAD_X + 66, TITLEBAR_H // 2 - 7), "vedant@onchain \u2014 x402", font=title_font, fill=DIM)

    char_w = font.getlength("M")
    last_xy = None
    for idx, (_typed, segments) in enumerate(LINES):
        shown = visible[idx]
        if shown is None:
            continue
        y = TITLEBAR_H + BODY_TOP + idx * LINE_H
        col = 0
        budget = shown
        for text, colour in segments:
            if budget <= 0:
                break
            chunk = text[:budget]
            if chunk:
                d.text((PAD_X + col * char_w, y), chunk, font=font, fill=colour)
            col += len(chunk)
            budget -= len(chunk)
        last_xy = (PAD_X + col * char_w, y)

    if cursor_on and last_xy:
        x, y = last_xy
        d.rectangle([x + 1, y + 3, x + char_w - 1, y + FONT_SIZE + 3], fill=CURSOR)
    return im


def build_frames(font, title_font):
    frames = []
    visible = [None] * len(LINES)

    def snap(cursor_on=True, times=1):
        frames.extend([draw_frame(font, title_font, list(visible), cursor_on)] * times)

    for idx, (typed, segments) in enumerate(LINES):
        total = sum(len(t) for t, _ in segments)
        if typed:
            visible[idx] = 0
            for n in range(0, total + 1, 3):
                visible[idx] = min(n, total)
                snap(cursor_on=True)
            visible[idx] = total
            # Blink while the request is in flight.
            for _ in range(2):
                snap(cursor_on=True, times=5)
                snap(cursor_on=False, times=5)
        else:
            visible[idx] = total
            snap(cursor_on=False, times=1 if total == 0 else 9)

    # Hold the finished transcript, then blink out so the loop reads cleanly.
    snap(cursor_on=False, times=30)
    for _ in range(2):
        snap(cursor_on=True, times=6)
        snap(cursor_on=False, times=6)
    return frames


def encode(frames):
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found; needed for palette-optimised GIF output")
    with tempfile.TemporaryDirectory() as tmp:
        for i, frame in enumerate(frames):
            frame.save(Path(tmp) / f"f{i:05d}.png")
        vf = "split[a][b];[a]palettegen=max_colors=64:stats_mode=full[p];[b][p]paletteuse=dither=none"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
             "-i", str(Path(tmp) / "f%05d.png"), "-vf", vf, "-loop", "0", str(OUT)],
            check=True,
        )


def main():
    font, title_font = load_fonts()
    frames = build_frames(font, title_font)

    # One runnable check: the animation must actually animate (distinct frames),
    # must end on the full transcript, and must stay small enough to load fast.
    assert len(frames) > 40, f"suspiciously few frames: {len(frames)}"
    assert frames[0].tobytes() != frames[-1].tobytes(), "first and last frame identical"
    blank = draw_frame(font, title_font, [None] * len(LINES), False)
    assert frames[-1].tobytes() != blank.tobytes(), "final frame is an empty terminal"

    if "--check" in sys.argv:
        print(f"OK: {len(frames)} frames, {W}x{H}, would write {OUT}")
        return

    encode(frames)
    size = OUT.stat().st_size
    assert size < 2_000_000, f"GIF too large for a profile page: {size} bytes"
    print(f"wrote {OUT} ({size:,} bytes, {len(frames)} frames, {W}x{H}, {FPS}fps)")


if __name__ == "__main__":
    main()
