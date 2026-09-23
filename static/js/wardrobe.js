/**
 * static/js/wardrobe.js
 * Monika Wardrobe Customization Module
 * Enables selecting Outfits, Hairstyles, Ahoge, and Backgrounds with live avatar preview.
 */

import Modals from './modalManager.js';
import { makeWindowDraggable } from './windowDrag.js';

let _open = false;
let _activeTab = 'outfits'; // 'outfits', 'hairstyles', 'ahoge', 'backgrounds'
let _escHandler = null;

export const OUTFITS = [
  { id: 'def', name: 'School Uniform' },
  { id: 'blazerless', name: 'Blazerless Uniform' },
  { id: 'sundress_white', name: 'White Sundress' },
  { id: 'blackdress', name: 'Black Dress' },
  { id: 'blackpinkdress', name: 'Black & Pink Dress' },
  { id: 'new_years_dress', name: "New Year's Gown" },
  { id: 'marisa', name: 'Witch Costume' },
  { id: 'santa', name: 'Santa Costume' },
  { id: 'santa_lingerie', name: 'Santa Lingerie' },
  { id: 'vday_lingerie', name: "Valentine's Lingerie" },
  { id: 'spider_lingerie', name: 'Spider Lingerie' },
  { id: 'bath_towel_white', name: 'Bath Towel' },
];

export const HAIRSTYLES = [
  { id: 'def', name: 'Classic Ponytail' },
  { id: 'down', name: 'Hair Down' },
  { id: 'braided', name: 'Braided Hair' },
  { id: 'downtiedstrand', name: 'Tied Strand' },
  { id: 'wet', name: 'Wet Hair' },
];

export const AHOGE_OPTIONS = [
  { id: 'none', name: 'None' },
  { id: 'ahoge_curl', name: 'Curl' },
  { id: 'ahoge_heart', name: 'Heart' },
  { id: 'ahoge_bent', name: 'Bent' },
  { id: 'ahoge_double', name: 'Double' },
  { id: 'ahoge_lightning', name: 'Lightning' },
  { id: 'ahoge_sharp', name: 'Sharp' },
  { id: 'ahoge_simple', name: 'Simple' },
  { id: 'ahoge_small', name: 'Small' },
  { id: 'ahoge_swoop', name: 'Swoop' },
  { id: 'ahoge_twisty', name: 'Twisty' },
];

export const BACKGROUNDS = [
  { id: 'auto', file: 'bg_room.png', name: 'Auto (Adaptive)' },
  { id: 'bg_room.png', file: 'bg_room.png', name: 'Clubroom (Day)' },
  { id: 'bg_room_night.png', file: 'bg_room_night.png', name: 'Clubroom (Night)' },
  { id: 'bg_kitchen.png', file: 'bg_kitchen.png', name: 'Kitchen (Day)' },
  { id: 'bg_kitchen_night.png', file: 'bg_kitchen_night.png', name: 'Kitchen (Night)' },
  { id: 'bg_school.png', file: 'bg_school.png', name: 'Classroom' },
  { id: 'bg_school_2.png', file: 'bg_school_2.png', name: 'Classroom 2' },
  { id: 'bg_school_corridor.png', file: 'bg_school_corridor.png', name: 'Hallway' },
  { id: 'bg_outside.png', file: 'bg_outside.png', name: 'Courtyard (Day)' },
  { id: 'bg_outside_night.png', file: 'bg_outside_night.png', name: 'Courtyard (Night)' },
  { id: 'bg_outside_2.png', file: 'bg_outside_2.png', name: 'Park (Day)' },
  { id: 'bg_outside_2_night.png', file: 'bg_outside_2_night.png', name: 'Park (Night)' },
  { id: 'bg_restaurant.png', file: 'bg_restaurant.png', name: 'Restaurant' },
  { id: 'bg_sea.png', file: 'bg_sea.png', name: 'Beach (Day)' },
  { id: 'bg_sea_night.png', file: 'bg_sea_night.png', name: 'Beach (Night)' },
  { id: 'bg_mountain.png', file: 'bg_mountain.png', name: 'Mountain' },
  { id: 'bg_closet.png', file: 'bg_closet.png', name: 'Closet' },
];

