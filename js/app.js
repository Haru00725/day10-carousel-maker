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

    document.getElementById('btn-mobile-done').addEventListener('click', () => {
      switchView('preview');
    });
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

    dropzone.addEventListener('click', () => fileInput.click());

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

    try {
      const response = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.error || 'Server returned an error');
      }

      const data = await response.json();
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

      // Render all slides via server API (or fallback)
      await renderAllSlidesViaApi();

      loadingModal.close();
      switchView('preview');

    } catch (err) {
      loadingModal.close();
      alert('Failed to generate carousel: ' + err.message);
    }
  }

  async function renderAllSlidesViaApi() {
    try {
      const res = await fetch('/api/render-all', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          spec: state.spec,
          images: state.images
        })
      });

      if (res.ok) {
        const data = await res.json();
        state.renderedSlides = data.slides || [];
        renderPreviewSlide();
        renderFilmstrip();
      }
    } catch (e) {
      console.warn('Could not render via API, falling back to editor canvas preview:', e);
    }
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
