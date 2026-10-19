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

    this.isMobile = window.innerWidth <= 768;

    this.init();
  }

  init() {
    this.canvas = new fabric.Canvas(this.canvasId, {
      preserveObjectStacking: true,
      selectionColor: 'rgba(212, 155, 69, 0.15)',
      selectionBorderColor: '#c28b5e',
      selectionLineWidth: 1.5,
      allowTouchScrolling: false, // Prevents webpage bounce on mobile touch drag
    });

    // Custom Fabric control styling (Canva-like touch handles)
    const isTouch = ('ontouchstart' in window) || navigator.maxTouchPoints > 0;
    fabric.Object.prototype.transparentCorners = false;
    fabric.Object.prototype.cornerColor = '#2c2523';
    fabric.Object.prototype.cornerStrokeColor = '#ffffff';
    fabric.Object.prototype.borderColor = '#c28b5e';
    fabric.Object.prototype.cornerSize = isTouch ? 14 : 10;
    fabric.Object.prototype.cornerStyle = 'circle';
    fabric.Object.prototype.borderScaleFactor = isTouch ? 2.0 : 1.5;
    fabric.Object.prototype.touchCornerSize = 32;

    this.bindEvents();
    this.bindToolbar();
    this.bindMobileDock();
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
    window.addEventListener('resize', () => {
      this.isMobile = window.innerWidth <= 768;
      this.fitCanvasToViewport();
    });

    // Keyboard shortcuts
    window.addEventListener('keydown', (e) => {
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

    // Touch gesture enhancements for mobile devices
    this.bindTouchGestures();
  }

  bindTouchGestures() {
    let lastScale = 1;
    let lastAngle = 0;

    this.canvas.on('touch:gesture', (e) => {
      const target = this.canvas.getActiveObject();
      if (!target) return;

      if (e.e.touches && e.e.touches.length === 2) {
        if (e.self.scale) {
          target.scale(lastScale * e.self.scale);
        }
        if (e.self.rotation) {
          target.rotate(lastAngle + e.self.rotation);
        }
        this.canvas.renderAll();
      }
    });

    this.canvas.on('touch:drag', (e) => {
      // Allow single touch drag on active object
      const target = this.canvas.getActiveObject();
      if (target && e.self.x && e.self.y) {
        target.set({
          left: target.left + e.self.x,
          top: target.top + e.self.y
        });
        target.setCoords();
        this.canvas.renderAll();
      }
    });
  }

  fitCanvasToViewport() {
    const viewport = document.getElementById('canvas-viewport');
    if (!viewport || !this.canvas) return;

    const availableWidth = viewport.clientWidth - (this.isMobile ? 16 : 48);
    const availableHeight = viewport.clientHeight - (this.isMobile ? 16 : 48);

    const scaleW = availableWidth / this.baseWidth;
    const scaleH = availableHeight / this.baseHeight;
    const scale = Math.min(scaleW, scaleH);

    this.scaleFactor = Math.max(scale, 0.2);

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

    // Update mobile indicator
    const total = spec.slides ? spec.slides.length : 1;
    const ind = document.getElementById('mobile-slide-indicator');
    if (ind) {
      ind.textContent = `Slide ${String(slideIndex + 1).padStart(2, '0')}/${String(total).padStart(2, '0')}`;
    }

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

    // 1. Background
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

    // 2. Elements
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
        const photoIdx = el.photo || 0;
        const imgDataUrl = this.images[photoIdx] || this.images[0];
        if (el.style === 'pichwai') {
          obj = await this.createPichwaiFrameObject(imgDataUrl, el.caption || '', el.font, x, y, angle, el.w || 520);
        } else if (el.style === 'gold_jaali') {
          obj = await this.createGoldJaaliFrameObject(imgDataUrl, el.caption || '', el.font, x, y, angle, el.w || 520);
        } else {
          obj = await this.createPolaroidObject(imgDataUrl, el.caption || '', el.font, x, y, angle, el.w || 540);
        }
        break;
      }

      case 'music_player': {
        obj = await this.createMusicPlayerObject(el.title, el.artist, el.current, el.total, x, y, angle, el.w || 460, el.h || 130);
        break;
      }

      case 'desi_badge': {
        obj = await this.createFeelingDesiObject(x, y, angle, el.w || 260, el.h || 120);
        break;
      }

      case 'desi_sticker': {
        obj = await this.createDesiStickerObject(el.kind || 'lotus', x, y, angle, el.size || 120);
        break;
      }

      case 'sticker':
      case 'asset': {
        const stkId = el.id || el.sticker_id || el.name || el.kind;
        const stkPath = el.path || '';
        obj = await this.createStickerAssetObject(stkId, stkPath, x, y, angle, el.size || 160);
        break;
      }

      case 'lotus_border': {
        obj = await this.createLotusBorderObject(x, y, W, el.h || 74);
        break;
      }

      case 'tape': {
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
        const sz = el.size || 50;
        const color = resolveColor(el.color || 'theme:star');
        obj = this.createStarObject(x, y, sz, color, angle, el.shape || 'sparkle4');
        break;
      }

      case 'torn': {
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
        const color = resolveColor(el.color || 'theme:note');
        obj = this.createArrowObject(x, y, angle, color, el.width || 6);
        break;
      }

      case 'squiggle': {
        const color = resolveColor(el.color || 'theme:hl');
        obj = this.createSquiggleObject(x, y, el.span || 0.4, color);
        break;
      }

      case 'inset': {
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

  createPichwaiFrameObject(imgSrc, caption, fontKey, left, top, angle, width = 520) {
    return new Promise((resolve) => {
      const frameUrl = '/assets/navratri/pichwai_filigree_frame.png';
      fabric.Image.fromURL(frameUrl, (frameImg) => {
        if (!frameImg || !frameImg.width) {
          resolve(this.createVectorPichwaiFrame(imgSrc, caption, fontKey, left, top, angle, width));
          return;
        }

        const fw = width;
        const fh = width * (frameImg.height / frameImg.width);
        const ox = fw * (41 / 308);
        const oy = fh * (45 / 434);
        const pw = fw * (226 / 308);
        const ph = fh * (361 / 434);

        frameImg.set({
          left: 0,
          top: 0,
          originX: 'left',
          originY: 'top',
          scaleX: fw / frameImg.width,
          scaleY: fh / frameImg.height
        });

        fabric.Image.fromURL(imgSrc, (photoImg) => {
          photoImg.set({
            left: ox,
            top: oy,
            originX: 'left',
            originY: 'top',
            scaleX: pw / photoImg.width,
            scaleY: ph / photoImg.height
          });

          const group = new fabric.Group([photoImg, frameImg], {
            left: left,
            top: top,
            originX: 'center',
            originY: 'center',
            angle: angle,
            shadow: new fabric.Shadow({ color: 'rgba(20, 4, 6, 0.35)', blur: 18, offsetX: 3, offsetY: 7 }),
            scrapbookType: 'frame',
            frameStyle: 'pichwai'
          });

          resolve(group);
        }, { crossOrigin: 'anonymous' });
      }, { crossOrigin: 'anonymous' });
    });
  }

  createGoldJaaliFrameObject(imgSrc, caption, fontKey, left, top, angle, width = 520) {
    return new Promise((resolve) => {
      const frameUrl = '/assets/navratri/gold_jaali_frame.png';
      fabric.Image.fromURL(frameUrl, (frameImg) => {
        if (!frameImg || !frameImg.width) {
          resolve(this.createVectorPichwaiFrame(imgSrc, caption, fontKey, left, top, angle, width));
          return;
        }

        const fw = width;
        const fh = width * (frameImg.height / frameImg.width);
        const ox = fw * (277 / 896);
        const oy = fh * (343 / 1200);
        const pw = fw * (343 / 896);
        const ph = fh * (522 / 1200);

        frameImg.set({
          left: 0,
          top: 0,
          originX: 'left',
          originY: 'top',
          scaleX: fw / frameImg.width,
          scaleY: fh / frameImg.height
        });

        fabric.Image.fromURL(imgSrc, (photoImg) => {
          photoImg.set({
            left: ox,
            top: oy,
            originX: 'left',
            originY: 'top',
            scaleX: pw / photoImg.width,
            scaleY: ph / photoImg.height
          });

          const group = new fabric.Group([photoImg, frameImg], {
            left: left,
            top: top,
            originX: 'center',
            originY: 'center',
            angle: angle,
            shadow: new fabric.Shadow({ color: 'rgba(15, 8, 4, 0.35)', blur: 20, offsetX: 4, offsetY: 8 }),
            scrapbookType: 'frame',
            frameStyle: 'gold_jaali'
          });

          resolve(group);
        }, { crossOrigin: 'anonymous' });
      }, { crossOrigin: 'anonymous' });
    });
  }

  createVectorPichwaiFrame(imgSrc, caption, fontKey, left, top, angle, width = 520) {
    return new Promise((resolve) => {
      const pad = 24;
      const height = width * 1.25;

      fabric.Image.fromURL(imgSrc, (img) => {
        const photoW = width - pad * 2;
        const photoH = height - pad * 2;

        img.set({
          left: pad,
          top: pad,
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
          fill: '#580b14',
          stroke: '#d6af41',
          strokeWidth: 4,
          rx: 8,
          ry: 8,
          shadow: new fabric.Shadow({ color: 'rgba(20, 4, 6, 0.35)', blur: 16, offsetX: 2, offsetY: 6 })
        });

        const innerBorder = new fabric.Rect({
          left: 10,
          top: 10,
          width: width - 20,
          height: height - 20,
          fill: 'transparent',
          stroke: '#fff3da',
          strokeWidth: 2,
          rx: 4,
          ry: 4
        });

        const photoBorder = new fabric.Rect({
          left: pad - 2,
          top: pad - 2,
          width: photoW + 4,
          height: photoH + 4,
          fill: 'transparent',
          stroke: '#d6af41',
          strokeWidth: 2
        });

        const group = new fabric.Group([bgRect, innerBorder, img, photoBorder], {
          left: left,
          top: top,
          originX: 'center',
          originY: 'center',
          angle: angle,
          scrapbookType: 'frame',
          frameStyle: 'pichwai'
        });

        resolve(group);
      }, { crossOrigin: 'anonymous' });
    });
  }

  createMusicPlayerObject(title = 'Chogada - Loveyatri', artist = 'Darshan Raval, Asees Kaur', current = '2:18', total = '3:45', left, top, angle = 0, width = 460) {
    return new Promise((resolve) => {
      let assetUrl = '/assets/navratri/spotify_chogada.png';
      const t = (title || '').toLowerCase();
      if (t.includes('tere chehre') || t.includes('chehre')) {
        assetUrl = '/assets/navratri/spotify_tere_chehre.png';
      } else if (t.includes('dholida')) {
        assetUrl = '/assets/navratri/spotify_dholida.png';
      } else if (t.includes('kamariya')) {
        assetUrl = '/assets/navratri/spotify_kamariya.png';
      } else if (t.includes('nagada')) {
        assetUrl = '/assets/navratri/spotify_nagada.png';
      }

      fabric.Image.fromURL(assetUrl, (img) => {
        if (!img || !img.width) {
          resolve(this.createVectorMusicPlayer(title, artist, current, total, left, top, angle, width, 130));
          return;
        }
        const scale = width / img.width;
        img.set({
          left: left,
          top: top,
          originX: 'center',
          originY: 'center',
          scaleX: scale,
          scaleY: scale,
          angle: angle,
          shadow: new fabric.Shadow({ color: 'rgba(10, 5, 5, 0.4)', blur: 20, offsetX: 3, offsetY: 8 }),
          scrapbookType: 'music_player',
          musicTitle: title,
          musicArtist: artist
        });
        resolve(img);
      }, { crossOrigin: 'anonymous' });
    });
  }

  createVectorMusicPlayer(title = 'Tere Chehre Se Nazar Nahin', artist = 'Lata Mangeshkar, Kishore Kumar', current = '2:57', total = '5:02', left, top, angle = 0, width = 460, height = 130) {
    const bg = new fabric.Rect({
      left: 0,
      top: 0,
      width: width,
      height: height,
      fill: 'rgba(24, 12, 14, 0.94)',
      rx: 14,
      ry: 14,
      shadow: new fabric.Shadow({ color: 'rgba(0,0,0,0.3)', blur: 12, offsetX: 0, offsetY: 4 })
    });

    const titleText = new fabric.IText((title || 'Chogada - Loveyatri').slice(0, 28), {
      left: 20,
      top: 16,
      originX: 'left',
      originY: 'top',
      fontFamily: 'Poppins',
      fontWeight: 'bold',
      fontSize: 18,
      fill: '#ffffff'
    });

    const artistText = new fabric.IText((artist || 'Darshan Raval, Asees Kaur').slice(0, 32), {
      left: 20,
      top: 42,
      originX: 'left',
      originY: 'top',
      fontFamily: 'Poppins',
      fontSize: 13,
      fill: '#d2c3c3'
    });

    const heartIcon = new fabric.IText('♡', {
      left: width - 30,
      top: 24,
      originX: 'center',
      originY: 'center',
      fontFamily: 'Poppins',
      fontSize: 22,
      fill: '#f0dcdc'
    });

    const barY = 76;
    const barBg = new fabric.Line([20, barY, width - 20, barY], {
      stroke: 'rgba(120, 80, 85, 0.7)',
      strokeWidth: 4,
      strokeLineCap: 'round'
    });

    const progX = 20 + (width - 40) * 0.58;
    const barProg = new fabric.Line([20, barY, progX, barY], {
      stroke: '#ffffff',
      strokeWidth: 4,
      strokeLineCap: 'round'
    });

    const thumb = new fabric.Circle({
      left: progX,
      top: barY,
      radius: 5,
      originX: 'center',
      originY: 'center',
      fill: '#ffffff'
    });

    const curText = new fabric.IText(current || '2:57', {
      left: 20,
      top: 92,
      originX: 'left',
      originY: 'top',
      fontFamily: 'Space Mono',
      fontSize: 11,
      fill: '#c0b0b0'
    });

    const totText = new fabric.IText(total || '5:02', {
      left: width - 20,
      top: 92,
      originX: 'right',
      originY: 'top',
      fontFamily: 'Space Mono',
      fontSize: 11,
      fill: '#c0b0b0'
    });

    const cx = width / 2;
    const cy = 98;
    const playCircle = new fabric.Circle({
      left: cx,
      top: cy,
      radius: 14,
      originX: 'center',
      originY: 'center',
      fill: '#ffffff'
    });
    const playTriangle = new fabric.Triangle({
      left: cx + 1,
      top: cy,
      width: 10,
      height: 12,
      angle: 90,
      originX: 'center',
      originY: 'center',
      fill: '#180c0e'
    });

    const prevIcon = new fabric.Triangle({
      left: cx - 36,
      top: cy,
      width: 8,
      height: 10,
      angle: -90,
      originX: 'center',
      originY: 'center',
      fill: '#e6dede'
    });

    const nextIcon = new fabric.Triangle({
      left: cx + 36,
      top: cy,
      width: 8,
      height: 10,
      angle: 90,
      originX: 'center',
      originY: 'center',
      fill: '#e6dede'
    });

    return new fabric.Group([bg, titleText, artistText, heartIcon, barBg, barProg, thumb, curText, totText, playCircle, playTriangle, prevIcon, nextIcon], {
      left: left,
      top: top,
      originX: 'center',
      originY: 'center',
      angle: angle,
      scrapbookType: 'music_player'
    });
  }

  createFeelingDesiObject(left, top, angle = 0, width = 260) {
    return new Promise((resolve) => {
      const assetUrl = '/assets/navratri/feeling_desi.png';
      fabric.Image.fromURL(assetUrl, (img) => {
        if (!img || !img.width) {
          resolve(this.createVectorDesiBadge(left, top, angle, width));
          return;
        }
        const scale = width / img.width;
        img.set({
          left: left,
          top: top,
          originX: 'center',
          originY: 'center',
          scaleX: scale,
          scaleY: scale,
          angle: angle,
          shadow: new fabric.Shadow({ color: 'rgba(20, 10, 10, 0.3)', blur: 16, offsetX: 2, offsetY: 6 }),
          scrapbookType: 'desi_badge'
        });
        resolve(img);
      }, { crossOrigin: 'anonymous' });
    });
  }

  createVectorDesiBadge(left, top, angle = 0, width = 260, height = 120) {
    const bg = new fabric.Rect({
      left: 0,
      top: 0,
      width: width,
      height: height,
      fill: '#f8f0e2',
      stroke: '#d4bfa8',
      strokeWidth: 1.5,
      rx: 6,
      ry: 6,
      shadow: new fabric.Shadow({ color: 'rgba(0,0,0,0.18)', blur: 8, offsetX: 1, offsetY: 3 })
    });

    const inner = new fabric.Rect({
      left: 6,
      top: 6,
      width: width - 12,
      height: height - 12,
      fill: 'transparent',
      stroke: '#c0a088',
      strokeWidth: 1,
      rx: 4,
      ry: 4
    });

    const lotus = new fabric.IText('🪷', {
      left: width / 2,
      top: 24,
      originX: 'center',
      originY: 'center',
      fontSize: 22
    });

    const script = new fabric.IText('Feeling', {
      left: width / 2,
      top: 52,
      originX: 'center',
      originY: 'center',
      fontFamily: 'Caveat',
      fontSize: 34,
      fill: '#460f14'
    });

    const caps = new fabric.IText('DESI', {
      left: width / 2,
      top: 86,
      originX: 'center',
      originY: 'center',
      fontFamily: 'Poppins',
      fontWeight: 'bold',
      fontSize: 26,
      fill: '#b4141e'
    });

    return new fabric.Group([bg, inner, lotus, script, caps], {
      left: left,
      top: top,
      originX: 'center',
      originY: 'center',
      angle: angle,
      scrapbookType: 'desi_badge'
    });
  }

  createDesiStickerObject(kind, left, top, angle = 0, size = 130) {
    return new Promise((resolve) => {
      const assetMap = {
        'jhumka': '/assets/navratri/lotus_jhumka_hd.png',
        'mojri': '/assets/navratri/embroidered_juttis.png',
        'basket_gajra': '/assets/navratri/basket_gajra.png',
        'marigold': '/assets/navratri/marigold_flower.png',
        'marigold_garland': '/assets/navratri/marigold_garland.png',
        'jasmine_gajra': '/assets/navratri/jasmine_gajra.png',
        'pink_lotus': '/assets/navratri/pink_lotus.png',
        'lotus': '/assets/navratri/pink_lotus.png',
        'dandiya': '/assets/navratri/dandiya_sticks.png',
        'diya': '/assets/navratri/clay_diya.png',
        'chai': '/assets/navratri/chai_hand.png',
        'mehndi_chai': '/assets/navratri/chai_hand.png',
        'mehndi-chai': '/assets/navratri/chai_hand.png',
        'rickshaw': '/assets/navratri/rickshaw.png',
        'garba': '/assets/navratri/dandiya_sticks.png'
      };

      const assetUrl = assetMap[kind];
      if (assetUrl) {
        fabric.Image.fromURL(assetUrl, (img) => {
          if (!img || !img.width) {
            resolve(this.createFallbackSticker(kind, left, top, angle, size));
            return;
          }
          const maxDim = Math.max(img.width, img.height);
          const scale = size / maxDim;

          img.set({
            left: left,
            top: top,
            originX: 'center',
            originY: 'center',
            scaleX: scale,
            scaleY: scale,
            angle: angle,
            shadow: new fabric.Shadow({ color: 'rgba(20, 10, 10, 0.28)', blur: 14, offsetX: 2, offsetY: 5 }),
            scrapbookType: 'desi_sticker',
            stickerKind: kind
          });
          resolve(img);
        }, { crossOrigin: 'anonymous' });
      } else {
        resolve(this.createFallbackSticker(kind, left, top, angle, size));
      }
    });
  }

  createFallbackSticker(kind, left, top, angle = 0, size = 120) {
    const emojiMap = {
      'jhumka': '🪞',
      'mojri': '🥿',
      'mehndi_chai': '☕',
      'mehndi-chai': '☕',
      'chai': '☕',
      'rickshaw': '🛺',
      'lotus': '🪷',
      'pink_lotus': '🪷',
      'dandiya': '🪘',
      'diya': '🪔',
      'garba': '💃',
      'marigold': '🌼',
      'marigold_garland': '🏵️',
      'jasmine_gajra': '🌸',
      'basket_gajra': '🧺'
    };
    const symbol = emojiMap[kind] || '✨';
    return new fabric.IText(symbol, {
      left: left,
      top: top,
      originX: 'center',
      originY: 'center',
      fontSize: size * 0.75,
      angle: angle,
      shadow: new fabric.Shadow({ color: 'rgba(0,0,0,0.22)', blur: 6, offsetX: 1, offsetY: 2 }),
      scrapbookType: 'sticker',
      stickerKind: kind
    });
  }

  createStickerAssetObject(stkId, stkPath = '', left, top, angle = 0, size = 160) {
    return new Promise((resolve) => {
      let resolvedPath = stkPath;
      if (!resolvedPath && stkId) {
        if (window.StickerCatalog && Array.isArray(window.StickerCatalog)) {
          const match = window.StickerCatalog.find(s => s.id === stkId || s.path === stkId || s.name === stkId);
          if (match && match.path) resolvedPath = match.path;
        }
      }

      const desiMap = {
        'jhumka': '/assets/navratri/lotus_jhumka_hd.png',
        'mojri': '/assets/navratri/embroidered_juttis.png',
        'basket_gajra': '/assets/navratri/basket_gajra.png',
        'marigold': '/assets/navratri/marigold_flower.png',
        'marigold_garland': '/assets/navratri/marigold_garland.png',
        'jasmine_gajra': '/assets/navratri/jasmine_gajra.png',
        'pink_lotus': '/assets/navratri/pink_lotus.png',
        'lotus': '/assets/navratri/pink_lotus.png',
        'dandiya': '/assets/navratri/dandiya_sticks.png',
        'diya': '/assets/navratri/clay_diya.png',
        'chai': '/assets/navratri/chai_hand.png',
        'mehndi_chai': '/assets/navratri/chai_hand.png',
        'rickshaw': '/assets/navratri/rickshaw.png',
        'garba': '/assets/navratri/dandiya_sticks.png'
      };

      if (!resolvedPath && stkId && desiMap[stkId]) {
        resolvedPath = desiMap[stkId];
      }

      if (!resolvedPath && stkId && (stkId.startsWith('/') || stkId.startsWith('http') || stkId.startsWith('data:'))) {
        resolvedPath = stkId;
      }

      if (resolvedPath) {
        fabric.Image.fromURL(resolvedPath, (img) => {
          if (!img || !img.width) {
            resolve(this.createFallbackSticker(stkId || 'sticker', left, top, angle, size));
            return;
          }
          const maxDim = Math.max(img.width, img.height);
          const scale = size / (maxDim || 1);

          img.set({
            left: left,
            top: top,
            originX: 'center',
            originY: 'center',
            scaleX: scale,
            scaleY: scale,
            angle: angle,
            shadow: new fabric.Shadow({ color: 'rgba(20, 10, 10, 0.28)', blur: 14, offsetX: 2, offsetY: 5 }),
            scrapbookType: 'sticker',
            stickerId: stkId || '',
            stickerPath: resolvedPath
          });
          resolve(img);
        }, { crossOrigin: 'anonymous' });
      } else {
        resolve(this.createFallbackSticker(stkId || 'sticker', left, top, angle, size));
      }
    });
  }

  createLotusBorderObject(left, top, width, height = 74) {
    return new Promise((resolve) => {
      const tileUrl = '/assets/navratri/pichwai_lotus_tile.png';
      fabric.Image.fromURL(tileUrl, (masterTile) => {
        if (!masterTile || !masterTile.width) {
          resolve(this.createVectorLotusBorder(left, top, width, height));
          return;
        }

        const tileScale = height / masterTile.height;
        const tileW = masterTile.width * tileScale;
        const count = Math.ceil(width / tileW);

        const bg = new fabric.Rect({
          left: 0,
          top: 0,
          width: width,
          height: height,
          fill: '#9e1a22',
          stroke: '#e6b347',
          strokeWidth: 2
        });
        const items = [bg];

        let cloned = 0;
        for (let i = 0; i < count; i++) {
          masterTile.clone((clonedImg) => {
            clonedImg.set({
              left: i * tileW,
              top: 0,
              originX: 'left',
              originY: 'top',
              scaleX: tileScale,
              scaleY: tileScale
            });
            items.push(clonedImg);
            cloned++;
            if (cloned === count) {
              const group = new fabric.Group(items, {
                left: left,
                top: top,
                originX: 'center',
                originY: 'center',
                selectable: true,
                scrapbookType: 'lotus_border'
              });
              resolve(group);
            }
          });
        }
      }, { crossOrigin: 'anonymous' });
    });
  }

  createVectorLotusBorder(left, top, width, height = 74) {
    const bg = new fabric.Rect({
      left: 0,
      top: 0,
      width: width,
      height: height,
      fill: '#c69830',
      stroke: '#fff0c8',
      strokeWidth: 2
    });

    const items = [bg];
    const step = 64;
    const count = Math.ceil(width / step);
    for (let i = 0; i < count; i++) {
      const tileLine = new fabric.Line([i * step, 0, i * step, height], {
        stroke: 'rgba(150, 110, 30, 0.6)',
        strokeWidth: 1
      });
      const lotus = new fabric.IText('🪷', {
        left: i * step + step / 2,
        top: height / 2 - 2,
        originX: 'center',
        originY: 'center',
        fontSize: 26
      });
      items.push(tileLine, lotus);
    }

    return new fabric.Group(items, {
      left: left,
      top: top,
      originX: 'center',
      originY: 'center',
      selectable: true,
      scrapbookType: 'lotus_border'
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
  // Selection Handling
  // ==========================================================================
  onObjectSelected(obj) {
    const tbText = document.getElementById('tb-text');
    const tbPhoto = document.getElementById('tb-photo');
    const tbSticker = document.getElementById('tb-sticker');

    if (tbText) tbText.classList.add('hidden');
    if (tbPhoto) tbPhoto.classList.add('hidden');
    if (tbSticker) tbSticker.classList.add('hidden');

    if (obj.type === 'i-text' || obj.type === 'text') {
      if (tbText) {
        tbText.classList.remove('hidden');
        document.getElementById('tb-text-font').value = obj.fontFamily || 'Caveat';
        document.getElementById('tb-text-size').value = obj.fontSize || 48;
        document.getElementById('tb-text-color').value = obj.fill || '#2c2523';
        document.getElementById('btn-text-bold').classList.toggle('active', obj.fontWeight === 'bold');
        document.getElementById('btn-text-italic').classList.toggle('active', obj.fontStyle === 'italic');
      }
    } else if (obj.scrapbookType === 'polaroid' || obj.scrapbookType === 'inset') {
      if (tbPhoto) tbPhoto.classList.remove('hidden');
    } else {
      if (tbSticker) {
        tbSticker.classList.remove('hidden');
        document.getElementById('tb-sticker-color').value = obj.fill || '#d49b45';
        document.getElementById('tb-sticker-opacity').value = obj.opacity || 1;
      }
    }
  }

  onSelectionCleared() {
    const tbText = document.getElementById('tb-text');
    const tbPhoto = document.getElementById('tb-photo');
    const tbSticker = document.getElementById('tb-sticker');
    if (tbText) tbText.classList.add('hidden');
    if (tbPhoto) tbPhoto.classList.add('hidden');
    if (tbSticker) tbSticker.classList.add('hidden');
  }

  // ==========================================================================
  // Mobile Dock & Bottom Sheet Drawer Handling
  // ==========================================================================
  bindMobileDock() {
    const dockButtons = document.querySelectorAll('.mobile-dock-btn[data-panel]');
    const sheet = document.getElementById('bottom-sheet');
    const backdrop = document.getElementById('bottom-sheet-backdrop');
    const closeBtn = document.getElementById('sheet-close-btn');
    const sheetTitle = document.getElementById('sheet-title');

    const openSheet = (panelName, title) => {
      // Hide all panels
      document.querySelectorAll('.sheet-panel').forEach(p => p.classList.add('hidden'));

      // Show requested panel
      const targetPanel = document.getElementById(`panel-${panelName}`);
      if (targetPanel) {
        targetPanel.classList.remove('hidden');
      }

      sheetTitle.textContent = title;
      sheet.classList.add('active');
      backdrop.classList.add('active');

      // If opening polaroid, populate photo list
      if (panelName === 'polaroid') {
        this.populateSheetPhotos();
      } else if (panelName === 'slides') {
        this.populateSheetSlides();
      }
    };

    const closeSheet = () => {
      sheet.classList.remove('active');
      backdrop.classList.remove('active');
    };

    dockButtons.forEach((btn) => {
      btn.addEventListener('click', () => {
        const panel = btn.dataset.panel;
        const titles = {
          'text': 'Add Typography',
          'polaroid': 'Add Photos & Polaroid',
          'tape': 'Add Washi Tape',
          'stickers': 'Add Stickers & Doodles',
          'paper': 'Change Paper Texture',
          'slides': 'Manage Slides'
        };
        openSheet(panel, titles[panel] || 'Add Elements');
      });
    });

    if (closeBtn) closeBtn.addEventListener('click', closeSheet);
    if (backdrop) backdrop.addEventListener('click', closeSheet);

    // Mobile Top Bar Back & Undo/Redo
    const backBtn = document.getElementById('btn-mobile-back');
    if (backBtn) {
      backBtn.addEventListener('click', () => {
        if (window.switchAppView) window.switchAppView('preview');
      });
    }

    const mUndo = document.getElementById('btn-mobile-undo');
    if (mUndo) mUndo.addEventListener('click', () => this.undo());

    const mRedo = document.getElementById('btn-mobile-redo');
    if (mRedo) mRedo.addEventListener('click', () => this.redo());

    // Mobile Bottom Sheet Action Items
    this.bindSheetActions(closeSheet);
  }

  bindSheetActions(closeSheet) {
    // Text additions
    const mTitle = document.getElementById('m-add-text-title');
    if (mTitle) {
      mTitle.addEventListener('click', () => {
        this.addTextElement('SCRAPBOOK TITLE', 'Playfair Display', 80, true);
        closeSheet();
      });
    }

    const mHand = document.getElementById('m-add-text-hand');
    if (mHand) {
      mHand.addEventListener('click', () => {
        this.addTextElement('handwritten memory...', 'Caveat', 64, false);
        closeSheet();
      });
    }

    const mBody = document.getElementById('m-add-text-body');
    if (mBody) {
      mBody.addEventListener('click', () => {
        this.addTextElement('Tell the story behind this moment', 'Poppins', 40, false);
        closeSheet();
      });
    }

    const mStamp = document.getElementById('m-add-text-stamp');
    if (mStamp) {
      mStamp.addEventListener('click', () => {
        this.addTextElement('01 / MEMORY ARCHIVE', 'Space Mono', 32, false);
        closeSheet();
      });
    }

    // Pichwai frame addition
    const mPichwai = document.getElementById('m-add-frame-pichwai');
    if (mPichwai) {
      mPichwai.addEventListener('click', () => {
        this.addPichwaiFrameElement();
        closeSheet();
      });
    }

    const mGoldJaali = document.getElementById('m-add-frame-gold-jaali');
    if (mGoldJaali) {
      mGoldJaali.addEventListener('click', () => {
        this.addGoldJaaliFrameElement();
        closeSheet();
      });
    }

    // Torn paper addition
    const mTorn = document.getElementById('m-add-torn-paper');
    if (mTorn) {
      mTorn.addEventListener('click', () => {
        this.addTornPaperElement();
        closeSheet();
      });
    }

    // Washi Tape sheet buttons
    document.querySelectorAll('.tape-sheet-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const tape = btn.dataset.tape;
        const colorMap = {
          'kraft': 'rgba(228, 203, 169, 0.88)',
          'sage': 'rgba(163, 196, 168, 0.85)',
          'rose': 'rgba(226, 168, 168, 0.85)',
          'gold': 'rgba(244, 218, 142, 0.88)',
        };
        this.addTapeElement(colorMap[tape] || colorMap.kraft);
        closeSheet();
      });
    });

    // Sticker sheet buttons
    document.querySelectorAll('.sticker-sheet-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        this.addStickerElement(btn.dataset.sticker);
        closeSheet();
      });
    });

    // Mobile paper swatches
    document.querySelectorAll('.m-paper-swatch').forEach((swatch) => {
      swatch.addEventListener('click', () => {
        document.querySelectorAll('.m-paper-swatch').forEach(s => s.classList.remove('active'));
        swatch.classList.add('active');
        const color = swatch.style.backgroundColor;
        this.canvas.setBackgroundColor(color, () => this.canvas.renderAll());
        this.syncCurrentSlideToSpec();
        closeSheet();
      });
    });
  }

  populateSheetPhotos() {
    const list = document.getElementById('sheet-photos-list');
    if (!list) return;
    list.innerHTML = '';

    const closeSheet = () => {
      document.getElementById('bottom-sheet').classList.remove('active');
      document.getElementById('bottom-sheet-backdrop').classList.remove('active');
    };

    this.images.forEach((imgSrc, idx) => {
      const thumb = document.createElement('div');
      thumb.className = 'sheet-photo-thumb';
      
      const img = document.createElement('img');
      img.src = imgSrc;
      img.alt = `Photo ${idx + 1}`;

      thumb.appendChild(img);
      thumb.addEventListener('click', async () => {
        await this.addPolaroidWithPhoto(imgSrc);
        closeSheet();
      });

      list.appendChild(thumb);
    });
  }

  populateSheetSlides() {
    const strip = document.getElementById('sheet-slides-strip');
    if (!strip) return;
    strip.innerHTML = '';

    const total = this.spec ? this.spec.slides.length : 0;
    for (let idx = 0; idx < total; idx++) {
      const item = document.createElement('div');
      item.className = `filmstrip-thumb ${idx === this.currentSlideIndex ? 'active' : ''}`;
      
      const img = document.createElement('img');
      img.src = this.images[idx % (this.images.length || 1)];
      img.alt = `Slide ${idx + 1}`;

      item.appendChild(img);
      item.addEventListener('click', () => {
        this.currentSlideIndex = idx;
        this.loadSlide(idx, this.spec, this.images);
        document.getElementById('bottom-sheet').classList.remove('active');
        document.getElementById('bottom-sheet-backdrop').classList.remove('active');
      });

      strip.appendChild(item);
    }
  }

  async addPolaroidWithPhoto(imgSrc) {
    const obj = await this.createPolaroidObject(imgSrc, 'polaroid memory', 'hand', this.baseWidth / 2, this.baseHeight / 2, -2.5, 520);
    this.canvas.add(obj);
    this.canvas.setActiveObject(obj);
    this.canvas.renderAll();
    this.saveHistoryState();
    this.syncCurrentSlideToSpec();
  }

  bindToolbar() {
    // Text controls
    const fontSelect = document.getElementById('tb-text-font');
    if (fontSelect) {
      fontSelect.addEventListener('change', (e) => {
        const active = this.canvas.getActiveObject();
        if (active && (active.type === 'i-text' || active.type === 'text')) {
          active.set('fontFamily', e.target.value);
          this.canvas.renderAll();
          this.syncCurrentSlideToSpec();
        }
      });
    }

    const sizeInput = document.getElementById('tb-text-size');
    if (sizeInput) {
      sizeInput.addEventListener('input', (e) => {
        const active = this.canvas.getActiveObject();
        if (active && (active.type === 'i-text' || active.type === 'text')) {
          active.set('fontSize', parseInt(e.target.value, 10));
          this.canvas.renderAll();
          this.syncCurrentSlideToSpec();
        }
      });
    }

    const colorInput = document.getElementById('tb-text-color');
    if (colorInput) {
      colorInput.addEventListener('input', (e) => {
        const active = this.canvas.getActiveObject();
        if (active && (active.type === 'i-text' || active.type === 'text')) {
          active.set('fill', e.target.value);
          this.canvas.renderAll();
          this.syncCurrentSlideToSpec();
        }
      });
    }

    // Alignment
    ['left', 'center', 'right'].forEach((align) => {
      const btn = document.getElementById(`btn-align-${align}`);
      if (btn) {
        btn.addEventListener('click', () => {
          const active = this.canvas.getActiveObject();
          if (active && (active.type === 'i-text' || active.type === 'text')) {
            active.set('textAlign', align);
            this.canvas.renderAll();
            this.syncCurrentSlideToSpec();
          }
        });
      }
    });

    // Layer controls
    ['btn-layer-up', 'btn-layer-up-photo', 'btn-layer-up-sticker'].forEach(id => {
      const btn = document.getElementById(id);
      if (btn) btn.addEventListener('click', () => this.bringForward());
    });

    ['btn-layer-down', 'btn-layer-down-photo', 'btn-layer-down-sticker'].forEach(id => {
      const btn = document.getElementById(id);
      if (btn) btn.addEventListener('click', () => this.sendBackward());
    });

    ['btn-delete-element', 'btn-delete-photo', 'btn-delete-sticker'].forEach(id => {
      const btn = document.getElementById(id);
      if (btn) btn.addEventListener('click', () => this.deleteSelected());
    });

    // Undo / Redo
    const undoBtn = document.getElementById('btn-undo');
    if (undoBtn) undoBtn.addEventListener('click', () => this.undo());

    const redoBtn = document.getElementById('btn-redo');
    if (redoBtn) redoBtn.addEventListener('click', () => this.redo());

    // Zoom controls
    const zFit = document.getElementById('btn-zoom-fit');
    if (zFit) zFit.addEventListener('click', () => this.fitCanvasToViewport());

    const zIn = document.getElementById('btn-zoom-in');
    if (zIn) zIn.addEventListener('click', () => {
      this.scaleFactor *= 1.15;
      this.canvas.setWidth(this.baseWidth * this.scaleFactor);
      this.canvas.setHeight(this.baseHeight * this.scaleFactor);
      this.canvas.setZoom(this.scaleFactor);
      this.canvas.renderAll();
    });

    const zOut = document.getElementById('btn-zoom-out');
    if (zOut) zOut.addEventListener('click', () => {
      this.scaleFactor *= 0.85;
      this.canvas.setWidth(this.baseWidth * this.scaleFactor);
      this.canvas.setHeight(this.baseHeight * this.scaleFactor);
      this.canvas.setZoom(this.scaleFactor);
      this.canvas.renderAll();
    });

    // Desktop Library actions
    const dTitle = document.getElementById('add-text-title');
    if (dTitle) {
      dTitle.addEventListener('click', () => {
        this.addTextElement('SCRAPBOOK TITLE', 'Playfair Display', 80, true);
      });
    }

    const dHand = document.getElementById('add-text-hand');
    if (dHand) {
      dHand.addEventListener('click', () => {
        this.addTextElement('handwritten memory...', 'Caveat', 64, false);
      });
    }

    const dBody = document.getElementById('add-text-body');
    if (dBody) {
      dBody.addEventListener('click', () => {
        this.addTextElement('Tell the story behind this moment', 'Poppins', 40, false);
      });
    }

    const dStamp = document.getElementById('add-text-stamp');
    if (dStamp) {
      dStamp.addEventListener('click', () => {
        this.addTextElement('01 / MEMORY ARCHIVE', 'Space Mono', 32, false);
      });
    }

    document.querySelectorAll('.tape-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const tape = btn.dataset.tape;
        const colorMap = {
          'kraft': 'rgba(228, 203, 169, 0.88)',
          'sage': 'rgba(163, 196, 168, 0.85)',
          'rose': 'rgba(226, 168, 168, 0.85)',
          'gold': 'rgba(244, 218, 142, 0.88)',
        };
        this.addTapeElement(colorMap[tape] || colorMap.kraft);
      });
    });

    document.querySelectorAll('.sticker-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        this.addStickerElement(btn.dataset.sticker);
      });
    });

    const dPol = document.getElementById('add-frame-polaroid');
    if (dPol) dPol.addEventListener('click', () => this.addPolaroidElement());

    const dPichwai = document.getElementById('add-frame-pichwai');
    if (dPichwai) dPichwai.addEventListener('click', () => this.addPichwaiFrameElement());

    const dGoldJaali = document.getElementById('add-frame-gold-jaali');
    if (dGoldJaali) dGoldJaali.addEventListener('click', () => this.addGoldJaaliFrameElement());

    const dTorn = document.getElementById('add-frame-torn');
    if (dTorn) dTorn.addEventListener('click', () => this.addTornPaperElement());

    const dMusic = document.getElementById('add-music-card');
    if (dMusic) dMusic.addEventListener('click', () => this.addMusicPlayerElement());

    const dMusicTere = document.getElementById('add-music-card-tere');
    if (dMusicTere) dMusicTere.addEventListener('click', () => this.addTereChehreMusicPlayerElement());

    const dDesi = document.getElementById('add-desi-badge');
    if (dDesi) dDesi.addEventListener('click', () => this.addFeelingDesiElement());

    const dLotus = document.getElementById('add-lotus-border');
    if (dLotus) dLotus.addEventListener('click', () => this.addLotusBorderElement(true));

    document.querySelectorAll('.desi-text-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const text = btn.dataset.text || btn.textContent.trim();
        this.addTextElement(text, 'Caveat', 50, false);
      });
    });

    document.querySelectorAll('.paper-swatch:not(.m-paper-swatch)').forEach((swatch) => {
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
  // Adding Elements
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

  async addStickerElement(stickerType) {
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
    } else if (stickerType && stickerType.startsWith('desi-')) {
      const kind = stickerType.replace('desi-', '');
      obj = await this.createDesiStickerObject(kind, cx, cy, 0, 140);
    } else if (stickerType === 'music-card') {
      obj = await this.createMusicPlayerObject('Chogada - Loveyatri', 'Darshan Raval, Asees Kaur', '2:18', '3:45', cx, cy, 0, 460);
    } else if (stickerType === 'music-card-tere') {
      obj = await this.createMusicPlayerObject('Tere Chehre Se Nazar Nahin', 'Lata Mangeshkar, Kishore Kumar', '2:57', '5:02', cx, cy, 0, 460);
    } else if (stickerType === 'desi-badge') {
      obj = await this.createFeelingDesiObject(cx, cy, 0, 260);
    } else if (stickerType === 'lotus-border') {
      obj = await this.createLotusBorderObject(cx, this.baseHeight * 0.03, this.baseWidth, 74);
    }

    if (obj) {
      this.canvas.add(obj);
      this.canvas.setActiveObject(obj);
      this.canvas.renderAll();
      this.saveHistoryState();
      this.syncCurrentSlideToSpec();
    }
  }

  async addStickerAsset(sticker, x = null, y = null) {
    let stkId = '';
    let stkPath = '';
    let defaultSize = 180;

    if (typeof sticker === 'string') {
      stkId = sticker;
      if (sticker.startsWith('/') || sticker.startsWith('http') || sticker.startsWith('data:')) {
        stkPath = sticker;
      }
    } else if (sticker && typeof sticker === 'object') {
      stkId = sticker.id || '';
      stkPath = sticker.path || '';
      if (sticker.suitable_placement && sticker.suitable_placement.default_scale) {
        defaultSize = Math.round(180 * sticker.suitable_placement.default_scale);
      }
    }

    const posX = x !== null ? x : (this.baseWidth / 2);
    const posY = y !== null ? y : (this.baseHeight / 2);

    const obj = await this.createStickerAssetObject(stkId, stkPath, posX, posY, 0, defaultSize);
    if (obj) {
      this.canvas.add(obj);
      this.canvas.setActiveObject(obj);
      this.canvas.renderAll();
      this.saveHistoryState();
      this.syncCurrentSlideToSpec();
    }
    return obj;
  }

  async addMusicPlayerElement(title = 'Chogada - Loveyatri', artist = 'Darshan Raval, Asees Kaur') {
    const obj = await this.createMusicPlayerObject(title, artist, '2:18', '3:45', this.baseWidth / 2, this.baseHeight * 0.65, 0, 460);
    this.canvas.add(obj);
    this.canvas.setActiveObject(obj);
    this.canvas.renderAll();
    this.saveHistoryState();
    this.syncCurrentSlideToSpec();
  }

  async addTereChehreMusicPlayerElement() {
    const obj = await this.createMusicPlayerObject('Tere Chehre Se Nazar Nahin', 'Lata Mangeshkar, Kishore Kumar', '2:57', '5:02', this.baseWidth / 2, this.baseHeight * 0.65, 0, 460);
    this.canvas.add(obj);
    this.canvas.setActiveObject(obj);
    this.canvas.renderAll();
    this.saveHistoryState();
    this.syncCurrentSlideToSpec();
  }

  async addFeelingDesiElement() {
    const obj = await this.createFeelingDesiObject(this.baseWidth / 2, this.baseHeight / 2, 2, 260);
    this.canvas.add(obj);
    this.canvas.setActiveObject(obj);
    this.canvas.renderAll();
    this.saveHistoryState();
    this.syncCurrentSlideToSpec();
  }

  async addLotusBorderElement(top = true) {
    const y = top ? (this.baseHeight * 0.026) : (this.baseHeight * 0.974);
    const obj = await this.createLotusBorderObject(this.baseWidth / 2, y, this.baseWidth, 74);
    this.canvas.add(obj);
    this.canvas.sendToBack(obj);
    this.canvas.setActiveObject(obj);
    this.canvas.renderAll();
    this.saveHistoryState();
    this.syncCurrentSlideToSpec();
  }

  async addPichwaiFrameElement() {
    const photoIdx = this.currentSlideIndex % (this.images.length || 1);
    const imgSrc = this.images[photoIdx] || this.images[0];
    const obj = await this.createPichwaiFrameObject(imgSrc, 'garba glow', 'hand', this.baseWidth / 2, this.baseHeight / 2, 0, 520);
    this.canvas.add(obj);
    this.canvas.setActiveObject(obj);
    this.canvas.renderAll();
    this.saveHistoryState();
    this.syncCurrentSlideToSpec();
  }

  async addGoldJaaliFrameElement() {
    const photoIdx = this.currentSlideIndex % (this.images.length || 1);
    const imgSrc = this.images[photoIdx] || this.images[0];
    const obj = await this.createGoldJaaliFrameObject(imgSrc, 'shubh navratri', 'hand', this.baseWidth / 2, this.baseHeight / 2, 0, 520);
    this.canvas.add(obj);
    this.canvas.setActiveObject(obj);
    this.canvas.renderAll();
    this.saveHistoryState();
    this.syncCurrentSlideToSpec();
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

    if (this.historyIndex < this.history.length - 1) {
      this.history = this.history.slice(0, this.historyIndex + 1);
    }

    const json = JSON.stringify(this.canvas.toDatalessJSON(['scrapbookType', 'scrapbookData', 'stickerId', 'stickerPath', 'stickerKind']));
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

  syncCurrentSlideToSpec() {
    if (!this.spec || !this.spec.slides[this.currentSlideIndex]) return;
    if (window.onSlideModified) {
      window.onSlideModified(this.currentSlideIndex);
    }
  }
}

window.ScrapbookEditor = ScrapbookEditor;