function _ensureStyles() {
  if (document.getElementById('wardrobe-module-styles')) return;
  const style = document.createElement('style');
  style.id = 'wardrobe-module-styles';
  style.textContent = `
    .wardrobe-tabs {
      padding: 0 14px;
    }
    .wardrobe-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(135px, 1fr));
      gap: 12px;
    }
    .wardrobe-grid.wardrobe-grid-wide {
      grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    }
    .wardrobe-card {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 8px;
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      cursor: pointer;
      position: relative;
      transition: border-color 0.15s, transform 0.15s, box-shadow 0.15s, background-color 0.15s;
      user-select: none;
      box-sizing: border-box;
    }
    .wardrobe-card:hover {
      transform: translateY(-2px);
      border-color: color-mix(in srgb, var(--accent, var(--red)) 50%, var(--border));
      box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);
    }
    .wardrobe-card.selected {
      border-color: var(--accent, var(--red));
      background: color-mix(in srgb, var(--accent, var(--red)) 10%, var(--panel));
      box-shadow: 0 0 12px color-mix(in srgb, var(--accent, var(--red)) 25%, transparent);
    }
    .wardrobe-card-preview {
      width: 100%;
      aspect-ratio: 3 / 4;
      border-radius: 8px;
      background: color-mix(in srgb, var(--fg) 4%, transparent);
      border: 1px solid color-mix(in srgb, var(--border) 60%, transparent);
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      position: relative;
    }
    .wardrobe-card-preview.preview-wide {
      aspect-ratio: 16 / 10;
    }
    .wardrobe-card-preview img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      object-position: center top;
      pointer-events: none;
      transition: transform 0.25s ease;
    }
    .wardrobe-card:hover .wardrobe-card-preview img {
      transform: scale(1.04);
    }
    .wardrobe-card-check {
      position: absolute;
      top: 6px;
      right: 6px;
      width: 18px;
      height: 18px;
      border-radius: 50%;
      background: var(--accent, var(--red));
      color: #fff;
      display: none;
      align-items: center;
      justify-content: center;
      font-size: 11px;
      font-weight: 700;
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.45);
      z-index: 2;
    }
    .wardrobe-card.selected .wardrobe-card-check {
      display: flex;
    }
    .wardrobe-card-title {
      font-size: 12px;
      font-weight: 500;
      color: var(--fg);
      margin-top: 8px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      width: 100%;
      line-height: 1.2;
    }
    .wardrobe-card.selected .wardrobe-card-title {
      color: var(--accent, var(--red));
      font-weight: 600;
    }
  `;
  document.head.appendChild(style);
}

