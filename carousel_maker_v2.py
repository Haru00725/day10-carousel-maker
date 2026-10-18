"""
Aesthetic Carousel Maker v2: drop photos, AI reads the vibe and writes the words, code builds the carousel,
then you can edit EVERYTHING: text, fonts, colours, stickers, inset photos, positions, backgrounds.

Run:  streamlit run carousel_maker.py
"""

import copy
import hashlib
import io
import json
import os
import random
import zipfile

import streamlit as st
from dotenv import load_dotenv
from PIL import Image, ImageOps

import carousel_engine as ce

load_dotenv()
HAS_KEY = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
SIZES = {"4:5 portrait (1080x1350)": (1080, 1350), "1:1 square (1080x1080)": (1080, 1080)}
FAMILY_LABELS = {"Auto (AI picks)": "auto", "Classic collage": "classic", "Whimsy (big word + stars)": "whimsy",
                 "Scribble poster": "scribble"}
FONT_OPTIONS = ["theme:title", "theme:body"] + ce.FONT_KEYS
LAYERS = {"behind": 0, "normal": 1, "on top": 2}
ICONS = {"text": "🔤", "star": "⭐", "inset": "🖼️", "frame": "📷", "tape": "🩹", "squiggle": "〰️", "ring": "⭕", "dots": "⠿",
         "arrow": "↗️", "highlight": "🔆", "scribble": "✏️", "torn": "📄", "film_strip": "🎞️"}

# (field, widget, ...options) for each element type
FIELDS = {
    "text": [("text", "area"), ("font", "font"), ("size", "int", 16, 420), ("color", "color"), ("align", "choice", ["left", "center", "right"]),
             ("max_w", "float", 0.0, 1.0, 0.01), ("tracking", "int", -20, 30), ("line_gap", "float", 0.7, 2.0, 0.05), ("rotate", "int", -60, 60),
             ("opacity", "float", 0.05, 1.0, 0.05), ("shadow", "bool"), ("upper", "bool")],
    "scribble": [("text", "area"), ("size", "int", 60, 420), ("color", "color"), ("hatch", "int", 5, 24), ("rotate", "int", -30, 30)],
    "star": [("shape", "choice", ["star5", "sparkle4"]), ("size", "int", 16, 300), ("color", "color"), ("rotate", "int", -90, 90)],
    "inset": [("photo", "photo"), ("label", "text"), ("w", "int", 100, 520), ("color", "color"), ("rotate", "int", -20, 20)],
    "frame": [("photo", "photo"), ("style", "choice", ce.STYLES), ("caption", "text"), ("font", "choice", ["serif", "hand", "sans", "mono"]),
              ("rotate", "int", -15, 15)],
    "tape": [("w", "int", 80, 500), ("h", "int", 30, 120), ("color", "color"), ("alpha", "int", 60, 255), ("rotate", "int", -60, 60)],
    "squiggle": [("span", "float", 0.1, 8.0, 0.1), ("amp", "int", 3, 200), ("wavelength", "int", 40, 1600), ("thick", "int", 3, 30),
                 ("color", "color"), ("rotate", "int", -45, 45)],
    "ring": [("size", "int", 40, 500), ("thick", "int", 3, 24), ("color", "color"), ("filled", "bool"), ("alpha", "int", 40, 255)],
    "dots": [("cols", "int", 2, 14), ("rows", "int", 2, 10), ("gap", "int", 16, 60), ("r", "int", 2, 12), ("color", "color")],
    "arrow": [("x2", "float", -0.5, 1.5, 0.01), ("y2", "float", -0.2, 1.2, 0.01), ("bend", "int", -300, 300), ("width", "int", 3, 16),
              ("color", "color")],
    "highlight": [("w", "int", 80, 900), ("h", "int", 50, 400), ("thick", "int", 3, 16), ("color", "color"), ("rotate", "int", -30, 30)],
    "torn": [("h", "int", 100, 900), ("jag", "int", 4, 40), ("color", "color")],
    "film_strip": [("span", "float", 1.0, 10.0, 1.0)],
}
NEW_ELEMENT = {
    "text": dict(text="your text", font="theme:body", size=56, color="theme:note", shadow=True),
    "star": dict(shape="star5", size=60, color="theme:star"),
    "inset": dict(photo=0, w=190, label="label", color="theme:note", rotate=2),
    "frame": dict(photo=0, style="polaroid", caption="caption", font="hand", rotate=0),
    "tape": dict(w=210, h=58, color="theme:accent", rotate=-8, z=2),
    "squiggle": dict(span=1.0, amp=40, wavelength=300, thick=9, color="theme:accent"),
    "ring": dict(size=160, thick=7, color="theme:accent"),
    "dots": dict(cols=6, rows=4, gap=30, r=5, color="theme:accent"),
    "arrow": dict(x2=0.7, y2=0.6, bend=80, width=7, color="#ffffff", z=2),
    "highlight": dict(w=300, h=110, thick=7, color="theme:hl", rotate=-3, z=2),
    "scribble": dict(text="HELLO", font="chunky", size=180, color="theme:hl", hatch=11),
    "torn": dict(y=0.7, h=300, jag=14, color="theme:band", z=0),
}
THEME_COLORS = [("title", "Title colour"), ("star", "Star colour"), ("note", "Small text colour"), ("hl", "Highlight colour"),
                ("text", "Text (classic)"), ("accent", "Accent (classic)"), ("second", "Second accent"), ("bg1", "Background 1"),
                ("bg2", "Background 2"), ("band", "Torn paper colour")]

