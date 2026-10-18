/**
 * Aesthetic Scrapbook Carousel Maker — Visual Canvas Editor (Fabric.js)
 * Supports Canva-like desktop interactions and Instagram Stories-like mobile gestures.
 */

class ScrapbookEditor {
  constructor(canvasId) {
    this.canvasId = canvasId;
    this.canvas = null;
    this.currentSlideIndex = 0;
    this.spec = null;
    this.images = [];
    this.history = [];
    this.historyIndex = -1;
    this.isHistoryTracking = true;

    // Base native dimensions (e.g. 1080x1350 or 1080x1080)
    this.baseWidth = 1080;
    this.baseHeight = 1350;
    this.scaleFactor = 1;

    this.init();
  }

  init() {
    this.canvas = new fabric.Canvas(this.canvasId, {
      preserveObjectStacking: true,
      selectionColor: 'rgba(212, 155, 69, 0.15)',
      selectionBorderColor: '#c28b5e',
      selectionLineWidth: 1.5,
    });

    // Custom Fabric control styling (Canva-like handles)
    fabric.Object.prototype.transparentCorners = false;
    fabric.Object.prototype.cornerColor = '#2c2523';
    fabric.Object.prototype.cornerStrokeColor = '#ffffff';
    fabric.Object.prototype.borderColor = '#c28b5e';
    fabric.Object.prototype.cornerSize = 10;
    fabric.Object.prototype.cornerStyle = 'circle';
    fabric.Object.prototype.borderScaleFactor = 1.5;

    this.bindEvents();
    this.bindToolbar();
  }

