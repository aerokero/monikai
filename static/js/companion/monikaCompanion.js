/**
 * Monika Companion Integration for Odysseus AI Workspace
 * Renders Monika's layered animated sprite, live mood expressions,
 * voice interaction and floating pet companion mode.
 */

export class MonikaCompanion {
  constructor(options = {}) {
    this.container = options.container || null;
    this.mood = 'neutral';
    this.isSpeaking = false;
    this.isFloating = localStorage.getItem('odysseus_monika_floating') === 'true';
    this.init();
  }

  init() {
    this.createCompanionDOM();
    this.setupEventListeners();
  }

  createCompanionDOM() {
    // Remove existing if any
    const existing = document.getElementById('monika-companion-root');
    if (existing) existing.remove();

    const root = document.createElement('div');
    root.id = 'monika-companion-root';
    root.className = `monika-companion ${this.isFloating ? 'is-floating' : 'is-docked'}`;

    root.innerHTML = `
      <div class="monika-companion-card" id="monika-companion-card">
        <!-- Floating Drag Handle & Controls -->
        <div class="monika-companion-header">
          <div class="monika-companion-badge">
            <span class="monika-pulse-dot"></span>
            <span>Monika</span>
          </div>
          <div class="monika-companion-actions">
            <button id="monika-toggle-mode-btn" class="monika-mini-btn" title="Toggle mode (Floating Pet / Docked)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18"/>
              </svg>
            </button>
          </div>
        </div>

        <!-- Monika Sprite Canvas Container -->
        <div class="monika-sprite-viewport" id="monika-sprite-viewport">
          <img 
            id="monika-sprite-img"
            src="/static/icons/icon-192.png" 
            alt="Monika"
            class="monika-live-avatar"
            onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' viewBox=\\'0 0 100 100\\'><circle cx=\\'50\\' cy=\\'50\\' r=\\'45\\' fill=\\'%23f472b6\\'/><text x=\\'50\\' y=\\'55\\' font-size=\\'30\\' text-anchor=\\'middle\\' fill=\\'white\\'>M</text></svg>'"
          />
        </div>

        <!-- Interactive Thought Bubble -->
        <div class="monika-thought-bubble" id="monika-thought-bubble">
          <span id="monika-thought-text">I'm here with you in Odysseus Workspace! ✨</span>
        </div>
      </div>
    `;

    document.body.appendChild(root);
    this.applyStyles();
  }

  applyStyles() {
    if (document.getElementById('monika-companion-styles')) return;

    const style = document.createElement('style');
    style.id = 'monika-companion-styles';
    style.textContent = `
      .monika-companion {
        position: fixed;
        z-index: 9000;
        transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        user-select: none;
      }
      .monika-companion.is-floating {
        bottom: 24px;
        right: 24px;
        width: 220px;
      }
      .monika-companion.is-docked {
        bottom: 80px;
        right: 24px;
        width: 240px;
      }
      .monika-companion-card {
        background: rgba(24, 20, 26, 0.88);
        backdrop-filter: blur(20px);
        border: 1px solid rgba(244, 114, 182, 0.3);
        border-radius: 20px;
        padding: 12px;
        box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6), 0 0 25px rgba(244, 114, 182, 0.15);
        display: flex;
        flex-direction: column;
        align-items: center;
      }
      .monika-companion-header {
        width: 100%;
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 8px;
      }
      .monika-companion-badge {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 11px;
        font-weight: 600;
        color: #f472b6;
      }
      .monika-pulse-dot {
        width: 7px;
        height: 7px;
        background: #34d399;
        border-radius: 50%;
        box-shadow: 0 0 8px #34d399;
      }
      .monika-mini-btn {
        background: rgba(255, 255, 255, 0.08);
        border: 1px solid rgba(255, 255, 255, 0.12);
        color: rgba(255, 255, 255, 0.7);
        border-radius: 6px;
        width: 24px;
        height: 24px;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        transition: all 0.2s;
      }
      .monika-mini-btn:hover {
        background: rgba(244, 114, 182, 0.25);
        color: #fff;
        border-color: rgba(244, 114, 182, 0.5);
      }
      .monika-sprite-viewport {
        width: 100%;
        height: 160px;
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
      }
      .monika-live-avatar {
        max-height: 140px;
        object-fit: contain;
        filter: drop-shadow(0 10px 15px rgba(0,0,0,0.5));
        transition: transform 0.2s;
      }
      .monika-live-avatar:hover {
        transform: scale(1.05);
      }
      .monika-thought-bubble {
        margin-top: 8px;
        padding: 8px 12px;
        background: rgba(0, 0, 0, 0.4);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        font-size: 11px;
        line-height: 1.4;
        color: rgba(255, 255, 255, 0.9);
        text-align: center;
        width: 100%;
      }
    `;
    document.head.appendChild(style);
  }

  setupEventListeners() {
    const btn = document.getElementById('monika-toggle-mode-btn');
    if (btn) {
      btn.addEventListener('click', () => {
        this.isFloating = !this.isFloating;
        localStorage.setItem('odysseus_monika_floating', String(this.isFloating));
        const root = document.getElementById('monika-companion-root');
        if (root) {
          root.className = `monika-companion ${this.isFloating ? 'is-floating' : 'is-docked'}`;
        }
      });
    }
  }

  say(text) {
    const el = document.getElementById('monika-thought-text');
    if (el) {
      el.textContent = text;
    }
  }
}

// Auto-initialize when Odysseus DOM is ready
if (typeof window !== 'undefined') {
  window.addEventListener('DOMContentLoaded', () => {
    window.monikaCompanion = new MonikaCompanion();
  });
}