st.set_page_config(page_title="Aesthetic Carousel Maker", page_icon="🎞️", layout="wide")


# ---------------------------------------------------------------- photos and rendering (cached)
def photos_key(files):
    h = hashlib.sha1()
    for f in files:
        h.update(f.getvalue())
    return h.hexdigest()[:12]


@st.cache_resource(show_spinner=False, max_entries=3)
def decode_photos(pkey, _files):
    out = []
    for f in _files:
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(f.getvalue()))).convert("RGB")
        im.thumbnail((2200, 2200))
        out.append(im)
    return out


@st.cache_resource(show_spinner=False, max_entries=300)
def render_one(key, _spec, _images, i):
    return ce.render_spec(_spec, _images, only=i)[i]


@st.cache_resource(show_spinner=False, max_entries=20)
def render_all(key, _spec, _images):
    return ce.render_spec(_spec, _images)


def get_slides(spec, images, pkey):
    if spec["mode"] == "continuous":
        return render_all(pkey + json.dumps(spec, sort_keys=True), spec, images)
    shared = json.dumps([spec["size"], spec["theme"], spec["global"], len(spec["slides"])], sort_keys=True)
    return [render_one(f"{pkey}|{i}|{shared}|{json.dumps(sl, sort_keys=True)}", spec, images, i) for i, sl in enumerate(spec["slides"])]


# ---------------------------------------------------------------- editor widgets
def pretty(name):
    return {"max_w": "Wrap width", "w": "Width", "h": "Height", "r": "Dot size", "x2": "Arrow end x", "y2": "Arrow end y"}.get(name, name.replace("_", " ").capitalize())


def field_widget(el, f, ver, nimg):
    name, kind, *opts = f
    key = f"{ver}_{el['id']}_{name}"
    cur = el.get(name)
    label = pretty(name)
    if kind == "area":
        el[name] = st.text_area(label, cur if cur is not None else "", key=key, height=80)
    elif kind == "text":
        el[name] = st.text_input(label, cur if cur is not None else "", key=key)
    elif kind in ("int", "float"):
        lo, hi = opts[0], opts[1]
        step = opts[2] if kind == "float" else 1
        cur = (float(cur) if kind == "float" else int(cur)) if cur is not None else (lo if kind == "int" else float(lo))
        el[name] = st.slider(label, min(lo, cur), max(hi, cur), cur, step, key=key)
    elif kind == "bool":
        el[name] = st.checkbox(label, bool(cur), key=key)
    elif kind == "choice":
        options = opts[0]
        el[name] = st.selectbox(label, options, index=options.index(cur) if cur in options else 0, key=key)
    elif kind == "font":
        el[name] = st.selectbox(label, FONT_OPTIONS, index=FONT_OPTIONS.index(cur) if cur in FONT_OPTIONS else 1, key=key,
                                format_func=lambda v: {"theme:title": "Title font (global)", "theme:body": "Body font (global)"}.get(v, v))
    elif kind == "photo":
        el[name] = st.selectbox(label, list(range(nimg)), index=int(cur or 0) % nimg, key=key, format_func=lambda i: f"Photo {i + 1}")
    elif kind == "color":
        resolved = ce.rgb_to_hex(ce.resolve_color(cur or "theme:accent", st.session_state.spec["theme"]))
        picked = st.color_picker(label, resolved, key=key)
        if picked.lower() != resolved.lower():
            el[name] = picked