  bindEvents() {
    this.canvas.on('selection:created', (e) => this.onObjectSelected(e.selected[0]));
    this.canvas.on('selection:updated', (e) => this.onObjectSelected(e.selected[0]));
    this.canvas.on('selection:cleared', () => this.onSelectionCleared());

    this.canvas.on('object:modified', () => {
      this.saveHistoryState();
      this.syncCurrentSlideToSpec();
    });

    // Window resize to fit canvas in viewport
    window.addEventListener('resize', () => this.fitCanvasToViewport());

    // Keyboard shortcuts: Cmd+Z (undo), Cmd+Shift+Z (redo), Backspace/Delete (delete element)
    window.addEventListener('keydown', (e) => {
      // Don't intercept if user is typing in an input
      if (['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') {
        if (e.shiftKey) {
          e.preventDefault();
          this.redo();
        } else {
          e.preventDefault();
          this.undo();
        }
      } else if (e.key === 'Backspace' || e.key === 'Delete') {
        const active = this.canvas.getActiveObject();
        if (active && !active.isEditing) {
          e.preventDefault();
          this.deleteSelected();
        }
      }
    });
  }

  fitCanvasToViewport() {
    const viewport = document.getElementById('canvas-viewport');
    if (!viewport || !this.canvas) return;

    const availableWidth = viewport.clientWidth - 48;
    const availableHeight = viewport.clientHeight - 48;

    const scaleW = availableWidth / this.baseWidth;
    const scaleH = availableHeight / this.baseHeight;
    const scale = Math.min(scaleW, scaleH, 0.75); // Don't scale up past comfortable editor size

    this.scaleFactor = Math.max(scale, 0.25);

    this.canvas.setWidth(this.baseWidth * this.scaleFactor);
    this.canvas.setHeight(this.baseHeight * this.scaleFactor);
    this.canvas.setZoom(this.scaleFactor);
    this.canvas.renderAll();
  }

  loadSlide(slideIndex, spec, images) {
    this.currentSlideIndex = slideIndex;
    this.spec = spec;
    this.images = images;

    const size = spec.size || [1080, 1350];
    this.baseWidth = size[0];
    this.baseHeight = size[1];

    this.fitCanvasToViewport();
    this.renderSlideObjects(slideIndex);
    this.resetHistory();
  }

  async renderSlideObjects(slideIndex) {
    this.isHistoryTracking = false;
    this.canvas.clear();

    const slide = this.spec.slides[slideIndex];
    if (!slide) return;

    const theme = this.spec.theme || {};

    // 1. Render Background
    const bg = slide.bg || { mode: 'gradient' };
    const bg1 = theme.bg1 || '#f8f5ee';
    const bg2 = theme.bg2 || '#f0ebe1';

    this.canvas.setBackgroundColor(
      new fabric.Gradient({
        type: 'linear',
        gradientUnits: 'pixels',
        coords: { x1: 0, y1: 0, x2: 0, y2: this.baseHeight },
        colorStops: [
          { offset: 0, color: bg1 },
          { offset: 1, color: bg2 }
        ]
      }),
      () => this.canvas.renderAll()
    );

    // 2. Render Elements
    const elements = slide.elements || [];
    for (const el of elements) {
      await this.createFabricElement(el, theme);
    }

    this.canvas.renderAll();
    this.isHistoryTracking = true;
  }

  async createFabricElement(el, theme) {
    const W = this.baseWidth;
    const H = this.baseHeight;
    const x = (el.x !== undefined ? el.x : 0.5) * W;
    const y = (el.y !== undefined ? el.y : 0.5) * H;
    const angle = el.rotate || 0;

    const resolveColor = (c) => {
      if (!c) return '#2c2523';
      if (c.startsWith('theme:')) {
        const key = c.replace('theme:', '');
        return theme[key] || '#2c2523';
      }
      return c;
    };

    let obj = null;

    switch (el.type) {
      case 'text': {
        const fontFamily = this.getFontName(el.font);
        obj = new fabric.IText(el.text || 'Text', {
          left: x,
          top: y,
          originX: 'center',
          originY: 'center',
          fontFamily: fontFamily,
          fontSize: el.size || 52,
          fill: resolveColor(el.color || 'theme:title'),
          angle: angle,
          textAlign: el.align || 'center',
          shadow: el.shadow ? new fabric.Shadow({ color: 'rgba(0,0,0,0.14)', blur: 4, offsetX: 2, offsetY: 2 }) : null,
          scrapbookType: 'text'
        });
        break;
      }

      case 'frame': {
        // Polaroid Frame
        const photoIdx = el.photo || 0;
        const imgDataUrl = this.images[photoIdx] || this.images[0];
        obj = await this.createPolaroidObject(imgDataUrl, el.caption || '', el.font, x, y, angle, el.w || 540);
        break;
      }

      case 'tape': {
        // Washi Tape Strip
        const w = el.w || 240;
        const h = el.h || 58;
        const color = resolveColor(el.color || 'theme:tape');
        obj = new fabric.Rect({
          left: x,
          top: y,
          width: w,
          height: h,
          originX: 'center',
          originY: 'center',
          fill: color,
          opacity: (el.alpha || 220) / 255,
          angle: angle,
          rx: 3,
          ry: 3,
          shadow: new fabric.Shadow({ color: 'rgba(44,37,35,0.12)', blur: 5, offsetX: 1, offsetY: 2 }),
          scrapbookType: 'tape'
        });
        break;
      }

      case 'star': {
        // Star Doodle
        const sz = el.size || 50;
        const color = resolveColor(el.color || 'theme:star');
        obj = this.createStarObject(x, y, sz, color, angle, el.shape || 'sparkle4');
        break;
      }

      case 'torn': {
        // Torn Paper Layer
        const bandH = el.h || 300;
        const color = resolveColor(el.color || 'theme:band');
        obj = new fabric.Rect({
          left: W / 2,
          top: y,
          width: W + 40,
          height: bandH,
          originX: 'center',
          originY: 'center',
          fill: color,
          shadow: new fabric.Shadow({ color: 'rgba(0,0,0,0.08)', blur: 8, offsetX: 0, offsetY: 4 }),
          selectable: true,
          scrapbookType: 'torn'
        });
        break;
      }

      case 'arrow': {
        // Hand-drawn arrow
        const color = resolveColor(el.color || 'theme:note');
        obj = this.createArrowObject(x, y, angle, color, el.width || 6);
        break;
      }

      case 'squiggle': {
        // Highlight Squiggle
        const color = resolveColor(el.color || 'theme:hl');
        obj = this.createSquiggleObject(x, y, el.span || 0.4, color);
        break;
      }

      case 'inset': {
        // Small Inset Photo
        const photoIdx = el.photo || 0;
        const imgDataUrl = this.images[photoIdx] || this.images[0];
        obj = await this.createInsetPhotoObject(imgDataUrl, el.label || '', x, y, angle, el.w || 220);
        break;
      }
    }

    if (obj) {
      obj.scrapbookData = el;
      this.canvas.add(obj);
    }
  }

  getFontName(fontKey) {
    const map = {
      'hand': 'Caveat',
      'serif': 'Playfair Display',
      'serif_italic': 'Playfair Display',
      'sans': 'Poppins',
      'sans_bold': 'Poppins',
      'mono': 'Space Mono',
      'rounded': 'Fredoka',
      'rounded_bold': 'Fredoka',
      'chunky': 'Fredoka'
    };
    return map[fontKey] || fontKey || 'Caveat';
  }

  createPolaroidObject(imgSrc, caption, fontKey, left, top, angle, width = 540) {
    return new Promise((resolve) => {
      const padding = 24;
      const bottomPadding = 90;
      const height = width * 1.25;

      fabric.Image.fromURL(imgSrc, (img) => {
        const photoW = width - padding * 2;
        const photoH = height - padding - bottomPadding;

        img.set({
          left: padding,
          top: padding,
          originX: 'left',
          originY: 'top',
          scaleX: photoW / img.width,
          scaleY: photoH / img.height,
        });

        const bgRect = new fabric.Rect({
          left: 0,
          top: 0,
          width: width,
          height: height,
          fill: '#ffffff',
          rx: 4,
          ry: 4,
          shadow: new fabric.Shadow({ color: 'rgba(35, 29, 27, 0.18)', blur: 18, offsetX: 2, offsetY: 8 })
        });

        const captionText = new fabric.IText(caption || 'polaroid', {
          left: width / 2,
          top: height - bottomPadding / 2 - 10,
          originX: 'center',
          originY: 'center',
          fontFamily: this.getFontName(fontKey || 'hand'),
          fontSize: 44,
          fill: '#332b28'
        });

        const group = new fabric.Group([bgRect, img, captionText], {
          left: left,
          top: top,
          originX: 'center',
          originY: 'center',
          angle: angle,
          scrapbookType: 'polaroid'
        });

        resolve(group);
      });
    });
  }

  createInsetPhotoObject(imgSrc, label, left, top, angle, width = 220) {
    return new Promise((resolve) => {
      const pad = 12;
      const height = width * 1.15;

      fabric.Image.fromURL(imgSrc, (img) => {
        img.set({
          left: pad,
          top: pad,
          originX: 'left',
          originY: 'top',
          scaleX: (width - pad * 2) / img.width,
          scaleY: (height - pad * 2) / img.height,
        });

        const bg = new fabric.Rect({
          left: 0,
          top: 0,
          width: width,
          height: height,
          fill: '#ffffff',
          rx: 3,
          ry: 3,
          shadow: new fabric.Shadow({ color: 'rgba(0,0,0,0.15)', blur: 10, offsetX: 1, offsetY: 4 })
        });

        const group = new fabric.Group([bg, img], {
          left: left,
          top: top,
          originX: 'center',
          originY: 'center',
          angle: angle,
          scrapbookType: 'inset'
        });

        resolve(group);
      });
    });
  }

  createStarObject(left, top, size, color, angle, shape = 'sparkle4') {
    const pathData = shape === 'star5'
      ? 'M 0,-50 L 14,-15 L 50,-15 L 21,7 L 32,43 L 0,22 L -32,43 L -21,7 L -50,-15 L -14,-15 Z'
      : 'M 0,-50 Q 0,0 50,0 Q 0,0 0,50 Q 0,0 -50,0 Q 0,0 0,-50 Z';

    return new fabric.Path(pathData, {
      left: left,
      top: top,
      originX: 'center',
      originY: 'center',
      fill: color,
      scaleX: size / 70,
      scaleY: size / 70,
      angle: angle,
      shadow: new fabric.Shadow({ color: 'rgba(0,0,0,0.1)', blur: 3, offsetX: 1, offsetY: 1 }),
      scrapbookType: 'star'
    });
  }

  createArrowObject(left, top, angle, color, strokeWidth = 6) {
    const path = new fabric.Path('M 0,0 Q 40,-20 80,10 L 72,-4 M 80,10 L 64,18', {
      left: left,
      top: top,
      originX: 'center',
      originY: 'center',
      fill: '',
      stroke: color,
      strokeWidth: strokeWidth,
      strokeLineCap: 'round',
      strokeLineJoin: 'round',
      angle: angle,
      scrapbookType: 'arrow'
    });
    return path;
  }

  createSquiggleObject(left, top, span = 0.4, color = '#d9b48f') {
    const w = this.baseWidth * span;
    let d = 'M 0,0';
    const steps = 6;
    const stepW = w / steps;
    for (let i = 0; i < steps; i++) {
      const cx = (i + 0.5) * stepW;
      const cy = (i % 2 === 0) ? -10 : 10;
      const ex = (i + 1) * stepW;
      d += ` Q ${cx},${cy} ${ex},0`;
    }

    return new fabric.Path(d, {
      left: left,
      top: top,
      originX: 'center',
      originY: 'center',
      fill: '',
      stroke: color,
      strokeWidth: 8,
      strokeLineCap: 'round',
      scrapbookType: 'squiggle'
    });
  }

  // ==========================================================================
  // Selection & Contextual Toolbar Handling
  // ==========================================================================
  onObjectSelected(obj) {
    const tbText = document.getElementById('tb-text');
    const tbPhoto = document.getElementById('tb-photo');
    const tbSticker = document.getElementById('tb-sticker');

    tbText.classList.add('hidden');
    tbPhoto.classList.add('hidden');
    tbSticker.classList.add('hidden');

    if (obj.type === 'i-text' || obj.type === 'text') {
      tbText.classList.remove('hidden');
      document.getElementById('tb-text-font').value = obj.fontFamily || 'Caveat';
      document.getElementById('tb-text-size').value = obj.fontSize || 48;
      document.getElementById('tb-text-color').value = obj.fill || '#2c2523';
      document.getElementById('btn-text-bold').classList.toggle('active', obj.fontWeight === 'bold');
      document.getElementById('btn-text-italic').classList.toggle('active', obj.fontStyle === 'italic');
    } else if (obj.scrapbookType === 'polaroid' || obj.scrapbookType === 'inset') {
      tbPhoto.classList.remove('hidden');
    } else {
      tbSticker.classList.remove('hidden');
      document.getElementById('tb-sticker-color').value = obj.fill || '#d49b45';
      document.getElementById('tb-sticker-opacity').value = obj.opacity || 1;
    }
  }

  onSelectionCleared() {
    document.getElementById('tb-text').classList.add('hidden');
    document.getElementById('tb-photo').classList.add('hidden');
    document.getElementById('tb-sticker').classList.add('hidden');
  }

  bindToolbar() {
    // Text controls
    document.getElementById('tb-text-font').addEventListener('change', (e) => {
      const active = this.canvas.getActiveObject();
      if (active && (active.type === 'i-text' || active.type === 'text')) {
        active.set('fontFamily', e.target.value);
        this.canvas.renderAll();
        this.syncCurrentSlideToSpec();
      }
    });

    document.getElementById('tb-text-size').addEventListener('input', (e) => {
      const active = this.canvas.getActiveObject();
      if (active && (active.type === 'i-text' || active.type === 'text')) {
        active.set('fontSize', parseInt(e.target.value, 10));
        this.canvas.renderAll();
        this.syncCurrentSlideToSpec();
      }
    });

    document.getElementById('tb-text-color').addEventListener('input', (e) => {
      const active = this.canvas.getActiveObject();
      if (active && (active.type === 'i-text' || active.type === 'text')) {
        active.set('fill', e.target.value);
        this.canvas.renderAll();
        this.syncCurrentSlideToSpec();
      }
    });

    document.getElementById('btn-text-bold').addEventListener('click', () => {
      const active = this.canvas.getActiveObject();
      if (active && (active.type === 'i-text' || active.type === 'text')) {
        const isBold = active.fontWeight === 'bold';
        active.set('fontWeight', isBold ? 'normal' : 'bold');
        document.getElementById('btn-text-bold').classList.toggle('active', !isBold);
        this.canvas.renderAll();
        this.syncCurrentSlideToSpec();
      }
    });

    document.getElementById('btn-text-italic').addEventListener('click', () => {
      const active = this.canvas.getActiveObject();
      if (active && (active.type === 'i-text' || active.type === 'text')) {
        const isItalic = active.fontStyle === 'italic';
        active.set('fontStyle', isItalic ? 'normal' : 'italic');
        document.getElementById('btn-text-italic').classList.toggle('active', !isItalic);
        this.canvas.renderAll();
        this.syncCurrentSlideToSpec();
      }
    });

    // Alignment
    ['left', 'center', 'right'].forEach((align) => {
      document.getElementById(`btn-align-${align}`).addEventListener('click', () => {
        const active = this.canvas.getActiveObject();
        if (active && (active.type === 'i-text' || active.type === 'text')) {
          active.set('textAlign', align);
          this.canvas.renderAll();
          this.syncCurrentSlideToSpec();
        }
      });
    });

    // Layer arrangement
    document.getElementById('btn-layer-up').addEventListener('click', () => this.bringForward());
    document.getElementById('btn-layer-down').addEventListener('click', () => this.sendBackward());
    document.getElementById('btn-delete-element').addEventListener('click', () => this.deleteSelected());

    document.getElementById('btn-layer-up-photo').addEventListener('click', () => this.bringForward());
    document.getElementById('btn-layer-down-photo').addEventListener('click', () => this.sendBackward());
    document.getElementById('btn-delete-photo').addEventListener('click', () => this.deleteSelected());

    document.getElementById('btn-layer-up-sticker').addEventListener('click', () => this.bringForward());
    document.getElementById('btn-layer-down-sticker').addEventListener('click', () => this.sendBackward());
    document.getElementById('btn-delete-sticker').addEventListener('click', () => this.deleteSelected());

    // Undo / Redo buttons
    document.getElementById('btn-undo').addEventListener('click', () => this.undo());
    document.getElementById('btn-redo').addEventListener('click', () => this.redo());

    // Zoom controls
    document.getElementById('btn-zoom-fit').addEventListener('click', () => this.fitCanvasToViewport());
    document.getElementById('btn-zoom-in').addEventListener('click', () => {
      this.scaleFactor *= 1.15;
      this.canvas.setWidth(this.baseWidth * this.scaleFactor);
      this.canvas.setHeight(this.baseHeight * this.scaleFactor);
      this.canvas.setZoom(this.scaleFactor);
      this.canvas.renderAll();
    });
    document.getElementById('btn-zoom-out').addEventListener('click', () => {
      this.scaleFactor *= 0.85;
      this.canvas.setWidth(this.baseWidth * this.scaleFactor);
      this.canvas.setHeight(this.baseHeight * this.scaleFactor);
      this.canvas.setZoom(this.scaleFactor);
      this.canvas.renderAll();
    });

    // Add elements from library
    document.getElementById('add-text-title').addEventListener('click', () => {
      this.addTextElement('SCRAPBOOK TITLE', 'Playfair Display', 80, true);
    });

    document.getElementById('add-text-hand').addEventListener('click', () => {
      this.addTextElement('handwritten memory...', 'Caveat', 64, false);
    });

    document.getElementById('add-text-body').addEventListener('click', () => {
      this.addTextElement('Tell the story behind this moment', 'Poppins', 40, false);
    });

    document.getElementById('add-text-stamp').addEventListener('click', () => {
      this.addTextElement('01 / MEMORY ARCHIVE', 'Space Mono', 32, false);
    });

    // Washi Tape library buttons
    document.querySelectorAll('.tape-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const tapeType = btn.dataset.tape;
        const colorMap = {
          'kraft': 'rgba(228, 203, 169, 0.88)',
          'sage': 'rgba(163, 196, 168, 0.85)',
          'rose': 'rgba(226, 168, 168, 0.85)',
          'gold': 'rgba(244, 218, 142, 0.88)',
        };
        this.addTapeElement(colorMap[tapeType] || colorMap.kraft);
      });
    });

    // Sticker library buttons
    document.querySelectorAll('.sticker-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const sticker = btn.dataset.sticker;
        this.addStickerElement(sticker);
      });
    });

    // Polaroid frame button
    document.getElementById('add-frame-polaroid').addEventListener('click', () => {
      this.addPolaroidElement();
    });

    // Torn paper button
    document.getElementById('add-frame-torn').addEventListener('click', () => {
      this.addTornPaperElement();
    });

    // Paper swatches
    document.querySelectorAll('.paper-swatch').forEach((swatch) => {
      swatch.addEventListener('click', () => {
        document.querySelectorAll('.paper-swatch').forEach(s => s.classList.remove('active'));
        swatch.classList.add('active');
        const color = swatch.style.backgroundColor;
        this.canvas.setBackgroundColor(color, () => this.canvas.renderAll());
        this.syncCurrentSlideToSpec();
      });
    });
  }

  // ==========================================================================
  // Adding New Scrapbook Elements
  // ==========================================================================
  addTextElement(text, fontFamily, fontSize, isBold = false) {
    const obj = new fabric.IText(text, {
      left: this.baseWidth / 2,
      top: this.baseHeight / 2,
      originX: 'center',
      originY: 'center',
      fontFamily: fontFamily,
      fontSize: fontSize,
      fontWeight: isBold ? 'bold' : 'normal',
      fill: '#2c2523',
      scrapbookType: 'text'
    });
    this.canvas.add(obj);
    this.canvas.setActiveObject(obj);
    this.canvas.renderAll();
    this.saveHistoryState();
    this.syncCurrentSlideToSpec();
  }

  addTapeElement(color) {
    const obj = new fabric.Rect({
      left: this.baseWidth / 2,
      top: this.baseHeight / 2,
      width: 250,
      height: 60,
      originX: 'center',
      originY: 'center',
      fill: color,
      angle: -8,
      rx: 3,
      ry: 3,
      shadow: new fabric.Shadow({ color: 'rgba(44,37,35,0.12)', blur: 6, offsetX: 1, offsetY: 2 }),
      scrapbookType: 'tape'
    });
    this.canvas.add(obj);
    this.canvas.setActiveObject(obj);
    this.canvas.renderAll();
    this.saveHistoryState();
    this.syncCurrentSlideToSpec();
  }

  addStickerElement(stickerType) {
    let obj = null;
    const cx = this.baseWidth / 2;
    const cy = this.baseHeight / 2;

    if (stickerType === 'star-sparkle') {
      obj = this.createStarObject(cx, cy, 64, '#d49b45', 0, 'sparkle4');
    } else if (stickerType === 'star-5') {
      obj = this.createStarObject(cx, cy, 60, '#d49b45', 0, 'star5');
    } else if (stickerType === 'arrow') {
      obj = this.createArrowObject(cx, cy, 0, '#4a4039', 6);
    } else if (stickerType === 'squiggle') {
      obj = this.createSquiggleObject(cx, cy, 0.45, '#d9b48f');
    } else if (stickerType === 'heart') {
      obj = new fabric.IText('🤍', {
        left: cx,
        top: cy,
        originX: 'center',
        originY: 'center',
        fontSize: 72,
        scrapbookType: 'sticker'
      });
    } else if (stickerType === 'paperclip') {
      obj = new fabric.IText('📎', {
        left: cx,
        top: cy,
        originX: 'center',
        originY: 'center',
        fontSize: 64,
        angle: 45,
        scrapbookType: 'sticker'
      });
    }

    if (obj) {
      this.canvas.add(obj);
      this.canvas.setActiveObject(obj);
      this.canvas.renderAll();
      this.saveHistoryState();
      this.syncCurrentSlideToSpec();
    }
  }

  async addPolaroidElement() {
    const photoIdx = this.currentSlideIndex % (this.images.length || 1);
    const imgSrc = this.images[photoIdx] || this.images[0];
    const obj = await this.createPolaroidObject(imgSrc, 'sweet moment', 'hand', this.baseWidth / 2, this.baseHeight / 2, -2.5, 520);
    this.canvas.add(obj);
    this.canvas.setActiveObject(obj);
    this.canvas.renderAll();
    this.saveHistoryState();
    this.syncCurrentSlideToSpec();
  }

  addTornPaperElement() {
    const obj = new fabric.Rect({
      left: this.baseWidth / 2,
      top: this.baseHeight * 0.75,
      width: this.baseWidth + 40,
      height: 320,
      originX: 'center',
      originY: 'center',
      fill: '#ede6d8',
      shadow: new fabric.Shadow({ color: 'rgba(0,0,0,0.08)', blur: 8, offsetX: 0, offsetY: 4 }),
      scrapbookType: 'torn'
    });
    this.canvas.add(obj);
    this.canvas.sendToBack(obj);
    this.canvas.setActiveObject(obj);
    this.canvas.renderAll();
    this.saveHistoryState();
    this.syncCurrentSlideToSpec();
  }

  bringForward() {
    const active = this.canvas.getActiveObject();
    if (active) {
      this.canvas.bringForward(active);
      this.canvas.renderAll();
      this.syncCurrentSlideToSpec();
    }
  }

  sendBackward() {
    const active = this.canvas.getActiveObject();
    if (active) {
      this.canvas.sendBackwards(active);
      this.canvas.renderAll();
      this.syncCurrentSlideToSpec();
    }
  }

  deleteSelected() {
    const active = this.canvas.getActiveObject();
    if (active) {
      this.canvas.remove(active);
      this.canvas.discardActiveObject();
      this.canvas.renderAll();
      this.saveHistoryState();
      this.syncCurrentSlideToSpec();
    }
  }

  // ==========================================================================
  // Undo / Redo History
  // ==========================================================================
  resetHistory() {
    this.history = [];
    this.historyIndex = -1;
    this.saveHistoryState();
  }

  saveHistoryState() {
    if (!this.isHistoryTracking || !this.canvas) return;

    // Prune future states if we were in the middle of undo
    if (this.historyIndex < this.history.length - 1) {
      this.history = this.history.slice(0, this.historyIndex + 1);
    }

    const json = JSON.stringify(this.canvas.toDatalessJSON(['scrapbookType', 'scrapbookData']));
    this.history.push(json);
    this.historyIndex++;

    if (this.history.length > 30) {
      this.history.shift();
      this.historyIndex--;
    }
  }

  undo() {
    if (this.historyIndex > 0) {
      this.historyIndex--;
      this.loadHistoryState(this.history[this.historyIndex]);
    }
  }

  redo() {
    if (this.historyIndex < this.history.length - 1) {
      this.historyIndex++;
      this.loadHistoryState(this.history[this.historyIndex]);
    }
  }

  loadHistoryState(stateJson) {
    this.isHistoryTracking = false;
    this.canvas.loadFromJSON(stateJson, () => {
      this.canvas.renderAll();
      this.isHistoryTracking = true;
      this.syncCurrentSlideToSpec();
    });
  }

  // Sync canvas objects back to spec data structure
  syncCurrentSlideToSpec() {
    if (!this.spec || !this.spec.slides[this.currentSlideIndex]) return;
    // In a live system, this informs the main app of modifications
    if (window.onSlideModified) {
      window.onSlideModified(this.currentSlideIndex);
    }
  }
}

window.ScrapbookEditor = ScrapbookEditor;
