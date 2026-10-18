/**
 * Aesthetic Scrapbook Carousel Maker — Main Application Controller
 */

(function () {
  // Application State
  const state = {
    currentView: 'create', // 'create' | 'preview' | 'editor'
    images: [], // array of base64 data URLs
    selectedPalette: 'Warm Cream & Espresso',
    selectedSize: '4:5',
    selectedMode: 'separate',
    includeCover: true,
    useAi: true,
    vibe: null,
    spec: null,
    source: null,
    activeSlideIndex: 0,
    renderedSlides: [], // array of base64 PNG data URLs
    editor: null,
  };

  const PALETTES = [
    {
      name: 'Warm Cream & Espresso',
      colors: ['#2c2523', '#d49b45', '#5c524b', '#d9b48f', '#ede6d8']
    },
    {
      name: 'Sage & Botanical',
      colors: ['#273a2e', '#7d9d83', '#485d4f', '#a3c4a8', '#dfe7df']
    },
    {
      name: 'Vintage Rose',
      colors: ['#3e282b', '#d49b45', '#6c4d51', '#e2a8a8', '#f1dedd']
    },
    {
      name: 'Terracotta & Clay',
      colors: ['#3b2b25', '#e29b68', '#66493e', '#c97a5b', '#eddccc']
    },
    {
      name: 'Midnight Journal',
      colors: ['#f4efe6', '#ffd166', '#e2dcd2', '#e5b869', '#2b2b34']
    }
  ];

  // DOM Elements
  const tabs = {
    create: document.getElementById('tab-create'),
    preview: document.getElementById('tab-preview'),
    editor: document.getElementById('tab-editor'),
  };

  const views = {
    create: document.getElementById('view-create'),
    preview: document.getElementById('view-preview'),
    editor: document.getElementById('view-editor'),
  };

  // ==========================================================================
  // Initialization
  // ==========================================================================
  function init() {
    renderPaletteChips();
    bindViewTabs();
    bindPhotoUpload();
    bindControls();
    checkApiHealth();

    // Initialize Fabric Editor instance
    state.editor = new ScrapbookEditor('scrapbook-canvas');
  }

  async function checkApiHealth() {
    try {
      const res = await fetch('/api/health');
      if (res.ok) {
        const data = await res.json();
        const aiLabel = document.getElementById('ai-status-label');
        if (data.has_gemini_key) {
          aiLabel.textContent = `Active (${data.model}) — reads photos & writes copy`;
        } else {
          aiLabel.textContent = 'No API key in .env — using color & mood heuristics';
        }
      }
    } catch (e) {
      console.warn('API health check skipped in offline mode:', e);
    }
  }

  // ==========================================================================
  // View Navigation
  // ==========================================================================
  function switchView(viewName) {
    state.currentView = viewName;

    Object.keys(views).forEach((v) => {
      views[v].classList.toggle('active', v === viewName);
      tabs[v].classList.toggle('active', v === viewName);
    });

    if (viewName === 'preview') {
      renderPreviewSlide();
      renderFilmstrip();
    } else if (viewName === 'editor') {
      state.editor.loadSlide(state.activeSlideIndex, state.spec, state.images);
      renderEditorFilmstrip();
    }
  }

  function bindViewTabs() {
    Object.keys(tabs).forEach((v) => {
      tabs[v].addEventListener('click', () => {
        if (!tabs[v].disabled) {
          switchView(v);
        }
      });
    });

    document.getElementById('nav-brand').addEventListener('click', () => {
      switchView('create');
    });

    document.getElementById('btn-goto-editor').addEventListener('click', () => {
      switchView('editor');
    });

    const mDone = document.getElementById('btn-mobile-done');
    if (mDone) {
      mDone.addEventListener('click', () => {
        switchView('preview');
      });
    }

    // Expose for mobile header & navigation
    window.switchAppView = switchView;
  }

  // ==========================================================================
  // Palette & Options Rendering
  // ==========================================================================
  function renderPaletteChips() {
    const container = document.getElementById('palette-selector');
    container.innerHTML = '';

    PALETTES.forEach((p) => {
      const chip = document.createElement('div');
      chip.className = `palette-chip ${p.name === state.selectedPalette ? 'active' : ''}`;
      chip.dataset.palette = p.name;

      const swatches = document.createElement('div');
      swatches.className = 'palette-swatches';
      p.colors.forEach((c) => {
        const s = document.createElement('span');
        s.style.backgroundColor = c;
        swatches.appendChild(s);
      });

      const label = document.createElement('span');
      label.className = 'palette-name';
      label.textContent = p.name;

      chip.appendChild(swatches);
      chip.appendChild(label);

      chip.addEventListener('click', () => {
        document.querySelectorAll('.palette-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        state.selectedPalette = p.name;
      });

      container.appendChild(chip);
    });
  }

  // ==========================================================================
  // Photo Upload & Grid Management
  // ==========================================================================
  function bindPhotoUpload() {
    const dropzone = document.getElementById('photo-dropzone');
    const fileInput = document.getElementById('file-input');
    const clearBtn = document.getElementById('btn-clear-photos');
    const mobileTrigger = document.querySelector('.mobile-upload-trigger');

    dropzone.addEventListener('click', () => fileInput.click());
    if (mobileTrigger) {
      mobileTrigger.addEventListener('click', (e) => {
        e.stopPropagation();
        fileInput.click();
      });
    }

    dropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropzone.classList.add('dragover');
    });

    dropzone.addEventListener('dragleave', () => {
      dropzone.classList.remove('dragover');
    });

    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.classList.remove('dragover');
      if (e.dataTransfer.files && e.dataTransfer.files.length) {
        handleFiles(e.dataTransfer.files);
      }
    });

    fileInput.addEventListener('change', (e) => {
      if (e.target.files && e.target.files.length) {
        handleFiles(e.target.files);
      }
    });

    clearBtn.addEventListener('click', () => {
      state.images = [];
      updatePhotoGrid();
    });
  }

  function handleFiles(fileList) {
    const validFiles = Array.from(fileList).filter(f => f.type.startsWith('image/'));
    const remainingSlots = 10 - state.images.length;
    const toLoad = validFiles.slice(0, remainingSlots);

    if (toLoad.length === 0) {
      if (state.images.length >= 10) {
        alert('Maximum 10 photos allowed for the carousel.');
      }
      return;
    }

    let loadedCount = 0;
    toLoad.forEach((file) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        state.images.push(e.target.result);
        loadedCount++;
        if (loadedCount === toLoad.length) {
          updatePhotoGrid();
        }
      };
      reader.readAsDataURL(file);
    });
  }

  function updatePhotoGrid() {
    const grid = document.getElementById('photo-preview-grid');
    const header = document.getElementById('photo-grid-header');
    const countLabel = document.getElementById('photo-count-label');
    const createBtn = document.getElementById('btn-create-carousel');

    grid.innerHTML = '';
    const n = state.images.length;

    if (n > 0) {
      header.style.display = 'flex';
      countLabel.textContent = `${n} photo${n > 1 ? 's' : ''} selected (up to 10)`;
    } else {
      header.style.display = 'none';
    }

    createBtn.disabled = n < 2;

    state.images.forEach((imgSrc, i) => {
      const card = document.createElement('div');
      card.className = 'photo-card';
      // Subtle natural rotation for photo cards
      const rot = (i % 2 === 0 ? -1.5 : 1.5) + (i % 3 === 0 ? 0.8 : -0.8);
      card.style.setProperty('--rot', `${rot}deg`);

      const wrap = document.createElement('div');
      wrap.className = 'photo-thumb-wrap';

      const img = document.createElement('img');
      img.className = 'photo-thumb';
      img.src = imgSrc;
      img.alt = `Uploaded photo ${i + 1}`;

      const badge = document.createElement('span');
      badge.className = 'photo-order-badge';
      badge.textContent = `Photo ${i + 1}`;

      const rmBtn = document.createElement('button');
      rmBtn.className = 'photo-remove-btn';
      rmBtn.innerHTML = '✕';
      rmBtn.title = 'Remove photo';
      rmBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        state.images.splice(i, 1);
        updatePhotoGrid();
      });

      wrap.appendChild(img);
      card.appendChild(wrap);
      card.appendChild(badge);
      card.appendChild(rmBtn);

      grid.appendChild(card);
    });
  }

  // ==========================================================================
  // Form Controls & Prompt Chips
  // ==========================================================================
  function bindControls() {
    // Format size
    document.querySelectorAll('input[name="size"]').forEach((radio) => {
      radio.addEventListener('change', (e) => {
        state.selectedSize = e.target.value;
        document.querySelectorAll('#size-selector .radio-pill').forEach(p => p.classList.remove('active'));
        e.target.closest('.radio-pill').classList.add('active');
      });
    });

    // Layout mode
    document.querySelectorAll('input[name="mode"]').forEach((radio) => {
      radio.addEventListener('change', (e) => {
        state.selectedMode = e.target.value;
        document.querySelectorAll('#mode-selector .radio-pill').forEach(p => p.classList.remove('active'));
        e.target.closest('.radio-pill').classList.add('active');
      });
    });

    // Cover slide
    document.getElementById('toggle-cover').addEventListener('change', (e) => {
      state.includeCover = e.target.checked;
    });

    // AI toggle
    document.getElementById('toggle-ai').addEventListener('change', (e) => {
      state.useAi = e.target.checked;
    });

    // Prompt chips
    document.querySelectorAll('.prompt-chips .chip').forEach((chip) => {
      chip.addEventListener('click', () => {
        document.getElementById('hint-input').value = chip.dataset.prompt;
      });
    });

    // Create Carousel Button
    document.getElementById('btn-create-carousel').addEventListener('click', generateCarousel);

    // Save / Load JSON
    document.getElementById('btn-save-json').addEventListener('click', () => {
      if (state.spec) {
        CanvasExporter.saveDesignJson(state.spec, `${state.vibe.vibe_name.toLowerCase().replace(/\s+/g, '_')}_scrapbook.json`);
      }
    });

    const fileLoader = document.createElement('input');
    fileLoader.type = 'file';
    fileLoader.accept = '.json,application/json';
    fileLoader.style.display = 'none';
    document.body.appendChild(fileLoader);

    document.getElementById('btn-load-json').addEventListener('click', () => {
      fileLoader.click();
    });

    fileLoader.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (event) => {
        try {
          const loadedSpec = JSON.parse(event.target.result);
          if (loadedSpec.slides && loadedSpec.theme) {
            state.spec = loadedSpec;
            state.vibe = {
              vibe_name: loadedSpec.theme.preset || 'Loaded Design',
              family: loadedSpec.family || 'scrapbook'
            };
            tabs.preview.disabled = false;
            tabs.editor.disabled = false;
            document.getElementById('btn-save-json').disabled = false;
            document.getElementById('btn-export-quick').disabled = false;
            renderAllSlidesViaApi();
          } else {
            alert('Invalid carousel design file format.');
          }
        } catch (err) {
          alert('Error parsing JSON design file: ' + err.message);
        }
      };
      reader.readAsText(file);
    });

    // Export Quick Button
    document.getElementById('btn-export-quick').addEventListener('click', () => {
      downloadAllZip();
    });

    document.getElementById('btn-download-zip').addEventListener('click', () => {
      downloadAllZip();
    });

    // Caption modal
    document.getElementById('btn-copy-caption').addEventListener('click', () => {
      if (!state.vibe) return;
      const modal = document.getElementById('modal-caption');
      const textarea = document.getElementById('caption-text-area');
      const caption = state.vibe.post_caption || 'Aesthetic scrapbook memories ✨';
      const hashtags = (state.vibe.hashtags || ['scrapbook', 'aesthetic', 'photodump']).map(h => '#' + h).join(' ');
      textarea.value = `${caption}\n\n${hashtags}`;
      modal.showModal();
    });

    document.getElementById('btn-close-caption').addEventListener('click', () => {
      document.getElementById('modal-caption').close();
    });

    document.getElementById('btn-copy-caption-action').addEventListener('click', () => {
      const textarea = document.getElementById('caption-text-area');
      textarea.select();
      navigator.clipboard.writeText(textarea.value);
      alert('Caption & hashtags copied to clipboard!');
    });

    // Carousel arrows
    document.getElementById('btn-prev-slide').addEventListener('click', () => {
      if (state.activeSlideIndex > 0) {
        state.activeSlideIndex--;
        renderPreviewSlide();
      }
    });

    document.getElementById('btn-next-slide').addEventListener('click', () => {
      const total = state.spec ? state.spec.slides.length : 0;
      if (state.activeSlideIndex < total - 1) {
        state.activeSlideIndex++;
        renderPreviewSlide();
      }
    });

    // Touch swipe on preview stage
    let touchStartX = 0;
    const stage = document.getElementById('carousel-stage');
    stage.addEventListener('touchstart', (e) => {
      touchStartX = e.touches[0].clientX;
    }, { passive: true });

    stage.addEventListener('touchend', (e) => {
      const diffX = e.changedTouches[0].clientX - touchStartX;
      if (Math.abs(diffX) > 40) {
        if (diffX < 0) {
          // Swipe left -> next
          document.getElementById('btn-next-slide').click();
        } else {
          // Swipe right -> prev
          document.getElementById('btn-prev-slide').click();
        }
      }
    });
  }

  // ==========================================================================
  // Carousel Generation with Staged Progress
  // ==========================================================================
  async function generateCarousel() {
    const loadingModal = document.getElementById('modal-loading');
    const stageTitle = document.getElementById('loading-stage-title');
    const stageDesc = document.getElementById('loading-stage-desc');
    const progressBar = document.getElementById('progress-bar');

    loadingModal.showModal();

    // Stage 1
    progressBar.style.width = '20%';
    stageTitle.textContent = 'Reading photo vibe with Gemini...';
    stageDesc.textContent = 'Analyzing colors, lighting, and composition.';

    const payload = {
      images: state.images,
      hint: document.getElementById('hint-input').value.trim(),
      family: 'scrapbook',
      size: state.selectedSize,
      mode: state.selectedMode,
      preset: state.selectedPalette,
      cover: state.includeCover,
      use_ai: state.useAi
    };

    // Stage 2
    setTimeout(() => {
      progressBar.style.width = '55%';
      stageTitle.textContent = 'Art-directing scrapbook story & handwritten notes...';
      stageDesc.textContent = 'Designing heartfelt polaroid captions and annotations.';
    }, 900);

    // Stage 3
    setTimeout(() => {
      progressBar.style.width = '80%';
      stageTitle.textContent = 'Placing washi tape, torn paper & polaroids...';
      stageDesc.textContent = 'Assembling realistic aesthetic layers.';
    }, 2200);

    let data = null;
    try {
      const response = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const responseText = await response.text();
      if (response.ok && responseText.trim().startsWith('{')) {
        data = JSON.parse(responseText);
      } else {
        console.warn('Server API returned non-JSON or status ' + response.status + ':\n' + responseText.slice(0, 150));
      }
    } catch (netErr) {
      console.warn('Network call to /api/generate failed, using instant client-side generation:', netErr);
    }

    // Bulletproof Fallback: Generate aesthetic scrapbook client-side if server is unavailable
    if (!data || !data.spec) {
      console.log('✨ Building aesthetic scrapbook carousel client-side...');
      data = generateClientSideScrapbook(payload);
    }

    state.spec = data.spec;
    state.vibe = data.vibe;
    state.source = data.source;
    state.activeSlideIndex = 0;

    progressBar.style.width = '100%';
    stageTitle.textContent = 'Finalizing your scrapbook carousel!';

    // Enable navigation tabs & actions
    tabs.preview.disabled = false;
    tabs.editor.disabled = false;
    document.getElementById('btn-save-json').disabled = false;
    document.getElementById('btn-export-quick').disabled = false;

    // Render all slides (tries server rendering, falls back to client canvas)
    await renderAllSlidesViaApi();

    loadingModal.close();
    switchView('preview');
  }

  function generateClientSideScrapbook(options) {
    const { images, hint, preset, size, cover, mode } = options;
    const n = images.length;
    const isSquare = size === '1:1';
    const W = 1080;
    const H = isSquare ? 1080 : 1350;
    const cont = mode === 'continuous';

    const paletteMap = {
      'Warm Cream & Espresso': {
        title: '#2c2523', star: '#d49b45', hl: '#d9b48f', note: '#5c524b',
        band: '#ede6d8', tape: '#e8d3b9', bg1: '#f8f5ee', bg2: '#f0ebe1'
      },
      'Sage & Botanical': {
        title: '#273a2e', star: '#7d9d83', hl: '#a3c4a8', note: '#485d4f',
        band: '#dfe7df', tape: '#c8dbc9', bg1: '#f3f6f3', bg2: '#eaf0ea'
      },
      'Vintage Rose': {
        title: '#3e282b', star: '#d49b45', hl: '#e2a8a8', note: '#6c4d51',
        band: '#f1dedd', tape: '#f5c6c6', bg1: '#fbf5f4', bg2: '#f3e8e7'
      },
      'Terracotta & Clay': {
        title: '#3b2b25', star: '#e29b68', hl: '#c97a5b', note: '#66493e',
        band: '#eddccc', tape: '#e8cbb6', bg1: '#f9f6f0', bg2: '#eee6dc'
      },
      'Midnight Journal': {
        title: '#f4efe6', star: '#ffd166', hl: '#e5b869', note: '#e2dcd2',
        band: '#2b2b34', tape: '#d9ab55', bg1: '#201f26', bg2: '#16161b'
      }
    };

    const theme = paletteMap[preset] || paletteMap['Warm Cream & Espresso'];
    const storyHeadline = hint ? hint.toUpperCase() : 'SWEET MEMORIES';
    const slides = [];

    // Cover Slide (only if cover is checked and not in continuous panorama mode)
    if (cover && !cont) {
      slides.push({
        bg: { mode: 'gradient' },
        elements: [
          { type: 'torn', y: 0.62, h: Math.round(0.32 * H), color: 'theme:band', z: 0 },
          { type: 'tape', w: 230, h: 56, x: 0.28, y: 0.09, rotate: -8, color: 'theme:tape', alpha: 220, z: 2 },
          { type: 'tape', w: 210, h: 54, x: 0.74, y: 0.10, rotate: 6, color: 'theme:tape', alpha: 220, z: 2 },
          { type: 'frame', photo: 0, style: 'polaroid', caption: 'moment 01', font: 'hand', x: 0.5, y: 0.38, rotate: -2.5, z: 1 },
          { type: 'text', text: 'SCRAPBOOK STORY', font: 'sans_bold', size: 32, color: 'theme:star', tracking: 4, x: 0.5, y: 0.64, z: 1 },
          { type: 'text', text: storyHeadline, font: 'serif', size: 76, color: 'theme:title', x: 0.5, y: 0.72, z: 1 },
          { type: 'text', text: 'flip through our favorite moments', font: 'hand', size: 54, color: 'theme:note', x: 0.48, y: 0.84, rotate: -1, z: 1 },
          { type: 'arrow', x: 0.74, y: 0.85, angle: 10, color: 'theme:note', z: 2 },
          { type: 'text', text: 'swipe →', font: 'hand', size: 44, color: 'theme:note', x: 0.84, y: 0.91, rotate: 4, z: 2 },
          { type: 'star', shape: 'sparkle4', size: 54, x: 0.15, y: 0.66, rotate: -12, color: 'theme:star', z: 2 },
          { type: 'star', shape: 'sparkle4', size: 38, x: 0.86, y: 0.68, rotate: 15, color: 'theme:star', z: 2 }
        ]
      });
    }

    // Story Slides
    const sampleNotes = [
      'Golden hour lights and easy smiles',
      'A little corner of peace we stumbled upon',
      'Taking the long way back home',
      'Little moments that felt like forever',
      'One of those days you want to replay',
      'Laughter that made our stomachs hurt'
    ];

    for (let i = 0; i < n; i++) {
      let cx = 0.5;
      let cy = 0.44;
      let rot = (i % 2 === 0 ? -2.8 : 2.8) + (i % 3 === 0 ? 0.6 : -0.6);

      if (cont) {
        if (i % 3 === 0) {
          cx = 0.48;
          cy = 0.44;
          rot = -2.8;
        } else if (i % 3 === 1) {
          cx = 0.54;
          cy = 0.42;
          rot = 3.2;
        } else {
          cx = 0.46;
          cy = 0.45;
          rot = -1.6;
        }
      } else {
        cy += (i % 2 === 0 ? 0.02 : -0.02);
      }

      const note = sampleNotes[i % sampleNotes.length];

      const els = [
        { type: 'torn', y: 0.76, h: Math.round(0.24 * H), color: 'theme:band', z: 0 },
        { type: 'frame', photo: i, style: 'polaroid', caption: `memory 0${i + 1}`, font: 'hand', x: cx, y: cy, rotate: rot, z: 1 },
        { type: 'tape', w: 220, h: 54, x: cx, y: cy - 0.28, rotate: rot - 4, color: 'theme:tape', alpha: 230, z: 2 },
        { type: 'text', text: note, font: 'hand', size: 54, color: 'theme:note', max_w: 0.8, x: cx, y: 0.86, rotate: 1, z: 1 },
        { type: 'star', shape: 'sparkle4', size: 52, x: i % 2 === 0 ? 0.14 : 0.86, y: 0.18, color: 'theme:star', z: 2 },
        { type: 'star', shape: 'sparkle4', size: 36, x: i % 2 === 0 ? 0.88 : 0.12, y: 0.72, color: 'theme:star', z: 2 }
      ];

      if (!cont) {
        if (n > 1 && i % 2 === 1) {
          els.push({ type: 'inset', photo: (i + 1) % n, w: 200, label: 'detail', x: 0.82, y: 0.22, rotate: 6, color: 'theme:note', z: 2 });
          els.push({ type: 'tape', w: 120, h: 40, x: 0.82, y: 0.14, rotate: -10, color: 'theme:hl', alpha: 200, z: 3 });
        } else if (i % 2 === 0) {
          els.push({ type: 'squiggle', span: 0.45, x: 0.5, y: 0.92, color: 'theme:hl', z: 2 });
        }
      }

      slides.push({
        bg: { mode: 'gradient' },
        elements: els
      });
    }

    // In continuous mode, add cross-seam bridge elements to connect every pair of slides!
    if (cont) {
      for (let b = 1; b < n; b++) {
        const prevSlide = slides[b - 1];
        if (prevSlide && prevSlide.elements) {
          // 1. Cross-seam washi tape at x = 1.0 (spanning into next slide)
          prevSlide.elements.push({
            type: 'tape',
            w: 260,
            h: 62,
            x: 1.0,
            y: b % 2 === 1 ? 0.22 : 0.70,
            rotate: b % 2 === 1 ? -6 : 8,
            color: 'theme:tape',
            alpha: 235,
            z: 2
          });

          // 2. Cross-seam sparkle star
          prevSlide.elements.push({
            type: 'star',
            shape: 'sparkle4',
            size: 60,
            x: 1.0,
            y: 0.48,
            rotate: 12,
            color: 'theme:star',
            z: 2
          });

          // 3. Alternate mini photo inset / arrow across the seam
          if (b % 2 === 1 && n > 1) {
            prevSlide.elements.push({
              type: 'inset',
              photo: (b + 1) % n,
              w: 220,
              label: 'moment',
              x: 1.0,
              y: 0.34,
              rotate: -4,
              color: 'theme:note',
              z: 2
            });
            prevSlide.elements.push({
              type: 'tape',
              w: 130,
              h: 40,
              x: 1.0,
              y: 0.22,
              rotate: -8,
              color: 'theme:hl',
              alpha: 210,
              z: 3
            });
          } else {
            prevSlide.elements.push({
              type: 'arrow',
              x: 0.88,
              y: 0.88,
              angle: 15,
              color: 'theme:note',
              z: 2
            });
            prevSlide.elements.push({
              type: 'text',
              text: 'continue →',
              font: 'hand',
              size: 42,
              color: 'theme:note',
              x: 0.98,
              y: 0.93,
              rotate: 2,
              z: 2
            });
          }

          // 4. Squiggle wave line crossing the seam
          prevSlide.elements.push({
            type: 'squiggle',
            span: 0.5,
            x: 1.0,
            y: 0.92,
            color: 'theme:hl',
            z: 1
          });
        }
      }
    }

    return {
      vibe: {
        vibe_name: storyHeadline,
        mood_word: 'memories',
        post_caption: `${hint || 'Aesthetic memories captured in time'} ✨`,
        hashtags: ['scrapbook', 'aesthetic', 'photodump', 'polaroid', 'memories']
      },
      spec: {
        size: [W, H],
        mode: 'separate',
        family: 'scrapbook',
        theme: theme,
        global: { counter: true, swipe: true },
        slides: slides
      },
      source: 'Scrapbook Engine'
    };
  }

  async function renderAllSlidesViaApi() {
    let renderedFromServer = false;
    try {
      const res = await fetch('/api/render-all', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          spec: state.spec,
          images: state.images
        })
      });

      const text = await res.text();
      if (res.ok && text.trim().startsWith('{')) {
        const data = JSON.parse(text);
        if (data.slides && data.slides.length) {
          state.renderedSlides = data.slides;
          renderedFromServer = true;
          renderPreviewSlide();
          renderFilmstrip();
        }
      }
    } catch (e) {
      console.warn('Could not render via API, falling back to client canvas:', e);
    }

    if (!renderedFromServer) {
      await renderAllSlidesViaClient();
    }
  }

  async function renderAllSlidesViaClient() {
    state.renderedSlides = [];
    const total = state.spec ? state.spec.slides.length : 0;
    for (let i = 0; i < total; i++) {
      await state.editor.renderSlideObjects(i);
      const dataUrl = await CanvasExporter.exportSlideCanvas(state.editor.canvas, 1);
      state.renderedSlides.push(dataUrl);
    }
    // Restore active slide
    state.editor.loadSlide(state.activeSlideIndex, state.spec, state.images);
    renderPreviewSlide();
    renderFilmstrip();
  }

  // ==========================================================================
  // Preview Slide & Filmstrip Rendering
  // ==========================================================================
  function renderPreviewSlide() {
    if (!state.spec || !state.renderedSlides.length) return;

    const imgEl = document.getElementById('active-slide-img');
    const badgeEl = document.getElementById('slide-badge');
    const vibeNameEl = document.getElementById('preview-vibe-name');
    const sourceEl = document.getElementById('preview-source-badge');

    vibeNameEl.textContent = state.vibe ? state.vibe.vibe_name : 'Aesthetic Scrapbook';
    sourceEl.textContent = state.source ? `Generated via ${state.source}` : 'Aesthetic Scrapbook';

    const currentImg = state.renderedSlides[state.activeSlideIndex];
    if (currentImg) {
      imgEl.src = currentImg;
    }

    const total = state.spec.slides.length;
    badgeEl.textContent = `${String(state.activeSlideIndex + 1).padStart(2, '0')} / ${String(total).padStart(2, '0')}`;

    // Update filmstrip active state
    document.querySelectorAll('.filmstrip-thumb').forEach((thumb, idx) => {
      thumb.classList.toggle('active', idx === state.activeSlideIndex);
    });

    document.querySelectorAll('.editor-slide-item').forEach((item, idx) => {
      item.classList.toggle('active', idx === state.activeSlideIndex);
    });

    // Arrow states
    document.getElementById('btn-prev-slide').disabled = state.activeSlideIndex === 0;
    document.getElementById('btn-next-slide').disabled = state.activeSlideIndex === total - 1;
  }

  function renderFilmstrip() {
    const strip = document.getElementById('filmstrip-bar');
    strip.innerHTML = '';

    state.renderedSlides.forEach((src, idx) => {
      const thumb = document.createElement('div');
      thumb.className = `filmstrip-thumb ${idx === state.activeSlideIndex ? 'active' : ''}`;
      
      const img = document.createElement('img');
      img.src = src;
      img.alt = `Slide ${idx + 1}`;

      thumb.appendChild(img);
      thumb.addEventListener('click', () => {
        state.activeSlideIndex = idx;
        renderPreviewSlide();
      });

      strip.appendChild(thumb);
    });
  }

  function renderEditorFilmstrip() {
    const strip = document.getElementById('editor-filmstrip');
    strip.innerHTML = '';

    const total = state.spec ? state.spec.slides.length : 0;
    for (let idx = 0; idx < total; idx++) {
      const item = document.createElement('div');
      item.className = `editor-slide-item ${idx === state.activeSlideIndex ? 'active' : ''}`;

      const img = document.createElement('img');
      img.className = 'editor-slide-thumb';
      img.src = state.renderedSlides[idx] || state.images[idx % state.images.length];
      img.alt = `Slide ${idx + 1}`;

      const num = document.createElement('div');
      num.className = 'editor-slide-num';
      num.textContent = `Slide ${idx + 1}`;

      item.appendChild(img);
      item.appendChild(num);

      item.addEventListener('click', () => {
        state.activeSlideIndex = idx;
        state.editor.loadSlide(idx, state.spec, state.images);
        renderEditorFilmstrip();
      });

      strip.appendChild(item);
    }
  }

  // ==========================================================================
  // ZIP Download Export
  // ==========================================================================
  async function downloadAllZip() {
    if (!state.renderedSlides || !state.renderedSlides.length) {
      alert('Please create a carousel first before exporting.');
      return;
    }

    const filename = `${(state.vibe?.vibe_name || 'scrapbook').toLowerCase().replace(/\s+/g, '_')}_carousel.zip`;
    await CanvasExporter.exportAllAsZip(state.renderedSlides, filename);
  }

  // Hook for slide edits to refresh rendered slide
  window.onSlideModified = async function (slideIndex) {
    if (state.editor && state.editor.canvas) {
      const dataUrl = await CanvasExporter.exportSlideCanvas(state.editor.canvas, 1);
      state.renderedSlides[slideIndex] = dataUrl;
      renderEditorFilmstrip();
    }
  };

  // Launch app when DOM is ready
  document.addEventListener('DOMContentLoaded', init);
})();
