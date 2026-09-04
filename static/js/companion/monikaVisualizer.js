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
        filter: brightness(0.92) saturate(1.05);
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
      /* === Authentic Google Gemini Chat Layout === */

      #chat-history {
        position: relative;
        z-index: 10;
        background: transparent !important;
        padding-top: 20px !important;
        padding-bottom: 110px !important;
        display: flex;
        flex-direction: column;
        gap: 16px;
        max-width: 860px !important;
        margin: 0 auto !important;
        width: 100% !important;
        padding: 32px 24px 130px 24px !important;
        display: flex !important;
        flex-direction: column !important;
        gap: 28px !important;
      }
      .chat-top-bar {
        position: relative;
        z-index: 15;
        background: transparent !important;
        background: rgba(14, 11, 18, 0.6) !important;
        backdrop-filter: blur(12px) !important;
        -webkit-backdrop-filter: blur(12px) !important;
        border-bottom: 1px solid rgba(244, 114, 182, 0.12) !important;
        background: rgba(18, 19, 22, 0.7) !important;
        backdrop-filter: blur(16px) !important;
        -webkit-backdrop-filter: blur(16px) !important;
        border-bottom: 1px solid rgba(255, 255, 255, 0.06) !important;
      }
      #welcome-screen {
        display: none !important;
      }

      /* Custom scrollbar - subtle warm rose */
      /* Gemini Slim Scrollbar */
      #chat-history::-webkit-scrollbar {
        width: 6px !important;
      }
      #chat-history::-webkit-scrollbar-track {
        background: transparent !important;
      }
      #chat-history::-webkit-scrollbar-thumb {
        background: rgba(244, 114, 182, 0.3) !important;
        background: rgba(255, 255, 255, 0.2) !important;
        border-radius: 9999px !important;
      }
      #chat-history::-webkit-scrollbar-thumb:hover {
        background: rgba(244, 114, 182, 0.55) !important;
        background: rgba(255, 255, 255, 0.35) !important;
      }

      /* Base message bubble */
      /* Base message container */
      .msg {
        transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
        transition: opacity 0.2s ease;
        position: relative;
        border: none !important;
        box-shadow: none !important;
        background: transparent !important;
      }

      /* Monika (Assistant) speech bubble - legacy MonikAI rounded dialogue style */
      .msg-ai {
        align-self: flex-start !important;
        margin-left: 14px !important;
        margin-right: auto !important;
        width: fit-content !important;
        max-width: min(84%, 54rem) !important;
        border-radius: 26px !important;
        background: rgba(14, 11, 18, 0.70) !important;
        backdrop-filter: blur(18px) saturate(1.15) !important;
        -webkit-backdrop-filter: blur(18px) saturate(1.15) !important;
        border: 1px solid rgba(244, 114, 182, 0.18) !important;
        box-shadow: 0 12px 36px rgba(0, 0, 0, 0.38), 0 0 16px rgba(244, 114, 182, 0.06) !important;
        padding: 16px 24px 14px 24px !important;
      /* Hide ALL role headers (No "• Monika", no "• You" - clean Gemini style) */
      .msg .role {
        display: none !important;
      }

      /* User speech bubble - legacy MonikAI rounded pill/capsule */
      /* User Message - Gemini Dark Charcoal Pill */
      .msg-user {
        align-self: flex-end !important;
        margin-right: 14px !important;
        margin-left: auto !important;
        margin-right: 0 !important;
        background: #282a2c !important;
        border-radius: 24px !important;
        padding: 12px 22px !important;
        max-width: min(76%, 38rem) !important;
        width: fit-content !important;
        max-width: min(76%, 40rem) !important;
        border-radius: 22px !important;
        background: rgba(26, 20, 30, 0.75) !important;
        backdrop-filter: blur(14px) saturate(1.1) !important;
        -webkit-backdrop-filter: blur(14px) saturate(1.1) !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        box-shadow: 0 10px 28px rgba(0, 0, 0, 0.3) !important;
        padding: 12px 22px 10px 22px !important;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35) !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
      }
      .msg-user .body {
        color: #e3e3e3 !important;
        font-family: -apple-system, BlinkMacSystemFont, 'Google Sans', 'Segoe UI', Roboto, 'Inter', sans-serif !important;
        font-size: 1.02rem !important;
        line-height: 1.52 !important;
        letter-spacing: 0.01em !important;
        text-shadow: none !important;
      }
      .msg-user .msg-footer {
        display: none !important;
      }

      /* Role Header - elegant & delicate */
      .msg .role {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Inter', sans-serif !important;
        font-size: 0.84rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.03em !important;
        margin-bottom: 8px !important;
        display: flex !important;
        align-items: center !important;
        gap: 6px !important;
      /* Monika (Assistant) Message - Gemini Frameless Text */
      .msg-ai {
        align-self: flex-start !important;
        margin-right: auto !important;
        margin-left: 0 !important;
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        border-radius: 0 !important;
        padding: 4px 0 !important;
        max-width: 100% !important;
        width: 100% !important;
      }
      .msg-ai .role {
        color: #f472b6 !important;
      .msg-ai .body {
        color: #e3e3e3 !important;
        font-family: -apple-system, BlinkMacSystemFont, 'Google Sans', 'Segoe UI', Roboto, 'Inter', sans-serif !important;
        font-size: 1.05rem !important;
        line-height: 1.65 !important;
        letter-spacing: 0.01em !important;
        text-shadow: 0 1px 3px rgba(0, 0, 0, 0.9), 0 2px 8px rgba(0, 0, 0, 0.75) !important;
      }
      .msg-ai .role::before {
        background: #f472b6 !important;
        box-shadow: 0 0 8px rgba(244, 114, 182, 0.6) !important;
      .msg-ai .body p {
        margin-top: 10px !important;
        margin-bottom: 10px !important;
      }
      .msg-user .role {
        color: rgba(255, 240, 225, 0.55) !important;
      .msg-ai .body p:first-child {
        margin-top: 0 !important;
      }
      .msg-user .role::before {
        background: rgba(255, 255, 255, 0.4) !important;
      .msg-ai .body p:last-child {
        margin-bottom: 0 !important;
      }
      .msg .role .role-timestamp {
        font-size: 0.72rem !important;
        font-weight: 400 !important;
        color: rgba(255, 255, 255, 0.38) !important;
        margin-left: 6px !important;
      .msg-ai .body ul,
      .msg-ai .body ol {
        margin: 10px 0 !important;
        padding-left: 22px !important;
      }

      /* Message Body - Humanist Sans-Serif Dialogue Typography */
      .msg .body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Inter', 'Helvetica Neue', Arial, sans-serif !important;
        font-size: 1.02rem !important;
        line-height: 1.58 !important;
        letter-spacing: 0.01em !important;
      .msg-ai .body li {
        margin-bottom: 6px !important;
      }
      .msg-ai .body {
        color: rgba(255, 248, 240, 0.95) !important;
        font-weight: 400 !important;
      .msg-ai .body strong {
        color: #ffffff !important;
        font-weight: 600 !important;
      }
      .msg-user .body {
        color: rgba(255, 246, 233, 0.92) !important;
        font-weight: 400 !important;
      }

      /* Code within message retains clean monospace with dark card */
      /* Code in message */
      .msg .body pre,
      .msg .body code {
        font-family: 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace !important;
        text-shadow: none !important;
      }
      .msg .body code {
        font-size: 0.9em !important;
        background: rgba(0, 0, 0, 0.38) !important;
        border: 1px solid rgba(255, 255, 255, 0.09) !important;
        background: rgba(40, 42, 44, 0.9) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 6px !important;
        padding: 2px 6px !important;
        color: #f0f0f0 !important;
      }
      .msg .body pre code {
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
      }
      .msg .body pre {
        background: rgba(10, 8, 14, 0.8) !important;
        border: 1px solid rgba(244, 114, 182, 0.18) !important;
        border-radius: 12px !important;
        padding: 12px 16px !important;
        background: #1e1f20 !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 14px !important;
        padding: 14px 18px !important;
        margin: 14px 0 !important;
      }

      /* Message Footer Actions - subtle, revealed on hover */
      .msg .msg-footer {
        margin-top: 6px !important;
        opacity: 0.28 !important;
      /* Action icons under Monika's response - Gemini row */
      .msg-ai .msg-footer {
        display: flex !important;
        align-items: center !important;
        gap: 6px !important;
        margin-top: 14px !important;
        background: transparent !important;
        opacity: 0.75 !important;
        transition: opacity 0.2s ease !important;
      }
      .msg:hover .msg-footer {
        opacity: 0.95 !important;
      .msg-ai:hover .msg-footer {
        opacity: 1 !important;
      }
      .msg-footer button {
        color: rgba(255, 240, 230, 0.45) !important;
        transition: color 0.15s ease, background 0.15s ease !important;
      .msg-ai .msg-footer button,
      .msg-ai .msg-actions button {
        background: transparent !important;
        border: none !important;
        color: #c4c7c5 !important;
        width: 32px !important;
        height: 32px !important;
        border-radius: 50% !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 0 !important;
        transition: background-color 0.15s ease, color 0.15s ease !important;
      }
      .msg-footer button:hover {
        color: #f472b6 !important;
        background: rgba(244, 114, 182, 0.12) !important;
      .msg-ai .msg-footer button:hover,
      .msg-ai .msg-actions button:hover {
        background: rgba(255, 255, 255, 0.12) !important;
        color: #ffffff !important;
      }

      /* Floating input bar - Smooth Pill Capsule */
      /* Gemini Input Bar (Composer Pill) */
      .chat-container.welcome-active .chat-input-bar,
      .chat-container .chat-input-bar {
        position: absolute !important;
        bottom: 24px !important;
        bottom: 26px !important;
        left: 50% !important;
        transform: translateX(-50%) !important;
        margin-bottom: 0 !important;
        margin-left: 0 !important;
        margin-right: 0 !important;
        width: min(840px, calc(100% - 48px)) !important;
        margin: 0 !important;
        width: min(840px, calc(100% - 36px)) !important;
        max-width: 840px !important;
        z-index: 50 !important;
        background: rgba(18, 16, 22, 0.84) !important;
        background: #1e1f20 !important;
        backdrop-filter: blur(24px) !important;
        border: 1px solid rgba(244, 114, 182, 0.3) !important;
        box-shadow: 0 15px 40px rgba(0, 0, 0, 0.7), 0 0 20px rgba(244, 114, 182, 0.15) !important;
        border-radius: 18px !important;
        background: rgba(16, 12, 19, 0.86) !important;
        backdrop-filter: blur(24px) saturate(1.2) !important;
        -webkit-backdrop-filter: blur(24px) saturate(1.2) !important;
        border: 1px solid rgba(244, 114, 182, 0.28) !important;
        box-shadow: 0 18px 45px rgba(0, 0, 0, 0.65), 0 0 24px rgba(244, 114, 182, 0.12) !important;
        border-radius: 28px !important;
        padding: 6px 14px !important;
        transition: border-color 0.25s ease, box-shadow 0.25s ease !important;
        -webkit-backdrop-filter: blur(24px) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.55) !important;
        border-radius: 34px !important;
        padding: 8px 16px 8px 18px !important;
        transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
      }
      .user-message, .assistant-message, .system-message {
        backdrop-filter: blur(16px);
        background: rgba(20, 18, 24, 0.85) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        box-shadow: 0 10px 30px rgba(0,0,0,0.4);
      .chat-container .chat-input-bar:focus-within {
        border-color: rgba(244, 114, 182, 0.48) !important;
        box-shadow: 0 20px 52px rgba(0, 0, 0, 0.7), 0 0 32px rgba(244, 114, 182, 0.22) !important;
        border-color: rgba(255, 255, 255, 0.2) !important;
        box-shadow: 0 10px 38px rgba(0, 0, 0, 0.65) !important;
      }

      /* Textarea within input bar */
      /* Textarea within Gemini pill */
      .chat-container .chat-input-bar textarea,
      #message {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Inter', sans-serif !important;
        font-size: 0.98rem !important;
        color: rgba(255, 248, 240, 0.95) !important;
        padding-left: 8px !important;
        background: transparent !important;
        border: none !important;
        outline: none !important;
        font-family: -apple-system, BlinkMacSystemFont, 'Google Sans', 'Segoe UI', Roboto, sans-serif !important;
        font-size: 1.02rem !important;
        line-height: 1.5 !important;
        color: #e3e3e3 !important;
        padding: 8px 6px !important;
      }
      .chat-container .chat-input-bar textarea::placeholder,
      #message::placeholder {
        color: rgba(255, 230, 240, 0.38) !important;
        color: #8e918f !important;
        font-style: normal !important;
      }

      /* Send button styling */
      /* Left '+' button in Gemini bar */
      .overflow-plus-btn {
        width: 36px !important;
        height: 36px !important;
        border-radius: 50% !important;
        background: rgba(255, 255, 255, 0.06) !important;
        color: #c4c7c5 !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        border: none !important;
        transition: background 0.15s, color 0.15s !important;
      }
      .overflow-plus-btn:hover {
        background: rgba(255, 255, 255, 0.14) !important;
        color: #ffffff !important;
      }

      /* Model picker styled as Gemini pill (e.g. Flash ∨ / Monika ∨) */
      #model-picker-btn {
        background: transparent !important;
        border: none !important;
        color: #c4c7c5 !important;
        font-family: -apple-system, BlinkMacSystemFont, 'Google Sans', 'Segoe UI', Roboto, sans-serif !important;
        font-size: 0.88rem !important;
        font-weight: 500 !important;
        padding: 6px 10px !important;
        border-radius: 16px !important;
        transition: background 0.15s, color 0.15s !important;
      }
      #model-picker-btn:hover {
        background: rgba(255, 255, 255, 0.08) !important;
        color: #ffffff !important;
      }

      /* Send / Action button */
      #send-btn,
      .chat-input-bar .send-btn {
        background: #f472b6 !important;
        color: #1a0b16 !important;
        width: 36px !important;
        height: 36px !important;
        border-radius: 50% !important;
        box-shadow: 0 0 14px rgba(244, 114, 182, 0.45) !important;
        transition: transform 0.15s ease, background-color 0.15s ease, box-shadow 0.15s ease !important;
        background: #e3e3e3 !important;
        color: #131314 !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3) !important;
        transition: background-color 0.15s, transform 0.15s !important;
      }
      #send-btn:hover,
      .chat-input-bar .send-btn:hover {
        background: #fb7185 !important;
        background: #ffffff !important;
        transform: scale(1.05) !important;
        box-shadow: 0 0 20px rgba(244, 114, 182, 0.6) !important;
      }

      /* Muted disclaimer at the very bottom */
      .gemini-disclaimer {
        position: absolute;
        bottom: 8px;
        left: 50%;
        transform: translateX(-50%);
        font-size: 11px;
        color: #8e918f;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.9);
        pointer-events: none;
        white-space: nowrap;
        z-index: 50;
        font-family: -apple-system, BlinkMacSystemFont, 'Google Sans', 'Segoe UI', Roboto, sans-serif;
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
    // Dynamic placeholder update
    const updatePlaceholder = () => {
    // Dynamic placeholder update & disclaimer mount
    const updateUiChrome = () => {
      const msg = document.getElementById('message');
      if (msg && (!msg.placeholder || msg.placeholder.includes('Odysseus'))) {
        msg.placeholder = 'Napisz do Moniki...';
      if (msg && (!msg.placeholder || msg.placeholder.includes('Odysseus') || msg.placeholder.includes('Napisz'))) {
        msg.placeholder = 'Zapytaj Monikę...';
      }

      // Ensure bottom disclaimer
      const chatContainer = document.getElementById('chat-container');
      if (chatContainer && !document.getElementById('gemini-disclaimer-text')) {
        const disc = document.createElement('div');
        disc.id = 'gemini-disclaimer-text';
        disc.className = 'gemini-disclaimer';
        disc.textContent = 'Monika to towarzyszka AI i może popełniać błędy.';
        chatContainer.appendChild(disc);
      }
    };
    updatePlaceholder();
    setInterval(updatePlaceholder, 1000);
    updateUiChrome();
    setInterval(updateUiChrome, 1000);

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
