#!/usr/bin/env python3
"""Generate the UX Audit Admin icon and apply it to the .command file on the Desktop."""

import base64
import os
import subprocess
import sys
import tempfile
import shutil

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Pillow is required. Run: pip install Pillow")

COMMAND_FILE = os.path.expanduser("~/Desktop/UX Audit Admin.command")

# ── Icon design ───────────────────────────────────────────────────────────────

def draw_rounded_rect(draw, xy, radius, fill):
    x0, y0, x1, y1 = xy
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    draw.ellipse([x0, y0, x0 + radius * 2, y0 + radius * 2], fill=fill)
    draw.ellipse([x1 - radius * 2, y0, x1, y0 + radius * 2], fill=fill)
    draw.ellipse([x0, y1 - radius * 2, x0 + radius * 2, y1], fill=fill)
    draw.ellipse([x1 - radius * 2, y1 - radius * 2, x1, y1], fill=fill)


def load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return None


def best_font(size):
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSDisplay.ttf",
        "/System/Library/Fonts/SFNSText.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for p in candidates:
        f = load_font(p, size)
        if f:
            return f
    return ImageFont.load_default()


def make_icon(size=1024):
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # ── Background: dark rounded square ──────────────────────────────────────
    radius = int(size * 0.18)
    BG     = (13, 13, 13, 255)        # #0D0D0D
    draw_rounded_rect(draw, [0, 0, size, size], radius, BG)

    # ── Subtle dot-grid overlay ───────────────────────────────────────────────
    dot_r   = max(1, size // 256)
    spacing = size // 16
    dot_col = (255, 255, 255, 14)
    for gx in range(spacing, size, spacing):
        for gy in range(spacing, size, spacing):
            draw.ellipse([gx - dot_r, gy - dot_r, gx + dot_r, gy + dot_r], fill=dot_col)

    # ── Orange accent bar at top ──────────────────────────────────────────────
    bar_h = int(size * 0.055)
    bar_w = int(size * 0.22)
    bar_x = int(size * 0.50 - bar_w / 2)
    bar_y = int(size * 0.12)
    draw.rounded_rectangle(
        [bar_x, bar_y, bar_x + bar_w, bar_y + bar_h],
        radius=bar_h // 2,
        fill=(240, 80, 35, 255),   # #F05023
    )

    # ── "UX" — large, white ───────────────────────────────────────────────────
    ux_size  = int(size * 0.46)
    ux_font  = best_font(ux_size)
    ux_text  = "UX"
    ux_color = (255, 255, 255, 255)
    bb  = draw.textbbox((0, 0), ux_text, font=ux_font)
    tw  = bb[2] - bb[0]
    th  = bb[3] - bb[1]
    ux_x = (size - tw) // 2 - bb[0]
    ux_y = int(size * 0.245) - bb[1]
    draw.text((ux_x, ux_y), ux_text, font=ux_font, fill=ux_color)

    # ── "AUDIT" — medium, orange ──────────────────────────────────────────────
    a_size  = int(size * 0.145)
    a_font  = best_font(a_size)
    a_text  = "AUDIT"
    a_color = (240, 80, 35, 255)    # #F05023
    bb  = draw.textbbox((0, 0), a_text, font=a_font)
    tw  = bb[2] - bb[0]
    a_x = (size - tw) // 2 - bb[0]
    a_y = ux_y + th + int(size * 0.01)
    draw.text((a_x, a_y), a_text, font=a_font, fill=a_color)

    # ── Divider line ──────────────────────────────────────────────────────────
    div_y = int(size * 0.76)
    div_x0 = int(size * 0.18)
    div_x1 = int(size * 0.82)
    draw.line([(div_x0, div_y), (div_x1, div_y)], fill=(255, 255, 255, 28), width=max(1, size // 256))

    # ── "ADMIN" badge — cyan ──────────────────────────────────────────────────
    adm_size   = int(size * 0.085)
    adm_font   = best_font(adm_size)
    adm_text   = "ADMIN"
    adm_color  = (26, 200, 212, 255)   # #1AC8D4
    bb  = draw.textbbox((0, 0), adm_text, font=adm_font)
    tw  = bb[2] - bb[0]
    th2 = bb[3] - bb[1]
    pad_x, pad_y = int(size * 0.055), int(size * 0.022)
    pill_x0 = (size - tw - pad_x * 2) // 2
    pill_y0 = int(size * 0.80)
    pill_x1 = pill_x0 + tw + pad_x * 2
    pill_y1 = pill_y0 + th2 + pad_y * 2
    draw.rounded_rectangle(
        [pill_x0, pill_y0, pill_x1, pill_y1],
        radius=(pill_y1 - pill_y0) // 2,
        fill=(26, 200, 212, 28),
        outline=(26, 200, 212, 90),
        width=max(1, size // 512),
    )
    adm_x = pill_x0 + pad_x - bb[0]
    adm_y = pill_y0 + pad_y - bb[1]
    draw.text((adm_x, adm_y), adm_text, font=adm_font, fill=adm_color)

    return img


# ── ICNS builder ──────────────────────────────────────────────────────────────

ICONSET_SIZES = [16, 32, 64, 128, 256, 512, 1024]

def make_icns(img, out_path):
    tmp = tempfile.mkdtemp(suffix=".iconset")
    try:
        for s in ICONSET_SIZES:
            resized = img.resize((s, s), Image.LANCZOS)
            resized.save(os.path.join(tmp, f"icon_{s}x{s}.png"))
            # @2x variant (only up to 512@2x = 1024)
            s2 = s * 2
            if s2 <= 1024:
                resized2 = img.resize((s2, s2), Image.LANCZOS)
                resized2.save(os.path.join(tmp, f"icon_{s}x{s}@2x.png"))
        result = subprocess.run(
            ["iconutil", "-c", "icns", tmp, "-o", out_path],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"iconutil failed: {result.stderr}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Apply icon to the .command file ──────────────────────────────────────────

def apply_icon(icns_path, target_path):
    script = f"""
use framework "AppKit"
use framework "Foundation"
set img to current application's NSImage's alloc()'s initWithContentsOfFile_("{icns_path}")
(current application's NSWorkspace's sharedWorkspace()'s setIcon_forFile_options_(img, "{target_path}", 0))
"""
    result = subprocess.run(
        ["osascript", "-l", "AppleScript", "-e", script],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"osascript failed: {result.stderr.strip()}")


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    icon_dir  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    icns_path = os.path.join(icon_dir, "app_icon.icns")
    png_path  = os.path.join(icon_dir, "app_icon.png")

    print("  Generating icon...")
    img = make_icon(1024)
    img.save(png_path)

    print("  Building .icns...")
    make_icns(img, icns_path)

    if not os.path.exists(COMMAND_FILE):
        print(f"  Warning: {COMMAND_FILE} not found — icon not applied.")
        print(f"  .icns saved to: {icns_path}")
        sys.exit(0)

    print("  Applying icon to Desktop shortcut...")
    apply_icon(icns_path, COMMAND_FILE)

    print("  Done. Icon applied to 'UX Audit Admin.command' on your Desktop.")
