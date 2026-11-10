/**
 * static/js/alarms.js
 * Alarm clock panel: list, add/edit, enable, delete, and Stop/Snooze while ringing.
 * Backed by /api/alarms (same AlarmManager as voice and Telegram).
 */

import uiModule from './ui.js';
import * as Modals from './modalManager.js';
import { makeWindowDraggable } from './windowDrag.js';
import { icon as phosphorIcon } from './iconRegistry.js';

const MODAL_ID = 'alarms-modal';
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const POLL_MS = 4000;

let _open = false;
let _escHandler = null;
let _pollTimer = null;
let _state = { alarms: [], ringing: null, sounds: [], snooze_minutes: 10 };
let _editing = null; // null = form hidden, {} = new, alarm = edit
let _preview = null; // { audio, button } while a sound preview plays
const SOUND_ACCEPT = 'audio/*,.mp3,.wav,.ogg,.oga,.opus,.flac,.m4a,.aac,.webm';

function _stopPreview() {
  if (!_preview) return;
  _preview.audio.pause();
  _preview.button.innerHTML = phosphorIcon('speaker');
  _preview.button.setAttribute('aria-pressed', 'false');
  _preview = null;
}

function _togglePreview(button, soundName) {
  const wasPlaying = Boolean(_preview);
  _stopPreview();
  if (wasPlaying) return;
  const audio = new Audio(`/api/alarms/sounds/preview?name=${encodeURIComponent(soundName)}`);
  _preview = { audio, button };
  button.innerHTML = phosphorIcon('stop');
  button.setAttribute('aria-pressed', 'true');
  audio.addEventListener('ended', _stopPreview);
  audio.play().catch(err => {
    _stopPreview();
    uiModule.showToast?.(`Preview failed: ${err.message}`);
  });
}

async function _uploadSound(file, select) {
  const body = new FormData();
  body.append('file', file);
  try {
    const res = await fetch('/api/alarms/sounds', { method: 'POST', body });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    _state = data;
    if (![...select.options].some(o => o.value === data.uploaded)) {
      select.add(new Option(data.uploaded, data.uploaded));
    }
    select.value = data.uploaded;
    uiModule.showToast?.(`Uploaded ${data.uploaded}`);
  } catch (err) {
    uiModule.showToast?.(`Upload failed: ${err.message}`);
  }
}

function _esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

async function _api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

async function _refresh() {
  try {
    _state = await _api('/api/alarms');
    _renderList();
  } catch (err) {
    _renderError(err.message);
  }
}

async function _act(path, options) {
  try {
    _state = await _api(path, options);
    _renderList();
    return true;
  } catch (err) {
    uiModule.showToast?.(`Alarm: ${err.message}`);
    return false;
  }
}

function _daysLabel(days) {
  const key = (days || []).join(',');
  if (!key) return 'Once';
  if (key === '0,1,2,3,4,5,6') return 'Every day';
  if (key === '0,1,2,3,4') return 'Weekdays';
  if (key === '5,6') return 'Weekends';
  return days.map(d => DAYS[d]).join(', ');
}

