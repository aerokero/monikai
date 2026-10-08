// Search Chat Module — Ctrl+K command palette for searching conversations

import uiModule from './ui.js';
import sessionModule from './sessions.js';

let API_BASE = '';
let debounceTimer = null;
let selectedIndex = -1;

function el(id) { return document.getElementById(id); }

function hideMobileSidebarForSearch() {
  if (window.innerWidth >= 768) return;
  const sidebar = el('sidebar');
  const rail = el('icon-rail');
  const backdrop = el('sidebar-backdrop');
  let changed = false;
  if (sidebar && !sidebar.classList.contains('hidden')) {
    sidebar.classList.add('hidden');
    changed = true;
  }
  if (rail && rail.classList.contains('mobile-mini')) {
    rail.classList.remove('mobile-mini');
    rail.style.cssText = '';
    changed = true;
  }
  if (backdrop) backdrop.classList.remove('visible');
  if (changed && typeof window.syncRailSide === 'function') {
    try { window.syncRailSide(); } catch (_) {}
  }
}

export function openSearch() {
  hideMobileSidebarForSearch();
  const overlay = el('search-overlay');
  if (!overlay) return;
  overlay.classList.remove('hidden');
  const input = el('search-input');
  if (input) {
    input.value = '';
    input.focus();
  }
  serverData = [];
  render('');
}

export function closeSearch() {
  const overlay = el('search-overlay');
  if (!overlay) return;
  overlay.classList.add('hidden');
  el('search-results').innerHTML = '';
  selectedIndex = -1;
}

export function isOpen() {
  const overlay = el('search-overlay');
  return overlay && !overlay.classList.contains('hidden');
}

var escapeHtml = uiModule.esc;

