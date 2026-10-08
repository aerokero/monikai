// static/js/voiceRecorder.js

/**
 * Voice recording with optional Speech-to-Text transcription.
 *
 * STT providers:
 *   "disabled"       — record audio as file attachment (original behavior)
 *   "browser"        — use Web Speech API for real-time transcription
 *   "local"          — send recording to server /api/stt/transcribe (Whisper)
 *   "endpoint:<id>"  — send recording to server /api/stt/transcribe (API)
 */

let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let recordingStartTime = null;
let recordingInterval = null;

// Browser STT state
let _recognition = null;
let _browserTranscript = '';

// Visualizer / UI state
let _audioCtx = null;
let _analyser = null;
let _vizRaf = 0;
let _cancelled = false;
let _sendAfter = false; // send the message as soon as the transcript lands
let _vizMode = ''; // '' | 'recording' | 'transcribing'

const BAR_W = 3, BAR_GAP = 3;

// Cached STT provider — refreshed on settings change
let _sttProvider = 'disabled';

/**
 * Fetch current STT provider from server settings
 */
async function refreshSttProvider() {
  try {
    const res = await fetch('/api/stt/stats', { credentials: 'same-origin' });
    if (res.ok) {
      const stats = await res.json();
      _sttProvider = stats.provider || 'disabled';
      // Notify the send button to update its icon
      if (window._updateSendBtnIcon) window._updateSendBtnIcon();
    }
  } catch (e) {
    console.warn('Failed to fetch STT stats:', e);
  }
}

/**
 * Format seconds as MM:SS
 */
function formatTime(seconds) {
  const mins = Math.floor(seconds / 60).toString().padStart(2, '0');
  const secs = (seconds % 60).toString().padStart(2, '0');
  return `${mins}:${secs}`;
}


/**
 * Waveform in the composer: live mic levels while recording, a travelling
 * wave while the server transcribes.
 */
function _setVizMode(mode) {
  _vizMode = mode;
  const pill = document.querySelector('.composer-pill');
  const overlay = document.getElementById('voice-overlay');
  if (pill) {
    pill.classList.toggle('voice-recording', mode === 'recording');
    pill.classList.toggle('voice-transcribing', mode === 'transcribing');
  }
  if (overlay) overlay.hidden = !mode;
}

function _startViz(stream) {
  const canvas = document.getElementById('voice-viz');
  const status = document.getElementById('voice-status');
  if (!canvas) return;
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (Ctx) {
    _audioCtx = new Ctx();
    _analyser = _audioCtx.createAnalyser();
    _analyser.fftSize = 512;
    _audioCtx.createMediaStreamSource(stream).connect(_analyser);
  }
  const buf = new Uint8Array(_analyser ? _analyser.fftSize : 0);
  const levels = [];
  let lastPush = 0;
  const g = canvas.getContext('2d');

  const frame = (t) => {
    _vizRaf = requestAnimationFrame(frame);
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== Math.round(w * dpr)) { canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr); }
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    const n = Math.floor(w / (BAR_W + BAR_GAP));
    const css = getComputedStyle(canvas);
    const color = _vizMode === 'transcribing' ? css.getPropertyValue('--ui-text-muted') || '#888' : css.getPropertyValue('--color-recording') || '#ff3b30';
    g.fillStyle = color.trim();

    if (_vizMode === 'recording' && _analyser && t - lastPush > 45) {
      lastPush = t;
      _analyser.getByteTimeDomainData(buf);
      let sum = 0;
      for (const v of buf) { const d = (v - 128) / 128; sum += d * d; }
      levels.push(Math.min(1, Math.sqrt(sum / buf.length) * 5)); // ponytail: fixed gain, add AGC if quiet mics look flat
      if (levels.length > n) levels.shift();
    }
    for (let i = 0; i < n; i++) {
      let v;
      if (_vizMode === 'transcribing') {
        v = 0.22 + 0.18 * Math.sin(t / 220 - i * 0.45);
      } else {
        v = levels[levels.length - n + i] ?? 0;
      }
      const bh = Math.max(3, v * h);
      const x = i * (BAR_W + BAR_GAP);
      g.globalAlpha = _vizMode === 'recording' ? 0.35 + 0.65 * (i / n) : 0.7;
      g.beginPath();
      g.roundRect(x, (h - bh) / 2, BAR_W, bh, BAR_W / 2);
      g.fill();
    }
    if (_vizMode === 'recording' && recordingStartTime && status) {
      status.textContent = formatTime(Math.floor((Date.now() - recordingStartTime) / 1000));
    }
  };
  _vizRaf = requestAnimationFrame(frame);
}

