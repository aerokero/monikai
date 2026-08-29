/**
 * Monika Visualizer for Odysseus AI Workspace
 * Renders the Visual Novel room scene and layered Monika sprite
 * directly into the main chat canvas behind messages.
 */

export class MonikaVisualizer {
  constructor() {
    this.stage = null;
    this.characterContainer = null;
    this.roomContainer = null;
    this.isBlinking = false;
    this.mood = 'neutral';
    this.currentPose = 'def';
    this.outfit = 'bath_towel_white'; // default or school uniform
    this.init();
  }

  init() {
    this.mountStage();
    this.startBlinkLoop();
    this.updateBackground();
  }

  mountStage() {
    const chatContainer = document.getElementById('chat-container');
    if (!chatContainer) return;

    // Remove old stage if exists
    const old = document.getElementById('monika-vn-stage');
    if (old) old.remove();

    this.stage = document.createElement('div');
    this.stage.id = 'monika-vn-stage';
    this.stage.className = 'monika-vn-stage';

    this.stage.innerHTML = `
      <div class="monika-vn-room" id="monika-vn-room"></div>
      <div class="monika-vn-char-wrap" id="monika-vn-char-wrap">
        <img id="m-layer-hair-back" class="m-layer" src="/static/vn/monika/h/def/0.png" />
        <img id="m-layer-body" class="m-layer" src="/static/vn/monika/b/body-def-0.png" />
        <img id="m-layer-head" class="m-layer" src="/static/vn/monika/b/body-def-head.png" />
        <img id="m-layer-eyes" class="m-layer" src="/static/vn/monika/f/face-eyes-normal.png" />
        <img id="m-layer-brows" class="m-layer" src="/static/vn/monika/f/face-eyebrows-mid.png" />
        <img id="m-layer-nose" class="m-layer" src="/static/vn/monika/f/face-nose-def.png" />
        <img id="m-layer-mouth" class="m-layer" src="/static/vn/monika/f/face-mouth-smile.png" />
        <img id="m-layer-hair-front" class="m-layer" src="/static/vn/monika/h/def/def-0.png" />
        <img id="m-layer-desk" class="m-layer m-desk" src="/static/vn/monika/t/table-def.png" onerror="this.style.display='none'" />
      </div>
      <div class="monika-vn-atmosphere"></div>
    `;

    // Insert at the beginning of chat container so it renders under messages & input
    chatContainer.insertBefore(this.stage, chatContainer.firstChild);
    this.applyStyles();
  }

  applyStyles() {
    if (document.getElementById('monika-vn-styles')) return;

    const style = document.createElement('style');
    style.id = 'monika-vn-styles';
    style.textContent = `
      .monika-vn-stage {
        position: absolute;
        inset: 0;
        z-index: 0;
        pointer-events: none;
        overflow: hidden;
      }
      .monika-vn-room {
        position: absolute;
        inset: 0;
        background-image: url('/static/vn/location/bg_room.png');
        background-size: cover;
        background-position: center 30%;
        filter: brightness(0.92) saturate(1.05);
        transition: background-image 1s ease-in-out;
      }
      .monika-vn-char-wrap {
        position: absolute;
        bottom: 0;
        left: 50%;
        transform: translateX(-50%);
        width: min(780px, 95vw);
        height: min(88vh, 860px);
        pointer-events: auto;
        cursor: pointer;
        animation: monika-breathe 4.5s ease-in-out infinite alternate;
      }
      @keyframes monika-breathe {
        0% { transform: translateX(-50%) translateY(0); }
        100% { transform: translateX(-50%) translateY(5px); }
      }
      .m-layer {
        position: absolute;
        bottom: 0;
        left: 0;
        width: 100%;
        height: 100%;
        object-fit: contain;
        object-position: center bottom;
        pointer-events: none;
      }
      .monika-vn-atmosphere {
        position: absolute;
        inset: 0;
        background: radial-gradient(circle at 50% 40%, transparent 40%, rgba(12, 10, 16, 0.45) 85%),
                    linear-gradient(to top, rgba(14, 12, 18, 0.85) 0%, transparent 40%);
        pointer-events: none;
      }
      
      /* Make Odysseus chat history transparent and comfortably floating */
      #chat-history {
        position: relative;
        z-index: 10;
        background: transparent !important;
      }
      .chat-top-bar {
        position: relative;
        z-index: 15;
        background: transparent !important;
      }
      #welcome-screen {
        position: relative;
        z-index: 10;
        background: transparent !important;
      }
      .welcome-name, .welcome-sub, .welcome-tip {
        text-shadow: 0 2px 10px rgba(0,0,0,0.8);
      }
      .chat-input-bar {
        position: relative;
        z-index: 20;
        background: rgba(18, 16, 22, 0.82) !important;
        backdrop-filter: blur(24px) !important;
        border: 1px solid rgba(244, 114, 182, 0.28) !important;
        box-shadow: 0 15px 40px rgba(0, 0, 0, 0.65), 0 0 20px rgba(244, 114, 182, 0.12) !important;
        border-radius: 18px !important;
      }
      .user-message, .assistant-message, .system-message {
        backdrop-filter: blur(16px);
        background: rgba(20, 18, 24, 0.85) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        box-shadow: 0 10px 30px rgba(0,0,0,0.4);
      }
    `;
    document.head.appendChild(style);
  }

  startBlinkLoop() {
    const blink = () => {
      const eyesEl = document.getElementById('m-layer-eyes');
      if (!eyesEl) return;

      // Close eyes
      eyesEl.src = '/static/vn/monika/f/face-eyes-closedhappy.png';
      setTimeout(() => {
        if (eyesEl) {
          eyesEl.src = '/static/vn/monika/f/face-eyes-normal.png';
        }
      }, 160);

      // Schedule next blink in 2.5 - 6.0 seconds
      const nextDelay = 2500 + Math.random() * 3500;
      setTimeout(blink, nextDelay);
    };

    setTimeout(blink, 2000);
  }

  updateBackground() {
    const hour = new Date().getHours();
    const isNight = hour >= 20 || hour < 6;
    const room = document.getElementById('monika-vn-room');
    if (room) {
      const bg = isNight ? '/static/vn/location/bg_room_night.png' : '/static/vn/location/bg_room.png';
      room.style.backgroundImage = `url('${bg}')`;
    }
  }
}

// Initialize on DOM load
if (typeof window !== 'undefined') {
  window.addEventListener('DOMContentLoaded', () => {
    window.monikaVisualizer = new MonikaVisualizer();
  });
}