function _renderContent() {
  const container = document.getElementById('wardrobe-grid-container');
  if (!container) return;

  const viz = window.monikaVisualizer;
  const state = viz ? viz.getWardrobeState() : {
    outfit: 'def',
    hairStyle: 'def',
    ahoge: 'ahoge_curl',
    background: 'auto',
    autoMode: false
  };

  if (_activeTab === 'outfits') {
    container.className = 'wardrobe-grid';
    container.innerHTML = OUTFITS.map(item => {
      const isSel = state.outfit === item.id;
      const imgPath = `/static/vn/monika/previews/outfits/${item.id}.png`;
      return `
        <div class="wardrobe-card ${isSel ? 'selected' : ''}" data-type="outfit" data-id="${item.id}" title="${item.name}">
          <div class="wardrobe-card-preview">
            <span class="wardrobe-card-check">✓</span>
            <img src="${imgPath}" alt="${item.name}" loading="lazy" />
          </div>
          <div class="wardrobe-card-title">${item.name}</div>
        </div>
      `;
    }).join('');
  } else if (_activeTab === 'hairstyles') {
    container.className = 'wardrobe-grid';
    container.innerHTML = HAIRSTYLES.map(item => {
      const isSel = state.hairStyle === item.id;
      const imgPath = `/static/vn/monika/previews/hairstyles/${item.id}.png`;
      return `
        <div class="wardrobe-card ${isSel ? 'selected' : ''}" data-type="hair" data-id="${item.id}" title="${item.name}">
          <div class="wardrobe-card-preview">
            <span class="wardrobe-card-check">✓</span>
            <img src="${imgPath}" alt="${item.name}" loading="lazy" />
          </div>
          <div class="wardrobe-card-title">${item.name}</div>
        </div>
      `;
    }).join('');
  } else if (_activeTab === 'ahoge') {
    container.className = 'wardrobe-grid';
    container.innerHTML = AHOGE_OPTIONS.map(item => {
      const isSel = (state.ahoge || 'none') === item.id;
      const imgPath = `/static/vn/monika/previews/ahoge/${item.id}.png`;
      return `
        <div class="wardrobe-card ${isSel ? 'selected' : ''}" data-type="ahoge" data-id="${item.id}" title="${item.name}">
          <div class="wardrobe-card-preview">
            <span class="wardrobe-card-check">✓</span>
            <img src="${imgPath}" alt="${item.name}" loading="lazy" />
          </div>
          <div class="wardrobe-card-title">${item.name}</div>
        </div>
      `;
    }).join('');
  } else if (_activeTab === 'backgrounds') {
    container.className = 'wardrobe-grid wardrobe-grid-wide';
    container.innerHTML = BACKGROUNDS.map(item => {
      const isSel = state.background === item.id;
      const isAuto = item.id === 'auto';
      const imgPath = isAuto 
        ? '/static/vn/location/bg_room.png' 
        : `/static/vn/location/${item.file}`;
      return `
        <div class="wardrobe-card ${isSel ? 'selected' : ''}" data-type="background" data-id="${item.id}" title="${item.name}">
          <div class="wardrobe-card-preview preview-wide">
            <span class="wardrobe-card-check">✓</span>
            <img src="${imgPath}" alt="${item.name}" loading="lazy" />
          </div>
          <div class="wardrobe-card-title">${item.name}</div>
        </div>
      `;
    }).join('');
  }

  // Update tabs active state
  const modal = document.getElementById('wardrobe-modal');
  if (modal) {
    modal.querySelectorAll('.wardrobe-tab').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === _activeTab);
    });
    const autoToggle = modal.querySelector('#wardrobe-auto-toggle');
    if (autoToggle) {
      autoToggle.checked = !!state.autoMode;
    }
  }
}

function _handleItemClick(e) {
  const card = e.target.closest('.wardrobe-card');
  if (!card) return;

  const type = card.dataset.type;
  const id = card.dataset.id;
  const viz = window.monikaVisualizer;
  if (!viz) return;

  if (type === 'outfit') {
    viz.setOutfit(id);
  } else if (type === 'hair') {
    viz.setHairStyle(id);
  } else if (type === 'ahoge') {
    viz.setAhoge(id);
  } else if (type === 'background') {
    viz.setBackground(id);
  }

  _renderContent();
}

