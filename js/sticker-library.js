/**
 * Scrapli — Reusable, Searchable Scrapbook Sticker Library
 * High-performance sticker asset manager with category filtering, tag search, and Fabric.js canvas integration.
 */

(function () {
  'use strict';

  const CATEGORIES = [
    { id: 'all', label: 'All', icon: '✨' },
    { id: 'city_life', label: 'City Life', icon: '🏙️' },
    { id: 'travel', label: 'Travel', icon: '✈️' },
    { id: 'cafe_food', label: 'Cafe & Food', icon: '☕' },
    { id: 'girly_coquette', label: 'Coquette', icon: '🎀' },
    { id: 'nature', label: 'Nature', icon: '🌿' },
    { id: 'fashion', label: 'Fashion', icon: '👠' },
    { id: 'vintage_grunge', label: 'Vintage', icon: '🎞️' }
  ];

  class StickerLibrary {
    constructor() {
      this.catalog = [];
      this.activeCategory = 'all';
      this.searchQuery = '';
      this.isLoading = false;
      this.isInitialized = false;
      this.desktopContainer = null;
      this.mobileContainer = null;
    }

    async init() {
      if (this.isInitialized) return;
      await this.loadCatalog();
      this.isInitialized = true;
      this.render();
      this.bindEvents();
    }

    async loadCatalog() {
      this.isLoading = true;
      try {
        const res = await fetch('/api/stickers');
        if (res.ok) {
          const data = await res.json();
          if (data.stickers && data.stickers.length) {
            this.catalog = data.stickers;
          }
        }
      } catch (err) {
        console.warn('Could not fetch stickers from /api/stickers, trying static JSON fallback:', err);
      }

      if (!this.catalog.length) {
        try {
          const res = await fetch('/assets/stickers_catalog.json');
          if (res.ok) {
            this.catalog = await res.json();
          }
        } catch (e) {
          console.error('Failed to load static stickers catalog:', e);
        }
      }

      this.isLoading = false;
      window.StickerCatalog = this.catalog;
    }

    getFilteredStickers() {
      const q = this.searchQuery.trim().toLowerCase();
      const cat = this.activeCategory;

      return this.catalog.filter((sticker) => {
        // Category check
        if (cat !== 'all' && sticker.category !== cat) {
          return false;
        }

        // Query check
        if (!q) return true;

        if (sticker.name && sticker.name.toLowerCase().includes(q)) return true;
        if (sticker.id && sticker.id.toLowerCase().includes(q)) return true;
        if (sticker.category && sticker.category.toLowerCase().includes(q)) return true;
        if (sticker.visual_style && sticker.visual_style.toLowerCase().includes(q)) return true;
        if (sticker.recommended_use && sticker.recommended_use.toLowerCase().includes(q)) return true;
        if (sticker.theme_tags && sticker.theme_tags.some(tag => tag.toLowerCase().includes(q))) return true;

        return false;
      });
    }

    getStickerById(id) {
      return this.catalog.find(s => s.id === id || s.path === id);
    }

    render() {
      this.desktopContainer = document.getElementById('sticker-library-desktop');
      this.mobileContainer = document.getElementById('sticker-library-mobile');

      if (this.desktopContainer) {
        this.renderContainer(this.desktopContainer, 'desktop');
      }
      if (this.mobileContainer) {
        this.renderContainer(this.mobileContainer, 'mobile');
      }
    }

    renderContainer(container, context = 'desktop') {
      const filtered = this.getFilteredStickers();
      const totalCount = this.catalog.length;
      const filteredCount = filtered.length;

      container.innerHTML = `
        <div class="sticker-lib-wrapper">
          <!-- Search Box -->
          <div class="sticker-search-bar">
            <span class="search-glyph">🔍</span>
            <input type="search" class="sticker-search-input" data-context="${context}" 
                   placeholder="Search stickers (e.g. camera, bow, taxi, coffee)..." 
                   value="${this.searchQuery}">
            ${this.searchQuery ? `<button type="button" class="sticker-clear-btn" data-context="${context}" title="Clear search">✕</button>` : ''}
          </div>

          <!-- Category Filter Pills -->
          <div class="sticker-cat-scroll" data-context="${context}">
            ${CATEGORIES.map(c => `
              <button type="button" class="sticker-cat-chip ${this.activeCategory === c.id ? 'active' : ''}" 
                      data-cat="${c.id}" data-context="${context}">
                <span class="cat-icon">${c.icon}</span>
                <span class="cat-name">${c.label}</span>
              </button>
            `).join('')}
          </div>

          <!-- Results Header -->
          <div class="sticker-results-meta">
            <span class="results-count">${filteredCount} ${filteredCount === 1 ? 'sticker' : 'stickers'}</span>
            ${this.activeCategory !== 'all' || this.searchQuery ? `<button type="button" class="sticker-reset-btn" data-context="${context}">Reset Filter</button>` : ''}
          </div>

          <!-- Sticker Grid -->
          <div class="sticker-asset-grid" id="grid-${context}">
            ${filteredCount === 0 ? `
              <div class="sticker-empty-state">
                <span class="empty-emoji">🔍</span>
                <p>No stickers found for "${this.searchQuery}"</p>
                <small>Try searching "camera", "coffee", "flower", or "vintage"</small>
              </div>
            ` : filtered.map(s => `
              <div class="sticker-asset-card" data-sticker-id="${s.id}" draggable="true" title="${s.name} (${s.visual_style.replace('_', ' ')})">
                <div class="sticker-thumb-box">
                  <img src="${s.path}" alt="${s.name}" class="sticker-thumb-img" loading="lazy">
                </div>
                <div class="sticker-card-name">${s.name}</div>
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }

    bindEvents() {
      const handleSearchInput = (e) => {
        if (!e.target.classList.contains('sticker-search-input')) return;
        this.searchQuery = e.target.value;
        this.render();
        // Restore focus to active input
        const context = e.target.getAttribute('data-context');
        const activeInput = document.querySelector(`.sticker-search-input[data-context="${context}"]`);
        if (activeInput) {
          activeInput.focus();
          activeInput.selectionStart = activeInput.selectionEnd = activeInput.value.length;
        }
      };

      const handleClearClick = (e) => {
        const btn = e.target.closest('.sticker-clear-btn');
        if (!btn) return;
        this.searchQuery = '';
        this.render();
      };

      const handleCategoryClick = (e) => {
        const chip = e.target.closest('.sticker-cat-chip');
        if (!chip) return;
        const cat = chip.getAttribute('data-cat');
        if (cat) {
          this.activeCategory = cat;
          this.render();
        }
      };

      const handleResetClick = (e) => {
        const resetBtn = e.target.closest('.sticker-reset-btn');
        if (!resetBtn) return;
        this.activeCategory = 'all';
        this.searchQuery = '';
        this.render();
      };

      const handleStickerClick = async (e) => {
        const card = e.target.closest('.sticker-asset-card');
        if (!card) return;
        const stickerId = card.getAttribute('data-sticker-id');
        const sticker = this.getStickerById(stickerId);
        if (!sticker) return;

        // Visual click feedback animation
        card.classList.add('pop-active');
        setTimeout(() => card.classList.remove('pop-active'), 250);

        // Add to active Fabric.js canvas editor
        const editor = window.editor || (window.state && window.state.editor);
        if (editor) {
          await editor.addStickerAsset(sticker);
        }

        // If on mobile, close sheet
        const sheet = document.getElementById('bottom-sheet');
        const backdrop = document.getElementById('bottom-sheet-backdrop');
        if (sheet && sheet.classList.contains('active')) {
          sheet.classList.remove('active');
          if (backdrop) backdrop.classList.remove('active');
        }
      };

      const handleDragStart = (e) => {
        const card = e.target.closest('.sticker-asset-card');
        if (!card) return;
        const stickerId = card.getAttribute('data-sticker-id');
        e.dataTransfer.setData('text/plain', JSON.stringify({ type: 'sticker', id: stickerId }));
      };

      // Delegate events to document
      document.addEventListener('input', handleSearchInput);
      document.addEventListener('click', handleClearClick);
      document.addEventListener('click', handleCategoryClick);
      document.addEventListener('click', handleResetClick);
      document.addEventListener('click', handleStickerClick);
      document.addEventListener('dragstart', handleDragStart);
    }
  }

  // Create singleton instance
  window.stickerLibrary = new StickerLibrary();

  // Initialize on DOMContentLoaded or immediate if DOM is already ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => window.stickerLibrary.init());
  } else {
    window.stickerLibrary.init();
  }
})();
