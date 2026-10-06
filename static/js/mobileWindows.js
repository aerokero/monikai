/**
 * Mobile tool-window chrome (≤768px, styled in sidebar.css): every tool window
 * gets the same full-screen header — [☰ menu] [centered title] [✕ close].
 * Minimize / grab handles / native close are hidden by CSS (.mw-hide).
 * Desktop is untouched: the injected buttons are display:none there.
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
  header.append(_btn('mw-close', 'Close', CLOSE_SVG, () => (native ? native.click() : closeFn())));
}
