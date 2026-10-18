#!/usr/bin/env python3
"""
Local development server for Aesthetic Scrapbook Carousel Maker.
Serves static frontend files and routes /api/* to Flask backend.
"""

import os
import sys

root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from flask import send_from_directory
from api.index import app

@app.route("/", defaults={"path": "index.html"})
@app.route("/<path:path>")
def serve_static(path):
    # If the file exists in current directory or public, serve it
    if os.path.exists(os.path.join(root_dir, path)):
        return send_from_directory(root_dir, path)
    public_path = os.path.join(root_dir, "public", path)
    if os.path.exists(public_path):
        return send_from_directory(os.path.join(root_dir, "public"), path)
    return send_from_directory(root_dir, "index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"\n==================================================")
    print(f"✨ Aesthetic Scrapbook Carousel Maker running at:")
    print(f"👉 http://localhost:{port}")
    print(f"==================================================\n")
    app.run(host="0.0.0.0", port=port, debug=True)