function highlightMatch(text, query) {
  if (!query) return escapeHtml(text);
  const escaped = escapeHtml(text);
  const regex = new RegExp('(' + query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
  return escaped.replace(regex, '<mark class="search-highlight">$1</mark>');
}

function formatTimestamp(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const now = new Date();
  const diff = now - d;
  if (diff < 86400000) {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  if (diff < 604800000) {
    return d.toLocaleDateString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' });
  }
  return d.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
}

const ICON_CHAT = '<svg class="search-row-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L3 21l1.9-5.4A8 8 0 1 1 21 12z"/></svg>';
const ICON_EMPTY = '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><circle cx="10.5" cy="10.5" r="7"/><path d="M21 21l-5.4-5.4M8 10.5h5"/></svg>';

let serverData = null; // null = not fetched yet for the current query

function listSessions() {
  const all = (sessionModule && sessionModule.getSessions && sessionModule.getSessions()) || [];
  const stamp = s => s.last_message_at || s.updated_at || s.created_at || '';
  return all
    .filter(s => !s.archived && s.folder !== 'Assistant' && !/^(Nobody|Incognito)$/.test((s.name || '').trim()))
    .sort((a, b) => stamp(b).localeCompare(stamp(a)))
    .map(s => ({ id: s.id, name: s.name || 'Untitled', at: stamp(s) }));
}

function chatRow(s, query) {
  return `<div class="search-result-item search-chat-row" data-session="${escapeHtml(String(s.id))}">
    ${ICON_CHAT}<div class="search-chat-name">${highlightMatch(s.name, query)}</div>
    <div class="search-result-time">${formatTimestamp(s.at)}</div>
  </div>`;
}

function section(label, count) {
  return `<div class="search-section">${label}${count ? `<span>${count}</span>` : ''}</div>`;
}

function render(query) {
  const container = el('search-results');
  if (!container) return;
  let html = '';

  if (!query) {
    const recent = listSessions().slice(0, 8);
    if (recent.length) html += section('Recent') + recent.map(s => chatRow(s, '')).join('');
    else html = `<div class="search-empty">${ICON_EMPTY}<b>No conversations yet</b></div>`;
  } else {
    const q = query.toLowerCase();
    const chats = listSessions().filter(s => s.name.toLowerCase().includes(q)).slice(0, 5);
    if (chats.length) html += section('Chats', chats.length) + chats.map(s => chatRow(s, query)).join('');

    if (serverData === null) {
      html += '<div class="search-loading"><i></i><i></i><i></i></div>';
    } else if (serverData.length) {
      const grouped = {};
      for (const r of serverData) (grouped[r.session_id] ||= { name: r.session_name, items: [] }).items.push(r);
      html += section('Messages', serverData.length);
      for (const [sid, group] of Object.entries(grouped)) {
        html += `<div class="search-group-header">${ICON_CHAT}${escapeHtml(group.name)}</div>`;
        for (const item of group.items) {
          html += `<div class="search-result-item" data-session="${escapeHtml(sid)}">
            <div class="search-result-role ${item.role === 'user' ? 'is-user' : ''}">${item.role === 'user' ? 'You' : 'AI'}</div>
            <div class="search-result-snippet">${highlightMatch(item.content_snippet, query)}</div>
            <div class="search-result-time">${formatTimestamp(item.timestamp)}</div>
          </div>`;
        }
      }
    } else if (!chats.length) {
      html = `<div class="search-empty">${ICON_EMPTY}<b>No results for “${escapeHtml(query)}”</b><span>Try a different word or a shorter phrase.</span></div>`;
    }
  }

  container.innerHTML = html;
  const items = container.querySelectorAll('.search-result-item');
  items.forEach((item, i) => {
    item.addEventListener('click', () => navigateToSession(item.dataset.session));
    item.addEventListener('mousemove', () => { if (selectedIndex !== i) { selectedIndex = i; updateSelection(false); } });
  });
  selectedIndex = items.length ? 0 : -1;
  updateSelection(false);
  container.scrollTop = 0;
}

function navigateToSession(sessionId) {
  closeSearch();
  if (sessionModule && sessionModule.selectSession) {
    sessionModule.selectSession(sessionId);
  }
}

function updateSelection(scroll = true) {
  const container = el('search-results');
  if (!container) return;
  const items = container.querySelectorAll('.search-result-item');
  items.forEach((item, i) => {
    item.classList.toggle('selected', i === selectedIndex);
  });
  // Scroll selected into view
  if (scroll && selectedIndex >= 0 && items[selectedIndex]) {
    items[selectedIndex].scrollIntoView({ block: 'nearest' });
  }
}

function handleKeydown(e) {
  if (!isOpen()) return;

  const container = el('search-results');
  const items = container ? container.querySelectorAll('.search-result-item') : [];
  const count = items.length;

  if (e.key === 'ArrowDown') {
    e.preventDefault();
    selectedIndex = count > 0 ? Math.min(selectedIndex + 1, count - 1) : -1;
    updateSelection();
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    selectedIndex = Math.max(selectedIndex - 1, 0);
    updateSelection();
  } else if (e.key === 'Enter') {
    e.preventDefault();
    if (selectedIndex >= 0 && items[selectedIndex]) {
      const sid = items[selectedIndex].dataset.session;
      navigateToSession(sid);
    }
  }
}

function handleInput(e) {
  const query = e.target.value.trim();
  if (debounceTimer) clearTimeout(debounceTimer);

  if (!query) {
    serverData = [];
    render('');
    return;
  }
  serverData = null;
  render(query);

  debounceTimer = setTimeout(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/search?q=${encodeURIComponent(query)}&limit=20`);
      if (!res.ok) { serverData = []; render(query); return; }
      const data = await res.json();
      if (el('search-input').value.trim() !== query) return; // stale response
      serverData = data;
      render(query);
    } catch (err) {
      console.error('Search error:', err);
      serverData = [];
      render(query);
    }
  }, 300);
}

export function init(apiBase) {
  API_BASE = apiBase || '';

  const input = el('search-input');
  if (input) {
    input.addEventListener('input', handleInput);
    input.addEventListener('keydown', handleKeydown);
  }

  // Close on overlay click (not popup click)
  const overlay = el('search-overlay');
  if (overlay) {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) closeSearch();
    });
  }
}

const searchChatModule = {
  init,
  openSearch,
  closeSearch,
  isOpen,
};

export default searchChatModule;