function _formatNext(iso) {
  if (!iso) return 'Off';
  return 'Next: ' + new Date(iso).toLocaleString('en-GB', {
    weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

function _ensureStyles() {
  if (document.getElementById('alarms-module-styles')) return;
  const style = document.createElement('style');
  style.id = 'alarms-module-styles';
  style.textContent = `
    .alarms-body { padding: var(--ui-s4); display: flex; flex-direction: column; gap: var(--ui-s3); }
    .alarms-ringing { display: flex; align-items: center; gap: var(--ui-s3); padding: var(--ui-s3) var(--ui-s4);
      border-radius: var(--ui-r-lg); background: var(--ui-accent-soft); font-weight: var(--ui-fw-bold); }
    .alarms-ringing .grow { flex: 1; }
    .alarms-row { display: flex; align-items: center; gap: var(--ui-s3); padding: var(--ui-s3) var(--ui-s4);
      border: 1px solid var(--ui-line); border-radius: var(--ui-r-lg); }
    .alarms-row.disabled { opacity: .55; }
    .alarms-time { font-size: 1.6em; font-variant-numeric: tabular-nums; font-weight: var(--ui-fw-bold); min-width: 3.2em; }
    .alarms-meta { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
    .alarms-meta .label { font-weight: var(--ui-fw-medium); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .alarms-meta .sub { color: var(--ui-text-muted); font-size: var(--ui-fs-sm); }
    .alarms-empty { color: var(--ui-text-muted); text-align: center; padding: var(--ui-s4); }
    .alarms-form { display: flex; flex-direction: column; gap: var(--ui-s3); padding: var(--ui-s4);
      border: 1px solid var(--ui-line-strong); border-radius: var(--ui-r-lg); }
    .alarms-form .line { display: flex; align-items: center; gap: var(--ui-s3); flex-wrap: wrap; }
    .alarms-form .line > span:first-child { min-width: 6.5em; color: var(--ui-text-muted); font-size: var(--ui-fs-sm); }
    .alarms-form .ui-input, .alarms-form .ui-select { flex: 1; min-width: 8em; }
    .alarms-day { min-width: 2.6em; }
    .alarms-day.active { background: var(--ui-accent); color: var(--ui-on-accent); }
    .alarms-hint { color: var(--ui-text-faint); font-size: var(--ui-fs-xs); }
  `;
  document.head.appendChild(style);
}

function _renderError(message) {
  const list = document.getElementById('alarms-list');
  if (list) list.innerHTML = `<div class="alarms-empty">Alarms unavailable: ${_esc(message)}</div>`;
}

function _renderList() {
  const modal = document.getElementById(MODAL_ID);
  if (!modal) return;

  const ringing = _state.alarms.find(a => a.id === _state.ringing);
  const banner = modal.querySelector('#alarms-ringing');
  banner.hidden = !ringing;
  if (ringing) {
    banner.querySelector('.grow').textContent =
      `⏰ Alarm ${ringing.time}${ringing.label ? ` “${ringing.label}”` : ''} is ringing`;
    banner.querySelector('[data-act="snooze"]').textContent = `Snooze ${_state.snooze_minutes} min`;
  }

  const list = modal.querySelector('#alarms-list');
  if (!_state.alarms.length) {
    list.innerHTML = '<div class="alarms-empty">No alarms yet. Add one here, or just ask Monika to wake you up.</div>';
    return;
  }
  list.innerHTML = _state.alarms.map(a => `
    <div class="alarms-row ${a.enabled ? '' : 'disabled'}" data-id="${_esc(a.id)}">
      <div class="alarms-time">${_esc(a.time)}</div>
      <div class="alarms-meta">
        <span class="label">${_esc(a.label || 'Alarm')}</span>
        <span class="sub">${_esc(_daysLabel(a.days))}${a.date && !a.days.length ? ` · ${_esc(a.date)}` : ''} · ${_esc(_formatNext(a.next))}${a.sound ? ` · ${_esc(a.sound)}` : ''}</span>
      </div>
      <label class="admin-switch" title="${a.enabled ? 'Disable' : 'Enable'}">
        <input type="checkbox" data-act="toggle" ${a.enabled ? 'checked' : ''} />
        <span class="admin-slider"></span>
      </label>
      <button class="admin-btn-sm" data-act="edit" title="Edit" aria-label="Edit alarm ${_esc(a.time)}">${phosphorIcon('pencil')}</button>
      <button class="admin-btn-sm danger" data-act="delete" title="Delete" aria-label="Delete alarm ${_esc(a.time)}">${phosphorIcon('trash')}</button>
    </div>
  `).join('');
}

function _renderForm() {
  const host = document.getElementById('alarms-form-host');
  if (!host) return;
  _stopPreview();
  if (!_editing) {
    host.innerHTML = '';
    return;
  }
  const a = _editing;
  const days = new Set(a.days || []);
  const sounds = ['', ..._state.sounds];
  if (a.sound && !sounds.includes(a.sound)) sounds.push(a.sound);
  host.innerHTML = `
    <form class="alarms-form" id="alarms-form">
      <label class="line"><span>Time</span>
        <input class="ui-input" type="time" name="time" required value="${_esc(a.time || '06:30')}" /></label>
      <div class="line"><span>Repeat</span>
        ${DAYS.map((d, i) => `<button type="button" class="ui-btn alarms-day ${days.has(i) ? 'active' : ''}" data-day="${i}" aria-pressed="${days.has(i)}">${d}</button>`).join('')}
      </div>
      <label class="line"><span>Date</span>
        <input class="ui-input" type="date" name="date" value="${_esc(a.days?.length ? '' : (a.date || ''))}" />
        <span class="alarms-hint">no days = one-time; empty date = next occurrence</span></label>
      <label class="line"><span>Label</span>
        <input class="ui-input" type="text" name="label" maxlength="60" placeholder="e.g. Work" value="${_esc(a.label || '')}" /></label>
      <div class="line"><span>Sound</span>
        <select class="ui-select" name="sound" aria-label="Alarm sound">
          ${sounds.map(s => `<option value="${_esc(s)}" ${s === (a.sound || '') ? 'selected' : ''}>${s ? _esc(s) : 'Beeps (generated)'}</option>`).join('')}
        </select>
        <button type="button" class="admin-btn-sm" data-act="preview" title="Preview sound" aria-label="Preview sound" aria-pressed="false">${phosphorIcon('speaker')}</button>
        <button type="button" class="ui-btn" data-act="upload">${phosphorIcon('paperclip')} Upload</button>
        <input type="file" name="sound_file" accept="${SOUND_ACCEPT}" hidden />
      </div>
      <span class="alarms-hint">Upload your own sound (mp3, wav, ogg…, max 20 MB). Preview plays in this browser.</span>
      <label class="line"><span>Greeting</span>
        <input type="checkbox" name="greeting" ${a.greeting === false ? '' : 'checked'} />
        <span class="alarms-hint">after you stop it, Monika tells you the weather, your day and the shopping list</span></label>
      <div class="line">
        <button type="submit" class="ui-btn ui-primary">${a.id ? 'Save' : 'Add alarm'}</button>
        <button type="button" class="ui-btn" data-act="cancel">Cancel</button>
      </div>
    </form>
  `;
  const form = host.querySelector('#alarms-form');
  form.querySelectorAll('.alarms-day').forEach(btn => btn.addEventListener('click', () => {
    const on = !btn.classList.contains('active');
    btn.classList.toggle('active', on);
    btn.setAttribute('aria-pressed', String(on));
  }));
  const soundSelect = form.querySelector('[name="sound"]');
  const fileInput = form.querySelector('[name="sound_file"]');
  form.querySelector('[data-act="preview"]').addEventListener('click', (e) => _togglePreview(e.currentTarget, soundSelect.value));
  soundSelect.addEventListener('change', _stopPreview);
  form.querySelector('[data-act="upload"]').addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', async () => {
    const file = fileInput.files?.[0];
    fileInput.value = '';
    if (!file) return;
    _stopPreview();
    await _uploadSound(file, soundSelect);
  });
  form.querySelector('[data-act="cancel"]').addEventListener('click', () => { _editing = null; _renderForm(); });
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const fd = new FormData(form);
    const payload = {
      id: _editing.id || '',
      time: fd.get('time'),
      days: [...form.querySelectorAll('.alarms-day.active')].map(b => Number(b.dataset.day)),
      date: fd.get('date') || '',
      label: fd.get('label') || '',
      sound: fd.get('sound') || '',
      greeting: fd.get('greeting') === 'on',
    };
    if (await _act('/api/alarms', { method: 'POST', body: JSON.stringify(payload) })) {
      _editing = null;
      _renderForm();
    }
  });
  form.querySelector('[name="time"]').focus();
}