def position_widgets(el, ver, spec, slide_i):
    n = len(spec["slides"])
    cont = spec["mode"] == "continuous"
    c1, c2, c3 = st.columns(3)
    xlo, xhi = (-0.5, n + 0.5) if cont else (-0.3, 1.3)
    xv = float(el.get("x", 0.5))
    el["x"] = c1.slider("Left / right", min(xlo, xv), max(xhi, xv), xv, 0.01, key=f"{ver}_{el['id']}_x")
    yv = float(el.get("y", 0.5))
    el["y"] = c2.slider("Up / down", min(-0.2, yv), max(1.2, yv), yv, 0.01, key=f"{ver}_{el['id']}_y")
    layer = {v: k for k, v in LAYERS.items()}.get(el.get("z", 1), "normal")
    el["z"] = LAYERS[c3.selectbox("Layer", list(LAYERS), index=list(LAYERS).index(layer), key=f"{ver}_{el['id']}_z")]


def element_summary(el):
    t = el["type"]
    hint = el.get("text") or el.get("label") or el.get("caption") or ""
    return f"{ICONS.get(t, '•')} {t}" + (f": {str(hint).splitlines()[0][:28]}" if hint else "")


def fresh_ids(slide):
    slide = copy.deepcopy(slide)
    for e in slide["elements"]:
        e["id"] = ce.uuid.uuid4().hex[:6]
    return slide


def slide_editor(spec, i, images, pkey, ver, slides_img):
    sl = spec["slides"][i]
    nimg = len(images)
    left, right = st.columns([5, 7])
    with left:
        st.image(slides_img[i])
        st.caption(f"Slide {i + 1} of {len(spec['slides'])}")
        if spec["mode"] == "separate":
            b1, b2 = st.columns(2)
            if b1.button("⧉ Duplicate slide", key=f"{ver}_dup{i}"):
                spec["slides"].insert(i + 1, fresh_ids(sl))
                st.session_state["_next_view"] = f"Slide {i + 2}"
                st.rerun()
            if b2.button("🗑️ Delete slide", key=f"{ver}_del{i}", disabled=len(spec["slides"]) <= 1):
                spec["slides"].pop(i)
                st.session_state["_next_view"] = "Overview"
                st.rerun()
    with right:
        bg = sl["bg"]
        with st.expander("🎨 Background", expanded=False):
            modes = ["photo", "collage", "gradient"]
            bg["mode"] = st.selectbox("Background type", modes, index=modes.index(bg.get("mode", "gradient")), key=f"{ver}_bg{i}_mode")
            if bg["mode"] == "photo":
                bg["photo"] = st.selectbox("Photo", list(range(nimg)), index=int(bg.get("photo", 0)) % nimg, key=f"{ver}_bg{i}_ph",
                                           format_func=lambda k: f"Photo {k + 1}")
                c1, c2 = st.columns(2)
                bg["fx"] = c1.slider("Focus left / right", 0.0, 1.0, float(bg.get("fx", 0.5)), 0.01, key=f"{ver}_bg{i}_fx")
                bg["fy"] = c2.slider("Focus up / down", 0.0, 1.0, float(bg.get("fy", 0.5)), 0.01, key=f"{ver}_bg{i}_fy")
                bg["zoom"] = st.slider("Zoom", 1.0, 3.0, float(bg.get("zoom", 1.0)), 0.05, key=f"{ver}_bg{i}_zoom")
            if bg["mode"] == "collage":
                cur = (bg.get("photos") or [0, 1, 2, 3]) + [0, 1, 2, 3]
                cols = st.columns(4)
                bg["photos"] = [cols[k].selectbox(f"Cell {k + 1}", list(range(nimg)), index=int(cur[k]) % nimg, key=f"{ver}_bg{i}_c{k}",
                                                   format_func=lambda p: f"Photo {p + 1}") for k in range(4)]
                bg["gap"] = st.slider("Grid line", 0, 30, int(bg.get("gap", 5)), key=f"{ver}_bg{i}_gap")
            if bg["mode"] in ("photo", "collage"):
                bg["dim"] = st.slider("Darken photo (helps text stand out)", 0.0, 0.7, float(bg.get("dim", 0.0)), 0.01, key=f"{ver}_bg{i}_dim")

        st.markdown("**Elements** (top of the list is drawn first)")
        for j, el in enumerate(list(sl["elements"])):
            with st.expander(element_summary(el), expanded=False):
                a, b, c, d = st.columns(4)
                moved = None
                if a.button("⬆️", key=f"{ver}_up_{el['id']}", help="Move earlier"):
                    moved = ("up", j)
                if b.button("⬇️", key=f"{ver}_dn_{el['id']}", help="Move later"):
                    moved = ("dn", j)
                if c.button("⧉", key=f"{ver}_cp_{el['id']}", help="Duplicate"):
                    moved = ("cp", j)
                if d.button("🗑️", key=f"{ver}_rm_{el['id']}", help="Delete"):
                    moved = ("rm", j)
                if moved:
                    act, k = moved
                    els = sl["elements"]
                    if act == "up" and k > 0:
                        els[k - 1], els[k] = els[k], els[k - 1]
                    elif act == "dn" and k < len(els) - 1:
                        els[k + 1], els[k] = els[k], els[k + 1]
                    elif act == "cp":
                        dup = copy.deepcopy(els[k])
                        dup["id"] = ce.uuid.uuid4().hex[:6]
                        dup["x"], dup["y"] = min(dup.get("x", 0.5) + 0.04, 1.2), min(dup.get("y", 0.5) + 0.03, 1.1)
                        els.insert(k + 1, dup)
                    elif act == "rm":
                        els.pop(k)
                    st.rerun()
                position_widgets(el, ver, spec, i)
                for f in FIELDS.get(el["type"], []):
                    field_widget(el, f, ver, nimg)

        add_c1, add_c2 = st.columns([3, 1])
        kind = add_c1.selectbox("Add an element", list(NEW_ELEMENT), key=f"{ver}_addkind{i}", format_func=lambda k: f"{ICONS.get(k, '')} {k}")
        if add_c2.button("➕ Add", key=f"{ver}_add{i}"):
            base = dict(NEW_ELEMENT[kind])
            if kind in ("inset", "frame"):
                base["photo"] = (int(sl["bg"].get("photo", i)) + 1) % nimg
            if kind == "text" and sl["bg"].get("mode") == "gradient":
                base["color"] = "theme:text"
            sl["elements"].append(ce.E(kind, x=0.5, y=0.5, **base))
            st.rerun()


