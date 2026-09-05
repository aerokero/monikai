/**
 * Pixel-Perfect Monika Visualizer for Odysseus AI Workspace
 * Renders MAS layered Monika (Hair, Body, Outfit, Arms, Face, Eyes, Mouth, Ahoge, Table)
 * with animated blinking, talking, breathing and time-of-day room transitions.
 */

export class MonikaVisualizer {
  constructor() {
    this.stage = null;
    this.isBlinking = false;
    this.isSpeaking = false;
    this.mood = 'neutral'; // 'neutral', 'happy', 'love', 'thinking'
    this.hairStyle = 'down'; // 'down' or 'def'
    this.outfit = 'bath_towel_white'; // 'bath_towel_white' or 'def'
    this.pose = 'rest'; // 'rest', 'crossed', 'steepling', 'point'
    this.ahoge = 'ahoge_curl'; // 'ahoge_curl' or null
    
    this.init();
  }

  init() {
    this.mountStage();
    this.startBlinkLoop();
    this.updateBackground();
    this.listenToOdysseusEvents();
  }

  mountStage() {
    const chatContainer = document.getElementById('chat-container');
    if (!chatContainer) {
      setTimeout(() => this.mountStage(), 100);
      return;
    }

    // Remove old stage if exists
    const old = document.getElementById('monika-vn-stage');
    if (old) old.remove();

    this.stage = document.createElement('div');
    this.stage.id = 'monika-vn-stage';
    this.stage.className = 'monika-vn-stage';

    this.stage.innerHTML = `
      <div class="monika-vn-room" id="monika-vn-room"></div>
      <div class="monika-vn-char-wrap" id="monika-vn-char-wrap">
        <!-- Layer 1: Chair -->
        <img class="m-layer" src="/static/vn/monika/t/chair-def.png" alt="" />
        
        <!-- Layer 2: Hair Back -->
        <img id="m-layer-hair-back" class="m-layer" src="/static/vn/monika/h/down/0.png" alt="" />
        
        <!-- Layer 3: Body Base -->
        <img class="m-layer" src="/static/vn/monika/b/body-def-0.png" alt="" />
        
        <!-- Layer 4: Outfit Base -->
        <img id="m-layer-outfit-0" class="m-layer" src="/static/vn/monika/c/bath_towel_white/body-def-0.png" alt="" />
        
        <!-- Layer 5: Body Upper -->
        <img class="m-layer" src="/static/vn/monika/b/body-def-1.png" alt="" />
        
        <!-- Layer 6: Outfit Upper -->
        <img id="m-layer-outfit-1" class="m-layer" src="/static/vn/monika/c/bath_towel_white/body-def-1.png" alt="" />
        
        <!-- Layer 7: Arms (Left & Right Rest Pose) -->
        <img id="m-layer-arm-l" class="m-layer" src="/static/vn/monika/b/arms-left-rest-10.png" alt="" />
        <img id="m-layer-arm-r" class="m-layer" src="/static/vn/monika/b/arms-right-restpoint-10.png" alt="" />
        
        <!-- Layer 8: Head Base -->
        <img class="m-layer" src="/static/vn/monika/b/body-def-head.png" alt="" />
        
        <!-- Layer 9: Face Elements -->
        <img class="m-layer" src="/static/vn/monika/f/face-nose-def.png" alt="" />
        <img id="m-layer-blush" class="m-layer" src="/static/vn/monika/f/face-blush-shade.png" style="opacity:0.6" alt="" />
        <img id="m-layer-eyes" class="m-layer" src="/static/vn/monika/f/face-eyes-normal.png" alt="" />
        <img id="m-layer-brows" class="m-layer" src="/static/vn/monika/f/face-eyebrows-mid.png" alt="" />
        <img id="m-layer-mouth" class="m-layer" src="/static/vn/monika/f/face-mouth-smile.png" alt="" />
        
        <!-- Layer 10: Hair Front / Bangs -->
        <img id="m-layer-hair-front" class="m-layer" src="/static/vn/monika/h/down/10.png" alt="" />
        
        <!-- Layer 11: Ahoge Accessory -->
        <img id="m-layer-ahoge" class="m-layer" src="/static/vn/monika/a/ahoge_curl/0.png" alt="" />
        
        <!-- Layer 12: Desk / Table -->
        <img class="m-layer" src="/static/vn/monika/t/table-def.png" alt="" />
      </div>
      <div class="monika-vn-atmosphere"></div>
    `;

    // Insert at the beginning of chat container so it renders under messages & composer
    chatContainer.insertBefore(this.stage, chatContainer.firstChild);
    this.applyStyles();
  }

