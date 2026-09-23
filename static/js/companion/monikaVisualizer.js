/**
 * Pixel-Perfect Monika Visualizer for Odysseus AI Workspace
 * Renders MAS layered Monika (Hair, Body, Outfit, Arms, Face, Eyes, Mouth, Ahoge, Table)
 * with animated blinking, talking, breathing and time-of-day room transitions.
 * Fully supports Wardrobe customization (outfit, hairStyle, ahoge, background).
 */

export const OUTFITS_WITH_ARMS = new Set([
  'def',
  'blazerless',
  'blackdress',
  'blackpinkdress',
  'marisa',
  'santa',
  'spider_lingerie',
]);

export class MonikaVisualizer {
  constructor() {
    this.stage = null;
    this.isBlinking = false;
    this.isSpeaking = false;
    this.mood = 'neutral'; // 'neutral', 'happy', 'love', 'thinking'
    this.pose = 'rest'; // 'rest', 'crossed', 'steepling', 'point'
    
    // Wardrobe state loaded from localStorage with sensible defaults
    this.outfit = localStorage.getItem('monikai_wardrobe_outfit') || 'def';
    this.hairStyle = localStorage.getItem('monikai_wardrobe_hair') || 'def';
    this.ahoge = localStorage.getItem('monikai_wardrobe_ahoge') || 'ahoge_curl';
    this.background = localStorage.getItem('monikai_wardrobe_bg') || 'auto';
    this.autoMode = localStorage.getItem('monikai_wardrobe_auto') === 'true';

    this.init();
  }

  init() {
    this.mountStage();
    if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      this.startBlinkLoop();
    }
    this.renderWardrobe();
    this.listenToOdysseusEvents();
    this.listenToWardrobeEvents();
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
    this.stage.setAttribute('aria-hidden', 'true');

    this.stage.innerHTML = `
      <div class="monika-vn-room" id="monika-vn-room"></div>
      <div class="monika-vn-char-wrap" id="monika-vn-char-wrap">
        <!-- Layer 1: Chair -->
        <img class="m-layer" src="/static/vn/monika/t/chair-def.png" alt="" />
        
        <!-- Layer 2: Hair Back -->
        <img id="m-layer-hair-back" class="m-layer" src="/static/vn/monika/h/${this.hairStyle}/0.png" alt="" />
        
        <!-- Layer 3: Body Base -->
        <img class="m-layer" src="/static/vn/monika/b/body-def-0.png" alt="" />
        
        <!-- Layer 4: Outfit Base -->
        <img id="m-layer-outfit-0" class="m-layer" src="/static/vn/monika/c/${this.outfit}/body-def-0.png" alt="" />
        
        <!-- Layer 5: Body Upper -->
        <img class="m-layer" src="/static/vn/monika/b/body-def-1.png" alt="" />
        
        <!-- Layer 6: Outfit Upper -->
        <img id="m-layer-outfit-1" class="m-layer" src="/static/vn/monika/c/${this.outfit}/body-def-1.png" alt="" />
        
        <!-- Layer 7 & 8: Table Desk & Shadow -->
        <img class="m-layer" src="/static/vn/monika/t/table-def.png" alt="" />
        <img class="m-layer" src="/static/vn/monika/t/table-def-s.png" alt="" />

        <!-- Layer 9: Body Arms (Left & Right Skin) -->
        <img id="m-layer-arm-l" class="m-layer" src="/static/vn/monika/b/arms-left-rest-10.png" alt="" />
        <img id="m-layer-arm-r" class="m-layer" src="/static/vn/monika/b/arms-right-restpoint-10.png" alt="" />
        
        <!-- Layer 10: Outfit Arms (Sleeves for sleeved outfits) -->
        <img id="m-layer-outfit-arm-l" class="m-layer" src="" alt="" style="display:none;" />
        <img id="m-layer-outfit-arm-r" class="m-layer" src="" alt="" style="display:none;" />

        <!-- Layer 11: Head Base -->
        <img class="m-layer" src="/static/vn/monika/b/body-def-head.png" alt="" />
        
        <!-- Layer 12: Face Elements -->
        <img class="m-layer" src="/static/vn/monika/f/face-nose-def.png" alt="" />
        <img id="m-layer-blush" class="m-layer" src="/static/vn/monika/f/face-blush-shade.png" style="opacity:0.6" alt="" />
        <img id="m-layer-eyes" class="m-layer" src="/static/vn/monika/f/face-eyes-normal.png" alt="" />
        <img id="m-layer-brows" class="m-layer" src="/static/vn/monika/f/face-eyebrows-mid.png" alt="" />
        <img id="m-layer-mouth" class="m-layer" src="/static/vn/monika/f/face-mouth-smile.png" alt="" />
        
        <!-- Layer 13: Hair Front / Bangs -->
        <img id="m-layer-hair-front" class="m-layer" src="/static/vn/monika/h/${this.hairStyle}/10.png" alt="" />
        
        <!-- Layer 14: Ribbon / Hair Accessory -->
        <img id="m-layer-ribbon" class="m-layer" src="/static/vn/monika/a/ribbon_def/0.png" alt="" style="display:none;" />

        <!-- Layer 15: Ahoge Accessory -->
        <img id="m-layer-ahoge" class="m-layer" src="" alt="" style="display:none;" />
      </div>
      <div class="monika-vn-atmosphere"></div>
    `;