def style_editor(spec, ver):
    th, g = spec["theme"], spec["global"]
    st.markdown("**Colour preset** (changes title, stars, small text and highlight)")
    preset = st.selectbox("Preset", ["(keep current)"] + list(ce.PRESETS), key=f"{ver}_preset")
    if preset != "(keep current)" and st.session_state.get("applied_preset") != (ver, preset):
        ce.apply_preset(th, preset)
        st.session_state.applied_preset = (ver, preset)
        for k, _ in THEME_COLORS:
            st.session_state.pop(f"{ver}_th_{k}", None)
        st.rerun()
    cols = st.columns(5)
    for n, (k, label) in enumerate(THEME_COLORS):
        th[k] = cols[n % 5].color_picker(label, th.get(k, "#ffffff"), key=f"{ver}_th_{k}")
    c1, c2 = st.columns(2)
    th["title_font"] = c1.selectbox("Title font (global)", ce.FONT_KEYS, index=ce.FONT_KEYS.index(th.get("title_font", "rounded_bold")), key=f"{ver}_tf")
    th["body_font"] = c2.selectbox("Body font (global)", ce.FONT_KEYS, index=ce.FONT_KEYS.index(th.get("body_font", "rounded")), key=f"{ver}_bf")
    t1, t2, t3 = st.columns(3)
    g["grain"] = t1.checkbox("Film grain", bool(g.get("grain")), key=f"{ver}_grain")
    g["counter"] = t2.checkbox("Slide counter (01 / 06)", bool(g.get("counter", True)), key=f"{ver}_counter")
    g["swipe"] = t3.checkbox("'swipe' hint on slide 1", bool(g.get("swipe", True)), key=f"{ver}_swipe")
    st.caption("Elements set to a theme colour or font follow these. If you pick a custom colour or font on one element, that element keeps it.")


# ---------------------------------------------------------------- page
st.title("🎞️ Aesthetic Carousel Maker")
st.caption("Drop your photos. AI reads the vibe and writes the words. Then edit everything.")

files = st.file_uploader("Your photos (5-6 works best, up to 10)", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True)
c1, c2, c3 = st.columns([2, 2, 3])
family_label = c1.radio("Style family", list(FAMILY_LABELS))
with c2:
    mode_label = st.radio("Classic layout", ["Separate slides", "Continuous swipe"], help="Continuous swipe is for the classic family.")
    size_label = st.radio("Size", list(SIZES), horizontal=True)
with c3:
    hint = st.text_input("What is it about? (optional)", placeholder="e.g. 5 weekend hobbies, or: birthday party Oct 6, 4:40pm")
    use_ai = st.toggle("Let Gemini read the photos and write the words", value=HAS_KEY,
                       help="Photos go to the Gemini API only when this is on. Off = colour-based style with placeholder words.")
    cover = st.checkbox("Whimsy: add a cover slide (2x2 collage)", True)