  applyStyles() {
    let style = document.getElementById('monika-vn-styles');
    if (!style) {
      style = document.createElement('style');
      style.id = 'monika-vn-styles';
      document.head.appendChild(style);
    }
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
        filter: brightness(0.94) saturate(1.05);
        transition: background-image 1.2s ease-in-out;
      }
      .monika-vn-char-wrap {
        position: absolute;
        bottom: 0;
        left: 50%;
        transform: translateX(-50%) scale(1.38);
        transform-origin: center bottom;
        width: min(1020px, 100vw);
        height: min(1020px, 100vh);
        pointer-events: auto;
        cursor: pointer;
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
        background: radial-gradient(circle at 50% 35%, transparent 50%, rgba(10, 8, 14, 0.35) 85%),
                    linear-gradient(to top, rgba(14, 12, 18, 0.75) 0%, transparent 35%);
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
        backdrop-filter: none !important;
        -webkit-backdrop-filter: none !important;
        border-bottom: none !important;
      }
      #welcome-screen {
        display: none !important;
      }
    `;
  }

  startBlinkLoop() {
    const blink = () => {
      const eyesEl = document.getElementById('m-layer-eyes');
      if (!eyesEl) return;

      // Close eyes
      eyesEl.src = '/static/vn/monika/f/face-eyes-closedhappy.png';
      setTimeout(() => {
        const el = document.getElementById('m-layer-eyes');
        if (el) {
          el.src = this.mood === 'love' 
            ? '/static/vn/monika/f/face-eyes-soft.png' 
            : '/static/vn/monika/f/face-eyes-normal.png';
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

  listenToOdysseusEvents() {
    // Dynamic placeholder update
    const updatePlaceholder = () => {
      const msg = document.getElementById('message');
      if (msg && (!msg.placeholder || msg.placeholder.includes('Odysseus') || msg.placeholder.includes('Search') || msg.placeholder.includes('Zapytaj'))) {
        msg.placeholder = 'Hej Moniko...';
      }
    };
    updatePlaceholder();
    setInterval(updatePlaceholder, 1000);

    // Interactive click on Monika triggers happy blush
    const wrap = document.getElementById('monika-vn-char-wrap');
    if (wrap) {
      wrap.addEventListener('click', () => {
        const mouth = document.getElementById('m-layer-mouth');
        const blush = document.getElementById('m-layer-blush');
        if (mouth) mouth.src = '/static/vn/monika/f/face-mouth-big.png';
        if (blush) blush.style.opacity = '0.9';
        setTimeout(() => {
          if (mouth) mouth.src = '/static/vn/monika/f/face-mouth-smile.png';
          if (blush) blush.style.opacity = '0.6';
        }, 1500);
      });
    }

    // React to chat activity / streaming
    const chatLog = document.getElementById('chat-history');
    if (chatLog && typeof MutationObserver !== 'undefined') {
      const observer = new MutationObserver(() => {
        const isBusy = chatLog.getAttribute('aria-busy') === 'true';
        const mouth = document.getElementById('m-layer-mouth');
        if (isBusy) {
          if (mouth && mouth.src.indexOf('face-mouth-big.png') === -1) {
            mouth.src = '/static/vn/monika/f/face-mouth-big.png';
          }
        } else {
          if (mouth && mouth.src.indexOf('face-mouth-smile.png') === -1) {
            mouth.src = '/static/vn/monika/f/face-mouth-smile.png';
          }
        }
      });
      observer.observe(chatLog, { attributes: true, attributeFilter: ['aria-busy'] });
    }
  }
}

function initVisualizer() {
  if (!window.monikaVisualizer) {
    window.monikaVisualizer = new MonikaVisualizer();
  }
}

// Initialize on DOM load or immediately if already loaded
if (typeof window !== 'undefined') {
  if (document.readyState === 'loading') {
    window.addEventListener('DOMContentLoaded', initVisualizer);
  } else {
    initVisualizer();
  }
}