function _stopViz() {
  cancelAnimationFrame(_vizRaf);
  _vizRaf = 0;
  if (_audioCtx) { _audioCtx.close().catch(() => {}); _audioCtx = null; _analyser = null; }
  _setVizMode('');
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && isRecording) { _cancelled = true; stopRecording(); }
});

/**
 * Reset UI state after recording ends
 */
function _resetRecordingUI() {
  isRecording = false;
  _sendAfter = false;
  _stopViz();
  const micBtn = document.getElementById('composer-mic-btn');
  if (micBtn) {
    micBtn.setAttribute('aria-pressed', 'false');
    micBtn.setAttribute('aria-label', 'Record voice message (not Live Voice)');
    micBtn.title = 'Record voice message (not Live Voice)';
    micBtn.disabled = false;
  }
  if (recordingInterval) {
    clearInterval(recordingInterval);
    recordingInterval = null;
  }
  // Reset send button via global callback
  const sendBtn = document.querySelector('.send-btn');
  if (sendBtn) {
    sendBtn.classList.remove('recording');
    if (sendBtn.dataset.mode === 'recording') sendBtn.dataset.mode = '';
  }
  if (window._updateSendBtnIcon) {
    setTimeout(window._updateSendBtnIcon, 50);
  }
}

/**
 * Start browser speech recognition alongside recording
 */
function startBrowserSTT() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) return;

  _browserTranscript = '';
  _recognition = new SpeechRecognition();
  _recognition.continuous = true;
  _recognition.interimResults = false;
  _recognition.lang = '';

  _recognition.onresult = (event) => {
    for (let i = event.resultIndex; i < event.results.length; i++) {
      if (event.results[i].isFinal) {
        _browserTranscript += event.results[i][0].transcript + ' ';
      }
    }
  };

  _recognition.onerror = (e) => {
    console.warn('Browser STT error:', e.error);
  };

  _recognition.start();
}

function stopBrowserSTT() {
  if (_recognition) {
    try { _recognition.stop(); } catch (e) { /* ignore */ }
    _recognition = null;
  }
  return _browserTranscript.trim();
}

function _submitIfRequested() {
  if (!_sendAfter) return;
  _sendAfter = false;
  document.getElementById('chat-form')?.requestSubmit();
}

/**
 * Send audio to server for transcription
 */
async function transcribeOnServer(audioBlob) {
  const formData = new FormData();
  formData.append('file', audioBlob, audioBlob.type.includes('mp4') ? 'audio.m4a' : 'audio.webm');

  const res = await fetch('/api/stt/transcribe', {
    method: 'POST',
    credentials: 'same-origin',
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail?.message || 'Transcription failed');
  }

  const data = await res.json();
  return data.text || '';
}

/**
 * Insert transcribed text into the chat input
 */
function insertTranscription(text, showToast) {
  if (!text) return false;
  const input = document.getElementById('message');
  if (!input) return false;

  const existing = input.value.trim();
  input.value = existing ? existing + ' ' + text : text;

  // Trigger auto-resize and icon update
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.focus();

  const pill = input.closest('.composer-pill');
  if (pill) {
    pill.classList.remove('voice-inserted');
    void pill.offsetWidth; // restart animation
    pill.classList.add('voice-inserted');
    setTimeout(() => pill.classList.remove('voice-inserted'), 900);
  }
  if (showToast) showToast('Transcribed');
  return true;
}

/**
 * Let the chat controller finish a pending control-plane turn from speech.
 * The server remains the authority: this event only removes the extra click
 * after STT has put the user's spoken reply into the composer.
 */
function notifyVoiceTranscription(text) {
  if (!text || typeof document === 'undefined') return;
  document.dispatchEvent(new CustomEvent('odysseus:voice-transcription', {
    detail: { text: String(text), source: _sttProvider },
  }));
}

/**
 * Start voice recording
 */
