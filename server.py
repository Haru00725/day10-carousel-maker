import base64
import io
import json
import os
import sys
import zipfile
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from PIL import Image, ImageOps

api_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(api_dir)
for p in [api_dir, root_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

import carousel_engine as ce

app = Flask(__name__, static_folder=None)
CORS(app)


def decode_image_data(img_item):
    """Decodes an image from base64 string or data URL."""
    if isinstance(img_item, str):
        if "," in img_item:
            img_item = img_item.split(",", 1)[1]
        raw_bytes = base64.b64decode(img_item)
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw_bytes))).convert("RGB")
        im.thumbnail((1200, 1500))
        return im
    return None


def find_static_file(subpath):
    """Locates static files in root_dir, public/, or api_dir."""
    candidates = [
        os.path.join(root_dir, subpath),
        os.path.join(root_dir, "public", subpath),
        os.path.join(api_dir, subpath),
        os.path.join(api_dir, "public", subpath),
        os.path.join(".", subpath),
        os.path.join("public", subpath)
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


# ==================== STATIC ASSETS & HOMEPAGE ====================
@app.route("/")
@app.route("/index.html")
def serve_index():
    path = find_static_file("index.html")
    if path:
        return send_file(path, mimetype="text/html")
    return "<h1>Scrapbook Carousel Maker</h1><p>index.html not found</p>", 200


@app.route("/css/<path:filename>")
def serve_css(filename):
    path = find_static_file(os.path.join("css", filename))
    if path:
        return send_file(path, mimetype="text/css")
    return "/* CSS not found */", 404


@app.route("/js/<path:filename>")
def serve_js(filename):
    path = find_static_file(os.path.join("js", filename))
    if path:
        return send_file(path, mimetype="application/javascript")
    return "// JS not found", 404


@app.route("/fonts/<path:filename>")
def serve_fonts(filename):
    path = find_static_file(os.path.join("fonts", filename))
    if path:
        return send_file(path)
    return "Font not found", 404


@app.route("/assets/<path:filename>")
def serve_assets(filename):
    path = find_static_file(os.path.join("assets", filename))
    if path:
        return send_file(path)
    return "Asset not found", 404


# ==================== API ROUTING DISPATCHER ====================
def get_target_endpoint():
    endpoint = request.args.get("endpoint")
    if endpoint:
        return endpoint.strip("/").lower()
    
    path = request.path.strip("/")
    if path.startswith("api/"):
        path = path[4:]
    if path.endswith(".py"):
        path = path[:-3]
    return path.lower()


@app.route("/api", methods=["GET", "POST", "OPTIONS"])
@app.route("/api/index", methods=["GET", "POST", "OPTIONS"])
@app.route("/api/<path:subpath>", methods=["GET", "POST", "OPTIONS"])
def vercel_api_entrypoint(subpath=""):
    if request.method == "OPTIONS":
        resp = jsonify({"status": "ok"})
        resp.headers.add("Access-Control-Allow-Origin", "*")
        resp.headers.add("Access-Control-Allow-Headers", "*")
        resp.headers.add("Access-Control-Allow-Methods", "*")
        return resp

    endpoint = get_target_endpoint()
    if not endpoint or endpoint in ("index", "api"):
        endpoint = subpath.strip("/").lower() or "health"

    if endpoint == "health":
        return health_handler()
    elif endpoint == "generate":
        return generate_handler()
    elif endpoint in ("render-slide", "render_slide"):
        return render_slide_handler()
    elif endpoint in ("render-all", "render_all"):
        return render_all_handler()
    elif endpoint in ("export-zip", "export_zip"):
        return export_zip_handler()
    elif endpoint in ("stickers", "assets"):
        return stickers_handler()
    else:
        return jsonify({"error": f"Unknown endpoint '{endpoint}'", "status": 404}), 404


def stickers_handler():
    cat = request.args.get("category", "all")
    q = request.args.get("q", "")
    items = ce.find_stickers(query=q, category=cat)
    return jsonify({
        "status": "ok",
        "total": len(items),
        "stickers": items
    })


def health_handler():
    has_key = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    return jsonify({
        "status": "ok",
        "has_key": has_key,
        "has_ai_key": has_key,
        "has_gemini_key": has_key,
        "model": "creative-ai-engine",
        "families": ce.FAMILIES,
        "presets": list(ce.PRESETS.keys())
    })


def generate_handler():
    try:
        data = request.get_json(force=True)
        raw_images = data.get("images", [])
        if not raw_images or len(raw_images) < 2:
            return jsonify({"error": "Please provide at least 2 images"}), 400

        images = []
        for item in raw_images:
            im = decode_image_data(item)
            if im:
                images.append(im)

        if len(images) < 2:
            return jsonify({"error": "Failed to decode at least 2 valid images"}), 400

        hint = data.get("hint", "")
        use_ai = data.get("use_ai", True)
        family = data.get("family", "scrapbook")
        mode = data.get("mode", "separate")
        preset = data.get("preset", "Warm Cream & Espresso")
        cover = data.get("cover", True)
        
        # Dimensions: default 4:5 portrait (1080x1350)
        size_type = data.get("size", "4:5")
        size = (1080, 1080) if size_type == "1:1" else (1080, 1350)

        # Analyze vibe with AI (or fallback)
        vibe, source = ce.analyze_vibe(images, hint=hint, use_ai=use_ai, family=family)
        
        # Build initial scrapbook specification
        spec = ce.build_spec(images, vibe, family=family, mode=mode, size=size, seed=0, cover=cover)

        # Apply manual preset only if user explicitly selected it from the palette chips
        user_chose_preset = data.get("user_chose_preset", False)
        if user_chose_preset and preset in ce.PRESETS:
            ce.apply_preset(spec["theme"], preset)

        return jsonify({
            "success": True,
            "vibe": vibe,
            "source": source,
            "spec": spec
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/render-slide", methods=["POST"])
def render_slide_handler():
    try:
        data = request.get_json(force=True)
        spec = data.get("spec")
        raw_images = data.get("images", [])
        slide_index = int(data.get("slide_index", 0))

        if not spec or not raw_images:
            return jsonify({"error": "Spec and images are required"}), 400

        images = [decode_image_data(item) for item in raw_images]
        rendered_slide = ce.render_spec(spec, images, only=slide_index)[slide_index]

        buf = io.BytesIO()
        rendered_slide.save(buf, format="JPEG", quality=92)
        b64_img = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

        return jsonify({
            "success": True,
            "slide_index": slide_index,
            "image": b64_img
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/render-all", methods=["POST"])
def render_all_handler():
    try:
        data = request.get_json(force=True)
        spec = data.get("spec")
        raw_images = data.get("images", [])

        if not spec or not raw_images:
            return jsonify({"error": "Spec and images are required"}), 400

        images = [decode_image_data(item) for item in raw_images]
        slides = ce.render_spec(spec, images)

        out_b64 = []
        for s in slides:
            buf = io.BytesIO()
            s.save(buf, format="JPEG", quality=92)
            out_b64.append("data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode())

        return jsonify({
            "success": True,
            "slides": out_b64
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/export-zip", methods=["POST"])
def export_zip_handler():
    try:
        data = request.get_json(force=True)
        spec = data.get("spec")
        raw_images = data.get("images", [])

        if not spec or not raw_images:
            return jsonify({"error": "Spec and images are required"}), 400

        images = [decode_image_data(item) for item in raw_images]
        slides = ce.render_spec(spec, images)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for i, s in enumerate(slides, 1):
                b = io.BytesIO()
                s.save(b, "PNG")
                z.writestr(f"slide_{i:02d}.png", b.getvalue())

        buf.seek(0)
        return send_file(
            buf,
            mimetype="application/zip",
            as_attachment=True,
            download_name="scrapbook_carousel.zip"
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# For local execution
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
