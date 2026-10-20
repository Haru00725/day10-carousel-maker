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
import re
import uuid
import zlib

import numpy as np
import requests
from dotenv import load_dotenv
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

load_dotenv()
HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "fonts")

def get_navratri_asset_path(filename):
    for base in [
        os.path.join(HERE, "assets", "navratri"),
        os.path.join(HERE, "public", "assets", "navratri"),
        os.path.join(HERE, "..", "assets", "navratri"),
        os.path.join(HERE, "..", "public", "assets", "navratri")
    ]:
        p = os.path.join(base, filename)
        if os.path.exists(p):
            return p
    return None

def get_asset_file_path(subpath):
    subpath = subpath.lstrip("/")
    for base in [
        HERE,
        os.path.join(HERE, "public"),
        os.path.join(HERE, ".."),
        os.path.join(HERE, "..", "public"),
        "."
    ]:
        p = os.path.join(base, subpath)
        if os.path.exists(p):
            return p
    return None

STICKERS_CATALOG = None

def get_stickers_catalog():
    global STICKERS_CATALOG
    if STICKERS_CATALOG is not None:
        return STICKERS_CATALOG
    catalog_path = get_asset_file_path("assets/stickers_catalog.json")
    if catalog_path and os.path.isfile(catalog_path):
        try:
            with open(catalog_path, "r", encoding="utf-8") as f:
                STICKERS_CATALOG = json.load(f)
        except Exception:
            STICKERS_CATALOG = []
    else:
        STICKERS_CATALOG = []
    return STICKERS_CATALOG

def find_stickers(query="", category="all", limit=60):
    catalog = get_stickers_catalog()
    results = []
    q = query.strip().lower() if query else ""
    cat = category.strip().lower() if category else "all"

    for item in catalog:
        if cat != "all" and item.get("category", "").lower() != cat:
            continue
        if q:
            match_score = 0
            if q in item.get("name", "").lower():
                match_score += 10
            if q in item.get("id", "").lower():
                match_score += 8
            if any(q in tag.lower() for tag in item.get("theme_tags", [])):
                match_score += 6
            if q in item.get("visual_style", "").lower() or q in item.get("recommended_use", "").lower():
                match_score += 3
            if match_score > 0:
                results.append((match_score, item))
        else:
            results.append((1, item))

    if q:
        results.sort(key=lambda x: x[0], reverse=True)
    return [r[1] for r in results[:limit]]

def get_sticker_asset(sticker_id_or_path, size=160):
    catalog = get_stickers_catalog()
    asset = None
    target_str = str(sticker_id_or_path).strip()
    
    # 1. Direct ID or path match
    for item in catalog:
        if item.get("id") == target_str or item.get("path") == target_str:
            asset = item
            break
            
    # 2. Tag or partial match
    if not asset:
        t_low = target_str.lower()
        for item in catalog:
            if t_low in item.get("id", "").lower() or any(t_low in tag.lower() for tag in item.get("theme_tags", [])):
                asset = item
                break

    resolved_path = None
    if asset:
        resolved_path = get_asset_file_path(asset.get("path", ""))
    elif "/" in target_str or target_str.endswith(".png"):
        resolved_path = get_asset_file_path(target_str)

    if resolved_path and os.path.isfile(resolved_path):
        try:
            im = Image.open(resolved_path).convert("RGBA")
            ratio = im.width / im.height
            if ratio >= 1:
                tw = size
                th = max(1, int(tw / ratio))
            else:
                th = size
                tw = max(1, int(th * ratio))
            return im.resize((tw, th), Image.Resampling.LANCZOS)
        except Exception:
            pass

    return make_desi_sticker(target_str, size)

THEME_SYNONYMS = {
    "city_life": [
        "city", "urban", "skyline", "buildings", "building", "taxi", "cab", "street",
        "sign", "subway", "metro", "transit", "traffic", "crosswalk", "ticket", "avenue",
        "broadway", "route", "doodle", "downtown", "metropolis", "commute", "lights",
        "city dump", "city life", "city trip", "manhattan", "nyc", "town", "concrete",
        "skyscraper", "streets"
    ],
    "girly_coquette": [
        "coquette", "girly", "cute", "bow", "ribbon", "ribbons", "gingham", "heart",
        "hearts", "locket", "ballet", "balletcore", "pink", "soft", "sweet", "dollette",
        "pretty", "love", "sparkle", "lace", "angelic", "pastel", "feminine", "pearl",
        "cute coquette", "princess"
    ],
    "cafe_food": [
        "cafe", "coffee", "latte", "espresso", "cappuccino", "croissant", "pastry",
        "pastries", "bakery", "food", "cherries", "cherry", "matcha", "tea", "brunch",
        "breakfast", "cookie", "plate", "plates", "drink", "bistro", "snack", "sweet",
        "chai", "coffee date", "cafe date", "delicious", "foodie", "baking", "treats"
    ],
    "nature": [
        "nature", "botanical", "garden", "flower", "flowers", "leaf", "leaves",
        "butterfly", "butterflies", "monarch", "daisy", "daisies", "ginkgo", "lotus",
        "spring", "bloom", "blooms", "blossom", "blossoms", "flora", "green", "organic",
        "earthy", "plants", "forest", "dreamy botanical", "meadow", "wildflowers", "foliage"
    ],
    "travel": [
        "travel", "trip", "vacation", "holiday", "journey", "explore", "explorer",
        "wanderlust", "camera", "cameras", "postcard", "postcards", "airmail",
        "suitcase", "suitcases", "luggage", "passport", "stamp", "stamps", "location",
        "pin", "map", "maps", "destination", "adventure", "flight", "tourist", "travel life"
    ],
    "fashion": [
        "fashion", "style", "ootd", "outfit", "outfits", "handbag", "handbags", "purse",
        "bag", "sunglasses", "shades", "glasses", "lipstick", "lipsticks", "makeup",
        "cosmetics", "beauty", "chic", "glam", "luxury", "accessories", "wardrobe",
        "shoes", "juttis", "jhumka", "jewelry", "model", "runway", "editorial"
    ],
    "vintage_grunge": [
        "vintage", "grunge", "retro", "film", "analog", "35mm", "negative", "stamp",
        "postage", "wax", "seal", "paperclip", "clip", "receipt", "distressed",
        "antique", "sepia", "nostalgia", "memories", "polaroid", "archive", "ephemera",
        "newspaper", "scrapbook", "thrift"
    ],
    "festive_desi": [
        "navratri", "garba", "dandiya", "desi", "indian", "ethnic", "lehenga", "jhumka",
        "jhumkas", "juttis", "mojri", "gajra", "marigold", "genda", "lotus", "pichwai",
        "diya", "rickshaw", "festive", "diwali", "chogada"
    ]
}

COMPATIBLE_CATEGORIES = {
    "city_life": ["travel", "vintage_grunge"],
    "girly_coquette": ["nature", "fashion"],
    "cafe_food": ["vintage_grunge", "girly_coquette"],
    "nature": ["girly_coquette", "travel"],
    "travel": ["city_life", "vintage_grunge"],
    "fashion": ["girly_coquette", "city_life"],
    "vintage_grunge": ["travel", "cafe_food"],
    "festive_desi": ["nature", "fashion"]
}

CATEGORY_PRIMARY_ASSETS = {
    "city_life": ["city-buildings", "city-yellow-cab", "city-street-sign", "city-subway-map", "travel-vintage-camera", "city-traffic-light", "city-transit-ticket"],
    "girly_coquette": ["coquette-pink-bow", "coquette-gingham-tape", "coquette-heart-locket", "coquette-sparkle-heart", "nature-white-daisy", "nature-monarch-butterfly"],
    "cafe_food": ["cafe-latte-art", "cafe-croissant", "cafe-cherries", "cafe-matcha", "vintage-cafe-receipt", "desi-mehndi-chai"],
    "nature": ["nature-white-daisy", "nature-monarch-butterfly", "nature-ginkgo-leaf", "nature-pink-lotus", "desi-marigold", "desi-jasmine_gajra"],
    "travel": ["travel-vintage-camera", "travel-airmail-postcard", "travel-passport-stamp", "travel-location-pin", "travel-leather-suitcase", "city-subway-map"],
    "fashion": ["fashion-quilted-handbag", "fashion-sunglasses", "fashion-lipstick", "coquette-pink-bow", "desi-jhumka", "desi-mojri"],
    "vintage_grunge": ["vintage-35mm-film", "vintage-postage-stamp", "vintage-wax-seal", "vintage-paperclip", "vintage-cafe-receipt", "travel-vintage-camera"],
    "festive_desi": ["desi-marigold_garland", "desi-lotus_jhumka_hd", "desi-embroidered_juttis", "desi-jasmine_gajra", "desi-basket_gajra", "desi-pink_lotus", "desi-mehndi_chai", "desi-rickshaw"]
}

def rank_theme_stickers(brief, hint=""):
    """
    Ranks sticker assets from the catalog based on the AI design plan and user creative brief.
    Scores tags, synonyms, categories, and compatible fallback themes.
    Returns an ordered list of sticker dicts or IDs with high theme relevance.
    """
    catalog = get_stickers_catalog()
    if not catalog:
        return []

    # 1. Gather all signals from brief & user hint
    main_theme = str(brief.get("main_theme", "")).lower()
    aesthetic = str(brief.get("aesthetic", "")).lower()
    mood_energy = str(brief.get("mood_energy", "")).lower()
    motifs = [str(m).lower() for m in brief.get("motifs", [])]
    exp = brief.get("explicit_instructions", {})
    user_notes = str(exp.get("user_notes", "")).lower() if isinstance(exp, dict) else ""
    raw_hint = str(hint or "").lower()

    text_tokens = f"{main_theme} {aesthetic} {mood_energy} {' '.join(motifs)} {user_notes} {raw_hint}"

    # 2. Identify primary and secondary theme clusters
    cluster_scores = {}
    for cat_key, keywords in THEME_SYNONYMS.items():
        score = 0
        for kw in keywords:
            if kw in text_tokens:
                score += 15 if len(kw) > 4 else 8
        cluster_scores[cat_key] = score

    top_cluster = max(cluster_scores, key=cluster_scores.get)
    if cluster_scores[top_cluster] == 0:
        top_cluster = "vintage_grunge" if "dark" in text_tokens else "nature"

    compatible_cats = COMPATIBLE_CATEGORIES.get(top_cluster, [])
    priority_ids = CATEGORY_PRIMARY_ASSETS.get(top_cluster, [])

    # 3. Score every catalog asset
    scored_assets = []
    for asset in catalog:
        aid = asset.get("id", "")
        acat = asset.get("category", "")
        atags = [t.lower() for t in asset.get("theme_tags", [])]
        aname = asset.get("name", "").lower()

        score = 0
        if acat == top_cluster:
            score += 40
        elif acat in compatible_cats:
            score += 15

        if aid in priority_ids:
            score += 30

        for tag in atags:
            if tag in text_tokens:
                score += 18

        for word in aname.split():
            if len(word) > 3 and word in text_tokens:
                score += 12

        if "flowers" in motifs and (acat == "nature" or "flower" in atags or "daisy" in atags):
            score += 25
        if "hearts" in motifs and ("heart" in atags or "locket" in atags):
            score += 25
        if "stars" in motifs and "sparkle" in atags:
            score += 15
        if "film_strip" in motifs and "film" in atags:
            score += 25

        if score > 0:
            scored_assets.append((score, asset))

    scored_assets.sort(key=lambda x: x[0], reverse=True)
    ranked = [item[1] for item in scored_assets]

    seen_ids = {a.get("id") for a in ranked}
    for pid in priority_ids:
        if pid not in seen_ids:
            for item in catalog:
                if item.get("id") == pid:
                    ranked.append(item)
                    seen_ids.add(pid)
                    break

    for ccat in compatible_cats:
        for item in catalog:
            if item.get("category") == ccat and item.get("id") not in seen_ids:
                ranked.append(item)
                seen_ids.add(item.get("id"))
                if len(ranked) >= 12:
                    break
        if len(ranked) >= 12:
            break

    return ranked