    // Insert at the beginning of chat container so it renders under messages & composer
    chatContainer.insertBefore(this.stage, chatContainer.firstChild);
    this.applyStyles();
    this.renderWardrobe();
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
        /* Keep the room and face readable; only the lower foreground needs
           a soft shadow so the chat pills remain legible. */
        background: linear-gradient(to top,
          rgba(10, 8, 14, 0.78) 0%,
          rgba(10, 8, 14, 0.52) 18%,
          rgba(10, 8, 14, 0.22) 38%,
          transparent 62%);
        pointer-events: none;
      }
      
      /* Keep the companion visible at welcome, quiet behind readable messages. */
      .chat-container:not(.welcome-active) .monika-vn-stage {
        opacity: 1;
      }
      @media (max-width: 768px) {
        .monika-vn-char-wrap {
          width: max(680px, 100%);
          height: auto;
          aspect-ratio: 1;
          transform: translateX(-50%) scale(1.1);
        }
      }
      @media (prefers-reduced-motion: reduce) {
        .monika-vn-room { transition: none; }
      }
      /* The shell owns layout and colors. */
      #chat-history {
        position: relative;
        z-index: 10;
      }
      .chat-top-bar {
        position: relative;
        z-index: 15;
        backdrop-filter: none !important;
        -webkit-backdrop-filter: none !important;
        border-bottom: none !important;
      }
      #welcome-screen {
        display: none !important;
      }
    `;
  }

  renderWardrobe() {
    // 1. Hair layers
    const hairBack = document.getElementById('m-layer-hair-back');
    const hairFront = document.getElementById('m-layer-hair-front');
    if (hairBack) hairBack.src = `/static/vn/monika/h/${this.hairStyle}/0.png`;
    if (hairFront) hairFront.src = `/static/vn/monika/h/${this.hairStyle}/10.png`;

    // 2. Ribbon layer (ponytail 'def' has classic white ribbon)
    const ribbonEl = document.getElementById('m-layer-ribbon');
    if (ribbonEl) {
      if (this.hairStyle === 'def') {
        ribbonEl.src = '/static/vn/monika/a/ribbon_def/0.png';
        ribbonEl.style.display = 'block';
      } else {
        ribbonEl.style.display = 'none';
      }
    }

    // 3. Outfit layers
    const outfit0 = document.getElementById('m-layer-outfit-0');
    const outfit1 = document.getElementById('m-layer-outfit-1');
    if (outfit0) outfit0.src = `/static/vn/monika/c/${this.outfit}/body-def-0.png`;
    if (outfit1) outfit1.src = `/static/vn/monika/c/${this.outfit}/body-def-1.png`;

    // 4. Arm sleeves (conditional on outfit having sleeves)
    const armL = document.getElementById('m-layer-outfit-arm-l');
    const armR = document.getElementById('m-layer-outfit-arm-r');
    const hasArms = OUTFITS_WITH_ARMS.has(this.outfit);
    if (armL && armR) {
      if (hasArms) {
        armL.src = `/static/vn/monika/c/${this.outfit}/arms-left-rest-10.png`;
        armR.src = `/static/vn/monika/c/${this.outfit}/arms-right-restpoint-10.png`;
        armL.style.display = 'block';
        armR.style.display = 'block';
      } else {
        armL.style.display = 'none';
        armR.style.display = 'none';
      }
    }

    // 5. Ahoge layer
    const ahogeEl = document.getElementById('m-layer-ahoge');
    if (ahogeEl) {
      if (this.ahoge && this.ahoge !== 'none') {
        ahogeEl.src = `/static/vn/monika/a/${this.ahoge}/0.png`;
        ahogeEl.style.display = 'block';
      } else {
        ahogeEl.style.display = 'none';
      }
    }

    // 6. Background
    this.updateBackground();
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
    const room = document.getElementById('monika-vn-room');
    if (!room) return;

    if (this.background && this.background !== 'auto') {
      const bgUrl = this.background.startsWith('/') 
        ? this.background 
        : `/static/vn/location/${this.background}`;
      room.style.backgroundImage = `url('${bgUrl}')`;
    } else {
      // Auto mode: Day/night based on system clock
      const hour = new Date().getHours();
      const isNight = hour >= 20 || hour < 6;
      const bg = isNight ? '/static/vn/location/bg_room_night.png' : '/static/vn/location/bg_room.png';
      room.style.backgroundImage = `url('${bg}')`;
    }
  }

  // --- Wardrobe Public API ---

  setOutfit(outfitKey, save = true) {
    if (!outfitKey) return;
    this.outfit = outfitKey;
    if (save) {
      localStorage.setItem('monikai_wardrobe_outfit', outfitKey);
    }
    this.renderWardrobe();
    this.emitWardrobeChange();
  }

  setHairStyle(hairKey, save = true) {
    if (!hairKey) return;
    this.hairStyle = hairKey;
    if (save) {
      localStorage.setItem('monikai_wardrobe_hair', hairKey);
    }
    this.renderWardrobe();
    this.emitWardrobeChange();
  }

  setAhoge(ahogeKey, save = true) {
    this.ahoge = ahogeKey || 'none';
    if (save) {
      localStorage.setItem('monikai_wardrobe_ahoge', this.ahoge);
    }
    this.renderWardrobe();
    this.emitWardrobeChange();
  }

  setBackground(bgKey, save = true) {
    if (!bgKey) return;
    this.background = bgKey;
    if (save) {
      localStorage.setItem('monikai_wardrobe_bg', bgKey);
    }
    this.updateBackground();
    this.emitWardrobeChange();
  }

  setWardrobe(config = {}, save = true) {
    if (config.outfit !== undefined) this.outfit = config.outfit;
    if (config.hairStyle !== undefined) this.hairStyle = config.hairStyle;
    if (config.ahoge !== undefined) this.ahoge = config.ahoge;
    if (config.background !== undefined) this.background = config.background;
    if (config.autoMode !== undefined) this.autoMode = !!config.autoMode;

    if (save) {
      if (config.outfit !== undefined) localStorage.setItem('monikai_wardrobe_outfit', this.outfit);
      if (config.hairStyle !== undefined) localStorage.setItem('monikai_wardrobe_hair', this.hairStyle);
      if (config.ahoge !== undefined) localStorage.setItem('monikai_wardrobe_ahoge', this.ahoge);
      if (config.background !== undefined) localStorage.setItem('monikai_wardrobe_bg', this.background);
      if (config.autoMode !== undefined) localStorage.setItem('monikai_wardrobe_auto', String(this.autoMode));
    }

    this.renderWardrobe();
    this.emitWardrobeChange();
  }

  getWardrobeState() {
    return {
      outfit: this.outfit,
      hairStyle: this.hairStyle,
      ahoge: this.ahoge,
      background: this.background,
      autoMode: this.autoMode,
    };
  }

  emitWardrobeChange() {
    window.dispatchEvent(new CustomEvent('monikai:wardrobe-updated', {
      detail: this.getWardrobeState()
    }));
  }

  listenToWardrobeEvents() {
    window.addEventListener('monikai:set-wardrobe', (e) => {
      if (e.detail) {
        this.setWardrobe(e.detail);
      }
    });
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
