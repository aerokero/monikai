// Settings navigation primitives.
//
// This module owns panel activation and sidebar click routing only. Individual
// panels continue to own their data loading and side effects.

import {
  DEFAULT_SETTINGS_PANEL_ID,
  SETTINGS_GROUPS,
  getSettingsPanel,
  isAdminManagedSettingsTab,
} from './registry.js';

const _boundModals = new WeakSet();

const BACK_SVG = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="15 18 9 12 15 6"/></svg>';

// Narrow layouts (phone / snapped window) show either the category list
// ("home") or one panel; CSS reads data-settings-view. Desktop shows both.
export function showSettingsHome(modalEl) {
  if (modalEl) modalEl.dataset.settingsView = 'home';
}

// Group labels, per-item descriptions and the page header all come from the
// registry so the markup stays a flat list of tab buttons.
function decorateSettingsNav(modalEl) {
  const nav = modalEl.querySelector('.settings-sidebar-content');
  if (!nav) return;
  nav.querySelectorAll('.settings-sidebar-divider, .settings-sidebar-label').forEach(el => el.remove());

  let lastGroup = null;
  nav.querySelectorAll('[data-settings-tab]').forEach(button => {
    const panel = getSettingsPanel(button.dataset.settingsTab);
    if (!panel) return;
    if (panel.group !== lastGroup) {
      lastGroup = panel.group;
      const group = SETTINGS_GROUPS.find(g => g.id === panel.group);
      const label = document.createElement('div');
      label.className = 'settings-sidebar-label' + (group?.adminOnly ? ' admin-only' : '');
      label.textContent = group?.label || '';
      button.before(label);
    }
    const text = button.querySelector(':scope > span');
    if (text && panel.description) {
      const wrap = document.createElement('span');
      wrap.className = 'settings-nav-text';
      const desc = document.createElement('small');
      desc.className = 'settings-nav-desc';
      desc.textContent = panel.description;
      text.replaceWith(wrap);
      wrap.append(text, desc);
    }
  });

  const panels = modalEl.querySelector('.settings-panels');
  if (panels && !panels.querySelector('.settings-page-head')) {
    const head = document.createElement('div');
    head.className = 'settings-page-head';
    head.innerHTML = `<button type="button" class="settings-back" aria-label="All settings">${BACK_SVG}</button>`
      + '<div class="settings-page-titles"><h2 class="settings-page-title"></h2><p class="settings-page-desc"></p></div>';
    head.querySelector('.settings-back').addEventListener('click', () => showSettingsHome(modalEl));
    panels.prepend(head);
  }
}

export function activateSettingsPanel(modalEl, tab) {
  if (!modalEl || !tab) return null;

  modalEl.querySelectorAll('[data-settings-tab]').forEach(button => {
    button.classList.toggle('active', button.dataset.settingsTab === tab);
  });
  modalEl.querySelectorAll('[data-settings-panel]').forEach(panel => {
    panel.classList.toggle('hidden', panel.dataset.settingsPanel !== tab);
  });

  const meta = getSettingsPanel(tab);
  const title = modalEl.querySelector('.settings-page-title');
  const desc = modalEl.querySelector('.settings-page-desc');
  if (title) title.textContent = meta?.label || '';
  if (desc) desc.textContent = meta?.description || '';
  if (modalEl.dataset.settingsView !== 'panel') modalEl.dataset.settingsView = 'panel';
  modalEl.querySelector('.settings-panels')?.scrollTo?.(0, 0);
  return tab;
}

export function getActiveSettingsTab(modalEl, fallback = DEFAULT_SETTINGS_PANEL_ID) {
  if (!modalEl) return fallback;
  const active = modalEl.querySelector('[data-settings-tab].active');
  return active?.dataset?.settingsTab || fallback;
}

export function bindSettingsNavigation(modalEl, options = {}) {
  if (!modalEl || _boundModals.has(modalEl)) return;
  _boundModals.add(modalEl);
  decorateSettingsNav(modalEl);

  const openAdminTab = options.openAdminTab;
  const onPanelActivated = options.onPanelActivated;

  modalEl.querySelectorAll('[data-settings-tab]').forEach(button => {
    button.addEventListener('click', () => {
      const tab = button.dataset.settingsTab;
      if (!tab) return;

      // Preserve the existing lazy-admin path: when the admin module accepts
      // the tab, it owns activation/rendering and the Settings shell does not
      // perform a second local switch.
      if (
        isAdminManagedSettingsTab(tab)
        && typeof openAdminTab === 'function'
        && openAdminTab(tab, button) === true
      ) {
        return;
      }

      activateSettingsPanel(modalEl, tab);
      if (typeof onPanelActivated === 'function') {
        onPanelActivated(tab, button);
      }
    });
  });
}