FONT_SPECS = {  # key: (file, variable-font weight)
    "rounded": ("Fredoka.ttf", 500), "rounded_bold": ("Fredoka.ttf", 600), "chunky": ("LilitaOne-Regular.ttf", None),
    "hand": ("Caveat.ttf", None), "serif": ("PlayfairDisplay.ttf", None), "serif_italic": ("PlayfairDisplay-Italic.ttf", None),
    "sans": ("Poppins-Regular.ttf", None), "sans_bold": ("Poppins-Bold.ttf", None), "mono": ("SpaceMono-Regular.ttf", None),
}
FONT_KEYS = list(FONT_SPECS)
SYSTEM_FONTS = ["/System/Library/Fonts/Supplemental/Georgia.ttf", "/System/Library/Fonts/Helvetica.ttc",
                "/Library/Fonts/Arial.ttf", "C:\\Windows\\Fonts\\arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]

FAMILIES = ["scrapbook", "classic", "whimsy", "scribble"]
STYLES = ["polaroid", "minimal", "film", "poster", "pichwai", "gold_jaali"]
ELEMENTS = ["tape", "stars", "circles", "squiggle", "dots", "film_border", "heart", "flower", "paperclip"]
DEFAULT_MODEL = "gemini-3.5-flash-lite"  # override with GEMINI_MODEL in .env

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


PRESET_THEMES = {
    "Warm Cream & Espresso": {
        "title": "#2c2523", "star": "#d49b45", "hl": "#d9b48f", "note": "#5c524b",
        "band": "#ede6d8", "tape": "#e8d3b9", "bg1": "#f8f5ee", "bg2": "#f0ebe1",
        "text": "#2c2523", "paper": (255, 255, 255), "accent": "#d49b45", "second": "#d9b48f", "tone": "light"
    },
    "Sage & Botanical": {
        "title": "#273a2e", "star": "#7d9d83", "hl": "#a3c4a8", "note": "#485d4f",
        "band": "#dfe7df", "tape": "#c8dbc9", "bg1": "#f3f6f3", "bg2": "#eaf0ea",
        "text": "#273a2e", "paper": (255, 255, 255), "accent": "#7d9d83", "second": "#a3c4a8", "tone": "light"
    },
    "Vintage Rose": {
        "title": "#3e282b", "star": "#d49b45", "hl": "#e2a8a8", "note": "#6c4d51",
        "band": "#fae4eb", "tape": "#f3c2cf", "bg1": "#fdf6f7", "bg2": "#f7e8ec",
        "text": "#3e282b", "paper": (255, 255, 255), "accent": "#d49b45", "second": "#e2a8a8", "tone": "light"
    },
    "Terracotta & Clay": {
        "title": "#3b2b25", "star": "#e29b68", "hl": "#c97a5b", "note": "#66493e",
        "band": "#eddccc", "tape": "#e8cbb6", "bg1": "#f9f6f0", "bg2": "#eee6dc",
        "text": "#3b2b25", "paper": (255, 255, 255), "accent": "#e29b68", "second": "#c97a5b", "tone": "light"
    },
    "Midnight Journal": {
        "title": "#f4efe6", "star": "#ffd166", "hl": "#e5b869", "note": "#e2dcd2",
        "band": "#2b2b34", "tape": "#d9ab55", "bg1": "#201f26", "bg2": "#16161b",
        "text": "#f4efe6", "paper": (32, 31, 38), "accent": "#ffd166", "second": "#e5b869", "tone": "dark"
    },
    "Royal Crimson & Pichwai": {
        "title": "#ffffff", "star": "#f3b334", "hl": "#e24358", "note": "#fedec6",
        "band": "#38060c", "tape": "#d49b45", "bg1": "#580b14", "bg2": "#3e050b",
        "text": "#fff1d6", "paper": (255, 248, 238), "accent": "#f3b334", "second": "#e24358", "tone": "dark"
    },
    "Bubblegum": {
        "title": "#ffa0e2", "star": "#f7e23a", "hl": "#fae23c", "note": "#ffffff",
        "band": "#ffe5f7", "tape": "#fff176", "bg1": "#fff0fa", "bg2": "#fce4ec",
        "text": "#d81b60", "paper": (255, 255, 255), "accent": "#f7e23a", "second": "#ffa0e2", "tone": "light"
    }
}


def apply_preset(theme, name):
    if name in PRESET_THEMES:
        theme.update(PRESET_THEMES[name])
    elif name in PRESETS:
        theme["title"], theme["star"], theme["note"], theme["hl"] = PRESETS[name]
    return theme


# ============================================================ vibe: Gemini + fallback
PROMPT = """You are an expert art director and visual designer for high-end Instagram carousels and story scrapbooks.
Analyze these {n} photos and the user's creative brief description.

User's Creative Brief / Description: "{hint}"

CRITICAL INSTRUCTION: The user's description is your primary source of truth.
Never force designs into a generic scrapbook style if the user requested a different aesthetic (e.g. vintage, grunge, coquette, minimalist, nature, cafe date, city life, fashion, cyber, desi festive, etc.).
Extract the visual identity, colors, typography, density, and layout rules directly from their brief.

For this generation, identify:
1. main_theme: e.g. "city life", "cafe date", "travel", "fashion", "nature", "festive celebration", "night out", "cozy home", "art & culture", etc.
2. aesthetic: e.g. "vintage", "girly", "coquette", "grunge", "dreamy", "minimalist", "dark academia", "y2k", "retro 90s", "desi festive", etc.
3. mood_energy: e.g. "soft & delicate", "raw & moody", "vibrant & electric", "calm & serene", "nostalgic & warm", etc.
4. preferred colors (palette): Complete harmonious hex colors reflecting the requested aesthetic and mood:
   - bg1: primary background color (e.g. dark charcoal for grunge, soft blush for coquette, ivory/linen for minimalist, warm sepia for vintage, forest olive for nature)
   - bg2: subtle gradient end background color
   - paper: photo frame / backing card color (e.g. off-white, kraft, dark card)
   - text: primary title text color (high contrast against bg1)
   - note: secondary caption / annotation text color
   - accent: doodle / star / graphic accent color
   - tape: washi tape color
   - band: torn paper band or banner color
   - star: sparkle/star color
   - hl: highlight squiggle/emphasis color
5. typography & annotation style:
   - title_font: "serif" (vintage/editorial), "serif_italic" (poetic/dreamy), "hand" (scrapbook/coquette), "sans" (clean/minimal), "sans_bold" (bold/modern), "mono" (grunge/tech/typewriter), "rounded" (friendly), "rounded_bold" (pop), or "chunky"
   - body_font: "hand", "serif", "sans", "mono", or "rounded"
   - annotation_style: "handwritten", "editorial_serif", "typewriter_mono", or "clean_sans"
6. suitable sticker categories and decorative motifs:
   List 3-6 motifs from: ["tape", "stars", "squiggle", "arrows", "paperclip", "hearts", "flowers", "film_strip", "dots", "highlight", "desi_sticker"]
7. decoration density:
   "minimal" (clean, spacious, focus on photo & type), "balanced" (tasteful tape & notes), or "heavily_decorated" (dense layering, torn bands, multiple stickers)
8. frame_style:
   "polaroid" (classic scrapbook), "minimal" (clean borderless/thin border), "film" (vintage 35mm film border), "poster" (bold graphic frame), "pichwai" (ornate Indian filigree), or "gold_jaali" (royal gold arch)
9. explicit instructions:
   - photo_placement: "center", "staggered", or "tilted"
   - preserve_faces: boolean (true if user asks not to cover photos/faces, or if portraits are prominent)
   - layering: "clean", "layered", or "overlapped"
   - user_notes: string summary of any specific rules mentioned in the user brief

Also write engaging, aesthetic captions for each slide, cover, and Instagram post matching the vibe.
If Indian festive, Navratri, or Desi elements are requested, write authentic festive captions.

Return ONLY one valid, compact JSON object matching this schema:
{{
  "creative_brief": {{
    "main_theme": "...",
    "aesthetic": "...",
    "mood_energy": "...",
    "palette": {{
      "bg1": "#hex",
      "bg2": "#hex",
      "paper": "#hex",
      "text": "#hex",
      "note": "#hex",
      "accent": "#hex",
      "tape": "#hex",
      "band": "#hex",
      "star": "#hex",
      "hl": "#hex"
    }},
    "typography": {{
      "title_font": "hand|serif|serif_italic|sans|sans_bold|mono|rounded|rounded_bold|chunky",
      "body_font": "hand|serif|sans|mono|rounded",
      "annotation_style": "handwritten|editorial_serif|typewriter_mono|clean_sans"
    }},
    "motifs": ["tape", "stars", "..."],
    "decoration_density": "minimal|balanced|heavily_decorated",
    "frame_style": "polaroid|minimal|film|poster|pichwai|gold_jaali",
    "explicit_instructions": {{
      "photo_placement": "center|staggered|tilted",
      "preserve_faces": true,
      "layering": "clean|layered|overlapped",
      "user_notes": "..."
    }}
  }},
  "vibe_name": "2-4 words title",
  "mood_word": "one word",
  "tone": "light|dark",
  "slides": [
    {{"title": "1-5 words caption", "subtitle": "6-14 words story note", "label": "1-2 words"}}
  ],
  "cover": {{"line1": "word", "line2": "word", "kicker": "2-4 words", "sub1": "3-6 words", "sub2": "3-6 words"}},
  "poster": {{"headline": "headline", "kicker": "kicker", "location": "location", "datetime": "datetime", "notes": ["n1", "n2", "n3", "n4"]}},
  "post_caption": "Instagram caption with relevant emojis",
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


def is_navratri_request(text="", brief=None, vibe=None):
    """
    Strictly checks if a text, creative brief, or vibe is an Indian festive/Navratri/Garba request.
    Uses regex word boundaries to avoid false positives like 'design', 'destination', etc.
    """
    candidates = []
    if text:
        candidates.append(str(text))
    if isinstance(brief, dict):
        candidates.extend([
            str(brief.get("main_theme") or ""),
            str(brief.get("aesthetic") or ""),
            str(brief.get("explicit_instructions", {}).get("user_notes") or "")
        ])
    if isinstance(vibe, dict):
        candidates.extend([
            str(vibe.get("vibe_name") or ""),
            str(vibe.get("hint") or "")
        ])
        v_brief = vibe.get("creative_brief")
        if isinstance(v_brief, dict):
            candidates.extend([
                str(v_brief.get("main_theme") or ""),
                str(v_brief.get("aesthetic") or ""),
                str(v_brief.get("explicit_instructions", {}).get("user_notes") or "")
            ])
            
    combined = " ".join(candidates).strip().lower()
    if not combined:
        return False
        
    # Direct high-confidence festive Indian keywords with word boundaries
    if re.search(r"\b(navratri|garba|dandiya|chogada|dholida|lehenga)\b", combined, re.IGNORECASE):
        return True
        
    # Pichwai or Desi only when explicitly associated with traditional/festive celebration
    if re.search(r"\b(pichwai|desi)\b", combined, re.IGNORECASE) and re.search(r"\b(festive|festival|traditional|ethnic|garba|celebration|navratri)\b", combined, re.IGNORECASE):
        return True
        
    return False


def heuristic_creative_brief(hint="", colors=None, tone="light"):
    h = (hint or "").lower()
    
    # 1. Main Theme
    if is_navratri_request(h):
        theme = "festive celebration"
    elif any(w in h for w in ["cafe", "coffee", "latte", "bakery", "cappuccino", "brunch", "date"]):
        theme = "cafe date"
    elif any(w in h for w in ["coquette", "bow", "pink", "doll", "ballet", "cute"]):
        theme = "cute coquette"
    elif any(w in h for w in ["city", "tokyo", "nyc", "urban", "metro", "street", "night out", "city dump", "city life"]):
        theme = "city life"
    elif any(w in h for w in ["travel", "vacation", "trip", "roadtrip", "beach", "summer", "island"]):
        theme = "travel"
    elif any(w in h for w in ["fashion", "outfit", "fit", "style", "editorial", "lookbook"]):
        theme = "fashion"
    elif any(w in h for w in ["nature", "hiking", "greenery", "mountain", "forest", "botanical", "lake", "dreamy botanical"]):
        theme = "dreamy botanical"
    else:
        theme = "lifestyle memories"
        
    # 2. Aesthetic
    if is_navratri_request(h):
        aes = "desi festive"
    elif any(w in h for w in ["coquette", "bow", "pink", "doll", "ballet"]):
        aes = "coquette"
    elif any(w in h for w in ["botanical", "flower", "leaves", "flora"]):
        aes = "botanical"
    elif any(w in h for w in ["grunge", "dark", "punk", "moody", "goth", "underground", "cyber"]):
        aes = "grunge"
    elif any(w in h for w in ["minimal", "minimalist", "clean", "simple", "neutral", "modern"]):
        aes = "minimalist"
    elif any(w in h for w in ["vintage", "retro", "90s", "sepia", "antique", "film", "classic"]):
        aes = "vintage"
    elif any(w in h for w in ["dreamy", "ethereal", "fantasy", "fairy", "cloud", "golden hour"]):
        aes = "dreamy"
    elif any(w in h for w in ["girly", "cute", "sweet", "soft"]):
        aes = "girly"
    else:
        aes = "vintage" if tone == "dark" else "dreamy"
        
    # 3. Mood & Energy
    mood_map = {
        "coquette": "soft & delicate",
        "botanical": "organic & serene",
        "grunge": "raw & moody",
        "minimalist": "calm & serene",
        "vintage": "nostalgic & warm",
        "dreamy": "ethereal & gentle",
        "girly": "sweet & playful",
        "desi festive": "vibrant & electric",
        "nature": "earthy & peaceful"
    }
    mood_energy = mood_map.get(aes, "balanced & warm")
    
    # 4. Color Palette
    if aes == "desi festive":
        pal = {
            "bg1": "#580b14", "bg2": "#3e050b", "paper": "#fff8ee", "text": "#fff1d6",
            "note": "#fedec6", "accent": "#f3b334", "tape": "#d49b45", "band": "#38060c",
            "star": "#f3b334", "hl": "#e24358"
        }
    elif aes == "grunge":
        pal = {
            "bg1": "#18181b", "bg2": "#0f0f11", "paper": "#27272a", "text": "#f4f4f5",
            "note": "#a1a1aa", "accent": "#dc2626", "tape": "#3f3f46", "band": "#27272a",
            "star": "#e4e4e7", "hl": "#ef4444"
        }
    elif aes == "coquette":
        pal = {
            "bg1": "#fdf6f7", "bg2": "#f7e8ec", "paper": "#ffffff", "text": "#4a3237",
            "note": "#8a616a", "accent": "#d8829d", "tape": "#f3c2cf", "band": "#fae4eb",
            "star": "#d8829d", "hl": "#eeb4c3"
        }
    elif aes == "minimalist":
        pal = {
            "bg1": "#f7f6f2", "bg2": "#ece9e1", "paper": "#ffffff", "text": "#1f2421",
            "note": "#555b57", "accent": "#2c3531", "tape": "#dedbd2", "band": "#e9e7df",
            "star": "#8e9089", "hl": "#b0b2a8"
        }
    elif aes == "nature":
        pal = {
            "bg1": "#f2f5f1", "bg2": "#e2eade", "paper": "#ffffff", "text": "#1c2b1e",
            "note": "#465e49", "accent": "#497151", "tape": "#c6d8c4", "band": "#d8e4d6",
            "star": "#6a9372", "hl": "#92b298"
        }
    elif aes == "girly":
        pal = {
            "bg1": "#fdf7f4", "bg2": "#f8ebe3", "paper": "#ffffff", "text": "#3d2b27",
            "note": "#7a5952", "accent": "#f28e82", "tape": "#f7c7be", "band": "#fae3dc",
            "star": "#f28e82", "hl": "#fbc4bc"
        }
    elif aes == "vintage":
        pal = {
            "bg1": "#f4efe6", "bg2": "#e8dfce", "paper": "#fffcf4", "text": "#2f2519",
            "note": "#5c4a38", "accent": "#a35d33", "tape": "#d4c2a5", "band": "#dfd3be",
            "star": "#c28b58", "hl": "#d8b28a"
        }
    else:
        pal = {
            "bg1": "#faf8f2", "bg2": "#f0ebe1", "paper": "#ffffff", "text": "#2c2523",
            "note": "#5c524b", "accent": "#d49b45", "tape": "#e8d3b9", "band": "#ede6d8",
            "star": "#d49b45", "hl": "#d9b48f"
        }
        
    # 5. Typography
    if aes == "grunge":
        typo = {"title_font": "mono", "body_font": "mono", "annotation_style": "typewriter_mono"}
    elif aes == "coquette":
        typo = {"title_font": "serif_italic", "body_font": "hand", "annotation_style": "handwritten"}
    elif aes == "minimalist":
        typo = {"title_font": "sans_bold", "body_font": "sans", "annotation_style": "clean_sans"}
    elif aes == "desi festive":
        typo = {"title_font": "hand", "body_font": "hand", "annotation_style": "handwritten"}
    elif aes == "vintage":
        typo = {"title_font": "serif", "body_font": "hand", "annotation_style": "handwritten"}
    else:
        typo = {"title_font": "rounded_bold", "body_font": "rounded", "annotation_style": "clean_sans"}
        
    # 6. Motifs
    if aes == "desi festive":
        motifs = ["desi_sticker", "stars", "tape"]
    elif aes == "coquette":
        motifs = ["hearts", "tape", "flowers", "stars"]
    elif aes in ("botanical", "nature"):
        motifs = ["flowers", "tape", "stars"]
    elif theme == "city life":
        motifs = ["tape", "stars", "squiggle", "arrows"]
    elif aes == "grunge":
        motifs = ["tape", "film_strip", "dots", "highlight"]
    elif aes == "minimalist":
        motifs = ["tape", "stars"]
    else:
        motifs = ["tape", "stars", "squiggle"]
        
    # 7. Decoration Density
    if any(w in h for w in ["minimal", "clean", "simple", "spacious", "uncluttered", "few stickers"]):
        density = "minimal"
    elif any(w in h for w in ["heavy", "heavily", "dense", "junk journal", "lots of", "maximalist", "packed", "crowded"]):
        density = "heavily_decorated"
    else:
        density = "balanced"
        
    # 8. Frame Style
    if aes == "desi festive":
        frame_style = "pichwai"
    elif aes == "grunge":
        frame_style = "film"
    elif aes == "minimalist":
        frame_style = "minimal"
    elif aes == "fashion":
        frame_style = "poster"
    else:
        frame_style = "polaroid"
        
    # 9. Explicit Instructions
    preserve_faces = any(w in h for w in ["face", "faces", "portrait", "dont cover", "don't cover", "focus on photo", "photos remain the focus"])
    if "center" in h:
        photo_placement = "center"
    elif "stagger" in h:
        photo_placement = "staggered"
    else:
        photo_placement = "center" if density == "minimal" else "tilted"
        
    layering = "clean" if (density == "minimal" or "clean" in h) else ("overlapped" if "overlap" in h else "layered")
    
    return {
        "main_theme": theme,
        "aesthetic": aes,
        "mood_energy": mood_energy,
        "palette": pal,
        "typography": typo,
        "motifs": motifs,
        "decoration_density": density,
        "frame_style": frame_style,
        "explicit_instructions": {
            "photo_placement": photo_placement,
            "preserve_faces": preserve_faces,
            "layering": layering,
            "user_notes": hint[:120] if hint else "aesthetic visual memories"
        }
    }


def heuristic_vibe(images, n, family="scrapbook", hint=""):
    is_nav = is_navratri_request(hint)
    colors = extract_palette(images)
    av = sum(max(c) for c in colors) / len(colors) / 255
    sa = sum(sat(c) for c in colors) / len(colors)
    tone = "dark" if (is_nav or av < 0.40) else "light"
    
    brief = heuristic_creative_brief(hint, colors, tone)
    
    v = {
        "creative_brief": brief,
        "vibe_name": f"{brief['aesthetic'].title()} {brief['main_theme'].title()}",
        "mood_word": brief["mood_energy"].split()[0],
        "tone": tone,
        "family": "scrapbook",
        "style": brief["frame_style"],
        "font": brief["typography"]["body_font"],
        "elements": brief["motifs"]
    }
    return clean_vibe(v, n, hint)


def clean_vibe(raw, n, hint=""):
    raw_brief = raw.get("creative_brief")
    is_nav = is_navratri_request(hint, brief=raw_brief, vibe=raw)
    
    # Extract or construct creative brief
    raw_brief = raw.get("creative_brief")
    fallback_brief = heuristic_creative_brief(hint, tone=raw.get("tone") or ("dark" if is_nav else "light"))
    
    if isinstance(raw_brief, dict):
        brief = {
            "main_theme": str(raw_brief.get("main_theme") or fallback_brief["main_theme"])[:40],
            "aesthetic": str(raw_brief.get("aesthetic") or fallback_brief["aesthetic"])[:40],
            "mood_energy": str(raw_brief.get("mood_energy") or fallback_brief["mood_energy"])[:40],
            "palette": {},
            "typography": {},
            "motifs": [],
            "decoration_density": raw_brief.get("decoration_density") if raw_brief.get("decoration_density") in ("minimal", "balanced", "heavily_decorated") else fallback_brief["decoration_density"],
            "frame_style": raw_brief.get("frame_style") if raw_brief.get("frame_style") in STYLES else fallback_brief["frame_style"],
            "explicit_instructions": {}
        }
        
        # Validate palette
        raw_pal = raw_brief.get("palette") if isinstance(raw_brief.get("palette"), dict) else {}
        fb_pal = fallback_brief["palette"]
        for col_key in ["bg1", "bg2", "paper", "text", "note", "accent", "tape", "band", "star", "hl"]:
            val = str(raw_pal.get(col_key) or fb_pal.get(col_key, "#ffffff")).strip()
            if not val.startswith("#") or len(val) not in (4, 7):
                val = fb_pal.get(col_key, "#ffffff")
            brief["palette"][col_key] = val
            
        # Validate typography
        raw_typo = raw_brief.get("typography") if isinstance(raw_brief.get("typography"), dict) else {}
        fb_typo = fallback_brief["typography"]
        tf = str(raw_typo.get("title_font") or fb_typo["title_font"]).strip()
        brief["typography"]["title_font"] = tf if tf in FONT_SPECS else "serif"
        bf = str(raw_typo.get("body_font") or fb_typo["body_font"]).strip()
        brief["typography"]["body_font"] = bf if bf in FONT_SPECS else "hand"
        brief["typography"]["annotation_style"] = str(raw_typo.get("annotation_style") or fb_typo["annotation_style"])[:30]
        
        # Validate motifs
        raw_motifs = raw_brief.get("motifs") or []
        valid_motifs = ["tape", "stars", "squiggle", "arrows", "paperclip", "hearts", "flowers", "film_strip", "dots", "highlight", "desi_sticker"]
        brief["motifs"] = [m for m in raw_motifs if m in valid_motifs] or fallback_brief["motifs"]
        
        # Explicit instructions
        raw_exp = raw_brief.get("explicit_instructions") if isinstance(raw_brief.get("explicit_instructions"), dict) else {}
        fb_exp = fallback_brief["explicit_instructions"]
        brief["explicit_instructions"] = {
            "photo_placement": raw_exp.get("photo_placement") if raw_exp.get("photo_placement") in ("center", "staggered", "tilted") else fb_exp["photo_placement"],
            "preserve_faces": bool(raw_exp.get("preserve_faces", fb_exp["preserve_faces"])),
            "layering": raw_exp.get("layering") if raw_exp.get("layering") in ("clean", "layered", "overlapped") else fb_exp["layering"],
            "user_notes": str(raw_exp.get("user_notes") or fb_exp["user_notes"])[:120]
        }
    else:
        brief = fallback_brief
        
    tone = raw.get("tone") if raw.get("tone") in ("light", "dark") else ("dark" if (is_nav or brief["aesthetic"] == "grunge") else "light")
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
    default_name = "Navratri Garba Nights" if is_nav else f"{brief['aesthetic'].title()} Aesthetic"
    return {
        "creative_brief": brief,
        "vibe_name": str(raw.get("vibe_name") or default_name)[:40],
        "mood_word": word,
        "tone": tone,
        "family": "scrapbook",
        "style": brief["frame_style"],
        "font": brief["typography"]["body_font"],
        "elements": brief["motifs"],
        "slides": slides,
        "cover": {
            "line1": str(c.get("line1") or ("NAVRATRI-" if is_nav else word[:max(3, len(word) // 2)] + "-"))[:14],
            "line2": str(c.get("line2") or ("DUMP" if is_nav else "MOOD"))[:14],
            "kicker": str(c.get("kicker") or (f"{n} festive nights" if is_nav else f"{n} memories"))[:30],
            "sub1": str(c.get("sub1") or ("garba beats & glowing lights" if is_nav else "flip through the story"))[:40],
            "sub2": str(c.get("sub2") or "swipe to twirl")[:40]
        },
        "poster": {
            "headline": str(p.get("headline") or (hint[:24] if hint else "AESTHETIC CAROUSEL"))[:30],
            "kicker": str(p.get("kicker") or ("garba nights & glowing lights" if is_nav else f"{n} visual moments"))[:36],
            "location": str(p.get("location") or ("garba ground" if is_nav else "here & now"))[:40],
            "datetime": str(p.get("datetime") or ("nine nights" if is_nav else "captured in time"))[:40],
            "notes": notes
        },
        "post_caption": str(raw.get("post_caption") or ("nine nights of pure magic, garba beats & lehenga twirls ✨💃🪘" if is_nav else "")).strip(),
        "hashtags": [str(h).lstrip("#").strip() for h in (raw.get("hashtags") or (["navratri", "garbanights", "feelingdesi", "chogada", "festivevibes"] if is_nav else [])) if str(h).strip()][:5],
        "hint": str(hint or raw.get("hint") or "")
    }


def analyze_with_gemini(images, hint="", family="scrapbook", api_key=None, model=None):
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("no AI API key (set GEMINI_API_KEY in .env)")
    candidate_models = [
        model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL),
        "gemini-3.5-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-flash-latest",
        "gemini-3.8-flash"
    ]
    seen = set()
    models = [m for m in candidate_models if m and not (m in seen or seen.add(m))]
    
    parts = [{"text": PROMPT.format(n=len(images), hint=hint or "aesthetic moments")}]
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
                        "maxOutputTokens": 1500
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

    raise RuntimeError(f"AI API error: {last_err}")


def analyze_vibe(images, hint="", use_ai=True, family="auto"):
    """Returns (vibe, source). Never raises: falls back to a colour-based vibe."""
    n = len(images)
    if use_ai:
        try:
            v = clean_vibe(analyze_with_gemini(images, hint, family), n, hint)
            if family in FAMILIES:
                v["family"] = family
            return v, "AI"
        except Exception as e:
            return heuristic_vibe(images, n, family, hint), "colour-based fallback"
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


def heart(size, color, alpha=255):
    def fn(d, s):
        w = size * s
        scale = w / 36.0
        cx, cy = w / 2, w / 2 + 2 * s
        pts = []
        for deg in range(0, 360, 4):
            t = math.radians(deg)
            x = cx + 16 * (math.sin(t) ** 3) * scale
            y = cy - (13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)) * scale
            pts.append((x, y))
        d.polygon(pts, fill=(*color, alpha))
    return aa_layer(size, size, fn)


def flower(size, color, alpha=255, petals=5):
    def fn(d, s):
        cx, cy = size * s / 2, size * s / 2
        r_center = size * s * 0.16
        r_petal = size * s * 0.22
        dist = size * s * 0.26
        for i in range(petals):
            ang = i * (2 * math.pi / petals)
            px = cx + dist * math.cos(ang)
            py = cy + dist * math.sin(ang)
            d.ellipse([px - r_petal, py - r_petal, px + r_petal, py + r_petal], fill=(*color, alpha))
        d.ellipse([cx - r_center, cy - r_center, cx + r_center, cy + r_center], fill=(255, 248, 220, alpha))
    return aa_layer(size, size, fn)


def paperclip(w, h, color, alpha=230):
    def fn(d, s):
        thick = max(2, int(w * s * 0.12))
        pad = thick + 2 * s
        pts = [
            (pad, h * s - pad),
            (pad, pad * 2),
            (w * s - pad, pad * 2),
            (w * s - pad, h * s - pad),
            (w * s / 2, h * s - pad),
            (w * s / 2, pad * 3)
        ]
        d.line(pts, fill=(*color, alpha), width=thick, joint="curve")
    return aa_layer(w, h, fn)


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


# ============================================================ photo helpers & composition engine
def fit_photo(img, size, centering=(0.5, 0.4)):
    return ImageOps.fit(img.convert("RGB"), size, Image.LANCZOS, centering=centering)


def cover_crop(img, W, H, fx=0.5, fy=0.5, zoom=1.0):
    iw, ih = img.size
    scale = max(W / iw, H / ih) * max(zoom, 1.0)
    cw, ch = W / scale, H / scale
    cx, cy = min(max(fx * iw, cw / 2), iw - cw / 2), min(max(fy * ih, ch / 2), ih - ch / 2)
    return img.resize((W, H), Image.LANCZOS, box=(cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2))


def analyze_photo_composition(img):
    """Fast, local saliency and composition analysis using PIL and NumPy (<2ms per image).
    Identifies main subject, approximate focal point, face-presence, scene type, and empty quadrants.
    """
    orig_w, orig_h = img.size
    aspect = orig_w / max(1, orig_h)

    # Work at 128x128 for instantaneous execution
    small = img.convert("RGB").resize((128, 128), Image.Resampling.BILINEAR)
    arr = np.array(small, dtype=np.float32)

    # 1. Edge energy
    gray = small.convert("L")
    edges = np.array(gray.filter(ImageFilter.FIND_EDGES), dtype=np.float32) / 255.0

    # 2. Color saturation & luminance contrast
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    max_c = np.maximum(np.maximum(r, g), b)
    min_c = np.minimum(np.minimum(r, g), b)
    sat = np.where(max_c > 1.0, (max_c - min_c) / (max_c + 1e-5), 0.0)
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    lum_dev = np.abs(lum - np.median(lum))

    # 3. Skin tone heuristic (typical human face in RGB: R > G > B and localized cluster)
    skin_mask = (r > 95) & (g > 40) & (b > 20) & (r > g) & (g > b) & ((r - g) > 12) & ((r - b) > 15)
    face_prior = np.zeros((128, 128), dtype=np.float32)
    face_prior[12:88, 22:106] = 1.0
    face_energy = skin_mask.astype(np.float32) * face_prior * (edges + 0.3)
    skin_fraction = float(np.mean(skin_mask))
    face_count = float(np.sum(face_energy))
    # Exclude wide uniform wooden floors/walls (>35% of frame)
    has_face = bool(80.0 < face_count < 1400.0 and 0.02 < skin_fraction < 0.35)

    # 4. Saliency map
    saliency = edges * 0.45 + sat * 0.25 + lum_dev * 0.30
    if has_face:
        saliency += face_energy * 0.50

    total_sal = float(np.sum(saliency)) or 1.0
    y_coords, x_coords = np.indices((128, 128))
    fx = float(np.sum(x_coords * saliency) / total_sal) / 128.0
    fy = float(np.sum(y_coords * saliency) / total_sal) / 128.0

    # Subject bounding box enclosing ~75-80% of energy
    col_energy = np.sum(saliency, axis=0)
    row_energy = np.sum(saliency, axis=1)
    cum_col = np.cumsum(col_energy) / total_sal
    cum_row = np.cumsum(row_energy) / total_sal

    sx0 = max(0.05, float(np.searchsorted(cum_col, 0.10)) / 128.0)
    sx1 = min(0.95, float(np.searchsorted(cum_col, 0.90)) / 128.0)
    sy0 = max(0.05, float(np.searchsorted(cum_row, 0.10)) / 128.0)
    sy1 = min(0.95, float(np.searchsorted(cum_row, 0.90)) / 128.0)
    if sx1 - sx0 < 0.25: sx1 = min(0.95, sx0 + 0.25)
    if sy1 - sy0 < 0.25: sy1 = min(0.95, sy0 + 0.25)

    # 5. Empty space analysis in quadrants and bands
    inv_sal = np.max(saliency) - saliency
    q_tl = float(np.mean(inv_sal[:64, :64]))
    q_tr = float(np.mean(inv_sal[:64, 64:]))
    q_bl = float(np.mean(inv_sal[64:, :64]))
    q_br = float(np.mean(inv_sal[64:, 64:]))
    quad_scores = {"top_left": q_tl, "top_right": q_tr, "bottom_left": q_bl, "bottom_right": q_br}
    empty_quadrants = sorted(quad_scores.keys(), key=lambda k: quad_scores[k], reverse=True)

    band_top = float(np.mean(inv_sal[:36, :]))
    band_bottom = float(np.mean(inv_sal[92:, :]))
    band_left = float(np.mean(inv_sal[:, :36]))
    band_right = float(np.mean(inv_sal[:, 92:]))

    # 6. Scene classification
    if has_face or (aspect < 0.88 and fy < 0.52 and (sy1 - sy0) > 0.45):
        scene_type = "portrait"
    elif aspect > 1.20:
        scene_type = "scenery"
    elif 0.75 <= aspect <= 1.20 and not has_face and (band_left + band_right) > (band_top + band_bottom):
        scene_type = "cafe"
    elif (sx1 - sx0) < 0.65 and (sy1 - sy0) < 0.65:
        scene_type = "object"
    else:
        scene_type = "general"

    return {
        "scene_type": scene_type,
        "focal_point": (round(fx, 3), round(fy, 3)),
        "subject_box": (round(sx0, 3), round(sy0, 3), round(sx1, 3), round(sy1, 3)),
        "has_face": has_face,
        "aspect_ratio": round(aspect, 3),
        "empty_quadrants": empty_quadrants,
        "empty_bands": {"top": band_top, "bottom": band_bottom, "left": band_left, "right": band_right}
    }


def boxes_intersect(b1, b2, margin=0.0):
    """Returns True if box1 (x0, y0, x1, y1) overlaps box2 with an optional margin buffer."""
    return not (b1[2] + margin < b2[0] or b1[0] - margin > b2[2] or
                b1[3] + margin < b2[1] or b1[1] - margin > b2[3])


def compute_slide_composition(photo_info, slide_idx, total_slides, brief, W=1080, H=1350, is_cover=False, rng=None):
    """Layout constraint solver that computes optimal frame placement and ranks candidate sticker slots
    around the photo subject without collisions, respecting user instructions and empty space.
    """
    rng = rng or random.Random(slide_idx)
    exp = brief.get("explicit_instructions", {})
    preserve_faces = exp.get("preserve_faces", False) or photo_info.get("has_face", False)
    placement = exp.get("photo_placement", "tilted")
    scene = photo_info.get("scene_type", "general")
    fx, fy = photo_info.get("focal_point", (0.5, 0.4))
    sx0, sy0, sx1, sy1 = photo_info.get("subject_box", (0.2, 0.2, 0.8, 0.8))

    # 1. Optimal Frame Placement
    if is_cover:
        cx, cy = 0.5, 0.38
        rot = 0.0 if (preserve_faces or brief.get("decoration_density") == "minimal") else -2.5
    elif preserve_faces or placement == "center":
        cx, cy, rot = 0.5, 0.44, 0.0
    elif placement == "staggered":
        cx = 0.46 if slide_idx % 2 == 0 else 0.54
        cy = 0.43 if slide_idx % 2 == 0 else 0.45
        rot = round((-1.5 if slide_idx % 2 == 0 else 1.5), 1)
    else:
        # Scene-aware dynamic composition archetype
        if scene == "scenery":
            cx = 0.5
            cy = 0.46 if photo_info["empty_bands"]["top"] > photo_info["empty_bands"]["bottom"] else 0.43
            rot = round(rng.uniform(-1.5, 1.5), 1)
        elif scene == "portrait":
            cx = 0.5
            cy = 0.44
            rot = round(rng.uniform(-1.5, 1.5) if not preserve_faces else 0.0, 1)
        elif scene == "cafe":
            cx = 0.48 if fx >= 0.5 else 0.52
            cy = 0.44
            rot = round((-2.2 if slide_idx % 2 == 0 else 2.2) + rng.uniform(-0.5, 0.5), 1)
        else: # object
            cx = 0.47 if slide_idx % 2 == 0 else 0.53
            cy = 0.43
            rot = round((-2.5 if slide_idx % 2 == 0 else 2.5), 1)

    # Frame footprint on canvas
    fw_norm = 640.0 / W
    fh_norm = 880.0 / H
    frame_box = (cx - fw_norm / 2, cy - fh_norm / 2, cx + fw_norm / 2, cy + fh_norm / 2)

    # Photo content area inside frame (inset by padding)
    px0 = frame_box[0] + 30.0 / W
    px1 = frame_box[2] - 30.0 / W
    py0 = frame_box[1] + 30.0 / H
    py1 = frame_box[1] + (30.0 + 760.0) / H
    pw = max(0.1, px1 - px0)
    ph = max(0.1, py1 - py0)

    # Subject forbidden zone in canvas normalized coordinates
    buffer_x = 0.04 if not preserve_faces else 0.07
    buffer_y = 0.04 if not preserve_faces else 0.07
    subj_box = (
        max(0.0, px0 + sx0 * pw - buffer_x),
        max(0.0, py0 + sy0 * ph - buffer_y),
        min(1.0, px0 + sx1 * pw + buffer_x),
        min(1.0, py0 + sy1 * ph + buffer_y)
    )

    # Text box (caption/subtitle at bottom, or title block on cover)
    if is_cover:
        text_box = (0.10, 0.60, 0.90, 0.94)
    else:
        text_box = (0.10, 0.82, 0.90, 0.93)

    # Candidate sticker slots around the subject & frame
    candidates = [
        # Bottom-Right frame margin overlap (classic scrapbook sweet spot)
        (min(0.88, frame_box[2] + 0.02), frame_box[3] - 0.06, 170, "bottom_right"),
        # Bottom-Left frame margin overlap
        (max(0.12, frame_box[0] - 0.02), frame_box[3] - 0.06, 170, "bottom_left"),
        # Top-Right corner / floating
        (min(0.88, frame_box[2] + 0.03), max(0.14, frame_box[1] + 0.04), 145, "top_right"),
        # Top-Left corner / floating
        (max(0.12, frame_box[0] - 0.03), max(0.14, frame_box[1] + 0.04), 145, "top_left"),
        # Right flank
        (0.86, cy, 150, "right_flank"),
        # Left flank
        (0.14, cy, 150, "left_flank"),
    ]

    # Score and filter candidate slots
    scored_slots = []
    for (sx, sy, sz, sname) in candidates:
        sz_w = sz / W
        sz_h = sz / H
        stk_box = (sx - sz_w / 2, sy - sz_h / 2, sx + sz_w / 2, sy + sz_h / 2)

        # Hard constraint: strictly inside canvas bounds [0.05, 0.95]
        if stk_box[0] < 0.05 or stk_box[2] > 0.95 or stk_box[1] < 0.05 or stk_box[3] > 0.95:
            continue
        # Hard constraint: NEVER overlap the photo subject / face box!
        if boxes_intersect(stk_box, subj_box):
            continue
        # Hard constraint: NEVER overlap text box
        if boxes_intersect(stk_box, text_box):
            continue

        score = 50.0
        # Empty quadrant preference
        if sname in photo_info.get("empty_quadrants", []):
            rank = photo_info["empty_quadrants"].index(sname)
            score += (4 - rank) * 15.0

        # Diagonal balance with subject focal point
        if fx > 0.52 and "left" in sname:
            score += 25.0
        elif fx < 0.48 and "right" in sname:
            score += 25.0

        if fy > 0.52 and "top" in sname:
            score += 20.0
        elif fy < 0.48 and "bottom" in sname:
            score += 20.0

        # Alternate primary corner across slides for visual variety
        if slide_idx % 2 == 0 and "right" in sname:
            score += 18.0
        elif slide_idx % 2 == 1 and "left" in sname:
            score += 18.0

        scored_slots.append({
            "slot": sname,
            "x": round(sx, 3),
            "y": round(sy, 3),
            "size": sz,
            "box": stk_box,
            "score": score
        })

    scored_slots.sort(key=lambda s: s["score"], reverse=True)
    return {
        "frame": {"cx": cx, "cy": cy, "rot": rot, "centering": (fx, fy)},
        "subject_box": subj_box,
        "slots": scored_slots
    }


FRAME_DIMS = {
    "polaroid": (660, 920, 0), "film": (640, 892, 100), "poster": (668, 848, 150),
    "minimal": (680, 880, 120), "pichwai": (640, 902, 0), "gold_jaali": (640, 858, 0)
}


def make_frame(photo, style, theme, caption, font_kind, centering=(0.5, 0.4)):
    t = {k: resolve_color(v, theme) for k, v in theme.items() if k in ("paper", "text", "accent", "second", "star", "note", "hl", "title")}
    if "paper" not in t:
        t["paper"] = (255, 255, 255)
    if "text" not in t:
        t["text"] = (40, 40, 40)
    if "accent" not in t:
        t["accent"] = (212, 155, 69)
    if style == "polaroid":
        pw, ph, side, top, bottom = 600, 760, 30, 30, 130
        body = Image.new("RGBA", (pw + 2 * side, ph + top + bottom), (*t["paper"], 255))
        body.paste(fit_photo(photo, (pw, ph), centering=centering), (side, top))
        body.putalpha(rounded_mask(body.size, 10))
        k = font_kind if font_kind != "serif" else "hand"
        body.alpha_composite(caption_layer(caption, body.width, k, 62 if k == "hand" else 34, t["text"], height=bottom), (0, top + ph))
        cap = None
    elif style == "film":
        pw, ph, side, tb = 580, 780, 30, 56
        body = Image.new("RGBA", (pw + 2 * side, ph + 2 * tb), (16, 16, 18, 255))
        body.paste(fit_photo(photo, (pw, ph), centering=centering), (side, tb))
        d = ImageDraw.Draw(body)
        for x in range(24, body.width - 30, 54):
            for y in (17, body.height - 37):
                d.rounded_rectangle([x, y, x + 26, y + 20], 5, fill=(235, 230, 220, 255))
        body.putalpha(rounded_mask(body.size, 8))
        cap = caption_layer(caption, body.width, "mono", 32, t["text"], height=100, upper=True)
    elif style == "pichwai":
        frame_asset = get_navratri_asset_path("pichwai_filigree_frame.png")
        if frame_asset:
            raw_f = Image.open(frame_asset).convert("RGBA")
            fw = 640
            fh = int(fw * (raw_f.height / raw_f.width))
            frame_img = raw_f.resize((fw, fh), Image.Resampling.LANCZOS)
            pw = int(fw * (226 / 308))
            ph = int(fh * (361 / 434))
            ox = int(fw * (41 / 308))
            oy = int(fh * (45 / 434))
            body = Image.new("RGBA", (fw, fh), (0, 0, 0, 0))
            body.paste(fit_photo(photo, (pw, ph), centering=centering), (ox, oy))
            body = Image.alpha_composite(body, frame_img)
            cap = None
        else:
            pw, ph, side, top, bottom = 580, 740, 36, 36, 44
            crimson = (88, 11, 20, 255)
            gold = (214, 175, 65, 255)
            ivory = (255, 243, 218, 240)
            body = Image.new("RGBA", (pw + 2 * side, ph + top + bottom), crimson)
            d = ImageDraw.Draw(body)
            d.rectangle([4, 4, body.width - 5, body.height - 5], outline=gold, width=3)
            d.rectangle([12, 12, body.width - 13, body.height - 13], outline=ivory, width=2)
            body.paste(fit_photo(photo, (pw, ph), centering=centering), (side, top))
            cap = None
    elif style == "gold_jaali":
        frame_asset = get_navratri_asset_path("gold_jaali_frame.png")
        if frame_asset:
            raw_f = Image.open(frame_asset).convert("RGBA")
            fw = 640
            fh = int(fw * (raw_f.height / raw_f.width))
            frame_img = raw_f.resize((fw, fh), Image.Resampling.LANCZOS)
            pw = int(fw * (343 / 896))
            ph = int(fh * (522 / 1200))
            ox = int(fw * (277 / 896))
            oy = int(fh * (343 / 1200))
            body = Image.new("RGBA", (fw, fh), (0, 0, 0, 0))
            body.paste(fit_photo(photo, (pw, ph), centering=centering), (ox, oy))
            body = Image.alpha_composite(body, frame_img)
            cap = None
        else:
            body = fit_photo(photo, (640, 860), centering=centering).convert("RGBA")
            cap = None
    elif style == "poster":
        pw, ph, off = 640, 820, 28
        body = Image.new("RGBA", (pw + off, ph + off), (0, 0, 0, 0))
        ImageDraw.Draw(body).rectangle([off, off, pw + off, ph + off], fill=(*t["accent"], 255))
        body.paste(fit_photo(photo, (pw, ph), centering=centering), (0, 0))
        cap = caption_layer(caption, body.width, "sans_bold", 56, t["text"], height=150, upper=True)
    else:
        body = fit_photo(photo, (680, 880), centering=centering).convert("RGBA")
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


def make_inset(photo, w, label, label_color, theme, centering=(0.5, 0.4)):
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


def make_music_player(title="Chogada", artist="Darshan Raval, Asees Kaur", current="1:48", total="4:11", width=480, height=222):
    # Check matching Spotify card
    song_map = {
        "chogada": "spotify_chogada.png",
        "tere chehre": "spotify_tere_chehre.png",
        "dholida": "spotify_dholida.png",
        "kamariya": "spotify_kamariya.png",
        "nagada": "spotify_nagada.png",
    }
    t_lower = (str(title) + " " + str(artist)).lower()
    match_file = None
    for k, v in song_map.items():
        if k in t_lower:
            match_file = v
            break
    if not match_file and "tere" in t_lower:
        match_file = "spotify_tere_chehre.png"
    if not match_file and any(w in t_lower for w in ["chogada", "garba", "navratri"]):
        match_file = "spotify_chogada.png"
        
    if match_file:
        p = get_navratri_asset_path(match_file)
        if p:
            im = Image.open(p).convert("RGBA")
            h = int(width * (im.height / im.width))
            return im.resize((width, h), Image.Resampling.LANCZOS)
    
    # If not matched or custom title, render crisp Spotify style card dynamically
    scale = 2
    W, H = width * scale, int(height * scale)
    card = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle([0, 0, W-1, H-1], radius=22*scale, fill=(25, 8, 12, 230), outline=(255, 255, 255, 30), width=2*scale)
    pad_x, pad_y = 28 * scale, 22 * scale
    f_title = get_font("sans_bold", 24 * scale)
    f_artist = get_font("sans", 16 * scale)
    f_time = get_font("sans", 13 * scale)
    
    d.text((pad_x, pad_y), str(title)[:30], font=f_title, fill=(255, 255, 255, 255))
    d.text((pad_x, pad_y + 30 * scale), str(artist)[:36], font=f_artist, fill=(195, 185, 188, 240))
    
    # Heart
    hx, hy = W - pad_x - 14*scale, pad_y + 16*scale
    r_h = 10 * scale
    d.line([(hx - r_h, hy), (hx, hy + r_h*1.3), (hx + r_h, hy)], fill=(255, 255, 255, 220), width=2*scale)
    d.arc([hx - r_h, hy - r_h, hx, hy + 2*scale], 180, 0, fill=(255, 255, 255, 220), width=2*scale)
    d.arc([hx, hy - r_h, hx + r_h, hy + 2*scale], 180, 0, fill=(255, 255, 255, 220), width=2*scale)
    
    # Progress bar
    bar_y = pad_y + 64 * scale
    bar_w = W - (pad_x * 2)
    bar_h = 4 * scale
    d.rounded_rectangle([pad_x, bar_y, pad_x + bar_w, bar_y + bar_h], radius=2*scale, fill=(255, 255, 255, 60))
    fill_w = int(bar_w * 0.45)
    d.rounded_rectangle([pad_x, bar_y, pad_x + fill_w, bar_y + bar_h], radius=2*scale, fill=(255, 255, 255, 255))
    d.ellipse([pad_x + fill_w - 6*scale, bar_y + (bar_h//2) - 6*scale, pad_x + fill_w + 6*scale, bar_y + (bar_h//2) + 6*scale], fill=(255, 255, 255, 255))
    
    # Time
    time_y = bar_y + 10 * scale
    d.text((pad_x, time_y), current, font=f_time, fill=(180, 175, 178, 220))
    bb = d.textbbox((0, 0), total, font=f_time)
    d.text((pad_x + bar_w - (bb[2] - bb[0]), time_y), total, font=f_time, fill=(180, 175, 178, 220))
    
    # Controls
    ctrl_y = H - pad_y - 20 * scale
    cx = W // 2
    play_r = 20 * scale
    d.ellipse([cx - play_r, ctrl_y - play_r, cx + play_r, ctrl_y + play_r], fill=(255, 255, 255, 255))
    d.polygon([(cx - 8*scale + 2*scale, ctrl_y - 8*scale), (cx + 8*scale + 2*scale, ctrl_y), (cx - 8*scale + 2*scale, ctrl_y + 8*scale)], fill=(20, 8, 12, 255))
    
    # Prev / Next
    d.line([(cx - 65*scale - 10*scale, ctrl_y - 10*scale), (cx - 65*scale - 10*scale, ctrl_y + 10*scale)], fill=(255, 255, 255, 230), width=2*scale)
    d.polygon([(cx - 65*scale + 8*scale, ctrl_y - 10*scale), (cx - 65*scale - 6*scale, ctrl_y), (cx - 65*scale + 8*scale, ctrl_y + 10*scale)], fill=(255, 255, 255, 230))
    
    d.line([(cx + 65*scale + 10*scale, ctrl_y - 10*scale), (cx + 65*scale + 10*scale, ctrl_y + 10*scale)], fill=(255, 255, 255, 230), width=2*scale)
    d.polygon([(cx + 65*scale - 8*scale, ctrl_y - 10*scale), (cx + 65*scale + 6*scale, ctrl_y), (cx + 65*scale - 8*scale, ctrl_y + 10*scale)], fill=(255, 255, 255, 230))
    
    final_h = int(W * (height / width)) // scale
    return card.resize((width, final_h), Image.Resampling.LANCZOS)


def make_feeling_desi_badge(width=320, height=150):
    p = get_navratri_asset_path("feeling_desi.png")
    if p:
        im = Image.open(p).convert("RGBA")
        h = int(width * (im.height / im.width))
        return im.resize((width, h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    card = Image.new("RGBA", (width - 16, height - 16), (248, 240, 226, 255))
    d_card = ImageDraw.Draw(card)
    d_card.rectangle([3, 3, card.width - 4, card.height - 4], outline=(160, 120, 100, 120), width=1)
    draw_lotus_shape(d_card, 1, card.width // 2, 22, 28, 26)
    d_card.text((card.width // 2, 56), "Feeling", font=get_font("hand", 36), fill=(70, 15, 20, 255), anchor="mm")
    d_card.text((card.width // 2, 90), "DESI", font=get_font("sans_bold", 28), fill=(180, 20, 30, 255), anchor="mm")
    card.putalpha(rounded_mask(card.size, 8))
    pad = 8
    canvas.paste(card, (pad, pad))
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sh.paste(card.getchannel("A").point(lambda v: int(v * 0.25)), (pad + 1, pad + 3))
    return Image.alpha_composite(sh.filter(ImageFilter.GaussianBlur(6)), canvas)


def make_desi_sticker(kind="lotus", size=160):
    asset_map = {
        "jhumka": "lotus_jhumka_hd.png",
        "jhumka_hd": "lotus_jhumka_hd.png",
        "jhumka_ref": "jhumka_reference.png",
        "mojri": "embroidered_juttis.png",
        "juttis": "embroidered_juttis.png",
        "mojri_ref": "mojri_reference.png",
        "basket_gajra": "basket_gajra.png",
        "basket": "basket_gajra.png",
        "jasmine": "jasmine_gajra.png",
        "gajra": "jasmine_gajra.png",
        "jasmine_gajra": "jasmine_gajra.png",
        "marigold": "marigold_flower.png",
        "marigold_flower": "marigold_flower.png",
        "marigold_garland": "marigold_garland.png",
        "garland": "marigold_garland.png",
        "pink_lotus": "pink_lotus.png",
        "lotus": "pink_lotus.png",
        "dandiya": "dandiya_sticks.png",
        "dandiya_sticks": "dandiya_sticks.png",
        "diya": "clay_diya.png",
        "clay_diya": "clay_diya.png",
        "chai": "chai_hand.png",
        "mehndi_chai": "chai_hand.png",
        "chai_hand": "chai_hand.png",
        "rickshaw": "rickshaw.png",
        "auto_rickshaw": "rickshaw.png",
    }
    fname = asset_map.get(str(kind).lower())
    if fname:
        p = get_navratri_asset_path(fname)
        if p:
            im = Image.open(p).convert("RGBA")
            ratio = im.width / im.height
            if ratio >= 1:
                tw = size
                th = max(1, int(tw / ratio))
            else:
                th = size
                tw = max(1, int(th * ratio))
            return im.resize((tw, th), Image.Resampling.LANCZOS)

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


def make_lotus_border(width, height=125):
    p = get_navratri_asset_path("pichwai_lotus_tile.png")
    if p:
        tile = Image.open(p).convert("RGBA")
        tw = int(tile.width * (height / tile.height))
        tile_scaled = tile.resize((tw, height), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        for x in range(0, width, tw):
            canvas.paste(tile_scaled, (x, 0))
        d = ImageDraw.Draw(canvas)
        d.line([(0, 0), (width, 0)], fill=(214, 175, 65, 255), width=2)
        d.line([(0, height - 1), (width, height - 1)], fill=(214, 175, 65, 255), width=2)
        return canvas

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
    elif t == "heart":
        put(canvas, heart(int(el.get("size", 60)), col), X, Y, rot, base=col)
    elif t == "flower":
        put(canvas, flower(int(el.get("size", 70)), col, petals=int(el.get("petals", 5))), X, Y, rot, base=col)
    elif t == "paperclip":
        put(canvas, paperclip(int(el.get("w", 42)), int(el.get("h", 90)), col), X, Y, rot, base=col)
    elif t == "inset":
        label_color = resolve_color(el.get("color", "theme:note"), theme)
        centering = tuple(el.get("centering", (0.5, 0.4)))
        put(canvas, make_inset(images[int(el.get("photo", 0)) % nimg], int(el.get("w", 190)), str(el.get("label", "")), label_color, theme, centering=centering),
            X, Y, rot)
    elif t == "frame":
        centering = tuple(el.get("centering", (0.5, 0.4)))
        frame = make_frame(images[int(el.get("photo", 0)) % nimg], el.get("style", "polaroid"), theme, str(el.get("caption", "")),
                           el.get("font", "serif"), centering=centering)
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
            title=str(el.get("title", "Chogada")),
            artist=str(el.get("artist", "Darshan Raval, Asees Kaur")),
            current=str(el.get("current", "1:48")),
            total=str(el.get("total", "4:11")),
            width=int(el.get("w", 480)),
            height=int(el.get("h", 222))
        )
        put(canvas, player, X, Y, rot)
    elif t == "desi_badge":
        badge = make_feeling_desi_badge(int(el.get("w", 330)), int(el.get("h", 150)))
        put(canvas, badge, X, Y, rot)
    elif t in ("sticker", "asset"):
        stk_id = el.get("id") or el.get("kind") or el.get("path", "city-yellow-cab")
        stk = get_sticker_asset(stk_id, int(el.get("size", 160)))
        put(canvas, stk, X, Y, rot)
    elif t == "desi_sticker":
        stk = get_sticker_asset(el.get("kind", "lotus"), int(el.get("size", 160)))
        put(canvas, stk, X, Y, rot)
    elif t == "lotus_border":
        lb = make_lotus_border(W, int(el.get("h", 125)))
        ey = float(el.get("y", 0.5))
        if ey <= 0.15:
            composite(canvas, lb, ox, 0)
        elif ey >= 0.85:
            composite(canvas, lb, ox, canvas.height - lb.height)
        else:
            composite(canvas, lb, ox, int(Y - lb.height // 2))


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
    el_id = kw.pop("id", None) or uuid.uuid4().hex[:6]
    kw["type"] = type_
    kw["id"] = el_id
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


def build_scrapbook(images, vibe, mode="separate", size=(1080, 1350), seed=0, cover=True, hint=""):
    W, H = size
    n = len(images)
    rng = random.Random(seed)
    cont = mode == "continuous"
    
    brief = vibe.get("creative_brief") or {}
    hint_str = str(hint or vibe.get("hint") or "")
    is_nav = is_navratri_request(hint_str, brief=brief, vibe=vibe)
    
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
    elif brief.get("palette"):
        pal = brief["palette"]
        typo = brief.get("typography", {})
        paper_val = pal.get("paper", "#ffffff")
        paper_tuple = hex_to_rgb(paper_val) if isinstance(paper_val, str) and paper_val.startswith("#") else (255, 255, 255)
        theme = {
            "title": pal.get("text", "#2c2523"),
            "star": pal.get("star", pal.get("accent", "#d49b45")),
            "hl": pal.get("hl", pal.get("accent", "#d9b48f")),
            "note": pal.get("note", "#5c524b"),
            "band": pal.get("band", "#ede6d8"),
            "tape": pal.get("tape", "#e8d3b9"),
            "bg1": pal.get("bg1", "#f8f5ee"),
            "bg2": pal.get("bg2", "#f0ebe1"),
            "paper": paper_tuple,
            "accent": pal.get("accent", "#d49b45"),
            "second": pal.get("accent", "#e24358"),
            "text": pal.get("text", "#2c2523"),
            "tone": vibe.get("tone", "light"),
            "title_font": typo.get("title_font", "serif"),
            "body_font": typo.get("body_font", "hand")
        }
    else:
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
    
    density = brief.get("decoration_density", "balanced")
    motifs = brief.get("motifs", ["tape", "stars", "squiggle"])
    frame_style = brief.get("frame_style") or ("pichwai" if is_nav else "polaroid")
    exp = brief.get("explicit_instructions", {})
    preserve_faces = exp.get("preserve_faces", False)
    photo_placement = exp.get("photo_placement", "tilted")
    
    ranked_sticker_objs = rank_theme_stickers(brief, hint_str)
    thematic_stickers = [s.get("id") for s in ranked_sticker_objs if s.get("id")]

    # 0. Analyze composition of all input photographs
    photo_analyses = [analyze_photo_composition(im) for im in images] if images else []

    total_slides = (n + 1) if (cover and not cont) else n
    spec = new_spec(size, mode, theme, grain=True, family="scrapbook", n=total_slides)
    spec["global"].update(counter=True, swipe=True)
    sl = spec["slides"]
    
    slide_offset = 0
    if cover and not cont:
        slide_offset = 1
        if is_nav:
            # Authentic Navratri Desi reference layout with real assets
            cov_p_info = photo_analyses[0] if photo_analyses else {
                "scene_type": "general", "focal_point": (0.5, 0.4), "subject_box": (0.2, 0.2, 0.8, 0.8),
                "has_face": False, "empty_quadrants": ["bottom_right", "top_right"],
                "empty_bands": {"top": 1.0, "bottom": 1.0, "left": 1.0, "right": 1.0}
            }
            cov_centering = cov_p_info["focal_point"]
            cov_els = [
                E("lotus_border", h=125, x=0.5, y=0.04, z=1),
                E("lotus_border", h=125, x=0.5, y=0.96, z=1),
                E("desi_badge", w=330, h=150, x=0.82, y=0.15, rotate=2, z=2),
                E("desi_sticker", kind="basket_gajra", size=240, x=0.78, y=0.32, rotate=4, z=2),
                E("desi_sticker", kind="jhumka", size=180, x=0.76, y=0.48, rotate=6, z=2),
                E("desi_sticker", kind="mojri", size=240, x=0.72, y=0.62, rotate=-12, z=2),
                E("frame", photo=0, centering=cov_centering, style="pichwai", caption="garba night", font="hand", x=0.31, y=0.35, rotate=-1, z=1),
                E("music_player", title="Chogada", artist="Darshan Raval, Asees Kaur", current="1:48", total="4:11", w=480, h=140, x=0.31, y=0.66, rotate=0, z=2),
                E("desi_sticker", kind="mehndi_chai", size=170, x=0.33, y=0.83, rotate=4, z=2),
                E("desi_sticker", kind="rickshaw", size=155, x=0.12, y=0.84, rotate=-4, z=2),
                E("frame", photo=(1 if n > 1 else 0), centering=cov_centering, style="pichwai", caption="chogada vibe", font="hand", x=0.76, y=0.78, rotate=1, z=1),
                E("star", shape="sparkle4", size=48, x=0.56, y=0.16, rotate=12, color="theme:star", z=2),
                E("star", shape="sparkle4", size=36, x=0.56, y=0.88, rotate=-8, color="theme:star", z=2),
            ]
            sl[0].update(bg={"mode": "gradient", "bg1": theme["bg1"], "bg2": theme["bg2"]}, elements=cov_els)
        else:
            headline = vibe.get("poster", {}).get("headline") or vibe.get("vibe_name") or "AESTHETIC STORY"
            kicker = vibe.get("poster", {}).get("kicker") or f"{n} visual moments"
            sub = vibe.get("cover", {}).get("sub1") or "flip through the story"
            
            words = headline.split()
            l1 = " ".join(words[:max(1, len(words)//2)])
            l2 = " ".join(words[max(1, len(words)//2):]) if len(words) > 1 else ""
            
            title_f = theme.get("title_font", "serif")
            body_f = theme.get("body_font", "hand")
            s1 = fit_size(l1, title_f, 0.82 * W, 0, 65, 145)
            
            cov_p_info = photo_analyses[0] if photo_analyses else {
                "scene_type": "general", "focal_point": (0.5, 0.4), "subject_box": (0.2, 0.2, 0.8, 0.8),
                "has_face": False, "empty_quadrants": ["top_right", "top_left", "bottom_right", "bottom_left"],
                "empty_bands": {"top": 1.0, "bottom": 1.0, "left": 1.0, "right": 1.0}
            }
            cov_comp = compute_slide_composition(cov_p_info, 0, n + 1, brief, W, H, is_cover=True, rng=rng)
            cov_rot = cov_comp["frame"]["rot"]
            cov_els = []
            
            # Layered torn paper band (for balanced & heavily_decorated)
            if density == "heavily_decorated":
                cov_els.append(E("torn", y=0.58, h=int(0.35 * H), color="theme:band", jag=16, z=0))
            
            # Washi tape strips on cover
            if "tape" in motifs and density != "minimal":
                cov_els.append(E("tape", w=240, h=60, x=0.25, y=0.08, rotate=-8, color="theme:tape", alpha=220, z=2))
                cov_els.append(E("tape", w=220, h=56, x=0.76, y=0.09, rotate=6, color="theme:tape", alpha=220, z=2))
            
            # Main cover frame with focal point centering
            cov_els.append(
                E("frame", photo=0, centering=cov_comp["frame"]["centering"], style=frame_style,
                  caption=vibe.get("slides", [{}])[0].get("title", "moment 01"),
                  font=body_f, x=cov_comp["frame"]["cx"], y=cov_comp["frame"]["cy"], rotate=cov_rot, z=1)
            )
            
            # Typography block
            cov_els.append(E("text", text=kicker.upper(), font="sans_bold", size=30, color="theme:star", tracking=4, x=0.5, y=0.62, shadow=False))
            cov_els.append(E("text", text=l1, font=title_f, size=s1, color="theme:title", x=0.5, y=0.70, shadow=False))
            if l2:
                s2 = fit_size(l2, title_f, 0.78 * W, 0, 55, 135)
                cov_els.append(E("text", text=l2, font=title_f, size=s2, color="theme:title", x=0.5, y=0.77, shadow=False))
            
            cov_els.extend([
                E("text", text=sub, font=body_f, size=52, color="theme:note", x=0.48, y=0.86, rotate=-1 if density != "minimal" else 0, shadow=False),
                E("arrow", x=0.72, y=0.86, x2=0.86, y2=0.88, bend=35, width=6, color="theme:note", z=2),
                E("text", text="swipe →", font=body_f, size=42, color="theme:note", x=0.84, y=0.92, rotate=4 if density != "minimal" else 0, z=2),
            ])
            
            # Cover decorative motifs based on creative brief & photo composition
            cov_slots = cov_comp.get("slots", [])
            s_cov1 = cov_slots[0] if cov_slots else {"x": 0.82, "y": 0.68, "size": 170}
            s_cov2 = cov_slots[1] if len(cov_slots) > 1 else {"x": 0.16, "y": 0.66, "size": 140}
            
            if density == "minimal":
                if thematic_stickers and not preserve_faces and cov_slots:
                    cov_els.append(E("sticker", id=thematic_stickers[0], size=min(140, s_cov1["size"]),
                                     x=s_cov1["x"], y=s_cov1["y"], rotate=6, z=2))
            else:
                if "hearts" in motifs:
                    cov_els.append(E("heart", size=54, x=0.15, y=0.65, rotate=-12, color="theme:accent", z=2))
                    cov_els.append(E("heart", size=40, x=0.88, y=0.68, rotate=15, color="theme:accent", z=2))
                elif "flowers" in motifs:
                    cov_els.append(E("flower", size=60, x=0.14, y=0.65, rotate=10, color="theme:star", z=2))
                    cov_els.append(E("flower", size=46, x=0.87, y=0.67, rotate=-12, color="theme:star", z=2))
                elif "stars" in motifs:
                    cov_els.append(E("star", shape="sparkle4", size=52, x=0.15, y=0.65, rotate=-12, color="theme:star", z=2))
                    cov_els.append(E("star", shape="sparkle4", size=38, x=0.88, y=0.68, rotate=15, color="theme:star", z=2))
                
                if "paperclip" in motifs:
                    cov_els.append(E("paperclip", w=38, h=88, x=0.22, y=0.17, rotate=12, color="theme:star", z=2))
                
                # City life route doodle on cover
                if any(w in (hint or "").lower() for w in ["city", "street", "route", "doodle"]):
                    cov_els.append(E("squiggle", span=0.40, x=0.5, y=0.92, amp=6, wavelength=60, thick=4, color="theme:hl", z=2))
                
                if thematic_stickers:
                    cov_els.append(E("sticker", id=thematic_stickers[0], size=s_cov1["size"],
                                     x=s_cov1["x"], y=s_cov1["y"], rotate=rng.randint(-8, 8), z=2))
                    if density == "heavily_decorated" and len(thematic_stickers) > 1:
                        cov_els.append(E("sticker", id=thematic_stickers[1], size=s_cov2["size"],
                                         x=s_cov2["x"], y=s_cov2["y"], rotate=rng.randint(-8, 8), z=2))
            
            sl[0].update(bg={"mode": "gradient", "bg1": theme["bg1"], "bg2": theme["bg2"]}, elements=cov_els)

    # In continuous mode, add subtle panoramic backdrop text
    if cont:
        mood_word = ("NAVRATRI" if is_nav else vibe.get("mood_word", "MEMORIES")).upper()
        sl[0]["elements"].append(
            E("text", text=mood_word, font=theme.get("title_font", "serif_italic"), size=180, color="theme:title",
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
        
        # Photo composition analysis for current slide
        p_info = photo_analyses[idx % len(photo_analyses)] if photo_analyses else {
            "scene_type": "general", "focal_point": (0.5, 0.4), "subject_box": (0.2, 0.2, 0.8, 0.8),
            "has_face": False, "empty_quadrants": ["bottom_right", "bottom_left", "top_right", "top_left"],
            "empty_bands": {"top": 1.0, "bottom": 1.0, "left": 1.0, "right": 1.0}
        }
        comp = compute_slide_composition(p_info, idx, n, brief, W, H, is_cover=False, rng=rng)
        cx, cy = comp["frame"]["cx"], comp["frame"]["cy"]
        rot_val = comp["frame"]["rot"]
        centering = comp["frame"]["centering"]
        slots = comp.get("slots", [])
        
        if is_nav:
            slide_els = [
                E("lotus_border", h=125, x=0.5, y=0.04, z=1),
                E("lotus_border", h=125, x=0.5, y=0.96, z=1),
                E("frame", photo=idx, centering=centering, style=frame_style, caption=title, font="hand", x=cx, y=cy, rotate=rot_val, z=1),
                E("tape", w=220, h=54, x=cx + rng.uniform(-0.04, 0.04), y=cy - 0.28, rotate=round(rot_val + rng.uniform(-6, 6), 1),
                  color="theme:tape", alpha=230, z=2),
                E("text", text=subtitle, font="hand", size=52, color="theme:note", max_w=0.82, x=cx, y=0.86,
                  rotate=round(rng.uniform(-2, 2), 1), shadow=True, line_gap=1.05),
                E("star", shape="sparkle4", size=rng.randint(40, 65), x=0.14 if idx % 2 == 0 else 0.86,
                  y=0.18 + rng.uniform(-0.04, 0.04), rotate=rng.randint(-15, 15), color="theme:star", z=2),
                E("star", shape="sparkle4", size=rng.randint(28, 44), x=0.88 if idx % 2 == 0 else 0.12,
                  y=0.72 + rng.uniform(-0.04, 0.04), rotate=rng.randint(-15, 15), color="theme:star", z=2),
            ]
            
            desi_stickers_pool = [
                [("marigold_garland", 0.5, 0.16, 0), ("jhumka", 0.84, 0.26, 8), ("mojri", 0.15, 0.74, -12)],
                [("jasmine_gajra", 0.84, 0.22, -6), ("dandiya", 0.16, 0.76, 20), ("mehndi_chai", 0.85, 0.72, 6)],
                [("marigold", 0.84, 0.22, 10), ("diya", 0.16, 0.24, 0), ("rickshaw", 0.15, 0.74, -6)],
                [("lotus", 0.84, 0.22, 0), ("basket_gajra", 0.16, 0.76, 4), ("jhumka", 0.85, 0.72, -8)],
            ]
            stk_set = desi_stickers_pool[idx % len(desi_stickers_pool)]
            for kind, sx, sy, srot in stk_set:
                sz = 260 if kind == "marigold_garland" else (210 if kind in ("basket_gajra", "dandiya", "jasmine_gajra") else 165)
                slide_els.append(E("desi_sticker", kind=kind, size=sz, x=sx, y=sy, rotate=srot, z=2))
                
            sl[target_idx].update(
                bg={"mode": "gradient", "bg1": theme["bg1"], "bg2": theme["bg2"]},
                elements=slide_els
            )
        else:
            slide_els = []
            
            # 1. Background torn paper band: only when heavily decorated
            if density == "heavily_decorated":
                slide_els.append(E("torn", y=0.76, h=int(0.24 * H), color="theme:band", jag=14, z=0))
            
            # 2. Main photo frame with subject-aware focal centering
            body_f = theme.get("body_font", "hand")
            slide_els.append(
                E("frame", photo=idx, centering=centering, style=frame_style, caption=title, font=body_f, x=cx, y=cy, rotate=rot_val, z=1)
            )
            
            # 3. Washi tape (if "tape" in motifs and not minimal with preserve_faces)
            if "tape" in motifs and density != "minimal":
                tape_y = cy - 0.31 if preserve_faces else cy - 0.28
                slide_els.append(
                    E("tape", w=220, h=54, x=cx + rng.uniform(-0.03, 0.03), y=tape_y,
                      rotate=round(rot_val + rng.uniform(-5, 5), 1), color="theme:tape", alpha=225, z=2)
                )
            
            # 4. Story annotation text (protected in bottom canvas margin)
            note_rot = round(rng.uniform(-1.5, 1.5), 1) if density != "minimal" else 0
            slide_els.append(
                E("text", text=subtitle, font=body_f, size=52, color="theme:note", max_w=0.82, x=cx, y=0.86,
                  rotate=note_rot, shadow=False, line_gap=1.05)
            )
            
            # 5. Thematic stickers placed in photo-aware, non-colliding candidate slots
            if not is_nav and thematic_stickers:
                stk_offset = 1 if cover else 0
                s1_pos = (slots[0]["x"], slots[0]["y"], slots[0]["size"]) if len(slots) > 0 else (0.84 if idx % 2 == 0 else 0.16, 0.74, 165)
                s2_pos = (slots[1]["x"], slots[1]["y"], slots[1]["size"]) if len(slots) > 1 else (0.16 if idx % 2 == 0 else 0.84, 0.18, 135)
                
                if density == "minimal":
                    # Minimal: placed on alternating slides only, small size, high breathing room
                    if idx % 2 == 0:
                        stk_id = thematic_stickers[(stk_offset + idx // 2) % len(thematic_stickers)]
                        slide_els.append(E("sticker", id=stk_id, size=min(140, s1_pos[2]), x=s1_pos[0], y=s1_pos[1], rotate=round(rng.uniform(-6, 6), 1), z=2))
                elif density == "balanced":
                    # Balanced: 1 sticker per slide, non-adjacent repetition, photo-aware slot
                    stk_id = thematic_stickers[(stk_offset + idx) % len(thematic_stickers)]
                    slide_els.append(E("sticker", id=stk_id, size=s1_pos[2], x=s1_pos[0], y=s1_pos[1], rotate=rng.randint(-12, 12), z=2))
                else:
                    # Heavily decorated: 2 stickers per slide in opposing photo-free slots
                    stk1 = thematic_stickers[(stk_offset + idx * 2) % len(thematic_stickers)]
                    slide_els.append(E("sticker", id=stk1, size=s1_pos[2], x=s1_pos[0], y=s1_pos[1], rotate=rng.randint(-12, 12), z=2))
                    
                    if len(thematic_stickers) > 1:
                        stk2 = thematic_stickers[(stk_offset + idx * 2 + 1) % len(thematic_stickers)]
                        slide_els.append(E("sticker", id=stk2, size=s2_pos[2], x=s2_pos[0], y=s2_pos[1], rotate=rng.randint(-10, 10), z=2))

            # 6. Secondary motifs (stars, hearts, route doodles, flowers) avoiding photo subject
            if density != "minimal":
                p_left = (0.14 if idx % 2 == 0 else 0.86, 0.18 + rng.uniform(-0.03, 0.03))
                p_right = (0.88 if idx % 2 == 0 else 0.12, 0.72 + rng.uniform(-0.03, 0.03))
                
                # Check collision with subject box and nudge if needed
                subj_box = comp["subject_box"]
                if boxes_intersect((p_left[0] - 0.04, p_left[1] - 0.04, p_left[0] + 0.04, p_left[1] + 0.04), subj_box):
                    p_left = (0.09 if idx % 2 == 0 else 0.91, 0.16)
                if boxes_intersect((p_right[0] - 0.04, p_right[1] - 0.04, p_right[0] + 0.04, p_right[1] + 0.04), subj_box):
                    p_right = (0.91 if idx % 2 == 0 else 0.09, 0.76)
                
                if "hearts" in motifs:
                    slide_els.append(E("heart", size=rng.randint(48, 66), x=p_left[0], y=p_left[1],
                                       rotate=rng.randint(-18, 18), color="theme:accent", z=2))
                elif "flowers" in motifs:
                    slide_els.append(E("flower", size=rng.randint(55, 75), x=p_left[0], y=p_left[1],
                                       rotate=rng.randint(-25, 25), color="theme:star", z=2))
                elif "stars" in motifs:
                    slide_els.append(E("star", shape="sparkle4", size=rng.randint(42, 68), x=p_left[0], y=p_left[1],
                                       rotate=rng.randint(-15, 15), color="theme:star", z=2))
                
                if "flowers" in motifs and "hearts" in motifs:
                    slide_els.append(E("flower", size=rng.randint(45, 62), x=p_right[0], y=p_right[1],
                                       rotate=rng.randint(-20, 20), color="theme:star", z=2))
                elif "stars" in motifs:
                    slide_els.append(E("star", shape="sparkle4", size=rng.randint(28, 44), x=p_right[0], y=p_right[1],
                                       rotate=rng.randint(-15, 15), color="theme:star", z=2))
                
                # City life route doodles
                if any(w in (hint or "").lower() for w in ["city", "street", "route", "doodle"]) and idx % 2 == 0:
                    slide_els.append(E("squiggle", span=0.45, x=0.5, y=0.92, amp=6, wavelength=60, thick=4, color="theme:hl", z=2))
                    slide_els.append(E("arrow", x=0.18, y=0.88, x2=0.28, y2=0.91, bend=-20, width=5, color="theme:note", z=2))
                
                if not cont:
                    if density == "heavily_decorated" and n > 1 and idx % 2 == 1 and not preserve_faces:
                        inset_ph = (idx + 1) % n
                        inset_centering = photo_analyses[inset_ph]["focal_point"] if photo_analyses else (0.5, 0.4)
                        slide_els.append(E("inset", photo=inset_ph, centering=inset_centering, w=200, label=label, x=0.82, y=0.22, rotate=6, color="theme:note", z=2))
                        slide_els.append(E("tape", w=120, h=40, x=0.82, y=0.14, rotate=-10, color="theme:hl", alpha=200, z=3))
                    elif "squiggle" in motifs and idx % 2 == 0 and not any(w in (hint or "").lower() for w in ["city", "street"]):
                        slide_els.append(E("squiggle", span=0.45, x=0.5, y=0.92, amp=5, wavelength=65, thick=5, color="theme:hl", z=2))
                
            sl[target_idx].update(
                bg={"mode": "gradient", "bg1": theme["bg1"], "bg2": theme["bg2"]},
                elements=slide_els
            )

    # In continuous mode, add cross-seam scrapbook bridge elements connecting every pair of slides
    if cont:
        for b in range(1, n):
            prev_idx = b - 1
            tape_y = 0.22 if b % 2 == 1 else 0.70
            tape_rot = rng.uniform(-10, 10)
            sl[prev_idx]["elements"].append(
                E("tape", w=260, h=62, x=1.0, y=tape_y, rotate=round(tape_rot, 1),
                  color="theme:tape", alpha=235, z=2)
            )
            
            # Bridge motif: heart, flower, or star
            if "hearts" in motifs:
                sl[prev_idx]["elements"].append(
                    E("heart", size=rng.randint(52, 74), x=1.0,
                      y=0.48 + rng.uniform(-0.10, 0.10), rotate=rng.randint(-15, 15),
                      color="theme:accent", z=2)
                )
            elif "flowers" in motifs:
                sl[prev_idx]["elements"].append(
                    E("flower", size=rng.randint(55, 75), x=1.0,
                      y=0.48 + rng.uniform(-0.10, 0.10), rotate=rng.randint(-20, 20),
                      color="theme:star", z=2)
                )
            else:
                sl[prev_idx]["elements"].append(
                    E("star", shape="sparkle4", size=rng.randint(52, 78), x=1.0,
                      y=0.48 + rng.uniform(-0.12, 0.12), rotate=rng.randint(-15, 15),
                      color="theme:star", z=2)
                )
            
            # Thematic cross-seam bridge sticker
            if thematic_stickers and not is_nav and b % 2 == 0:
                bridge_stk = thematic_stickers[(b + 1) % len(thematic_stickers)]
                sl[prev_idx]["elements"].append(
                    E("sticker", id=bridge_stk, size=135, x=1.0, y=round(0.48 + rng.uniform(-0.06, 0.06), 2),
                      rotate=rng.randint(-8, 8), z=2)
                )
            
            # Additional seam element
            if is_nav:
                desi_seam_kinds = ["lotus", "jhumka", "dandiya", "garba"]
                sl[prev_idx]["elements"].append(
                    E("desi_sticker", kind=desi_seam_kinds[b % len(desi_seam_kinds)], size=130, x=1.0,
                      y=0.34, rotate=round(rng.uniform(-8, 8), 1), z=2)
                )
            elif b % 2 == 1 and n > 1 and density == "heavily_decorated":
                inset_ph = (b + 1) % n
                sl[prev_idx]["elements"].append(
                    E("inset", photo=inset_ph, w=220, label="moment", x=1.0,
                      y=0.34, rotate=round(rng.uniform(-6, 6), 1), color="theme:note", z=2)
                )
                sl[prev_idx]["elements"].append(
                    E("tape", w=130, h=40, x=1.0, y=0.22, rotate=round(rng.uniform(-10, 10), 1),
                      color="theme:hl", alpha=210, z=3)
                )
            else:
                sl[prev_idx]["elements"].append(
                    E("arrow", x=0.86, y=0.88, x2=1.14, y2=0.88, bend=28, width=6, color="theme:note", z=2)
                )
                sl[prev_idx]["elements"].append(
                    E("text", text="continue →", font=theme.get("body_font", "hand"), size=42, color="theme:note",
                      x=0.98, y=0.93, rotate=2, shadow=False, z=2)
                )
            
            if not is_nav and "squiggle" in motifs:
                sl[prev_idx]["elements"].append(
                    E("squiggle", span=0.5, x=1.0, y=0.92, amp=6, wavelength=65, thick=6, color="theme:hl", z=1)
                )
        
    return spec
