"""
Carousel engine v2.

A carousel is a SPEC: a plain dict of slides, and each slide is a background plus a list of
elements (text, stars, inset photos, tape, arrows...). Gemini reads the photos and writes the
words; code builds the first spec; the editor changes the spec; render_spec() turns it into PNGs.
Everything visual is drawn by code, so edits are instant and results look designed.
"""

import base64
import colorsys
import copy
import io
import json
import math
import os
import random
import uuid
import zlib

import numpy as np
import requests
from dotenv import load_dotenv
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

load_dotenv()
HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "fonts")
FONT_SPECS = {  # key: (file, variable-font weight)
    "rounded": ("Fredoka.ttf", 500), "rounded_bold": ("Fredoka.ttf", 600), "chunky": ("LilitaOne-Regular.ttf", None),
    "hand": ("Caveat.ttf", None), "serif": ("PlayfairDisplay.ttf", None), "serif_italic": ("PlayfairDisplay-Italic.ttf", None),
    "sans": ("Poppins-Regular.ttf", None), "sans_bold": ("Poppins-Bold.ttf", None), "mono": ("SpaceMono-Regular.ttf", None),
}
FONT_KEYS = list(FONT_SPECS)
SYSTEM_FONTS = ["/System/Library/Fonts/Supplemental/Georgia.ttf", "/System/Library/Fonts/Helvetica.ttc",
                "/Library/Fonts/Arial.ttf", "C:\\Windows\\Fonts\\arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]

FAMILIES = ["scrapbook", "classic", "whimsy", "scribble"]
STYLES = ["polaroid", "minimal", "film", "poster"]
ELEMENTS = ["tape", "stars", "circles", "squiggle", "dots", "film_border"]
DEFAULT_MODEL = "gemini-flash-latest"  # override with GEMINI_MODEL in .env

PRESETS = {  # title, star, note, highlight
    "Warm Cream & Espresso": ("#2c2523", "#d49b45", "#5c524b", "#d9b48f"),
    "Sage & Botanical": ("#273a2e", "#7d9d83", "#485d4f", "#a3c4a8"),
    "Vintage Rose": ("#3e282b", "#d49b45", "#6c4d51", "#e2a8a8"),
    "Terracotta & Clay": ("#3b2b25", "#e29b68", "#66493e", "#c97a5b"),
    "Midnight Journal": ("#f4efe6", "#ffd166", "#e2dcd2", "#e5b869"),
    "Royal Crimson & Pichwai": ("#fff1d6", "#f3b334", "#fedec6", "#e24358"),
    "Bubblegum": ("#ffa0e2", "#f7e23a", "#ffffff", "#fae23c"),
}
_font_cache = {}


# ============================================================ fonts and colours
def get_font(kind, size):
    key = (kind, size)
    if key in _font_cache:
        return _font_cache[key]
    fname, wght = FONT_SPECS.get(kind, FONT_SPECS["sans"])
    font = None
    for path in [os.path.join(FONT_DIR, fname), *SYSTEM_FONTS]:
        try:
            font = ImageFont.truetype(path, size)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default(size)
    elif wght:
        try:
            font.set_variation_by_axes([wght, 100])  # Fredoka axes: Weight, Width
        except Exception:
            pass
    _font_cache[key] = font
    return font


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(c):
    return "#%02x%02x%02x" % tuple(int(x) for x in c)


def resolve_color(c, theme):
    if isinstance(c, str) and c.startswith("theme:"):
        c = theme.get(c[6:], "#ffffff")
    return hex_to_rgb(c) if isinstance(c, str) else tuple(c)


def resolve_font(f, theme):
    return theme.get(f[6:] + "_font", "sans") if isinstance(f, str) and f.startswith("theme:") else f


def mix(a, b, t):
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


def lum(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def sat(c):
    return colorsys.rgb_to_hsv(*(x / 255 for x in c))[1]


def vivid(c):
    h, s, v = colorsys.rgb_to_hsv(*(x / 255 for x in c))
    r, g, b = colorsys.hsv_to_rgb(h, min(1, max(s, 0.45)), min(1, max(v, 0.72)))
    return (int(r * 255), int(g * 255), int(b * 255))


def extract_palette(images, k=5):
    tiles = [im.convert("RGB").resize((64, 64)) for im in images]
    combo = Image.new("RGB", (64 * len(tiles), 64))
    for i, t in enumerate(tiles):
        combo.paste(t, (64 * i, 0))
    q = combo.quantize(colors=k, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    return [tuple(pal[i * 3:i * 3 + 3]) for _, i in sorted(q.getcolors(), reverse=True)]


def make_theme(colors, tone, preset="Bubblegum"):
    colors = list(colors) + [colors[-1]] * (5 - len(colors))
    accent = vivid(max(colors, key=lambda c: sat(c) * (0.4 + lum(c) / 255 * 0.6)))
    second = vivid(colors[1] if colors[1] != colors[0] else colors[2])
    if tone == "dark":
        ink = (10, 10, 14)
        t = dict(bg1=mix(colors[0], ink, 0.75), bg2=mix(accent, ink, 0.80), text=(244, 240, 232), paper=(34, 32, 36), accent=accent)
    else:
        w = (255, 255, 255)
        t = dict(bg1=mix(colors[0], w, 0.80), bg2=mix(accent, w, 0.68), text=(38, 33, 35), paper=(255, 253, 248),
                 accent=mix(accent, (0, 0, 0), 0.06))
    theme = {k: rgb_to_hex(v) for k, v in t.items()}
    theme.update(second=rgb_to_hex(second), tone=tone, band="#1c1c1e", title_font="rounded_bold", body_font="rounded")
    apply_preset(theme, preset)
    return theme


def apply_preset(theme, name):
    if name in PRESETS:
        theme["title"], theme["star"], theme["note"], theme["hl"] = PRESETS[name]
        if name == "Royal Crimson & Pichwai":
            theme["bg1"] = "#580b14"
            theme["bg2"] = "#3e050b"
            theme["tape"] = "#d49b45"
            theme["band"] = "#38060c"
            theme["text"] = "#fff1d6"
            theme["paper"] = (255, 248, 238)
            theme["accent"] = "#f3b334"
            theme["second"] = "#e24358"
            theme["tone"] = "dark"
    return theme


# ============================================================ vibe: Gemini + fallback
PROMPT = """Analyze these {n} photos for an aesthetic Instagram scrapbook carousel.
Story / User Hint: {hint}
If the hint or photos suggest Indian festivities, Navratri, Garba, Dandiya, or Desi aesthetics, generate festive desi captions (e.g., "chogada on repeat", "lehenga twirls", "nine nights of magic", "post-garba chai", "feeling desi").
Otherwise generate warm, aesthetic scrapbook polaroid captions and notes.

Return ONLY this JSON object:
{{
  "vibe_name": "2-4 words title",
  "mood_word": "one word",
  "tone": "light or dark",
  "slides": [
    {{"title": "1-4 words polaroid caption", "subtitle": "6-12 words note", "label": "1-2 words"}}
  ],
  "cover": {{"line1": "short word", "line2": "second word", "kicker": "2-4 words", "sub1": "3-6 words", "sub2": "3-6 words"}},
  "poster": {{"headline": "headline", "kicker": "kicker", "location": "location", "datetime": "datetime", "notes": ["note 1", "note 2", "note 3", "note 4"]}},
  "post_caption": "Instagram caption with emojis",
  "hashtags": ["tag1", "tag2", "tag3"]
}}"""

WORDS = ["moment", "daydream", "sunny", "cosy", "wander", "golden", "gentle", "bloom"]
CAPS = {"light": ["soft days", "good light", "just vibes", "memory lane", "golden hour", "no filter", "slow mornings", "little joys"],
        "dark": ["after dark", "quiet hours", "film roll", "late night", "still here", "frames", "neon haze", "midnight"]}
SUBS = ["Add your own words here", "Tell the story of this photo", "Something you love about this", "Make it yours"]
LABELS = ["idea", "mood", "tip", "fun", "calm", "cozy", "snack", "joy"]

NAVRATRI_CAPS = [
    "chogada on repeat",
    "lehenga twirls",
    "garba nights",
    "dandiya beats",
    "feeling desi",
    "nine nights",
    "post-garba chai",
    "ghoomar mood"
]
NAVRATRI_SUBS = [
    "garba nights and glowing festive lights ✨",
    "nine nights of sheer joy & jhumka swish 💃",
    "dandiya beats echoing in our hearts till 3 am 🪘",
    "post-garba discussions and sore happy feet ☕",
    "dressed up in nine yards of festive grace 🌸",
    "twirling into the golden festive hour 💫",
    "colors, beats and endless smiles 🌺",
    "little moments of magic under the stars 🌙"
]


def heuristic_vibe(images, n, family="scrapbook", hint=""):
    is_nav = any(w in hint.lower() for w in ["navratri", "garba", "dandiya", "desi", "chogada", "festive"])
    colors = extract_palette(images)
    av = sum(max(c) for c in colors) / len(colors) / 255
    sa = sum(sat(c) for c in colors) / len(colors)
    if is_nav:
        v = dict(vibe_name="Navratri Garba Nights", mood_word="festive", tone="dark", style="pichwai", font="hand", elements=["tape", "stars", "squiggle"])
    elif av < 0.40:
        v = dict(vibe_name="Moody Film", mood_word="nocturne", tone="dark", style="polaroid", font="mono", elements=["tape", "stars", "dots"])
    elif sa > 0.55:
        v = dict(vibe_name="Bold Pop", mood_word="electric", tone="light", style="polaroid", font="sans", elements=["stars", "circles", "squiggle"])
    else:
        v = dict(vibe_name="Soft Scrapbook", mood_word="daydream", tone="light", style="polaroid", font="hand", elements=["tape", "stars", "squiggle"])
    v["family"] = "scrapbook"
    return clean_vibe(v, n, hint)


def clean_vibe(raw, n, hint=""):
    is_nav = any(w in hint.lower() for w in ["navratri", "garba", "dandiya", "desi", "chogada", "festive"])
    tone = raw.get("tone") if raw.get("tone") in ("light", "dark") else ("dark" if is_nav else "light")
    raw_slides = [s for s in (raw.get("slides") or []) if isinstance(s, dict)]
    slides = []
    for i in range(n):
        s = raw_slides[i] if i < len(raw_slides) else {}
        fallback_title = NAVRATRI_CAPS[i % len(NAVRATRI_CAPS)] if is_nav else CAPS[tone][i % 8]
        fallback_sub = NAVRATRI_SUBS[i % len(NAVRATRI_SUBS)] if is_nav else SUBS[i % 4]
        title = str(s.get("title") or fallback_title).strip()
        slides.append({
            "title": title[:30],
            "subtitle": str(s.get("subtitle") or fallback_sub)[:90],
            "label": str(s.get("label") or ("moment" if is_nav else LABELS[i % 8]))[:16],
            "label2": str(s.get("label2") or LABELS[(i + 3) % 8])[:16]
        })
    c, p = raw.get("cover") or {}, raw.get("poster") or {}
    notes = [str(x)[:24] for x in (p.get("notes") or []) if str(x).strip()]
    if is_nav and not notes:
        notes = ["garba beats", "jhumka swish", "midnight chai", "twirl mode"]
    else:
        notes = (notes + ["your note", "add a detail", "something fun", "see you there"])[:4]
    word = str(raw.get("mood_word") or ("festive" if is_nav else "memories")).strip().split()[0][:16]
    default_name = "Navratri Garba Nights" if is_nav else "Aesthetic Scrapbook"
    return {
        "vibe_name": str(raw.get("vibe_name") or default_name)[:40],
        "mood_word": word,
        "tone": tone,
        "family": "scrapbook",
        "style": "pichwai" if is_nav else "polaroid",
        "font": "hand",
        "elements": ["tape", "stars", "squiggle"],
        "slides": slides,
        "cover": {
            "line1": str(c.get("line1") or ("NAVRATRI-" if is_nav else word[:max(3, len(word) // 2)] + "-"))[:14],
            "line2": str(c.get("line2") or ("DUMP" if is_nav else "MOOD"))[:14],
            "kicker": str(c.get("kicker") or (f"{n} festive nights" if is_nav else f"{n} memories"))[:30],
            "sub1": str(c.get("sub1") or ("garba beats & glowing lights" if is_nav else "flip through the story"))[:40],
            "sub2": str(c.get("sub2") or "swipe to twirl")[:40]
        },
        "poster": {
            "headline": str(p.get("headline") or (hint[:24] if hint else "NAVRATRI 2024"))[:30],
            "kicker": str(p.get("kicker") or "garba nights & glowing lights")[:36],
            "location": str(p.get("location") or "garba ground")[:40],
            "datetime": str(p.get("datetime") or "nine nights")[:40],
            "notes": notes
        },
        "post_caption": str(raw.get("post_caption") or ("nine nights of pure magic, garba beats & lehenga twirls ✨💃🪘" if is_nav else "")).strip(),
        "hashtags": [str(h).lstrip("#").strip() for h in (raw.get("hashtags") or (["navratri", "garbanights", "feelingdesi", "chogada", "festivevibes"] if is_nav else [])) if str(h).strip()][:5],
    }


def analyze_with_gemini(images, hint="", family="scrapbook", api_key=None, model=None):
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("no Gemini key (set GEMINI_API_KEY in .env)")
    candidate_models = [model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL), "gemini-flash-latest", "gemini-3.8-flash", "gemini-3.5-flash"]
    seen = set()
    models = [m for m in candidate_models if m and not (m in seen or seen.add(m))]
    
    parts = [{"text": PROMPT.format(n=len(images), hint=hint or "none")}]
    for im in images:
        small = im.convert("RGB")
        # 384x384 downsampling reduces vision token usage by 75% and uploads 10x faster!
        small.thumbnail((384, 384))
        buf = io.BytesIO()
        small.save(buf, "JPEG", quality=65)
        parts.append({"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}})

    last_err = None
    for m in models:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json={
                    "contents": [{"parts": parts}],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "temperature": 0.7,
                        "maxOutputTokens": 600
                    }
                },
                timeout=45
            )
            if r.ok:
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(txt)
            else:
                try:
                    last_err = r.json().get("error", {}).get("message", r.text)
                except Exception:
                    last_err = r.text
        except Exception as ex:
            last_err = str(ex)

    raise RuntimeError(f"Gemini API error: {last_err}")


def analyze_vibe(images, hint="", use_ai=True, family="auto"):
    """Returns (vibe, source). Never raises: falls back to a colour-based vibe."""
    n = len(images)
    if use_ai:
        try:
            v = clean_vibe(analyze_with_gemini(images, hint, family), n, hint)
            if family in FAMILIES:
                v["family"] = family
            return v, "Gemini"
        except Exception as e:
            return heuristic_vibe(images, n, family, hint), f"colour-based fallback ({e})"
    return heuristic_vibe(images, n, family, hint), "colour-based (AI off)"


# ============================================================ drawing primitives
def aa_layer(w, h, draw_fn, scale=3):
    layer = Image.new("RGBA", (max(1, int(w * scale)), max(1, int(h * scale))), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(layer), scale)
    return layer.resize((max(1, int(w)), max(1, int(h))), Image.LANCZOS)


def composite(canvas, layer, x, y):
    cw, ch = canvas.size
    x, y = int(x), int(y)
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + layer.width, cw), min(y + layer.height, ch)
    if x0 >= x1 or y0 >= y1:
        return
    canvas.alpha_composite(layer.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))


def put(canvas, layer, cx, cy, angle=0, base=(255, 255, 255)):
    if angle:
        layer = layer.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=(*base, 0))
    composite(canvas, layer, cx - layer.width / 2, cy - layer.height / 2)


def rounded_mask(size, r):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], r, fill=255)
    return m


def text_width(text, font, tracking=0):
    return font.getlength(text) if not tracking else sum(font.getlength(c) for c in text) + tracking * (len(text) - 1)


def wrap_text(text, font, max_w, tracking=0):
    lines = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split(" "):
            trial = (cur + " " + word).strip()
            if cur and text_width(trial, font, tracking) > max_w:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        lines.append(cur)
    return lines


def fit_size(text, kind, target_w, tracking=0, lo=40, hi=400):
    """Font size so the text (with absolute-px tracking) is about target_w wide."""
    per_px = sum(get_font(kind, 100).getlength(c) for c in text) / 100.0
    size = (target_w - tracking * (len(text) - 1)) / max(per_px, 0.01)
    return int(max(lo, min(hi, size)))


def star5(size, color, alpha=255):
    def fn(d, s):
        c, R = size * s / 2, size * s / 2 * 0.97
        pts = [(c + (R if k % 2 == 0 else R * 0.46) * math.cos(-math.pi / 2 + k * math.pi / 5),
                c + (R if k % 2 == 0 else R * 0.46) * math.sin(-math.pi / 2 + k * math.pi / 5)) for k in range(10)]
        d.polygon(pts, fill=(*color, alpha))
    return aa_layer(size, size, fn)


def sparkle(size, color, alpha=255):
    def fn(d, s):
        c, R = size * s / 2, size * s / 2 * 0.95
        pts = [(c + (R if k % 2 == 0 else R * 0.2) * math.cos(math.pi / 4 * k - math.pi / 2),
                c + (R if k % 2 == 0 else R * 0.2) * math.sin(math.pi / 4 * k - math.pi / 2)) for k in range(8)]
        d.polygon(pts, fill=(*color, alpha))
    return aa_layer(size, size, fn)


def ring(size, color, width=7, alpha=230, filled=False):
    def fn(d, s):
        if filled:
            d.ellipse([0, 0, size * s, size * s], fill=(*color, alpha))
        else:
            d.ellipse([width * s, width * s, (size - width) * s, (size - width) * s], outline=(*color, alpha), width=width * s)
    return aa_layer(size, size, fn)


def tape(w, h, color, alpha=190):
    def fn(d, s):
        steps, zig = 6, 9 * s
        pts = [(zig if k % 2 else 0, h * s * k / steps) for k in range(steps + 1)]
        pts += [(w * s - (zig if k % 2 else 0), h * s * k / steps) for k in range(steps, -1, -1)]
        d.polygon(pts, fill=(*color, alpha))
    return aa_layer(w, h, fn)


def squiggle(width, height, color, amp, wavelength, thick, alpha=210, phase=0.0):
    def fn(d, s):
        pts = [(x * s, (height / 2 + amp * math.sin(2 * math.pi * x / wavelength + phase)) * s) for x in range(0, int(width) + 1, 4)]
        d.line(pts, fill=(*color, alpha), width=int(thick * s), joint="curve")
    return aa_layer(width, height, fn, scale=2)


def dot_grid(cols, rows, gap, r, color, alpha=170):
    def fn(d, s):
        for i in range(cols):
            for j in range(rows):
                cx, cy = (i + 0.5) * gap * s, (j + 0.5) * gap * s
                d.ellipse([cx - r * s, cy - r * s, cx + r * s, cy + r * s], fill=(*color, alpha))
    return aa_layer(cols * gap, rows * gap, fn, scale=2)


def film_strip(width, height=64, hole=(235, 230, 220)):
    def fn(d, s):
        d.rectangle([0, 0, width * s, height * s], fill=(14, 14, 16, 238))
        for x in range(20, int(width), 64):
            d.rounded_rectangle([x * s, (height / 2 - 11) * s, (x + 26) * s, (height / 2 + 11) * s], 5 * s, fill=(*hole, 255))
    return aa_layer(width, height, fn, scale=2)


def arrow_layer(p0, p2, bend, width, color):
    """Hand-drawn curved arrow. Returns (layer, left, top) in canvas pixels."""
    (x1, y1), (x2, y2) = p0, p2
    mx, my, dx, dy = (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1
    ln = math.hypot(dx, dy) or 1
    cx, cy = mx - dy / ln * bend, my + dx / ln * bend
    m = 60
    left, top = min(x1, x2, cx) - m, min(y1, y2, cy) - m
    w, h = int(max(x1, x2, cx) - left + m), int(max(y1, y2, cy) - top + m)

    def fn(d, s):
        pts = []
        for k in range(61):
            t = k / 60
            pts.append(((((1 - t) ** 2 * x1 + 2 * (1 - t) * t * cx + t * t * x2) - left) * s,
                        (((1 - t) ** 2 * y1 + 2 * (1 - t) * t * cy + t * t * y2) - top) * s))
        d.line(pts, fill=(*color, 255), width=int(width * s), joint="curve")
        ang = math.atan2(y2 - cy, x2 - cx)
        for da in (0.5, -0.5):
            d.line([((x2 - left) * s, (y2 - top) * s),
                    ((x2 - left - 42 * math.cos(ang + da)) * s, (y2 - top - 42 * math.sin(ang + da)) * s)],
                   fill=(*color, 255), width=int(width * s))
    return aa_layer(w, h, fn, scale=2), left, top


def highlight_layer(w, h, thick, color, rng):
    pad = 30

    def fn(d, s):
        phi, pts = rng.uniform(0, 6), []
        for k in range(0, 135):
            t = k / 100 * 2 * math.pi
            pts.append(((pad + w / 2 + (w / 2) * (1 + 0.03 * math.sin(3 * t + phi)) * math.cos(t) - (1 - 0.5) * 0) * s,
                        (pad + h / 2 + (h / 2) * (1 + 0.04 * math.sin(2 * t + phi)) * math.sin(t)) * s))
        d.line(pts, fill=(*color, 255), width=int(thick * s), joint="curve")
    return aa_layer(w + 2 * pad, h + 2 * pad, fn, scale=2)


def torn_layer(W, h, color, jag, rng):
    pad = 50
    n = W // 6 + 2
    raw = [rng.uniform(-1, 1) for _ in range(n)]
    sm = [sum(raw[max(0, i - 3):i + 4]) / len(raw[max(0, i - 3):i + 4]) for i in range(n)]
    edge = [pad + sm[i] * jag * 2.2 + (rng.uniform(-jag, jag) * 0.6 if rng.random() < 0.18 else 0) for i in range(n)]
    pts = [(i * 6, edge[i]) for i in range(n)] + [(W + 6, h + pad), (0, h + pad)]
    layer = Image.new("RGBA", (W, h + pad), (*color, 0))
    ImageDraw.Draw(layer).polygon(pts, fill=(*color, 255))
    noise = np.array(Image.effect_noise(layer.size, 40), dtype=np.float32) - 128
    arr = np.array(layer, dtype=np.float32)
    arr[:, :, :3] = np.clip(arr[:, :, :3] + noise[:, :, None] * 0.18, 0, 255)
    return Image.fromarray(arr.astype("uint8"), "RGBA")


def scribble_layer(lines, kind, size, color, hatch, rng):
    font = get_font(kind, size)
    pad = 40
    lh = int(size * 1.0)
    w = int(max(text_width(l, font) for l in lines)) + 2 * pad
    h = lh * len(lines) + 2 * pad
    m = Image.new("L", (w, h), 0)
    dm = ImageDraw.Draw(m)
    for k, l in enumerate(lines):
        dm.text((w / 2, pad + k * lh), l, font=font, fill=255, anchor="ma")
    ring_band = ImageChops.subtract(m.filter(ImageFilter.MaxFilter(5)), m.filter(ImageFilter.MinFilter(9)))
    hat = Image.new("L", (w, h), 0)
    dh = ImageDraw.Draw(hat)
    for x in range(-h, w, hatch):
        dh.line([(x + rng.uniform(-3, 3), h), (x + h * 0.7 + rng.uniform(-3, 3), 0)], fill=255, width=max(3, hatch // 3))
    fill = ImageChops.multiply(m.filter(ImageFilter.MinFilter(5)), hat)
    alpha = ImageChops.lighter(ring_band, fill)
    layer = Image.new("RGBA", (w, h), (*color, 0))
    layer.putalpha(alpha)
    return layer


def caption_layer(text, width, kind, size, color, height=130, upper=False, shadow=False):
    text = text.upper() if upper else text
    font = get_font(kind, size)
    while font.getlength(text) > width - 44 and size > 16:
        size -= 2
        font = get_font(kind, size)
    m = Image.new("L", (width, height), 0)
    ImageDraw.Draw(m).text((width / 2, height / 2), text, font=font, fill=255, anchor="mm")
    layer = Image.new("RGBA", (width, height), (*color, 0))
    if shadow:
        sh = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        sh.putalpha(m.filter(ImageFilter.GaussianBlur(3)).point(lambda v: int(v * 0.55)))
        layer = Image.alpha_composite(layer, sh)
    top = Image.new("RGBA", (width, height), (*color, 0))
    top.putalpha(m)
    return Image.alpha_composite(layer, top)


def text_layer(el, theme, W):
    kind = resolve_font(el.get("font", "theme:body"), theme)
    size = int(el.get("size", 44))
    font = get_font(kind, size)
    color = resolve_color(el.get("color", "theme:text"), theme)
    text = str(el.get("text", ""))
    text = text.upper() if el.get("upper") else text
    track = int(el.get("tracking", 0))
    max_w = float(el.get("max_w", 0)) * W
    lines = wrap_text(text, font, max_w, track) if max_w else text.split("\n")
    lh = int(size * float(el.get("line_gap", 1.12)))
    widths = [text_width(l, font, track) for l in lines]
    bw, bh, pad = int(max(widths + [10])), lh * len(lines), 40
    m = Image.new("L", (bw + 2 * pad, bh + 2 * pad), 0)
    d = ImageDraw.Draw(m)
    align = el.get("align", "center")
    for k, (l, lw) in enumerate(zip(lines, widths)):
        x = pad if align == "left" else (pad + bw - lw if align == "right" else pad + (bw - lw) / 2)
        y = pad + k * lh
        if track:
            for ch in l:
                d.text((x, y), ch, font=font, fill=255)
                x += font.getlength(ch) + track
        else:
            d.text((x, y), l, font=font, fill=255)
    op = float(el.get("opacity", 1.0))
    layer = Image.new("RGBA", m.size, (*color, 0))
    if el.get("shadow"):
        sh = Image.new("RGBA", m.size, (0, 0, 0, 0))
        sh.putalpha(m.filter(ImageFilter.GaussianBlur(max(3, size // 22))).point(lambda v: int(v * 0.5 * op)))
        shifted = Image.new("RGBA", m.size, (0, 0, 0, 0))
        shifted.paste(sh, (0, max(2, size // 28)))
        layer = Image.alpha_composite(layer, shifted)
    top = Image.new("RGBA", m.size, (*color, 0))
    top.putalpha(m.point(lambda v: int(v * op)))
    return Image.alpha_composite(layer, top)


# ============================================================ photo helpers
def fit_photo(img, size, centering=(0.5, 0.4)):
    return ImageOps.fit(img.convert("RGB"), size, Image.LANCZOS, centering=centering)


def cover_crop(img, W, H, fx=0.5, fy=0.5, zoom=1.0):
    iw, ih = img.size
    scale = max(W / iw, H / ih) * max(zoom, 1.0)
    cw, ch = W / scale, H / scale
    cx, cy = min(max(fx * iw, cw / 2), iw - cw / 2), min(max(fy * ih, ch / 2), ih - ch / 2)
    return img.resize((W, H), Image.LANCZOS, box=(cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2))


FRAME_DIMS = {"polaroid": (660, 920, 0), "film": (640, 892, 100), "poster": (668, 848, 150), "minimal": (680, 880, 120), "pichwai": (652, 820, 0)}


def make_frame(photo, style, theme, caption, font_kind):
    t = {k: resolve_color(v, theme) for k, v in theme.items() if isinstance(v, str) and v.startswith("#")}
    if style == "polaroid":
        pw, ph, side, top, bottom = 600, 760, 30, 30, 130
        body = Image.new("RGBA", (pw + 2 * side, ph + top + bottom), (*t["paper"], 255))
        body.paste(fit_photo(photo, (pw, ph)), (side, top))
        body.putalpha(rounded_mask(body.size, 10))
        k = font_kind if font_kind != "serif" else "hand"
        body.alpha_composite(caption_layer(caption, body.width, k, 62 if k == "hand" else 34, t["text"], height=bottom), (0, top + ph))
        cap = None
    elif style == "film":
        pw, ph, side, tb = 580, 780, 30, 56
        body = Image.new("RGBA", (pw + 2 * side, ph + 2 * tb), (16, 16, 18, 255))
        body.paste(fit_photo(photo, (pw, ph)), (side, tb))
        d = ImageDraw.Draw(body)
        for x in range(24, body.width - 30, 54):
            for y in (17, body.height - 37):
                d.rounded_rectangle([x, y, x + 26, y + 20], 5, fill=(235, 230, 220, 255))
        body.putalpha(rounded_mask(body.size, 8))
        cap = caption_layer(caption, body.width, "mono", 32, t["text"], height=100, upper=True)
    elif style == "pichwai":
        pw, ph, side, top, bottom = 580, 740, 36, 36, 44
        crimson = (88, 11, 20, 255)
        gold = (214, 175, 65, 255)
        ivory = (255, 243, 218, 240)
        body = Image.new("RGBA", (pw + 2 * side, ph + top + bottom), crimson)
        d = ImageDraw.Draw(body)
        d.rectangle([4, 4, body.width - 5, body.height - 5], outline=gold, width=3)
        d.rectangle([12, 12, body.width - 13, body.height - 13], outline=ivory, width=2)
        for cx, cy in [(22, 22), (body.width - 23, 22), (22, body.height - 23), (body.width - 23, body.height - 23)]:
            d.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], fill=gold)
            d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=(226, 67, 88, 255))
        for x in range(36, body.width - 40, 28):
            d.line([(x, 8), (x + 14, 8)], fill=ivory, width=1)
            d.line([(x, body.height - 9), (x + 14, body.height - 9)], fill=ivory, width=1)
        for y in range(36, body.height - 40, 28):
            d.line([(8, y), (8, y + 14)], fill=ivory, width=1)
            d.line([(body.width - 9, y), (body.width - 9, y + 14)], fill=ivory, width=1)
        body.paste(fit_photo(photo, (pw, ph)), (side, top))
        d.rectangle([side - 2, top - 2, side + pw + 1, top + ph + 1], outline=gold, width=2)
        body.putalpha(rounded_mask(body.size, 10))
        cap = None
    elif style == "poster":
        pw, ph, off = 640, 820, 28
        body = Image.new("RGBA", (pw + off, ph + off), (0, 0, 0, 0))
        ImageDraw.Draw(body).rectangle([off, off, pw + off, ph + off], fill=(*t["accent"], 255))
        body.paste(fit_photo(photo, (pw, ph)), (0, 0))
        cap = caption_layer(caption, body.width, "sans_bold", 56, t["text"], height=150, upper=True)
    else:
        body = fit_photo(photo, (680, 880)).convert("RGBA")
        body.putalpha(rounded_mask(body.size, 44))
        k = font_kind if font_kind != "hand" else "serif"
        cap = caption_layer(caption, body.width, k, 46 if k == "serif" else 36, t["text"], height=120)
    pad, cap_h = 70, (cap.height if cap else 0)
    canvas = Image.new("RGBA", (body.width + 2 * pad, body.height + cap_h + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", body.size, (0, 0, 0, 0))
    sh.putalpha(body.getchannel("A").point(lambda v: int(v * 0.30)))
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow.paste(sh, (pad, pad + 16))
    canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(20)))
    composite(canvas, body, pad, pad)
    if cap:
        composite(canvas, cap, pad, pad + body.height)
    return canvas


def make_inset(photo, w, label, label_color, theme):
    h, b = int(w * 1.25), max(5, w // 28)
    body = Image.new("RGBA", (w + 2 * b, h + 2 * b), (255, 255, 255, 255))
    body.paste(fit_photo(photo, (w, h)), (b, b))
    cap = caption_layer(label, w + 2 * b + 60, "sans_bold", max(18, w // 8), label_color, height=int(w * 0.28), shadow=True)
    pad = 36
    canvas = Image.new("RGBA", (cap.width + 2 * pad, body.height + cap.height + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", body.size, (0, 0, 0, 0))
    sh.putalpha(body.getchannel("A").point(lambda v: int(v * 0.35)))
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow.paste(sh, ((canvas.width - body.width) // 2, pad + 6))
    canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(8)))
    composite(canvas, body, (canvas.width - body.width) // 2, pad)
    composite(canvas, cap, 0, pad + body.height - 4)
    return canvas


def draw_lotus_shape(d, s, cx, cy, w, h):
    pink_dark = (195, 35, 75, 255)
    pink_mid = (235, 75, 115, 255)
    pink_light = (255, 160, 190, 255)
    green = (55, 120, 65, 255)
    gold = (245, 195, 60, 255)

    # Base leaves
    d.polygon([(cx, cy + h * 0.35), (cx - w * 0.45, cy + h * 0.25), (cx - w * 0.2, cy + h * 0.45)], fill=green)
    d.polygon([(cx, cy + h * 0.35), (cx + w * 0.45, cy + h * 0.25), (cx + w * 0.2, cy + h * 0.45)], fill=green)
    d.line([(cx, cy + h * 0.35), (cx, cy + h * 0.48)], fill=green, width=int(2 * s))

    # Outer back petals
    d.polygon([(cx, cy + h * 0.2), (cx - w * 0.45, cy - h * 0.15), (cx - w * 0.35, cy - h * 0.35), (cx - w * 0.1, cy - h * 0.1)], fill=pink_dark)
    d.polygon([(cx, cy + h * 0.2), (cx + w * 0.45, cy - h * 0.15), (cx + w * 0.35, cy - h * 0.35), (cx + w * 0.1, cy - h * 0.1)], fill=pink_dark)

    # Middle petals
    d.polygon([(cx, cy + h * 0.25), (cx - w * 0.35, cy), (cx - w * 0.25, cy - h * 0.4), (cx, cy - h * 0.1)], fill=pink_mid)
    d.polygon([(cx, cy + h * 0.25), (cx + w * 0.35, cy), (cx + w * 0.25, cy - h * 0.4), (cx, cy - h * 0.1)], fill=pink_mid)

    # Center main petal
    d.polygon([(cx, cy + h * 0.25), (cx - w * 0.18, cy - h * 0.1), (cx, cy - h * 0.48), (cx + w * 0.18, cy - h * 0.1)], fill=pink_mid)
    d.polygon([(cx, cy + h * 0.2), (cx - w * 0.1, cy - h * 0.05), (cx, cy - h * 0.38), (cx + w * 0.1, cy - h * 0.05)], fill=pink_light)
    d.ellipse([(cx - w * 0.15, cy + h * 0.15), (cx + w * 0.15, cy + h * 0.32)], fill=gold)


def draw_jhumka_shape(d, s, cx, cy, sz):
    gold = (225, 175, 55, 255)
    gold_dark = (175, 125, 30, 255)
    ruby = (215, 35, 60, 255)
    pearl = (255, 245, 230, 255)

    r_stud = sz * 0.22
    y_stud = cy - sz * 0.38
    d.ellipse([(cx - r_stud, y_stud - r_stud), (cx + r_stud, y_stud + r_stud)], fill=gold)
    d.ellipse([(cx - r_stud * 0.55, y_stud - r_stud * 0.55), (cx + r_stud * 0.55, y_stud + r_stud * 0.55)], fill=ruby)

    y_bell = cy + sz * 0.05
    w_bell = sz * 0.75
    h_bell = sz * 0.45
    pts = [(cx - w_bell * 0.5, y_bell + h_bell), (cx - w_bell * 0.45, y_bell), (cx, y_bell - h_bell * 0.4),
           (cx + w_bell * 0.45, y_bell), (cx + w_bell * 0.5, y_bell + h_bell)]
    d.polygon(pts, fill=gold)
    d.line(pts, fill=gold_dark, width=int(2 * s))
    d.line([(cx - w_bell * 0.5, y_bell + h_bell), (cx + w_bell * 0.5, y_bell + h_bell)], fill=ruby, width=int(3 * s))

    n_pearls = 7
    for k in range(n_pearls):
        px = cx - w_bell * 0.42 + (w_bell * 0.84 / (n_pearls - 1)) * k
        py = y_bell + h_bell + sz * 0.15
        d.line([(px, y_bell + h_bell), (px, py)], fill=gold, width=int(2 * s))
        d.ellipse([(px - sz * 0.05, py - sz * 0.05), (px + sz * 0.05, py + sz * 0.05)], fill=pearl)


def draw_chai_shape(d, s, cx, cy, sz):
    glass_col = (255, 255, 255, 160)
    chai_col = (195, 115, 50, 245)
    chai_milk = (235, 175, 120, 245)

    w_top = sz * 0.5
    w_bot = sz * 0.35
    h_glass = sz * 0.75
    y_top = cy - h_glass * 0.4
    y_bot = cy + h_glass * 0.5

    glass_pts = [(cx - w_top / 2, y_top), (cx + w_top / 2, y_top), (cx + w_bot / 2, y_bot), (cx - w_bot / 2, y_bot)]
    d.polygon(glass_pts, fill=(240, 240, 240, 70))

    y_chai = y_top + h_glass * 0.18
    w_chai = w_top - (w_top - w_bot) * 0.18
    chai_pts = [(cx - w_chai / 2, y_chai), (cx + w_chai / 2, y_chai), (cx + w_bot / 2 - 2 * s, y_bot - 4 * s), (cx - w_bot / 2 + 2 * s, y_bot - 4 * s)]
    d.polygon(chai_pts, fill=chai_col)
    d.ellipse([(cx - w_chai / 2, y_chai - 5 * s), (cx + w_chai / 2, y_chai + 5 * s)], fill=chai_milk)

    for fx in [-0.2, 0, 0.2]:
        d.line([(cx + w_top * fx, y_top + 4 * s), (cx + w_bot * fx, y_bot - 4 * s)], fill=glass_col, width=int(2 * s))

    d.arc([(cx - 15 * s, y_top - 25 * s), (cx + 5 * s, y_top - 5 * s)], 180, 360, fill=(255, 255, 255, 180), width=int(2 * s))
    d.arc([(cx - 5 * s, y_top - 38 * s), (cx + 15 * s, y_top - 18 * s)], 0, 180, fill=(255, 255, 255, 180), width=int(2 * s))


def draw_mojri_shape(d, s, cx, cy, sz):
    maroon = (130, 20, 35, 255)
    gold = (230, 185, 65, 255)

    for ox, oy, rot in [(-sz * 0.15, -sz * 0.1, -25), (sz * 0.12, sz * 0.1, 15)]:
        rad = math.radians(rot)
        cos_r, sin_r = math.cos(rad), math.sin(rad)
        pts = [
            (-sz * 0.35, -sz * 0.12), (sz * 0.35, -sz * 0.18), (sz * 0.48, 0),
            (sz * 0.35, sz * 0.18), (-sz * 0.35, sz * 0.12), (-sz * 0.42, 0)
        ]
        tf_pts = [(cx + ox + (px * cos_r - py * sin_r), cy + oy + (px * sin_r + py * cos_r)) for px, py in pts]
        d.polygon(tf_pts, fill=maroon)
        d.line(tf_pts + [tf_pts[0]], fill=gold, width=int(2 * s))
        d.line([(cx + ox - 5 * s, cy + oy), (cx + ox + 5 * s, cy + oy)], fill=gold, width=int(2 * s))


def draw_rickshaw_shape(d, s, cx, cy, sz):
    yellow = (245, 195, 45, 255)
    green = (35, 135, 80, 255)
    black = (30, 30, 35, 255)
    glass = (220, 240, 250, 220)

    w, h = sz * 0.85, sz * 0.75
    hood = [(cx - w * 0.45, cy - h * 0.2), (cx - w * 0.3, cy - h * 0.5), (cx + w * 0.35, cy - h * 0.5), (cx + w * 0.45, cy - h * 0.2)]
    d.polygon(hood, fill=yellow)

    wind = [(cx - w * 0.42, cy - h * 0.2), (cx + w * 0.42, cy - h * 0.2), (cx + w * 0.38, cy + h * 0.05), (cx - w * 0.38, cy + h * 0.05)]
    d.polygon(wind, fill=glass)

    body = [(cx - w * 0.45, cy + h * 0.05), (cx + w * 0.45, cy + h * 0.05), (cx + w * 0.4, cy + h * 0.35), (cx - w * 0.4, cy + h * 0.35)]
    d.polygon(body, fill=green)
    d.ellipse([(cx - w * 0.1, cy + h * 0.12), (cx + w * 0.1, cy + h * 0.32)], fill=yellow)
    d.ellipse([(cx - w * 0.42, cy + h * 0.25), (cx - w * 0.2, cy + h * 0.52)], fill=black)
    d.ellipse([(cx + w * 0.2, cy + h * 0.25), (cx + w * 0.42, cy + h * 0.52)], fill=black)


def draw_dandiya_shape(d, s, cx, cy, sz):
    gold = (235, 185, 60, 255)
    red = (215, 45, 65, 255)
    blue = (40, 130, 210, 255)

    for da in [-35, 35]:
        rad = math.radians(da)
        c, sn = math.cos(rad), math.sin(rad)
        p1 = (cx - sz * 0.45 * c, cy - sz * 0.45 * sn)
        p2 = (cx + sz * 0.45 * c, cy + sz * 0.45 * sn)
        d.line([p1, p2], fill=gold, width=int(8 * s))
        d.line([(cx - sz * 0.15 * c, cy - sz * 0.15 * sn), (cx + sz * 0.15 * c, cy + sz * 0.15 * sn)], fill=red, width=int(8 * s))
        d.line([(cx - sz * 0.05 * c, cy - sz * 0.05 * sn), (cx + sz * 0.05 * c, cy + sz * 0.05 * sn)], fill=blue, width=int(8 * s))


def draw_diya_shape(d, s, cx, cy, sz):
    clay = (185, 75, 45, 255)
    gold = (245, 195, 60, 255)
    flame_orange = (255, 140, 25, 255)
    flame_yellow = (255, 235, 80, 255)

    d.chord([(cx - sz * 0.4, cy - sz * 0.1), (cx + sz * 0.4, cy + sz * 0.4)], 0, 180, fill=clay)
    d.ellipse([(cx - sz * 0.35, cy - sz * 0.12), (cx + sz * 0.35, cy + sz * 0.08)], fill=gold)

    flame_pts = [(cx, cy - sz * 0.45), (cx + sz * 0.16, cy - sz * 0.12), (cx, cy), (cx - sz * 0.16, cy - sz * 0.12)]
    d.polygon(flame_pts, fill=flame_orange)
    flame_core = [(cx, cy - sz * 0.38), (cx + sz * 0.09, cy - sz * 0.12), (cx, cy - sz * 0.02), (cx - sz * 0.09, cy - sz * 0.12)]
    d.polygon(flame_core, fill=flame_yellow)


def make_music_player(title="Tere Chehre Se Nazar Nahin", artist="Lata Mangeshkar, Kishore Kumar", current="2:57", total="5:02", width=460, height=130):
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    card = Image.new("RGBA", (width, height), (24, 12, 14, 238))
    mask = rounded_mask((width, height), 16)
    card.putalpha(mask)
    canvas = Image.alpha_composite(canvas, card)
    d = ImageDraw.Draw(canvas)
    
    t_font = get_font("sans_bold", 20)
    a_font = get_font("sans", 15)
    d.text((20, 18), title[:30], font=t_font, fill=(255, 255, 255, 245))
    d.text((20, 46), artist[:34], font=a_font, fill=(210, 195, 195, 200))
    
    # Clean vector heart icon
    hx, hy = width - 32, 26
    d.arc([(hx - 10, hy - 8), (hx, hy + 2)], 180, 0, fill=(240, 220, 220, 220), width=2)
    d.arc([(hx, hy - 8), (hx + 10, hy + 2)], 180, 0, fill=(240, 220, 220, 220), width=2)
    d.line([(hx - 10, hy - 3), (hx, hy + 8)], fill=(240, 220, 220, 220), width=2)
    d.line([(hx + 10, hy - 3), (hx, hy + 8)], fill=(240, 220, 220, 220), width=2)
    
    bar_y = 80
    d.line([(20, bar_y), (width - 20, bar_y)], fill=(120, 80, 85, 180), width=4)
    prog_x = int(20 + (width - 40) * 0.58)
    d.line([(20, bar_y), (prog_x, bar_y)], fill=(255, 255, 255, 240), width=4)
    d.ellipse([(prog_x - 5, bar_y - 5), (prog_x + 5, bar_y + 5)], fill=(255, 255, 255, 255))
    
    s_font = get_font("mono", 12)
    d.text((20, 96), current, font=s_font, fill=(190, 175, 175, 190))
    d.text((width - 20, 96), total, font=s_font, fill=(190, 175, 175, 190), anchor="ra")
    
    cx, cy = width // 2, 102
    d.ellipse([(cx - 15, cy - 15), (cx + 15, cy + 15)], fill=(255, 255, 255, 250))
    d.polygon([(cx - 4, cy - 6), (cx - 4, cy + 6), (cx + 5, cy)], fill=(20, 10, 12, 255))
    d.polygon([(cx - 38, cy - 5), (cx - 38, cy + 5), (cx - 44, cy)], fill=(230, 220, 220, 230))
    d.polygon([(cx + 38, cy - 5), (cx + 38, cy + 5), (cx + 44, cy)], fill=(230, 220, 220, 230))
    return canvas


def make_feeling_desi_badge(width=280, height=130):
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    card = Image.new("RGBA", (width - 16, height - 16), (248, 240, 226, 255))
    d_card = ImageDraw.Draw(card)
    d_card.rectangle([3, 3, card.width - 4, card.height - 4], outline=(160, 120, 100, 120), width=1)
    
    # Vector lotus above script
    draw_lotus_shape(d_card, 1, card.width // 2, 22, 28, 26)
    
    d_card.text((card.width // 2, 56), "Feeling", font=get_font("hand", 36), fill=(70, 15, 20, 255), anchor="mm")
    d_card.text((card.width // 2, 90), "DESI", font=get_font("sans_bold", 28), fill=(180, 20, 30, 255), anchor="mm")
    card.putalpha(rounded_mask(card.size, 8))
    
    pad = 8
    canvas.paste(card, (pad, pad))
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sh.paste(card.getchannel("A").point(lambda v: int(v * 0.25)), (pad + 1, pad + 3))
    return Image.alpha_composite(sh.filter(ImageFilter.GaussianBlur(6)), canvas)


def make_desi_sticker(kind="lotus", size=130):
    def fn(d, s):
        cx, cy = (size * s) / 2, (size * s) / 2
        sz = size * s * 0.85
        if kind == "lotus":
            draw_lotus_shape(d, s, cx, cy, sz * 0.55, sz * 0.55)
        elif kind == "jhumka":
            draw_jhumka_shape(d, s, cx, cy, sz)
        elif kind == "mojri":
            draw_mojri_shape(d, s, cx, cy, sz)
        elif kind in ("mehndi_chai", "chai"):
            draw_chai_shape(d, s, cx, cy, sz)
        elif kind == "rickshaw":
            draw_rickshaw_shape(d, s, cx, cy, sz)
        elif kind == "dandiya":
            draw_dandiya_shape(d, s, cx, cy, sz)
        elif kind == "diya":
            draw_diya_shape(d, s, cx, cy, sz)
        else:
            draw_lotus_shape(d, s, cx, cy, sz * 0.55, sz * 0.55)

    return aa_layer(size, size, fn)


def make_lotus_border(width, height=74):
    canvas = Image.new("RGBA", (width, height), (198, 152, 48, 255))
    d = ImageDraw.Draw(canvas)
    step = 64
    for x in range(0, width, step):
        d.rectangle([x, 0, x + step - 2, height], outline=(150, 110, 30, 255), width=1)
        cx = x + step // 2
        cy = height // 2
        draw_lotus_shape(d, 1, cx, cy, 32, 30)
    d.line([(0, 0), (width, 0)], fill=(255, 240, 200, 240), width=2)
    d.line([(0, height - 1), (width, height - 1)], fill=(255, 240, 200, 240), width=2)
    return canvas


# ============================================================ backgrounds
def gradient(w, h, c1, c2, horizontal_weight):
    x = np.linspace(0, 1, w)[None, :, None]
    y = np.linspace(0, 1, h)[:, None, None]
    tt = np.clip(x * horizontal_weight + y * (1 - horizontal_weight), 0, 1)
    return np.array(c1) * (1 - tt) + np.array(c2) * tt


def make_background(W, H, n, theme, mode, rng, flip=False):
    c1, c2 = resolve_color("theme:bg1", theme), resolve_color("theme:bg2", theme)
    acc, sec = resolve_color("theme:accent", theme), resolve_color("theme:second", theme)
    total = W * n
    arr = gradient(total, H, c1, c2, 0.88) if mode == "continuous" else gradient(W, H, *((c2, c1) if flip else (c1, c2)), 0.1)
    width = total if mode == "continuous" else W
    img = Image.fromarray(arr.astype("uint8"), "RGB").convert("RGBA")
    blobs = Image.new("RGBA", (width // 4, H // 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(blobs)
    for i in range(max(3, 3 * (n if mode == "continuous" else 1))):
        x = rng.uniform(0, width) if mode == "continuous" else rng.uniform(80, width - 80)
        y, r = rng.uniform(0, H), rng.uniform(150, 300)
        col = rng.choice([acc, sec])
        if theme.get("tone") == "light":
            col = mix(col, (255, 255, 255), 0.38)
        d.ellipse([(x - r) / 4, (y - r) / 4, (x + r) / 4, (y + r) / 4], fill=(*col, 85))
    return Image.alpha_composite(img, blobs.filter(ImageFilter.GaussianBlur(34)).resize((width, H), Image.BICUBIC))


def draw_slide_bg(slide, i, W, H, theme, images, seed):
    bg = slide.get("bg", {"mode": "gradient"})
    mode = bg.get("mode", "gradient")
    nimg = len(images)
    if mode == "gradient":
        return make_background(W, H, 1, theme, "separate", random.Random(seed + i), flip=bool(i % 2))
    if mode == "collage":
        canvas = Image.new("RGB", (W, H), (20, 20, 22))
        photos = (bg.get("photos") or [0, 1, 2, 3])[:4]
        photos = (photos + photos * 4)[:4]
        gap = int(bg.get("gap", 5))
        cw, ch = (W - gap) // 2, (H - gap) // 2
        for k, p in enumerate(photos):
            cell = cover_crop(images[p % nimg].convert("RGB"), cw, ch, 0.5, 0.45)
            canvas.paste(cell, ((k % 2) * (cw + gap), (k // 2) * (ch + gap)))
        out = canvas.convert("RGBA")
    else:
        photo = images[int(bg.get("photo", 0)) % nimg].convert("RGB")
        out = cover_crop(photo, W, H, float(bg.get("fx", 0.5)), float(bg.get("fy", 0.5)), float(bg.get("zoom", 1.0))).convert("RGBA")
    dim = float(bg.get("dim", 0.0))
    if dim > 0:
        out = Image.alpha_composite(out, Image.new("RGBA", out.size, (0, 0, 0, int(255 * dim))))
    return out


# ============================================================ element drawing
def draw_element(canvas, el, ox, W, H, theme, images, seed):
    t = el["type"]
    X, Y = ox + float(el.get("x", 0.5)) * W, float(el.get("y", 0.5)) * H
    rot = float(el.get("rotate", 0))
    rng = random.Random(zlib.crc32(f"{seed}{el.get('id', '')}".encode()))
    col = resolve_color(el.get("color", "theme:accent"), theme)
    nimg = len(images)
    if t == "text":
        put(canvas, text_layer(el, theme, W), X, Y, rot, base=resolve_color(el.get("color", "theme:text"), theme))
    elif t == "scribble":
        lines = str(el.get("text", "")).split("\n")
        put(canvas, scribble_layer(lines, resolve_font(el.get("font", "chunky"), theme), int(el.get("size", 200)), col,
                                   int(el.get("hatch", 11)), rng), X, Y, rot, base=col)
    elif t == "star":
        fn = star5 if el.get("shape", "star5") == "star5" else sparkle
        put(canvas, fn(int(el.get("size", 60)), col), X, Y, rot, base=col)
    elif t == "inset":
        label_color = resolve_color(el.get("color", "theme:note"), theme)
        put(canvas, make_inset(images[int(el.get("photo", 0)) % nimg], int(el.get("w", 190)), str(el.get("label", "")), label_color, theme),
            X, Y, rot)
    elif t == "frame":
        frame = make_frame(images[int(el.get("photo", 0)) % nimg], el.get("style", "polaroid"), theme, str(el.get("caption", "")),
                           el.get("font", "serif"))
        put(canvas, frame, X, Y, rot)
    elif t == "tape":
        put(canvas, tape(int(el.get("w", 210)), int(el.get("h", 58)), col, int(el.get("alpha", 190))), X, Y, rot, base=col)
    elif t == "squiggle":
        put(canvas, squiggle(int(float(el.get("span", 1)) * W), int(el.get("amp", 55)) * 2 + 80, col, int(el.get("amp", 55)),
                             int(el.get("wavelength", 420)), int(el.get("thick", 11)), phase=float(el.get("phase", 0))), X, Y, rot, base=col)
    elif t == "ring":
        put(canvas, ring(int(el.get("size", 160)), col, int(el.get("thick", 7)), int(el.get("alpha", 220)), bool(el.get("filled"))),
            X, Y, rot, base=col)
    elif t == "dots":
        put(canvas, dot_grid(int(el.get("cols", 6)), int(el.get("rows", 4)), int(el.get("gap", 30)), int(el.get("r", 5)), col), X, Y, rot, base=col)
    elif t == "film_strip":
        put(canvas, film_strip(int(float(el.get("span", 1)) * W)), X, Y)
    elif t == "arrow":
        layer, left, top = arrow_layer((X, Y), (ox + float(el.get("x2", 0.5)) * W, float(el.get("y2", 0.5)) * H),
                                       float(el.get("bend", 80)), int(el.get("width", 7)), col)
        composite(canvas, layer, left, top)
    elif t == "highlight":
        put(canvas, highlight_layer(int(el.get("w", 300)), int(el.get("h", 110)), int(el.get("thick", 7)), col, rng), X, Y, rot, base=col)
    elif t == "torn":
        h = int(el.get("h", 300))
        composite(canvas, torn_layer(W, h, col, int(el.get("jag", 14)), rng), ox, Y - 50)
    elif t == "music_player":
        player = make_music_player(
            title=str(el.get("title", "Chogada - Loveyatri")),
            artist=str(el.get("artist", "Darshan Raval, Asees Kaur")),
            current=str(el.get("current", "2:57")),
            total=str(el.get("total", "5:02")),
            width=int(el.get("w", 480)),
            height=int(el.get("h", 136))
        )
        put(canvas, player, X, Y, rot)
    elif t == "desi_badge":
        badge = make_feeling_desi_badge(int(el.get("w", 280)), int(el.get("h", 130)))
        put(canvas, badge, X, Y, rot)
    elif t == "desi_sticker":
        stk = make_desi_sticker(el.get("kind", "lotus"), int(el.get("size", 130)))
        put(canvas, stk, X, Y, rot)
    elif t == "lotus_border":
        lb = make_lotus_border(W, int(el.get("h", 72)))
        composite(canvas, lb, ox, int(Y))


def overlays(img, i, n, spec, theme, on_photo):
    g = spec["global"]
    W, H = img.size
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    ink = (255, 255, 255) if on_photo else resolve_color("theme:text", theme)
    is_nav = any(el.get("type") == "lotus_border" for s in spec.get("slides", []) for el in s.get("elements", []))
    low = 100 if spec.get("film") else (55 if is_nav else 0)
    if g.get("counter", True) and not (i == 0 and is_nav):
        d.text((W - 64, 62 + low), f"{i + 1:02d} / {n:02d}", font=get_font("mono", 30), fill=(*ink, 200), anchor="ra")
    if i == 0 and g.get("swipe", True):
        ax, ay = W - 64, H - 90 - low
        d.text((ax - 100, ay), "swipe", font=get_font("hand", 58), fill=(*ink, 230), anchor="rm")
        d.line([(ax - 84, ay), (ax, ay)], fill=(*ink, 230), width=5)
        d.line([(ax - 20, ay - 17), (ax, ay)], fill=(*ink, 230), width=5)
        d.line([(ax - 20, ay + 17), (ax, ay)], fill=(*ink, 230), width=5)
    return Image.alpha_composite(img.convert("RGBA"), over)


def add_grain(img):
    W, H = img.size
    noise = np.array(Image.effect_noise((W, H), 30), dtype=np.float32) - 128
    return Image.fromarray(np.clip(np.array(img.convert("RGB"), dtype=np.float32) + noise[:, :, None] * 0.22, 0, 255).astype("uint8"))


def render_spec(spec, images, only=None):
    """Returns the list of RGB slides. For separate layouts, `only=i` renders just that slide."""
    W, H = spec["size"]
    slides, theme, seed = spec["slides"], spec["theme"], spec["global"].get("seed", 0)
    n = len(slides)
    images = [ImageOps.exif_transpose(im).convert("RGB") for im in images]
    out = []
    if spec["mode"] == "continuous":
        pano = make_background(W, H, n, theme, "continuous", random.Random(seed))
        items = sorted(((el.get("z", 1), i, j, el) for i, sl in enumerate(slides) for j, el in enumerate(sl["elements"])),
                       key=lambda x: (x[0], x[1], x[2]))
        for _, i, _, el in items:
            draw_element(pano, el, i * W, W, H, theme, images, seed)
        for i in range(n):
            s = pano.crop((i * W, 0, (i + 1) * W, H)).convert("RGB")
            if spec["global"].get("grain"):
                s = add_grain(s)
            out.append(overlays(s, i, n, spec, theme, False).convert("RGB"))
        return out
    for i, sl in enumerate(slides):
        if only is not None and i != only:
            out.append(None)
            continue
        canvas = draw_slide_bg(sl, i, W, H, theme, images, seed)
        for _, _, el in sorted(((e.get("z", 1), j, e) for j, e in enumerate(sl["elements"])), key=lambda x: (x[0], x[1])):
            draw_element(canvas, el, 0, W, H, theme, images, seed + i)
        s = canvas.convert("RGB")
        if spec["global"].get("grain"):
            s = add_grain(s)
        out.append(overlays(s, i, n, spec, theme, sl.get("bg", {}).get("mode") in ("photo", "collage")).convert("RGB"))
    return out


def stitch(slides, gap=0):
    w, h = slides[0].size
    out = Image.new("RGB", (len(slides) * w + gap * (len(slides) - 1), h), (255, 255, 255))
    for i, s in enumerate(slides):
        out.paste(s, (i * (w + gap), 0))
    return out


# ============================================================ building the first spec
def E(type_, **kw):
    kw.update(type=type_, id=uuid.uuid4().hex[:6])
    kw.setdefault("z", 1)
    return kw


def new_spec(size, mode, theme, grain, family, n):
    return {"size": list(size), "mode": mode, "family": family, "theme": theme,
            "global": {"seed": 0, "grain": grain, "counter": True, "swipe": True},
            "slides": [{"bg": {"mode": "gradient"}, "elements": []} for _ in range(n)]}


def build_spec(images, vibe, family=None, mode="separate", size=(1080, 1350), seed=0, cover=True):
    # Strictly enforce scrapbook aesthetic for this editor
    spec = build_scrapbook(images, vibe, mode, size, seed, cover)
    spec["global"]["seed"] = seed
    return spec


def build_classic(images, vibe, mode, size, seed, cover=True):
    W, H = size
    n = len(images)
    rng = random.Random(seed)
    cont = mode == "continuous"
    theme = make_theme(extract_palette(images), vibe["tone"])
    style, els = vibe["style"], list(vibe["elements"])
    if style == "film" and "film_border" not in els:
        els.append("film_border")
    spec = new_spec(size, mode, theme, vibe["tone"] == "dark" or style == "film", "classic", n)
    spec["film"] = "film_border" in els
    sl = spec["slides"]

    def add(i, el):
        sl[min(max(i, 0), n - 1)]["elements"].append(el)

    def place(xabs):  # absolute (in slide widths) -> (slide index, x inside that slide)
        i = min(max(int(xabs), 0), n - 1)
        return i, xabs - i

    if cont:
        word = vibe["mood_word"].upper() if style in ("poster", "film") else vibe["mood_word"]
        kind = "sans_bold" if style == "poster" else "serif_italic"
        px = max(60, min(int(200 * W * n * 0.92 / max(get_font(kind, 200).getlength(word), 1)), int(H * 0.6)))
        add(0, E("text", text=word, font=kind, size=px, color="theme:text", x=n / 2, y=0.5, opacity=0.10, z=0))
    if "film_border" in els:
        for i in ([0] if cont else range(n)):
            span = n if cont else 1
            add(i, E("film_strip", span=span, x=span / 2, y=32 / H, z=0))
            add(i, E("film_strip", span=span, x=span / 2, y=(H - 32) / H, z=0))
    if "squiggle" in els:
        if cont:
            add(0, E("squiggle", span=n, x=n / 2, y=0.52, amp=70, wavelength=760, thick=12, color="theme:accent", z=0))
        else:
            for i in range(n):
                add(i, E("squiggle", span=1, x=0.5, y=0.5 + rng.uniform(-0.19, 0.19), amp=55, wavelength=420, thick=11,
                         phase=round(rng.uniform(0, 6), 2), color="theme:accent", z=0))
    if "circles" in els:
        for k in range(n * 2):
            xa = rng.uniform(0, n) if cont else (k % n) + rng.uniform(0.07, 0.93)
            i, xr = place(xa)
            add(i, E("ring", size=rng.randint(120, 260), x=xr, y=rng.uniform(0.11, 0.89), color=rng.choice(["theme:accent", "theme:second"]),
                     filled=rng.random() < 0.4, alpha=110 if rng.random() < 0.5 else 200, z=0))
    if "dots" in els:
        for i in range(n):
            add(i, E("dots", x=rng.choice([170, W - 170]) / W, y=rng.choice([170, H - 190]) / H, cols=6, rows=4, gap=30, r=5,
                     color="theme:accent" if i % 2 else "theme:second", z=0))
    if "stars" in els:
        for k in range(n * 4):
            xa = rng.uniform(0.04, n - 0.04) if cont else rng.randint(0, n - 1) + rng.uniform(0.05, 0.95)
            i, xr = place(xa)
            add(i, E("star", shape="sparkle4", size=rng.randint(34, 90), x=xr, y=rng.uniform(0.07, 0.93), rotate=rng.randint(-15, 15),
                     color=rng.choice(["theme:accent", "#ffffff"]), z=0))
    bw, bh, cap = FRAME_DIMS[style]
    fw, fh = bw + 140, bh + cap + 140
    for i in range(n):
        if cont:
            shift = 0.17 if (i % 2 == 0 and i + 1 < n) else (-0.17 if i % 2 == 1 else 0)
            cx, cy = 0.5 + shift, 0.5 + (-34 if i % 2 == 0 else 34) / H
            ang = (-2.5 if i % 2 == 0 else 2.5) + rng.uniform(-1, 1)
        else:
            cx, cy, ang = 0.5, 0.5 + (-20 + rng.uniform(-18, 18)) / H, rng.uniform(-3.5, 3.5)
        add(i, E("frame", photo=i, style=style, caption=vibe["slides"][i]["title"], font=vibe["font"], x=cx, y=cy, rotate=round(ang, 1)))
        if "tape" in els and style in ("polaroid", "minimal", "poster"):
            add(i, E("tape", w=210, h=58, x=cx + rng.uniform(-30, 30) / W, y=cy - fh / 2 / H + 78 / H, rotate=round(ang + rng.uniform(-9, 9), 1),
                     color="theme:accent", z=2))
        if "stars" in els:
            for sx, sy in rng.sample([(-1, -1), (1, -1), (1, 1), (-1, 1)], 2):
                add(i, E("star", shape="sparkle4", size=rng.randint(70, 110), x=cx + sx * (fw / 2 - 35) / W, y=cy + sy * (fh / 2 - 85) / H,
                         rotate=rng.randint(-12, 12), color=rng.choice(["theme:accent", "#ffffff"]), z=2))
    if cont:
        for b in range(1, n):
            if b % 2 == 1:
                add(b - 1, E("tape", w=330, h=66, x=1.0, y=0.5 + rng.uniform(-170, 170) / H, rotate=round(rng.uniform(-14, 14), 1),
                             color="theme:accent", alpha=215, z=2))
            else:
                add(b - 1, E("star", shape="sparkle4", size=150, x=1.0, y=rng.uniform(260, H - 260) / H, rotate=rng.randint(-10, 10),
                             color="theme:accent", z=2))
                add(b - 1, E("ring", size=190, thick=8, x=1.0 + rng.uniform(-60, 60) / W, y=rng.uniform(220, H - 220) / H,
                             color="theme:second", z=2))
    return spec


STAR_SLOTS = [(0.14, 0.22, 38), (0.78, 0.30, 64), (0.93, 0.42, 28), (0.06, 0.56, 30), (0.88, 0.80, 36), (0.45, 0.91, 56)]
INSET_SETS = [[(0.2, 0.2), (0.8, 0.86)], [(0.8, 0.17), (0.17, 0.85)], [(0.18, 0.84), (0.8, 0.19)], [(0.5, 0.18), (0.82, 0.86)]]


def build_whimsy(images, vibe, mode, size, seed, cover=True):
    W, H = size
    n = len(images)
    rng = random.Random(seed)
    theme = make_theme(extract_palette(images), vibe["tone"], "Bubblegum")
    spec = new_spec(size, "separate", theme, False, "whimsy", 0)
    spec["global"].update(counter=False, swipe=False)
    spec["slides"] = []
    if cover:
        c = vibe["cover"]
        s1 = fit_size(c["line1"], "rounded_bold", 0.80 * W, -8, 120, 380)
        s2 = fit_size(c["line2"], "rounded_bold", 0.60 * W, -8, 120, 380)
        els = [E("text", text=c["kicker"], font="theme:body", size=36, color="#f7e23a", tracking=6, x=0.46, y=0.295, shadow=True),
               E("text", text=c["line1"], font="theme:title", size=s1, color="theme:title", tracking=-8, x=0.43, y=0.43, shadow=True),
               E("text", text=c["line2"], font="theme:title", size=s2, color="#ffffff", tracking=-8, x=0.72, y=0.60, shadow=True),
               E("text", text=c["sub1"], font="theme:body", size=44, color="#ffffff", align="left", max_w=0.4, x=0.31, y=0.64, shadow=True),
               E("text", text=c["sub2"], font="theme:body", size=38, color="#f7e23a", x=0.36, y=0.835, shadow=True),
               E("text", text="@yourhandle", font="sans_bold", size=24, color="#ffffff", tracking=2, upper=True, x=0.5, y=0.935, opacity=0.9)]
        els += [E("star", shape="star5", size=sz, x=x, y=y, rotate=rng.randint(-20, 20), color="theme:star") for x, y, sz in STAR_SLOTS[:5]]
        spec["slides"].append({"bg": {"mode": "collage", "photos": [i % n for i in range(4)], "dim": 0.0, "gap": 5}, "elements": els})
    for i in range(n):
        v = vibe["slides"][i]
        ts = fit_size(v["title"], "rounded_bold", 0.70 * W, -8, 120, 250)
        ty = 0.47 + (0.03 if i % 2 else 0)
        els = [E("text", text=v["title"], font="theme:title", size=ts, color="theme:title", tracking=-8, x=0.5, y=ty, shadow=True),
               E("text", text=v["subtitle"], font="theme:body", size=46, color="theme:note", align="left", max_w=0.58, x=0.48, y=0.66,
                 shadow=True, line_gap=1.05)]
        pos = INSET_SETS[(i + (1 if cover else 0)) % len(INSET_SETS)]
        for k, (px, py) in enumerate(pos):
            src = (i + 1 + k) % n if n > 1 else 0
            if src == i and n > 1:
                src = (i + 1) % n
            els.append(E("inset", photo=src, w=190, label=v["label"] if k == 0 else v["label2"], x=px, y=py, rotate=rng.choice([-3, -2, 0, 2, 3]),
                         color="theme:note"))
        for x, y, sz in rng.sample(STAR_SLOTS, 5):
            els.append(E("star", shape="star5", size=sz, x=min(max(x + rng.uniform(-0.05, 0.05), 0.05), 0.95), y=y + rng.uniform(-0.04, 0.04),
                         rotate=rng.randint(-20, 20), color="theme:star"))
        spec["slides"].append({"bg": {"mode": "photo", "photo": i, "fx": 0.5, "fy": 0.5, "zoom": 1.0, "dim": 0.10}, "elements": els})
    return spec


def build_scribble(images, vibe, mode, size, seed, cover=True):
    W, H = size
    n = len(images)
    rng = random.Random(seed)
    theme = make_theme(extract_palette(images), vibe["tone"], "Bubblegum")
    theme.update(title="#fae23c", star="#fae23c", hl="#fae23c", note="#ffffff", band="#1c1c1e")
    spec = new_spec(size, "separate", theme, False, "scribble", n)
    spec["global"].update(counter=False, swipe=False)
    p = vibe["poster"]
    words = p["headline"].upper().split()
    l1, l2 = (words[0], " ".join(words[1:]) or "") if len(words) > 1 else (words[0] if words else "HELLO", "")
    s1 = fit_size(l1, "chunky", 0.86 * W, 0, 120, 330)
    els = [E("torn", y=0.63, h=int(0.22 * H), color="theme:band", jag=14, z=0),
           E("text", text=p["kicker"], font="sans", size=40, color="#ffffff", x=0.5, y=0.075, shadow=True),
           E("star", shape="sparkle4", size=34, x=0.31, y=0.06, color="theme:star"), E("star", shape="sparkle4", size=26, x=0.7, y=0.085, color="theme:star"),
           E("scribble", text=l1, font="chunky", size=s1, color="theme:hl", hatch=11, x=0.5, y=0.25, rotate=-2)]
    if l2:
        s2 = fit_size(l2, "chunky", 0.68 * W, 0, 120, 330)
        els.append(E("scribble", text=l2, font="chunky", size=s2, color="theme:hl", hatch=11, x=0.55, y=0.43, rotate=1.5))
    notes = p["notes"]
    for (x, y, r), t in zip([(0.2, 0.15, -4), (0.8, 0.165, 5), (0.15, 0.575, -14), (0.88, 0.565, 7)], notes):
        els.append(E("text", text=t, font="hand", size=50, color="theme:note", x=x, y=y, rotate=r, shadow=True))
    els += [E("text", text=p["location"], font="sans", size=58, color="#ffffff", align="left", max_w=0.5, x=0.30, y=0.70, line_gap=1.05),
            E("squiggle", span=0.42, x=0.26, y=0.785, amp=7, wavelength=70, thick=7, color="theme:hl", z=2),
            E("text", text=p["datetime"], font="sans", size=62, color="#ffffff", x=0.76, y=0.69, line_gap=1.2),
            E("highlight", w=300, h=105, thick=7, color="theme:hl", x=0.76, y=0.725, rotate=-3, z=2),
            E("arrow", x=0.17, y=0.605, x2=0.22, y2=0.665, bend=40, width=6, color="#ffffff", z=2),
            E("arrow", x=0.9, y=0.60, x2=0.935, y2=0.665, bend=40, width=6, color="#ffffff", z=2)]
    spec["slides"][0].update(bg={"mode": "photo", "photo": 0, "fx": 0.5, "fy": 0.45, "zoom": 1.0, "dim": 0.04}, elements=els)
    for i in range(1, n):
        v = vibe["slides"][i]
        ts = fit_size(v["title"].upper(), "chunky", 0.66 * W, 0, 100, 200)
        spec["slides"][i].update(bg={"mode": "photo", "photo": i, "fx": 0.5, "fy": 0.45, "zoom": 1.0, "dim": 0.05}, elements=[
            E("torn", y=0.72, h=int(0.28 * H), color="theme:band", jag=12, z=0),
            E("scribble", text=v["title"].upper(), font="chunky", size=ts, color="theme:hl", hatch=10, x=0.5, y=0.17, rotate=-2),
            E("text", text=v["subtitle"], font="hand", size=60, color="#ffffff", max_w=0.76, x=0.5, y=0.84, shadow=True),
            E("star", shape="sparkle4", size=44, x=0.15, y=0.6, color="theme:star"), E("star", shape="sparkle4", size=30, x=0.86, y=0.66, color="theme:star")])
    return spec


def build_scrapbook(images, vibe, mode="separate", size=(1080, 1350), seed=0, cover=True):
    W, H = size
    n = len(images)
    rng = random.Random(seed)
    cont = mode == "continuous"
    
    is_nav = any(w in str(vibe).lower() for w in ["navratri", "garba", "dandiya", "desi", "chogada", "pichwai", "festive"]) or vibe.get("style") == "pichwai"
    
    if is_nav:
        theme = {
            "title": "#ffffff",
            "star": "#f3b334",
            "hl": "#e24358",
            "note": "#fedec6",
            "band": "#38060c",
            "tape": "#d49b45",
            "bg1": "#580b14",
            "bg2": "#3e050b",
            "paper": (255, 248, 238),
            "accent": "#f3b334",
            "second": "#e24358",
            "text": "#fff1d6",
            "tone": "dark",
            "title_font": "hand",
            "body_font": "hand"
        }
    else:
        # Curated Scrapbook Palette
        theme = make_theme(extract_palette(images), vibe.get("tone", "light"), "Warm Cream & Espresso")
        theme.update({
            "title": "#2c2523",
            "star": "#d49b45",
            "hl": "#d9b48f",
            "note": "#4a4039",
            "band": "#ede6d8",
            "tape": "#e8d3b9",
            "bg1": "#f8f5ee",
            "bg2": "#f0ebe1"
        })
    
    total_slides = (n + 1) if (cover and not cont) else n
    spec = new_spec(size, mode, theme, grain=True, family="scrapbook", n=total_slides)
    spec["global"].update(counter=True, swipe=True)
    sl = spec["slides"]
    
    slide_offset = 0
    if cover and not cont:
        slide_offset = 1
        if is_nav:
            # Recreate the stunning Navratri Desi reference layout!
            cov_els = [
                # Top & Bottom Pichwai Lotus Borders
                E("lotus_border", h=74, x=0.5, y=0.026, z=1),
                E("lotus_border", h=74, x=0.5, y=0.974, z=1),
                # "Feeling Desi" torn parchment badge
                E("desi_badge", w=260, h=120, x=0.82, y=0.10, rotate=3, z=2),
                # Jhumka & Mojri stickers
                E("desi_sticker", kind="jhumka", size=130, x=0.82, y=0.30, rotate=8, z=2),
                E("desi_sticker", kind="mojri", size=140, x=0.74, y=0.46, rotate=-16, z=2),
                # Pichwai Photo Frame 1 (top-left)
                E("frame", photo=0, style="pichwai", caption="garba night", font="hand", x=0.31, y=0.35, rotate=-1, z=1),
                # Instagram / Spotify Music Player card
                E("music_player", title="Tere Chehre Se Nazar Nahin", artist="Lata Mangeshkar, Kishore Kumar", current="2:57", total="5:02", w=460, h=130, x=0.31, y=0.65, rotate=0, z=2),
                # Bottom stickers: Mehndi Chai & Auto Rickshaw
                E("desi_sticker", kind="mehndi_chai", size=130, x=0.33, y=0.82, rotate=4, z=2),
                E("desi_sticker", kind="rickshaw", size=120, x=0.12, y=0.85, rotate=-4, z=2),
                # Pichwai Photo Frame 2 (bottom-right)
                E("frame", photo=(1 if n > 1 else 0), style="pichwai", caption="chogada vibe", font="hand", x=0.76, y=0.70, rotate=1, z=1),
                # Golden sparkles
                E("star", shape="sparkle4", size=48, x=0.56, y=0.16, rotate=12, color="theme:star", z=2),
                E("star", shape="sparkle4", size=36, x=0.56, y=0.88, rotate=-8, color="theme:star", z=2),
            ]
            sl[0].update(bg={"mode": "gradient", "bg1": "#580b14", "bg2": "#3e050b"}, elements=cov_els)
        else:
            headline = vibe.get("poster", {}).get("headline") or vibe.get("vibe_name") or "SCRAPBOOK MEMORIES"
            kicker = vibe.get("poster", {}).get("kicker") or f"{n} visual moments"
            sub = vibe.get("cover", {}).get("sub1") or "flip through the story"
            
            words = headline.split()
            l1 = " ".join(words[:max(1, len(words)//2)])
            l2 = " ".join(words[max(1, len(words)//2):]) if len(words) > 1 else ""
            
            s1 = fit_size(l1, "serif", 0.82 * W, 0, 70, 150)
            
            cov_els = [
                E("torn", y=0.58, h=int(0.35 * H), color="theme:band", jag=16, z=0),
                E("tape", w=240, h=60, x=0.25, y=0.08, rotate=-8, color="theme:tape", alpha=220, z=2),
                E("tape", w=220, h=56, x=0.76, y=0.09, rotate=6, color="theme:tape", alpha=220, z=2),
                E("frame", photo=0, style="polaroid", caption=vibe.get("slides", [{}])[0].get("title", "moment 01"),
                  font="hand", x=0.5, y=0.38, rotate=-2.5, z=1),
                E("text", text=kicker.upper(), font="sans_bold", size=32, color="theme:star", tracking=4, x=0.5, y=0.62, shadow=False),
                E("text", text=l1, font="serif", size=s1, color="theme:title", x=0.5, y=0.70, shadow=False),
            ]
            if l2:
                s2 = fit_size(l2, "serif", 0.78 * W, 0, 60, 140)
                cov_els.append(E("text", text=l2, font="serif", size=s2, color="theme:title", x=0.5, y=0.77, shadow=False))
            
            cov_els.extend([
                E("text", text=sub, font="hand", size=54, color="theme:note", x=0.48, y=0.86, rotate=-1, shadow=False),
                E("arrow", x=0.72, y=0.86, x2=0.86, y2=0.88, bend=35, width=6, color="theme:note", z=2),
                E("text", text="swipe →", font="hand", size=44, color="theme:note", x=0.84, y=0.92, rotate=4, z=2),
                E("star", shape="sparkle4", size=52, x=0.15, y=0.65, rotate=-12, color="theme:star", z=2),
                E("star", shape="sparkle4", size=38, x=0.88, y=0.68, rotate=15, color="theme:star", z=2),
            ])
            sl[0].update(bg={"mode": "gradient", "bg1": "#f9f6ee", "bg2": "#efe9dc"}, elements=cov_els)

    # In continuous mode, add subtle panoramic backdrop text
    if cont:
        mood_word = ("NAVRATRI" if is_nav else vibe.get("mood_word", "MEMORIES")).upper()
        # Ambient background text on slide 0 that subtly flows across the whole panorama
        sl[0]["elements"].append(
            E("text", text=mood_word, font="serif_italic" if not is_nav else "hand", size=180, color="theme:title",
              opacity=0.07, x=n * 0.45, y=0.20, shadow=False, z=0)
        )

    for idx in range(n):
        target_idx = idx + slide_offset
        if target_idx >= len(sl):
            break
        v_slide = vibe.get("slides", [{}])[idx] if idx < len(vibe.get("slides", [])) else {}
        title = v_slide.get("title") or (NAVRATRI_CAPS[idx % len(NAVRATRI_CAPS)] if is_nav else f"moment {idx+1}")
        subtitle = v_slide.get("subtitle") or (NAVRATRI_SUBS[idx % len(NAVRATRI_SUBS)] if is_nav else "A special memory captured in time")
        label = v_slide.get("label") or "detail"
        
        frame_style = "pichwai" if is_nav else "polaroid"
        
        if cont:
            # Stagger frames dynamically across slides for an authentic scrapbook panorama
            if idx % 3 == 0:
                cx, cy = 0.48, 0.44
                rot = -2.8 + rng.uniform(-0.8, 0.8)
            elif idx % 3 == 1:
                cx, cy = 0.54, 0.42
                rot = 3.2 + rng.uniform(-0.8, 0.8)
            else:
                cx, cy = 0.46, 0.45
                rot = -1.6 + rng.uniform(-0.8, 0.8)
        else:
            rot = (-3.0 if idx % 2 == 0 else 3.0) + rng.uniform(-1.0, 1.0)
            cy = 0.44 + (0.02 if idx % 2 == 0 else -0.02)
            cx = 0.5
        
        if is_nav:
            slide_els = [
                E("lotus_border", h=74, x=0.5, y=0.026, z=1),
                E("lotus_border", h=74, x=0.5, y=0.974, z=1),
                E("frame", photo=idx, style=frame_style, caption=title, font="hand", x=cx, y=cy, rotate=round(rot, 1), z=1),
                E("tape", w=220, h=54, x=cx + rng.uniform(-0.04, 0.04), y=cy - 0.28, rotate=round(rot + rng.uniform(-6, 6), 1),
                  color="theme:tape", alpha=230, z=2),
                E("text", text=subtitle, font="hand", size=52, color="theme:note", max_w=0.82, x=cx, y=0.86,
                  rotate=round(rng.uniform(-2, 2), 1), shadow=True, line_gap=1.05),
                E("star", shape="sparkle4", size=rng.randint(40, 65), x=0.14 if idx % 2 == 0 else 0.86,
                  y=0.18 + rng.uniform(-0.04, 0.04), rotate=rng.randint(-15, 15), color="theme:star", z=2),
                E("star", shape="sparkle4", size=rng.randint(28, 44), x=0.88 if idx % 2 == 0 else 0.12,
                  y=0.72 + rng.uniform(-0.04, 0.04), rotate=rng.randint(-15, 15), color="theme:star", z=2),
            ]
            
            desi_stickers_pool = [
                [("jhumka", 0.84, 0.22, 8), ("mojri", 0.15, 0.74, -12)],
                [("mehndi_chai", 0.85, 0.70, 6), ("rickshaw", 0.15, 0.24, -6)],
                [("lotus", 0.84, 0.22, 0), ("dandiya", 0.15, 0.74, 15)],
                [("garba", 0.85, 0.70, -8), ("diya", 0.15, 0.24, 5)],
            ]
            stk_set = desi_stickers_pool[idx % len(desi_stickers_pool)]
            for kind, sx, sy, srot in stk_set:
                slide_els.append(E("desi_sticker", kind=kind, size=125, x=sx, y=sy, rotate=srot, z=2))
                
            sl[target_idx].update(
                bg={"mode": "gradient", "bg1": "#580b14", "bg2": "#3e050b"},
                elements=slide_els
            )
        else:
            slide_els = [
                E("torn", y=0.76, h=int(0.24 * H), color="theme:band", jag=14, z=0),
                E("frame", photo=idx, style="polaroid", caption=title, font="hand", x=cx, y=cy, rotate=round(rot, 1), z=1),
                E("tape", w=220, h=54, x=cx + rng.uniform(-0.04, 0.04), y=cy - 0.28, rotate=round(rot + rng.uniform(-6, 6), 1),
                  color="theme:tape", alpha=230, z=2),
                E("text", text=subtitle, font="hand", size=54, color="theme:note", max_w=0.80, x=cx, y=0.86,
                  rotate=round(rng.uniform(-2, 2), 1), shadow=False, line_gap=1.05),
                E("star", shape="sparkle4", size=rng.randint(42, 68), x=0.14 if idx % 2 == 0 else 0.86,
                  y=0.18 + rng.uniform(-0.04, 0.04), rotate=rng.randint(-15, 15), color="theme:star", z=2),
                E("star", shape="sparkle4", size=rng.randint(28, 44), x=0.88 if idx % 2 == 0 else 0.12,
                  y=0.72 + rng.uniform(-0.04, 0.04), rotate=rng.randint(-15, 15), color="theme:star", z=2),
            ]
            
            if not cont:
                if n > 1 and idx % 2 == 1:
                    inset_ph = (idx + 1) % n
                    slide_els.append(E("inset", photo=inset_ph, w=200, label=label, x=0.82, y=0.22, rotate=6, color="theme:note", z=2))
                    slide_els.append(E("tape", w=120, h=40, x=0.82, y=0.14, rotate=-10, color="theme:hl", alpha=200, z=3))
                elif idx % 2 == 0:
                    slide_els.append(E("squiggle", span=0.45, x=0.5, y=0.92, amp=6, wavelength=65, thick=6, color="theme:hl", z=2))
                
            sl[target_idx].update(
                bg={"mode": "gradient", "bg1": "#faf8f2", "bg2": "#f1ebe0"},
                elements=slide_els
            )

    # In continuous mode, add cross-seam scrapbook bridge elements connecting every pair of slides!
    if cont:
        for b in range(1, n):
            prev_idx = b - 1
            # 1. Washi tape strip crossing directly over the seam (x=1.0)
            tape_y = 0.22 if b % 2 == 1 else 0.70
            tape_rot = rng.uniform(-10, 10)
            sl[prev_idx]["elements"].append(
                E("tape", w=260, h=62, x=1.0, y=tape_y, rotate=round(tape_rot, 1),
                  color="theme:tape", alpha=235, z=2)
            )
            
            # 2. Sparkle star doodle bridging the cut
            sl[prev_idx]["elements"].append(
                E("star", shape="sparkle4", size=rng.randint(52, 78), x=1.0,
                  y=0.48 + rng.uniform(-0.12, 0.12), rotate=rng.randint(-15, 15),
                  color="theme:star", z=2)
            )
            
            # 3. Desi sticker or photo inset sitting across the seam on alternating slides
            if is_nav:
                desi_seam_kinds = ["lotus", "jhumka", "dandiya", "garba"]
                sl[prev_idx]["elements"].append(
                    E("desi_sticker", kind=desi_seam_kinds[b % len(desi_seam_kinds)], size=130, x=1.0,
                      y=0.34, rotate=round(rng.uniform(-8, 8), 1), z=2)
                )
            elif b % 2 == 1 and n > 1:
                inset_ph = (b + 1) % n
                sl[prev_idx]["elements"].append(
                    E("inset", photo=inset_ph, w=220, label="moment", x=1.0,
                      y=0.34, rotate=round(rng.uniform(-6, 6), 1),
                      color="theme:note", z=2)
                )
                sl[prev_idx]["elements"].append(
                    E("tape", w=130, h=40, x=1.0, y=0.22, rotate=round(rng.uniform(-10, 10), 1),
                      color="theme:hl", alpha=210, z=3)
                )
            else:
                # Doodled connecting arrow across the seam with swipe cue
                sl[prev_idx]["elements"].append(
                    E("arrow", x=0.86, y=0.88, x2=1.14, y2=0.88, bend=28, width=6,
                      color="theme:note", z=2)
                )
                sl[prev_idx]["elements"].append(
                    E("text", text="continue →", font="hand", size=42, color="theme:note",
                      x=0.98, y=0.93, rotate=2, shadow=False, z=2)
                )
            
            # 4. Squiggle wave line crossing the bottom seam (only for non-nav, nav has lotus borders)
            if not is_nav:
                sl[prev_idx]["elements"].append(
                    E("squiggle", span=0.5, x=1.0, y=0.92, amp=6, wavelength=65, thick=6, color="theme:hl", z=1)
                )
        
    return spec
