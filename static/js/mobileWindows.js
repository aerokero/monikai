/**
 * Mobile tool-window chrome (≤768px, styled in sidebar.css): every tool window
 * gets the same full-screen header — [☰ menu] [centered title].
 * Minimize / grab handles / native close are hidden by CSS (.mw-hide).
 * Desktop is untouched: the injected buttons are display:none there.
 *
 * Mobile is one view at a time: picking a tool in the menu replaces the open
 * window, picking a chat closes it, and Android's back gesture returns to chat.
 */
const MENU_SVG = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>';
const CLOSE_SVG = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/></svg>';
const NATIVE_CLOSE = '.close-btn, .modal-close, [data-close]';
const HIDDEN = `${NATIVE_CLOSE}, .modal-minimize-btn, .minimize-btn, [data-minimize]`;

function _btn(cls, label, svg, onClick) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = cls;
  b.setAttribute('aria-label', label);
  b.innerHTML = svg;
  b.addEventListener('click', (e) => { e.stopPropagation(); onClick(); });
  return b;
}

/** root: the .modal / .notes-pane element. closeFn: full close of that window. */
export function decorateWindow(root, closeFn) {
  const header = root?.querySelector('.modal-header, .notes-pane-header');
  if (!header || header.dataset.mw) return;
  header.dataset.mw = '1';
  header.classList.add('mw-header');
  (root.querySelector('.modal-content') || root).classList.add('mw-win');

  // Title = the heading's direct-child ancestor in the header (may wrap an icon).
  let title = header.querySelector('h1, h2, h3, h4, h5, [class*="title"]');
  while (title && title.parentElement !== header) title = title.parentElement;
  if (title) title.classList.add('mw-title');

  header.querySelectorAll(HIDDEN).forEach((el) => el.classList.add('mw-hide'));
  // Hide spacers and wrappers left with nothing interactive (e.g. the
  // minimize+close button groups) so they don't take a flex slot / wrap row.
  for (const c of header.children) {
    if (c === title || c.classList.contains('mw-hide')) continue;
    const ui = c.querySelectorAll('button, input, select, a, label');
    if (!ui.length ? !c.textContent.trim() : [...ui].every((el) => el.closest('.mw-hide'))) c.classList.add('mw-hide');
  }

  // Native close (if any) does the tool's own teardown; fall back to closeFn.
  const native = header.querySelector(NATIVE_CLOSE);
  header.prepend(_btn('mw-menu', 'Menu', MENU_SVG, () => document.getElementById('hamburger-btn')?.click()));
  root._mwClose = () => (native ? native.click() : closeFn());
  header.append(_btn('mw-close', 'Close', CLOSE_SVG, root._mwClose));
}

// ── One view at a time (mobile) ──
const VIEW_SEL = '[id^="tool-"], [id^="rail-"], [id^="user-bar-"], #email-section-title';
const CHAT_SEL = '#sidebar-new-chat-btn, #session-list .session-item';

function _shown(el) {
  return !el.classList.contains('hidden') && !el.classList.contains('notes-pane-leaving')
    && getComputedStyle(el).display !== 'none' && el.getClientRects().length > 0;
}

function _openWindows() {
  return [...document.querySelectorAll('.modal, #notes-pane')].filter(_shown);
}

function _closeWindow(w) {
  if (w._mwClose) return w._mwClose();
  if (w.id === 'notes-pane') return import('./notes.js').then((n) => n.closePanel());
  const native = w.querySelector(NATIVE_CLOSE);
  if (native) native.click(); else w.classList.add('hidden');
}

// Android back closes the current view (CloseWatcher: Chromium only). History
// entries are avoided on purpose: sessions own the URL hash via replaceState.
let _backWatcher = null;
const _viewOf = {}; // menu button id → window id it opened
function _watchBack(on) {
  _backWatcher?.destroy();
  _backWatcher = null;
  if (!on || !('CloseWatcher' in window)) return;
  _backWatcher = new CloseWatcher();
  _backWatcher.onclose = () => {
    _backWatcher = null;
    if (!_openWindows().length) return;
    // Back = Esc: the window first closes its own inner layer (an event form,
    // a sub-panel) and marks the key handled; only an unhandled back closes
    // the whole view.
    const esc = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
    (document.activeElement || document).dispatchEvent(esc);
    if (!esc.defaultPrevented) _openWindows().forEach(_closeWindow);
    setTimeout(() => { if (_openWindows().length) _watchBack(true); }, 300);
  };
}

document.addEventListener('click', (e) => {
  if (window.innerWidth > 768 || !e.target.closest('#sidebar, #icon-rail')) return;
  if (e.target.closest('.session-menu-btn, .item-drag-handle')) return;
  if (e.target.closest(CHAT_SEL)) {
    _openWindows().forEach(_closeWindow);
    _watchBack(false);
    // A chat is a view too: land in it (session rows close the menu themselves).
    setTimeout(() => {
      if (!document.getElementById('sidebar')?.classList.contains('hidden')) document.getElementById('hamburger-btn')?.click();
    }, 0);
    return;
  }
  const btn = e.target.closest(VIEW_SEL);
  if (!btn) return;
  const before = _openWindows();
  // Tool buttons toggle their window; tapping the current view just hides the menu.
  const current = document.getElementById(_viewOf[btn.id]);
  if (current && before.includes(current)) {
    e.preventDefault();
    e.stopImmediatePropagation();
    document.getElementById('hamburger-btn')?.click();
    return;
  }
  // Tools open asynchronously; close the previous view once the new one is up.
  let tries = 0;
  const poll = setInterval(() => {
    const added = _openWindows().find((w) => !before.includes(w));
    if (added) { _viewOf[btn.id] = added.id; before.forEach(_closeWindow); _watchBack(true); }
    if (added || ++tries > 40) clearInterval(poll);
  }, 50);
}, true);
