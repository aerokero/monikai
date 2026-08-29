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
        <!-- Layer 1: Chair -->
        <img class="m-layer" src="/static/vn/monika/t/chair-def.png" />
        
        <!-- Layer 2: Hair Back -->
        <img id="m-layer-hair-back" class="m-layer" src="/static/vn/monika/h/down/0.png" />
        
        <!-- Layer 3: Body Base -->
        <img class="m-layer" src="/static/vn/monika/b/body-def-0.png" />
        
        <!-- Layer 4: Outfit Base -->
        <img id="m-layer-outfit-0" class="m-layer" src="/static/vn/monika/c/bath_towel_white/body-def-0.png" />
        
        <!-- Layer 5: Body Upper -->
        <img class="m-layer" src="/static/vn/monika/b/body-def-1.png" />
        
        <!-- Layer 6: Outfit Upper -->
        <img id="m-layer-outfit-1" class="m-layer" src="/static/vn/monika/c/bath_towel_white/body-def-1.png" />
        
        <!-- Layer 7: Arms (Left & Right Rest Pose) -->
        <img id="m-layer-arm-l" class="m-layer" src="/static/vn/monika/b/arms-left-rest-10.png" />
        <img id="m-layer-arm-r" class="m-layer" src="/static/vn/monika/b/arms-right-restpoint-10.png" />
        
        <!-- Layer 8: Head Base -->
        <img class="m-layer" src="/static/vn/monika/b/body-def-head.png" />
        
        <!-- Layer 9: Face Elements -->
        <img class="m-layer" src="/static/vn/monika/f/face-nose-def.png" />
        <img id="m-layer-blush" class="m-layer" src="/static/vn/monika/f/face-blush-shade.png" style="opacity:0.6" />
        <img id="m-layer-eyes" class="m-layer" src="/static/vn/monika/f/face-eyes-normal.png" />
        <img id="m-layer-brows" class="m-layer" src="/static/vn/monika/f/face-eyebrows-mid.png" />
        <img id="m-layer-mouth" class="m-layer" src="/static/vn/monika/f/face-mouth-smile.png" />
        
        <!-- Layer 10: Hair Front / Bangs -->
        <img id="m-layer-hair-front" class="m-layer" src="/static/vn/monika/h/down/10.png" />
        
        <!-- Layer 11: Ahoge Accessory -->
        <img id="m-layer-ahoge" class="m-layer" src="/static/vn/monika/a/ahoge_curl/0.png" />
        
        <!-- Layer 12: Desk / Table -->
        <img class="m-layer" src="/static/vn/monika/t/table-def.png" />
      </div>
      <div class="monika-vn-atmosphere"></div>
    `;

    // Insert at the beginning of chat container so it renders under messages & composer
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
        background-position: center 25%;
        filter: brightness(0.92) saturate(1.05);
        transition: background-image 1.2s ease-in-out;
      }
      .monika-vn-char-wrap {
        position: absolute;
        bottom: 0;
        left: 50%;
        transform: translateX(-50%);
        width: min(920px, 98vw);
        height: 98vh;
        max-height: 960px;
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
        background: radial-gradient(circle at 50% 40%, transparent 45%, rgba(10, 8, 14, 0.4) 85%),
                    linear-gradient(to top, rgba(14, 12, 18, 0.82) 0%, transparent 40%);
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
          eyesEl.src = this.mood === 'love' 
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
  }
}

// Initialize on DOM load
if (typeof window !== 'undefined') {
  window.addEventListener('DOMContentLoaded', () => {
    window.monikaVisualizer = new MonikaVisualizer();
  });
}
