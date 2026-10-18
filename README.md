# 🎞️ Aesthetic Scrapbook Carousel Maker

A mobile-first, Canva-like and Instagram Stories-like scrapbook carousel editor. Drop in your photos, let Gemini AI read the vibe and craft heartfelt story copy, and customize every element on an interactive canvas with authentic paper textures, washi tape, torn paper borders, polaroids, and hand-drawn doodles.

Ready to deploy seamlessly on **Vercel** with serverless backend APIs and client-side canvas rendering.

---

## ✨ Features

- **Exclusive Scrapbook Aesthetic**: Focused entirely on warm, tactile scrapbook art direction:
  - Textured paper backgrounds (Warm Cream, Kraft Paper, Sage Linen, Blush Rose, Midnight Chalkboard)
  - Torn-paper edges with authentic jagged contours and realistic soft drop shadows
  - Translucent washi tape strips in pastel and earthy tones
  - Classic Polaroid frames with handwritten captions
  - Doodled stars, sparkle accents, curved arrows, and highlight strokes
- **Dual Visual Canvas Editor (Fabric.js)**:
  - **Desktop (Canva-like)**: Left slide filmstrip, central interactive canvas with drag-and-drop, resize, rotate, and floating contextual toolbars for typography, frames, and stickers.
  - **Mobile (Instagram Stories-like)**: Full-viewport touch stage with pinch-to-zoom/rotate gestures, bottom tool dock, and non-intrusive bottom sheets.
- **Smart Gemini AI Integration**:
  - Analyzes uploaded photos and user story prompt to generate cohesive mood words, storytelling copy, captions, and curated hashtags.
  - Automatic fallback to color & mood heuristics if offline or without API key.
- **Instant High-Res Export**:
  - 4:5 Portrait (1080×1350) and 1:1 Square (1080×1080).
  - High-res PNG downloads and 1-click **Download All as ZIP** bundled directly in the browser via JSZip.
  - Save and Load `.json` design specifications to resume editing anytime.

---

## 🚀 1-Click Deployment to Vercel

1. Push this repository to GitHub (or use your repository: `https://github.com/Haru00725/day10-carousel-maker.git`).
2. Go to [Vercel Dashboard](https://vercel.com/new) and **Import** this Git repository.
3. In **Project Settings > Environment Variables**, add:
   - `GEMINI_API_KEY`: Your Google Gemini API Key.
   - `GEMINI_MODEL`: (Optional, defaults to `gemini-flash-latest` or `gemini-3.8-flash`).
4. Click **Deploy**! Vercel will automatically build the static frontend and Python serverless endpoints in `/api/`.

---

## 💻 Local Development

1. Clone the repository:
   ```bash
   git clone https://github.com/Haru00725/day10-carousel-maker.git
   cd day10-carousel-maker
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Create a `.env` file with your Gemini API key:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   GEMINI_MODEL=gemini-flash-latest
   ```

4. Start the local development server:
   ```bash
   python server.py
   ```
   Open [http://localhost:5001](http://localhost:5001) in your browser.

---

## 📁 Project Structure

```
├── api/
│   └── index.py            # Vercel serverless function & Flask backend
├── css/
│   └── style.css           # Aesthetic Scrapbook design system & responsive layout
├── js/
│   ├── app.js              # State manager, photo uploader & carousel flow
│   ├── editor.js           # Fabric.js visual canvas editor (desktop + mobile)
│   └── canvas-export.js    # High-res client rendering & ZIP bundler
├── fonts/                  # TrueType fonts (Caveat, Playfair, Poppins, Space Mono)
├── index.html              # Modern, semantic mobile-first web app
├── carousel_engine.py      # Core PIL drawing engine & scrapbook layout algorithms
├── requirements.txt        # Python backend dependencies
├── vercel.json             # Vercel serverless route configuration
└── server.py               # Local development server runner
```

---

## 🎨 Scrapbook Color Presets

- **Warm Cream & Espresso**: Rich vintage journal tones with sepia accents.
- **Sage & Botanical**: Calming muted green linen with gold sparkle stars.
- **Vintage Rose**: Romantic memories on warm blush paper.
- **Terracotta & Clay**: Earthy clay hues with warm washi tape.
- **Midnight Journal**: Moody chalkboard dark mode with chalk white and gold washi tape.
