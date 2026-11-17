# /// script
# requires-python = ">=3.12"
# dependencies = ["fonttools>=4.50", "brotli>=1.1", "uharfbuzz>=0.40"]
# ///
"""Builds banner.svg, the header of the profile README.

It mirrors the hero of gerwintorres.com: the name in Plus Jakarta Sans, the roles typed one
after another behind a zsh prompt in JetBrains Mono, and the portrait on the navy panel.

GitHub shows README images without loading web fonts, so every text is drawn as vector
outlines, and the typing runs on SVG animation (no scripts). Viewers who ask for reduced
motion get the first role, still.

The fonts and the portrait come from the website's checkout:

    uv run banner/build.py --site ../portfolio
"""

from __future__ import annotations

import argparse
import base64
import io
import shutil
import struct
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

# Same order and wording as the typed card on the site (src/data/content.ts, hero.roles).
ROLES = [
    "Software Backend Engineer",
    "Python & FastAPI",
    "REST APIs",
    "Event-driven architecture",
    "Cloud & Data",
    "GCP & Azure",
    "AI-first development",
]

# Site palette (src/styles/tokens.css).
NAVY_900 = "#0f1726"
NAVY_800 = "#141e30"
NAVY_600 = "#2a3f5f"
STEEL_500 = "#35577d"
ORANGE_400 = "#f2803f"
ORANGE_500 = "#e0641a"
ICE_50 = "#eef2f7"

W, H = 1120, 440
PANEL_X = 740  # where the portrait panel starts
LEFT = 80

# Typing rhythm of the site, in milliseconds.
TYPE_MS, DELETE_MS, HOLD_MS, PAUSE_MS = 75, 35, 1800, 350


@dataclass
class Face:
    font: TTFont
    hb_font: hb.Font
    upem: int

    @property
    def cap_height(self) -> float:
        """Height of capitals, as a fraction of the font size."""
        return self.font["OS/2"].sCapHeight / self.upem

    @classmethod
    def load(cls, path: Path, weight: int) -> Face:
        variable = TTFont(path)
        static = instancer.instantiateVariableFont(variable, {"wght": weight})
        static.flavor = None
        data = io.BytesIO()
        static.save(data)
        blob = hb.Blob(data.getvalue())
        return cls(TTFont(io.BytesIO(data.getvalue())), hb.Font(hb.Face(blob)), static["head"].unitsPerEm)

    def path(self, text: str, x: float, baseline: float, size: float, tracking: float = 0) -> tuple[str, float]:
        """Outline of `text` with its left edge at x; returns the path data and the advance width."""
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.hb_font, buf, {"kern": True, "liga": False, "calt": False})

        scale = size / self.upem
        order = self.font.getGlyphOrder()
        glyphs = self.font.getGlyphSet()
        pen = SVGPathPen(glyphs, ntos=lambda n: f"{n:.1f}".rstrip("0").rstrip("."))
        cursor = 0.0
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            gx = x + (cursor + pos.x_offset) * scale
            transform = (scale, 0, 0, -scale, gx, baseline - pos.y_offset * scale)
            glyphs[order[info.codepoint]].draw(TransformPen(pen, transform))
            cursor += pos.x_advance + tracking * self.upem
        return pen.getCommands(), cursor * scale