export function startRecording(onFileCreated, showToast, showError) {
  // Check for secure context (getUserMedia requires HTTPS or localhost)
  if (!window.isSecureContext) {
    if (showError) showError('Microphone requires HTTPS. Use a reverse proxy with SSL or access via localhost.');
    _resetRecordingUI();
    return;
  }

  if (!window.MediaRecorder || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    if (showError) showError('Microphone not supported in this browser.');
    _resetRecordingUI();
    return;
  }

  const micBtn = document.getElementById('composer-mic-btn');
  if (micBtn) micBtn.disabled = true;
  audioChunks = [];
  let activeStream = null;

  navigator.mediaDevices.getUserMedia({ audio: true })
    .then(stream => {
      activeStream = stream;
      const mimeType = ['audio/webm', 'audio/mp4'].find(type => MediaRecorder.isTypeSupported(type));
      mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      const recordingType = mediaRecorder.mimeType || mimeType || 'audio/webm';
      const extension = recordingType.includes('mp4') ? 'm4a' : 'webm';

      mediaRecorder.ondataavailable = event => {
        if (event.data.size > 0) {
          audioChunks.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(track => track.stop());
        if (_cancelled) {
          _cancelled = false;
          stopBrowserSTT();
          _resetRecordingUI();
          return;
        }

        const audioBlob = new Blob(audioChunks, { type: recordingType });
        const provider = _sttProvider;

        if (provider === 'browser') {
          const transcript = stopBrowserSTT();
          if (transcript) {
            if (insertTranscription(transcript, showToast)) { notifyVoiceTranscription(transcript); _submitIfRequested(); }
          } else {
            if (showToast) showToast('No speech detected');
            const audioFile = new File([audioBlob], `voice-message-${Date.now()}.${extension}`, { type: recordingType });
            if (onFileCreated) onFileCreated(audioFile);
          }
        } else if (provider === 'local' || provider.startsWith('endpoint:')) {
          // Show "Transcribing..." feedback
          _setVizMode('transcribing');
          const st = document.getElementById('voice-status');
          if (st) st.textContent = 'Transcribing…';
          try {
            const transcript = await transcribeOnServer(audioBlob);
            if (transcript) {
              if (insertTranscription(transcript, showToast)) { notifyVoiceTranscription(transcript); _submitIfRequested(); }
            } else {
              if (showToast) showToast('No speech detected');
            }
          } catch (e) {
            console.error('STT transcription error:', e);
            if (showError) showError('Transcription failed: ' + e.message);
            // Fallback: attach as file
            const audioFile = new File([audioBlob], `voice-message-${Date.now()}.${extension}`, { type: recordingType });
            if (onFileCreated) onFileCreated(audioFile);
          }
        } else {
          // STT disabled — attach audio file
          const audioFile = new File([audioBlob], `voice-message-${Date.now()}.${extension}`, { type: recordingType });
          if (onFileCreated) onFileCreated(audioFile);
        }

        _resetRecordingUI();
      };

      mediaRecorder.start();
      isRecording = true;
      _cancelled = false;
      if (micBtn) {
        micBtn.disabled = false;
        micBtn.setAttribute('aria-pressed', 'true');
        micBtn.setAttribute('aria-label', 'Stop recording');
        micBtn.title = 'Stop recording';
      }
      recordingStartTime = Date.now();
      _setVizMode('recording');
      _startViz(stream);

      // Start browser STT if that's the provider
      if (_sttProvider === 'browser') {
        startBrowserSTT();
      }

    })
    .catch(error => {
      activeStream?.getTracks().forEach(track => track.stop());
      console.error('Microphone access error:', error);
      if (showError) {
        if (error.name === 'NotAllowedError') {
          showError('Microphone access denied. Check browser permissions.');
        } else if (error.name === 'NotFoundError') {
          showError('No microphone found.');
        } else {
          showError('Microphone error: ' + error.message);
        }
      }
      _resetRecordingUI();
    });
}

/**
 * Stop voice recording
 */
export function stopRecording(send = false) {
  if (send) _sendAfter = true;
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop();
    // isRecording will be set to false in _resetRecordingUI called from onstop
  } else {
    _resetRecordingUI();
  }
}

/**
 * Check if currently recording
 */
export function requestSendAfterTranscribe() {
  if (_vizMode === 'transcribing') _sendAfter = true;
  return _vizMode === 'transcribing';
}

export function getIsRecording() {
  return isRecording;
}

/**
 * Initialize recording state
 */
export function init() {
  isRecording = false;
  refreshSttProvider();
}

const voiceRecorderModule = {
  startRecording,
  stopRecording,
  requestSendAfterTranscribe,
  getIsRecording,
  init,
  refreshSttProvider,
  get _sttProvider() { return _sttProvider; },
  set _sttProvider(v) { _sttProvider = v; },
};

export default voiceRecorderModule;