function _onListClick(event) {
  const target = event.target.closest('[data-act]');
  const row = event.target.closest('.alarms-row');
  if (!target || !row) return;
  const id = row.dataset.id;
  const act = target.dataset.act;
  if (act === 'edit') {
    _editing = { ...(_state.alarms.find(a => a.id === id) || {}) };
    _renderForm();
  } else if (act === 'delete') {
    const a = _state.alarms.find(x => x.id === id);
    if (confirm(`Delete alarm ${a?.time || ''}${a?.label ? ` “${a.label}”` : ''}?`)) {
      _act(`/api/alarms/${encodeURIComponent(id)}`, { method: 'DELETE' });
    }
  }
}

function _onListChange(event) {
  if (event.target.dataset.act !== 'toggle') return;
  const id = event.target.closest('.alarms-row')?.dataset.id;
  _act(`/api/alarms/${encodeURIComponent(id)}/enabled`, {
    method: 'POST', body: JSON.stringify({ enabled: event.target.checked }),
  });
}

function _startPolling() {
  _stopPolling();
  _pollTimer = setInterval(() => { if (!document.hidden) _refresh(); }, POLL_MS);
}

function _stopPolling() {
  if (_pollTimer) clearInterval(_pollTimer);
  _pollTimer = null;
}

export function openAlarms() {
  if (Modals.isMinimized(MODAL_ID)) {
    Modals.restore(MODAL_ID);
    _open = true;
    _startPolling();
    _refresh();
    return;
  }

  let modal = document.getElementById(MODAL_ID);
  if (modal) {
    modal.classList.remove('hidden', 'modal-minimized');
    modal.style.display = 'flex';
  } else {
    _ensureStyles();
    modal = document.createElement('div');
    modal.className = 'modal';
    modal.id = MODAL_ID;
    modal.innerHTML = `
      <div class="modal-content" style="width:min(560px, 94vw); height:600px; max-height:85vh; display:flex; flex-direction:column; overflow:hidden;">
        <div class="modal-header">
          <h4>${phosphorIcon('alarm')} Alarms</h4>
          <button class="ui-btn ui-primary" id="alarms-new" style="margin-left:auto;margin-right:var(--ui-s2)">${phosphorIcon('plus')} New</button>
          <button class="close-btn" id="alarms-close" aria-label="Close alarms">✖</button>
        </div>
        <div class="modal-body alarms-body" style="flex:1 1 auto; min-height:0; overflow-y:auto;">
          <div class="alarms-ringing" id="alarms-ringing" role="alert" hidden>
            <span class="grow"></span>
            <button class="ui-btn ui-primary" data-act="stop">Stop</button>
            <button class="ui-btn" data-act="snooze">Snooze</button>
          </div>
          <div id="alarms-form-host"></div>
          <div id="alarms-list" style="display:flex;flex-direction:column;gap:var(--ui-s2)"></div>
        </div>
      </div>
    `;
    document.body.appendChild(modal);

    modal.querySelector('#alarms-new').addEventListener('click', () => { _editing = {}; _renderForm(); });
    modal.querySelector('#alarms-close').addEventListener('click', closeAlarms);
    modal.querySelector('#alarms-ringing [data-act="stop"]').addEventListener('click', () => _act('/api/alarms/ringing/stop', { method: 'POST' }));
    modal.querySelector('#alarms-ringing [data-act="snooze"]').addEventListener('click', () => _act('/api/alarms/ringing/snooze', { method: 'POST', body: '{}' }));
    const list = modal.querySelector('#alarms-list');
    list.addEventListener('click', _onListClick);
    list.addEventListener('change', _onListChange);
    modal.addEventListener('click', (event) => {
      if (event.target === modal) {
        event.stopPropagation();
        closeAlarms();
      }
    });

    const content = modal.querySelector('.modal-content');
    const header = modal.querySelector('.modal-header');
    if (content && header) makeWindowDraggable(modal, { content, header });

    Modals.register(MODAL_ID, {
      railBtnId: 'rail-alarms',
      sidebarBtnId: 'tool-alarms-btn',
      label: 'Alarms',
      icon: phosphorIcon('alarm'),
      restoreFn: () => { _open = true; _startPolling(); _refresh(); },
      closeFn: closeAlarms,
    });
    Modals.injectMinimizeButton(modal, MODAL_ID);
  }

  _open = true;
  if (!_escHandler) {
    _escHandler = (event) => {
      if (event.key !== 'Escape' || !_open) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      if (_editing) { _editing = null; _renderForm(); } else closeAlarms();
    };
    document.addEventListener('keydown', _escHandler, true);
  }
  _renderForm();
  _refresh();
  _startPolling();
}

export function closeAlarms() {
  if (Modals.isRegistered(MODAL_ID)) Modals.close(MODAL_ID);
  document.getElementById(MODAL_ID)?.remove();
  _open = false;
  _editing = null;
  _stopPreview();
  _stopPolling();
  if (_escHandler) {
    document.removeEventListener('keydown', _escHandler, true);
    _escHandler = null;
  }
}

export function toggleAlarms() {
  if (Modals.toggle(MODAL_ID)) return;
  if (_open) closeAlarms();
  else openAlarms();
}

export default { openAlarms, closeAlarms, toggleAlarms };