export function openWardrobe() {
  if (Modals.isMinimized('wardrobe-modal')) {
    Modals.restore('wardrobe-modal');
    _open = true;
    return;
  }

  let modal = document.getElementById('wardrobe-modal');
  if (modal) {
    modal.classList.remove('hidden', 'modal-minimized');
    modal.style.display = 'flex';
  } else {
    _ensureStyles();
    modal = document.createElement('div');
    modal.className = 'modal';
    modal.id = 'wardrobe-modal';
    modal.innerHTML = `
      <div class="modal-content wardrobe-modal-content" style="background:var(--bg); width:min(740px, 94vw); height:600px; max-height:85vh; display:flex; flex-direction:column; overflow:hidden;">
        <div class="modal-header">
          <h4>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-right:6px">
              <path d="M12 2a3 3 0 0 0-3 3c0 .8.3 1.5.8 2.1L2.4 15.6A2 2 0 0 0 4 19h16a2 2 0 0 0 1.6-3.4L14.2 7.1c.5-.6.8-1.3.8-2.1a3 3 0 0 0-3-3z"/>
            </svg>Wardrobe
          </h4>
          <label class="admin-switch-inline" style="margin-left:auto;margin-right:12px;font-size:12px;cursor:pointer;user-select:none;" title="Monika adapts appearance automatically based on context">
            <span>Auto</span>
            <label class="admin-switch" title="Auto appearance">
              <input type="checkbox" id="wardrobe-auto-toggle" />
              <span class="admin-slider"></span>
            </label>
          </label>
          <button class="close-btn" id="wardrobe-close" aria-label="Close wardrobe">✖</button>
        </div>

        <div class="memory-tabs wardrobe-tabs" role="tablist">
          <button class="memory-tab wardrobe-tab ${_activeTab === 'outfits' ? 'active' : ''}" data-tab="outfits" role="tab">Outfits</button>
          <button class="memory-tab wardrobe-tab ${_activeTab === 'hairstyles' ? 'active' : ''}" data-tab="hairstyles" role="tab">Hairstyles</button>
          <button class="memory-tab wardrobe-tab ${_activeTab === 'ahoge' ? 'active' : ''}" data-tab="ahoge" role="tab">Ahoge</button>
          <button class="memory-tab wardrobe-tab ${_activeTab === 'backgrounds' ? 'active' : ''}" data-tab="backgrounds" role="tab">Backgrounds</button>
        </div>

        <div class="modal-body wardrobe-modal-body" style="flex:1 1 auto; min-height:0; overflow-y:auto; padding:14px;">
          <div class="wardrobe-grid" id="wardrobe-grid-container"></div>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    // Tab switching
    modal.querySelectorAll('.wardrobe-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        _activeTab = btn.dataset.tab;
        _renderContent();
      });
    });

    // Grid item selection
    const grid = modal.querySelector('#wardrobe-grid-container');
    if (grid) {
      grid.addEventListener('click', _handleItemClick);
    }

    // Auto-mode toggle
    const autoToggle = modal.querySelector('#wardrobe-auto-toggle');
    if (autoToggle) {
      autoToggle.addEventListener('change', () => {
        const viz = window.monikaVisualizer;
        if (viz) {
          viz.setWardrobe({ autoMode: autoToggle.checked });
        }
      });
    }

    // Close handlers
    modal.querySelector('#wardrobe-close')?.addEventListener('click', closeWardrobe);
    modal.addEventListener('click', (event) => {
      if (event.target === modal) {
        event.stopPropagation();
        closeWardrobe();
      }
    });

    // Make draggable
    const content = modal.querySelector('.modal-content');
    const header = modal.querySelector('.modal-header');
    if (content && header) makeWindowDraggable(modal, { content, header });

    // Register in Modals manager
    Modals.register('wardrobe-modal', {
      railBtnId: 'rail-wardrobe',
      sidebarBtnId: 'tool-wardrobe-btn',
      label: 'Wardrobe',
      icon: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3c0 .8.3 1.5.8 2.1L2.4 15.6A2 2 0 0 0 4 19h16a2 2 0 0 0 1.6-3.4L14.2 7.1c.5-.6.8-1.3.8-2.1a3 3 0 0 0-3-3z"/></svg>`,
      restoreFn: () => {
        _open = true;
      },
      closeFn: closeWardrobe,
    });

    Modals.injectMinimizeButton(modal, 'wardrobe-modal');
  }

  _open = true;

  // ESC handler
  if (!_escHandler) {
    _escHandler = (event) => {
      if (event.key !== 'Escape' || !_open) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      closeWardrobe();
    };
    document.addEventListener('keydown', _escHandler, true);
  }

  _renderContent();
}

export function closeWardrobe() {
  if (Modals.isRegistered('wardrobe-modal')) {
    Modals.close('wardrobe-modal');
  }
  const modal = document.getElementById('wardrobe-modal');
  if (modal) modal.remove();
  _open = false;
  if (_escHandler) {
    document.removeEventListener('keydown', _escHandler, true);
    _escHandler = null;
  }
}

export function toggleWardrobe() {
  if (Modals.toggle('wardrobe-modal')) return;
  if (_open) closeWardrobe();
  else openWardrobe();
}

export function isWardrobeOpen() {
  return _open;
}

const wardrobeModule = {
  openWardrobe,
  closeWardrobe,
  toggleWardrobe,
  isWardrobeOpen,
  OUTFITS,
  HAIRSTYLES,
  AHOGE_OPTIONS,
  BACKGROUNDS,
};

export default wardrobeModule;