if use_ai and not HAS_KEY:
    st.warning("No GEMINI_API_KEY in .env, so it will use the colour-based style and placeholder words.")
if len(files or []) > 10:
    st.error("Please use 10 photos or fewer.")
    st.stop()

go = st.button("✨ Create carousel", type="primary", disabled=len(files or []) < 2)
if len(files or []) < 2:
    st.info("Add at least 2 photos to start.")
    st.stop()

pkey = photos_key(files)
images = decode_photos(pkey, files)

if go:
    with st.spinner("Reading the vibe..."):
        fam = FAMILY_LABELS[family_label]
        vibe, source = ce.analyze_vibe(images, hint, use_ai, fam)
        mode = "continuous" if mode_label == "Continuous swipe" and vibe["family"] == "classic" else "separate"
        seed = random.randint(0, 9999)
        spec = ce.build_spec(images, vibe, vibe["family"], mode, SIZES[size_label], seed, cover)
    st.session_state.update(spec=spec, vibe=vibe, source=source, pkey=pkey, view="Overview", ver=st.session_state.get("ver", 0) + 1,
                            build=dict(mode=mode, size=SIZES[size_label], cover=cover))

if "spec" not in st.session_state:
    st.stop()
spec, vibe, ver = st.session_state.spec, st.session_state.vibe, st.session_state.ver
if st.session_state.pkey != pkey:
    st.warning("You changed the photos. Click **Create carousel** again so the design matches them.")

n = len(spec["slides"])
views = ["Overview", "Style"] + [f"Slide {i + 1}" for i in range(n)]
if "_next_view" in st.session_state:
    st.session_state.view = st.session_state.pop("_next_view")
if st.session_state.get("view") not in views:
    st.session_state.view = "Overview"
st.subheader(f"{vibe['vibe_name']}  ·  {spec['family']} family")
st.caption(f"Words and style read by: {st.session_state.source}")
view = st.radio("Edit", views, horizontal=True, key="view", label_visibility="collapsed")

with st.spinner("Rendering..."):
    slides_img = get_slides(spec, images, pkey)

if view == "Overview":
    if spec["mode"] == "continuous":
        st.markdown("**Swipe preview** (slides side by side)")
        st.image(ce.stitch(slides_img))
    cols = st.columns(min(n, 6))
    for i, s in enumerate(slides_img):
        cols[i % len(cols)].image(s, caption=f"Slide {i + 1}")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for i, s in enumerate(slides_img, 1):
            b = io.BytesIO()
            s.save(b, "PNG")
            z.writestr(f"slide_{i:02d}.png", b.getvalue())
    d1, d2 = st.columns(2)
    d1.download_button("⬇️ Download all slides (ZIP)", buf.getvalue(), file_name="carousel.zip", mime="application/zip", type="primary")
    d2.download_button("💾 Save this design (.json)", json.dumps(spec, indent=1), file_name="carousel_design.json", mime="application/json")
    up = st.file_uploader("Load a saved design (.json, use the same photos)", type=["json"], key="designup")
    if up is not None and st.button("Load this design"):
        try:
            loaded = json.loads(up.getvalue())
            assert {"size", "mode", "theme", "global", "slides"} <= set(loaded)
            st.session_state.spec = loaded
            st.session_state.ver += 1
            st.rerun()
        except Exception:
            st.error("That file isn't a valid carousel design.")
    if vibe["post_caption"] or vibe["hashtags"]:
        st.markdown("**Caption idea**")
        st.code((vibe["post_caption"] + "\n\n" + " ".join("#" + h for h in vibe["hashtags"])).strip(), language=None)
elif view == "Style":
    left, right = st.columns([5, 7])
    with left:
        st.image(ce.stitch(slides_img[:3]) if n > 1 else slides_img[0])
    with right:
        style_editor(spec, ver)
        with st.expander("🔄 Start over with a new layout (resets your edits)"):
            fams = ce.FAMILIES
            new_fam = st.selectbox("Style family", fams, index=fams.index(spec["family"]), key=f"{ver}_newfam")
            if st.button("Rebuild", key=f"{ver}_rebuild"):
                b = st.session_state.build
                mode = b["mode"] if new_fam == "classic" else "separate"
                st.session_state.spec = ce.build_spec(images, vibe, new_fam, mode, b["size"], random.randint(0, 9999), b["cover"])
                st.session_state.ver += 1
                st.rerun()
else:
    i = int(view.split()[1]) - 1
    slide_editor(spec, i, images, pkey, ver, slides_img)