def portrait_data_uri(png: Path, height: int) -> str:
    """The cut-out portrait as WebP (keeps the transparency, a fraction of the PNG's weight)."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "portrait.webp"
        subprocess.run(
            [
                "cwebp",
                "-quiet",
                "-q",
                "82",
                "-alpha_q",
                "90",
                "-resize",
                "0",
                str(height * 2),
                str(png),
                "-o",
                str(out),
            ],
            check=True,
        )
        return "data:image/webp;base64," + base64.b64encode(out.read_bytes()).decode()


def typing_timeline(lengths: list[int]) -> tuple[list[list[tuple[float, int]]], float]:
    """For each role, the (time, visible characters) changes over one loop.

    The loop opens with the first role already typed, like the site, and ends by typing
    it again, so it repeats without a jump.
    """
    events: list[list[tuple[float, int]]] = [[(0.0, 0)] for _ in lengths]
    events[0] = [(0.0, lengths[0])]
    t = float(HOLD_MS)

    def delete(i: int) -> None:
        nonlocal t
        for n in range(lengths[i] - 1, -1, -1):
            t += DELETE_MS
            events[i].append((t, n))
        t += PAUSE_MS

    def type_(i: int) -> None:
        nonlocal t
        for n in range(1, lengths[i] + 1):
            t += TYPE_MS
            events[i].append((t, n))

    delete(0)
    for i in range(1, len(lengths)):
        type_(i)
        t += HOLD_MS
        delete(i)
    type_(0)
    return events, t


def animate(attr: str, changes: list[tuple[float, float]], total: float) -> str:
    times, values = [], []
    for t, v in changes:
        key = round(t / total, 5)
        if times and key <= times[-1]:
            key = times[-1] + 0.00001
        times.append(key)
        values.append(f"{v:g}")
    return (
        f'<animate attributeName="{attr}" dur="{total / 1000:g}s" repeatCount="indefinite" '
        f'calcMode="discrete" keyTimes="{";".join(f"{k:.5f}".rstrip("0").rstrip(".") or "0" for k in times)}" '
        f'values="{";".join(values)}"/>'
    )


def build(site: Path) -> str:
    fonts = site / "node_modules/@fontsource-variable"
    display = Face.load(fonts / "plus-jakarta-sans/files/plus-jakarta-sans-latin-wght-normal.woff2", 800)
    jetbrains = fonts / "jetbrains-mono/files/jetbrains-mono-latin-wght-normal.woff2"
    mono, mono_bold = Face.load(jetbrains, 500), Face.load(jetbrains, 700)

    parts: list[str] = []

    # Big faint initials behind the name, as on the site.
    gt_size = 360
    gt, _ = display.path("GT", 36, (H + display.cap_height * gt_size) / 2, gt_size, tracking=-0.06)
    parts.append(f'<path d="{gt}" fill="{ICE_50}" opacity="0.04"/>')

    # Address, name and typed card, stacked and centered vertically.
    url_size, name_size, line_step, card_h, card_w = 22, 78, 74, 60, 470
    url_rise = 0.73 * url_size  # ascenders above the address' baseline
    name_cap = display.cap_height * name_size
    url_gap, card_gap = 26, 30
    block = url_rise + url_gap + name_cap + 2 * line_step + card_gap + card_h
    url_base = (H - block) / 2 + url_rise
    name_base = url_base + url_gap + name_cap
    card_y = name_base + 2 * line_step + card_gap

    url, _ = mono.path("gerwintorres.com", LEFT, url_base, url_size)
    parts.append(f'<path d="{url}" fill="{ORANGE_400}"/>')

    # One word per line, the middle one in orange.
    for i, (word, color) in enumerate([("GERWIN", ICE_50), ("LAMBRAÑO", ORANGE_400), ("TORRES", ICE_50)]):
        d, _ = display.path(word, LEFT - 4, name_base + i * line_step, name_size, tracking=-0.03)
        parts.append(f'<path d="{d}" fill="{color}"/>')

    # The typed card: prompt, roles and caret.
    parts.append(
        f'<rect x="{LEFT}" y="{card_y:g}" width="{card_w}" height="{card_h}" rx="14" '
        f'fill="{NAVY_800}" stroke="{NAVY_600}"/>'
    )
    text_size = 23
    baseline = card_y + card_h / 2 + mono.cap_height * text_size / 2
    prompt, prompt_w = mono_bold.path("%", LEFT + 22, baseline, text_size)
    parts.append(f'<path d="{prompt}" fill="{ORANGE_400}"/>')
    text_x = LEFT + 22 + prompt_w + 12
    char_w = mono.path("M", 0, 0, text_size)[1]

    events, total = typing_timeline([len(r) for r in ROLES])
    clips, roles_svg = [], []
    for i, role in enumerate(ROLES):
        d, _ = mono.path(role, text_x, baseline, text_size)
        start = events[i][0][1] * char_w
        clips.append(
            f'<clipPath id="r{i}"><rect x="{text_x - 1:g}" y="{card_y:g}" width="{start:g}" height="{card_h}">'
            f"{animate('width', [(t, n * char_w) for t, n in events[i]], total)}</rect></clipPath>"
        )
        roles_svg.append(f'<path d="{d}" fill="{ICE_50}" clip-path="url(#r{i})"/>')

    # The caret follows whichever role is on screen.
    caret_changes = sorted({t: text_x + n * char_w + 2 for ev in events for t, n in ev if t > 0}.items())
    caret_start = text_x + len(ROLES[0]) * char_w + 2
    caret_y = card_y + (card_h - 24) / 2
    caret = (
        f'<rect class="caret" x="{caret_start:g}" y="{caret_y:g}" width="2.5" height="24" fill="{ORANGE_400}">'
        f"{animate('x', [(0, caret_start), *caret_changes], total)}"
        '<animate attributeName="opacity" values="1;0" dur="1s" calcMode="discrete" repeatCount="indefinite"/>'
        "</rect>"
    )
    still, _ = mono.path(ROLES[0], text_x, baseline, text_size)
    parts.append(f'<g class="typing">{"".join(roles_svg)}{caret}</g>')
    parts.append(
        f'<g class="still"><path d="{still}" fill="{ICE_50}"/>'
        f'<rect x="{caret_start:g}" y="{caret_y:g}" width="2.5" height="24" fill="{ORANGE_400}"/></g>'
    )

    # Portrait panel on the right, with the orange edge of the site's hero.
    png = site / "src/assets/gerwin-portrait.png"
    png_w, png_h = struct.unpack(">II", png.read_bytes()[16:24])  # from the PNG header
    portrait_h = 410
    portrait_w = round(portrait_h * png_w / png_h)
    panel_w = W - PANEL_X
    portrait = portrait_data_uri(png, portrait_h)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title">
<title id="title">Gerwin Lambraño Torres · Python backend engineer · gerwintorres.com</title>
<style>
.still {{ display: none; }}
@media (prefers-reduced-motion: reduce) {{
  .typing {{ display: none; }}
  .still {{ display: inline; }}
}}
</style>
<defs>
<clipPath id="frame"><rect width="{W}" height="{H}" rx="24"/></clipPath>
<linearGradient id="panel" x1="0" y1="0" x2="0.55" y2="1">
<stop offset="0" stop-color="{NAVY_800}"/><stop offset="1" stop-color="{STEEL_500}"/>
</linearGradient>
{"".join(clips)}
</defs>
<g clip-path="url(#frame)">
<rect width="{W}" height="{H}" fill="{NAVY_900}"/>
<rect x="{PANEL_X}" width="{panel_w}" height="{H}" fill="url(#panel)"/>
<rect x="{PANEL_X}" width="4" height="{H}" fill="{ORANGE_500}"/>
<image href="{portrait}" x="{PANEL_X + (panel_w - portrait_w) / 2 + 2:g}" y="{H - portrait_h}" width="{portrait_w}" height="{portrait_h}"/>
{chr(10).join(parts)}
</g>
</svg>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", type=Path, default=Path("../portfolio"), help="checkout of gerwintorres.com")
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("banner.svg"))
    args = parser.parse_args()

    if not shutil.which("cwebp"):
        raise SystemExit("cwebp not found (brew install webp)")
    args.out.write_text(build(args.site.expanduser()), encoding="utf-8")
    print(f"wrote {args.out} ({args.out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
