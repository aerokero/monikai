import React, { useEffect, useState, useRef, useMemo } from 'react';
import io from 'socket.io-client';

import ConfirmationPopup from './components/ConfirmationPopup';
import AuthLock from './components/AuthLock';
import SessionPromptWindow from './components/SessionPromptWindow';
import MinecraftConnectPopup from './components/MinecraftConnectPopup';
import SettingsWindow from './components/SettingsWindow';
import GoodbyePopup from './components/GoodbyePopup';
import ToastStack from './components/toasts/ToastStack';
import { LanguageProvider, useLanguage } from './contexts/LanguageContext';
import { LayoutProvider } from './contexts/LayoutContext';
import { useLayout } from './contexts/LayoutContext';
import { ModeProvider } from './contexts/ModeContext';
import { RealtimeProvider } from './contexts/RealtimeContext';
import { useSettings } from './contexts/SettingsContext';
import MonikaShell from './layout/MonikaShell';
import { MonikaContextProvider } from './contexts/MonikaContext';
import { SettingsProvider } from './contexts/SettingsContext';
import { AudioVideoProvider } from './contexts/AudioVideoContext';
import {
  VN_BACKGROUNDS,
} from './features/scene/backgroundConstants';
import {
  resolveVnBackground,
  pickVnScene,
  isValidScene,
} from './features/scene/backgroundUtils';
import {
  EAT_MEAL_ASSETS,
  MONIKA_MEAL_ASSETS,
} from './features/meal/mealConstants';
import {
  detectMealKey,
  detectFinishedMeal,
  shouldStartEatTogether,
  shouldStopEatTogether,
  pickRandomMonikaMeal,
} from './features/meal/mealUtils';
import {
  buildVisualState,
} from './features/outfit/visualStateUtils';
import {
  buildMasLayers,
} from './features/outfit/masLayerUtils';
import { useRandomBlink } from './features/outfit/hooks/useRandomBlink';
import { useRandomGlance } from './features/outfit/hooks/useRandomGlance';
import { useRandomPose } from './features/outfit/hooks/useRandomPose';
import { useHeadpat } from './features/outfit/hooks/useHeadpat';
import { useToasts } from './features/toasts/useToasts';

const SOCKET_URL = 'http://localhost:8000';
const socket = (() => {
  const existing = globalThis.__monikaiSocket;
  if (existing) return existing;
  const created = io(SOCKET_URL);
  globalThis.__monikaiSocket = created;
  return created;
})();

const ipcRenderer = (() => {
  try {
    if (typeof window !== 'undefined' && typeof window.require === 'function') {
      const electron = window.require('electron');
      return electron?.ipcRenderer || null;
    }
  } catch {
    // No Electron preload available in plain web mode.
  }
  return null;
})();

const TOOL_PERMISSION_ALIASES = {
  list_skills: ['list_skills', 'list_openclaw_skills'],
  get_skill: ['get_skill', 'get_openclaw_skill'],
  refresh_skills: ['refresh_skills', 'refresh_openclaw_skills'],
  run_skill_command: ['run_skill_command', 'run_openclaw_skill_command'],
};

const normalizeToolPermissions = (raw) => {
  const next = { ...(raw || {}) };
  Object.values(TOOL_PERMISSION_ALIASES).forEach((keys) => {
    const value = keys.map((key) => next[key]).find((v) => typeof v !== 'undefined');
    if (typeof value === 'undefined') return;
    keys.forEach((key) => {
      next[key] = value;
    });
  });
  return next;
};

function AppContent() {
  const { t, language } = useLanguage();
  const { isPortrait } = useLayout();
  const { showSettings, setShowSettings } = useSettings();
  const tRef = useRef(t);

  useEffect(() => {
    tRef.current = t;
  }, [t]);

  // ---------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------
  const calcLevelRms = (arr) => {
    if (!arr || !arr.length) return 0;
    let sum = 0;
    for (let i = 0; i < arr.length; i++) {
      const x = (arr[i] || 0) / 255;
      sum += x * x;
    }
    return Math.sqrt(sum / arr.length);
  };

  // ---------------------------------------------------------------------
  // Viewport (for fullscreen VN Visualizer)
  // ---------------------------------------------------------------------
  const [viewport, setViewport] = useState({ w: window.innerWidth, h: window.innerHeight });
  useEffect(() => {
    const onResize = () => {
      setViewport({ w: window.innerWidth, h: window.innerHeight });
    };
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('resize', onResize);
    };
  }, []);

  // Listen for close app request from Electron
  useEffect(() => {
    if (!ipcRenderer) return;
    
    const handleCloseRequest = () => {
      setShowGoodbyePopup(true);
    };
    
    ipcRenderer.on('request-close-app', handleCloseRequest);
    return () => {
      ipcRenderer.off('request-close-app', handleCloseRequest);
    };
  }, []);

  // ---------------------------------------------------------------------
  // Core State
  // ---------------------------------------------------------------------
  const [status, setStatus] = useState('Disconnected');
  const [socketConnected, setSocketConnected] = useState(socket.connected);

  // Auth State
  const [isAuthenticated, setIsAuthenticated] = useState(() => {
    return localStorage.getItem('face_auth_enabled') !== 'true';
  });

  const [isLockScreenVisible, setIsLockScreenVisible] = useState(() => {
    const saved = localStorage.getItem('face_auth_enabled');
    return saved === 'true';
  });

  const [faceAuthEnabled, setFaceAuthEnabled] = useState(() => {
    return localStorage.getItem('face_auth_enabled') === 'true';
  });
  const [settingsLoaded, setSettingsLoaded] = useState(false);

  // Logout function - kill server and close app
  const handleLogout = () => {
    // Kill the backend server
    if (socket && socket.connected) {
      socket.emit('kill_server');
      socket.disconnect();
    }
    // Close the window
    window.close();
  };

  // Set Monika's temporary mood (for UI interactions like avoiding quit button)
  const handleMonikaTemporaryMood = (mood) => {
    if (!socket) return;
    // Emit mood change through socket
    socket.emit('update_personality', { mood });
  };

  const [isConnected, setIsConnected] = useState(true);
  const [isMuted, setIsMuted] = useState(true);
  const [isVideoOn, setIsVideoOn] = useState(false);

  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const lastTypingEmitRef = useRef(0);
  const studyShareRef = useRef(null);

  const [browserData, setBrowserData] = useState({ image: null, logs: [] });
  const [confirmationQueue, setConfirmationQueue] = useState([]);

  const [showGoodbyePopup, setShowGoodbyePopup] = useState(false);
  const [showMinecraftWindow, setShowMinecraftWindow] = useState(false);
  const [showStudyWindow, setShowStudyWindow] = useState(false);
  const [eatTogetherActive, setEatTogetherActive] = useState(false);
  const [eatTogetherMeal, setEatTogetherMeal] = useState(null);
  const [monikaMeal, setMonikaMeal] = useState("pasta");

  const [currentTime, setCurrentTime] = useState(new Date());

  // VN Scene / Background is now imported from features/scene/backgroundConstants.ts and features/scene/backgroundUtils.ts
  // See src/features/scene/ for scene management logic
  
  const [vnScene, setVnScene] = useState("room");
  const [vnBackground, setVnBackground] = useState(VN_BACKGROUNDS.room);
  const lastSceneChangeRef = useRef(0);
  const lastActivityRef = useRef(Date.now());
  const sceneRef = useRef(vnScene);
  const [sceneOverrideUntil, setSceneOverrideUntil] = useState(0);
  const prevSceneRef = useRef(null);
  const eatPrevSceneRef = useRef(null);
  const eatTogetherActiveRef = useRef(eatTogetherActive);

  // Meal system logic is now imported from features/meal/mealConstants.ts and features/meal/mealUtils.ts
  // Outfit and ahoge constants are imported from features/outfit/outfitConstants.ts

  // Meal detection functions are now imported from features/meal/mealUtils.ts

  // Meal mode management (uses imported pickRandomMonikaMeal)
  const startEatTogether = () => {
    setEatTogetherActive(true);
    setEatTogetherMeal(null);
    const pick = pickRandomMonikaMeal();
    if (pick) setMonikaMeal(pick);
  };

  const stopEatTogether = () => {
    setEatTogetherActive(false);
    setEatTogetherMeal(null);
  };

  // ---------------------------------------------------------------------
  // RESTORED STATE (must be declared BEFORE talking logic uses it)
  // ---------------------------------------------------------------------
  const [aiAudioData, setAiAudioData] = useState(new Array(64).fill(0));
  const [micAudioData, setMicAudioData] = useState(new Array(32).fill(0));
  const [fps, setFps] = useState(0);

  // Compute continuous levels (RMS)
  const aiLevel = useMemo(() => calcLevelRms(aiAudioData), [aiAudioData]);
  const micLevel = useMemo(() => calcLevelRms(micAudioData), [micAudioData]);

  // ---------------------------------------------------------------------
  // Talking state (AI / USER) with hysteresis + hold (prevents "stuck TALK")
  // ---------------------------------------------------------------------
  const [aiSpeaking, setAiSpeaking] = useState(false);
  const [userSpeaking, setUserSpeaking] = useState(false);

  const aiOffTimerRef = useRef(null);
  const userOffTimerRef = useRef(null);

  useEffect(() => {
    if (!isConnected) {
      setAiSpeaking(false);
      return;
    }

    const ON = 0.06;
    const OFF = 0.04;
    const HOLD_MS = 240;

    if (aiLevel > ON) {
      if (aiOffTimerRef.current) {
        clearTimeout(aiOffTimerRef.current);
        aiOffTimerRef.current = null;
      }
      setAiSpeaking(true);
      return;
    }

    if (aiSpeaking && aiLevel < OFF && !aiOffTimerRef.current) {
      aiOffTimerRef.current = setTimeout(() => {
        setAiSpeaking(false);
        aiOffTimerRef.current = null;
      }, HOLD_MS);
    }

    if (!aiSpeaking && aiLevel < ON) {
      setAiSpeaking(false);
    }
  }, [aiLevel, aiSpeaking, isConnected]);

  useEffect(() => {
    // Reset user speaking state if muted or disconnected
    if (!isConnected || isMuted) {
      setUserSpeaking(false);
      if (userOffTimerRef.current) {
        clearTimeout(userOffTimerRef.current);
        userOffTimerRef.current = null;
      }
    }
  }, [isConnected, isMuted]);

  useEffect(() => {
    return () => {
      if (aiOffTimerRef.current) clearTimeout(aiOffTimerRef.current);
      if (userOffTimerRef.current) clearTimeout(userOffTimerRef.current);
    };
  }, []);

  // ---------------------------------------------------------------------
  // Device states - microphones, speakers, webcams
  // ---------------------------------------------------------------------
  const [micDevices, setMicDevices] = useState([]);
  const [speakerDevices, setSpeakerDevices] = useState([]);
  const [webcamDevices, setWebcamDevices] = useState([]);

  // Selected device IDs - restored from localStorage
  const [selectedMicId, setSelectedMicId] = useState(() => localStorage.getItem('selectedMicId') || '');
  const [selectedSpeakerId, setSelectedSpeakerId] = useState(() => localStorage.getItem('selectedSpeakerId') || '');
  const [selectedWebcamId, setSelectedWebcamId] = useState(() => localStorage.getItem('selectedWebcamId') || '');
  const [toolPermissions, setToolPermissions] = useState({});
  const [skills, setSkills] = useState([]);
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [skillsActionBusy, setSkillsActionBusy] = useState(false);
  const [personalityState, setPersonalityState] = useState({ mood: 'neutral', affection: 0 });
  const [sessionMode, setSessionMode] = useState({ active: false, kind: 'auto' });
  const [sessionPromptQueue, setSessionPromptQueue] = useState([]);
  const [studyCatalog, setStudyCatalog] = useState({ folders: [] });
  const [studySelection, setStudySelection] = useState({ folder: '', file: '', path: '' });

  // ---------------------------------------------------------------------
  // Camera / Vision State
  // ---------------------------------------------------------------------
  const [isCameraFlipped, setIsCameraFlipped] = useState(false);
  const [visionMode, setVisionMode] = useState(() => localStorage.getItem('video_mode') || 'none');
  const [visionFrame, setVisionFrame] = useState(null);
  const [geminiModelPreset, setGeminiModelPreset] = useState('2.5');
  const [geminiVoice, setGeminiVoice] = useState('Leda');

  // Web Audio Context for Mic Visualization
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const sourceRef = useRef(null);
  const animationFrameRef = useRef(null);

  // Video Refs
  const videoRef = useRef(null);
  const transmissionCanvasRef = useRef(null);
  const lastFrameTimeRef = useRef(0);
  const frameCountRef = useRef(0);

  // Ref to track video state for the loop (avoids closure staleness)
  const isVideoOnRef = useRef(false);

  const { toasts, pushToast, dismissToast } = useToasts();


  const makeId = () =>
    (typeof crypto !== "undefined" && crypto.randomUUID)
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random()}`;

  const enqueueSessionPrompt = (payload) => {
    if (!payload) return;
    setSessionPromptQueue(prev => [
      ...prev,
      { ...payload, _id: payload._id || payload.id || makeId() }
    ]);
  };

  const popSessionPrompt = () => {
    setSessionPromptQueue(prev => prev.slice(1));
  };

  const fetchStudyCatalog = async () => {
    try {
      const res = await fetch('http://localhost:8000/study/catalog');
      if (!res.ok) return;
      const data = await res.json();
      setStudyCatalog(data || { folders: [] });
    } catch (err) {
      console.error("Study catalog fetch failed:", err);
    }
  };

  useEffect(() => {
    fetchStudyCatalog();
  }, []);

  useEffect(() => {
    if (!socket) return;
    const onStudyRequestShare = () => {
      if (showStudyWindow && studyShareRef.current) {
        try {
          studyShareRef.current();
        } catch {}
      }
    };
    socket.on('study_request_share', onStudyRequestShare);
    return () => socket.off('study_request_share', onStudyRequestShare);
  }, [showStudyWindow]);

  const handleSelectStudy = (selection) => {
    if (!selection) return;
    setStudySelection(selection);
    setShowStudyWindow(true);
    if (socket) socket.emit('study_select', selection);
  };


  useEffect(() => {
    if (showStudyWindow) {
      if (!prevSceneRef.current) prevSceneRef.current = vnScene;
      setVnScene('school');
      setVnBackground(resolveVnBackground('school', new Date()));
      setSceneOverrideUntil(Date.now() + 6 * 60 * 60 * 1000);
    } else if (prevSceneRef.current) {
      const prev = prevSceneRef.current;
      const nextScene = eatTogetherActive ? 'restaurant' : prev;
      setVnScene(nextScene);
      setVnBackground(resolveVnBackground(nextScene, new Date()));
      prevSceneRef.current = null;
      setSceneOverrideUntil(0);
    }
  }, [showStudyWindow, eatTogetherActive, vnScene]);

  useEffect(() => {
    if (!eatTogetherActive) {
      if (!showStudyWindow && eatPrevSceneRef.current) {
        const prev = eatPrevSceneRef.current;
        eatPrevSceneRef.current = null;
        setVnScene(prev);
        setVnBackground(resolveVnBackground(prev, new Date()));
        setSceneOverrideUntil(0);
      }
      return;
    }

    if (showStudyWindow) return;

    if (!eatPrevSceneRef.current) eatPrevSceneRef.current = vnScene;
    if (vnScene !== 'restaurant') {
      setVnScene('restaurant');
      setVnBackground(resolveVnBackground('restaurant', new Date()));
    }
    setSceneOverrideUntil(Date.now() + 3 * 60 * 60 * 1000);
  }, [eatTogetherActive, showStudyWindow, vnScene]);

  const clearSessionPrompts = () => {
    setSessionPromptQueue([]);
  };

  // Live Clock Update
  useEffect(() => {
    const timer = setInterval(() => {
      const now = new Date();
      setCurrentTime(now);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    sceneRef.current = vnScene;
  }, [vnScene]);

  useEffect(() => {
    eatTogetherActiveRef.current = eatTogetherActive;
  }, [eatTogetherActive]);

  // Scene selection function is now imported from features/scene/backgroundUtils.ts
  // It determines Monika's location based on time of day

  useEffect(() => {
    const initialScene = pickVnScene(new Date());
    setVnScene(initialScene);
    setVnBackground(resolveVnBackground(initialScene, new Date()));
  }, []);

  useEffect(() => {
    if (showStudyWindow) return;
    if (vnScene !== 'outside') return;
    if (sceneOverrideUntil && Date.now() < sceneOverrideUntil) return;
    setVnBackground(resolveVnBackground(vnScene, currentTime));
  }, [currentTime, vnScene, showStudyWindow, sceneOverrideUntil]);

  const { headpatActive, triggerHeadpat } = useHeadpat();

  const isBlinking = useRandomBlink();
  const randomGlance = useRandomGlance();
  const randomPose = useRandomPose(aiSpeaking);

  // ---------------------------------------------------------------------
  // MAS Layer Logic (Monika After Story Assets)
  // ---------------------------------------------------------------------
  const currentHour = currentTime.getHours();
  const currentMinute = currentTime.getMinutes();
  const currentMonth = currentTime.getMonth(); // 0-11
  const currentDay = currentTime.getDate();
  const currentYear = currentTime.getFullYear();

  // Calculate outfit/accessory state in a dedicated feature helper.
  const visualState = useMemo(() => buildVisualState({
    mood: personalityState.mood,
    affection: personalityState.affection || 0,
    weather: personalityState.weather,
    currentHour,
    currentMinute,
    currentMonth,
    currentDay,
    currentYear,
    vnScene,
    eatTogetherActive,
    sessionModeActive: sessionMode.active,
    showStudyWindow,
  }), [personalityState.mood, personalityState.affection, personalityState.weather, currentHour, currentMinute, currentMonth, currentDay, currentYear, vnScene, eatTogetherActive, sessionMode.active, showStudyWindow]);

  // Report Visual State to Backend
  useEffect(() => {
    if (socketConnected) {
      socket.emit('report_visual_state', { 
        location: vnScene, 
        outfit: visualState.outfitName 
      });
    }
  }, [vnScene, visualState.outfitName, socketConnected]);

  const masLayers = useMemo(() => buildMasLayers({
    personalityMood: personalityState.mood,
    personalityEnergy: personalityState.energy,
    visualState,
    headpatActive,
    showStudyWindow,
    currentHour,
    currentMinute,
    randomPose,
    vnScene,
    isBlinking,
    randomGlance,
    eatTogetherActive,
    eatTogetherMeal,
    monikaMeal,
    monikaMealAssets: MONIKA_MEAL_ASSETS,
    eatMealAssets: EAT_MEAL_ASSETS,
  }), [personalityState.mood, personalityState.energy, visualState, isBlinking, randomGlance, randomPose, vnScene, showStudyWindow, headpatActive, eatTogetherActive, eatTogetherMeal, monikaMeal, currentHour, currentMinute]);

  useEffect(() => {
    if (aiSpeaking || userSpeaking) {
      lastActivityRef.current = Date.now();
    }
  }, [aiSpeaking, userSpeaking]);

  useEffect(() => {
    const now = Date.now();
    if (sceneOverrideUntil && now < sceneOverrideUntil) return;
    const quietFor = now - lastActivityRef.current;
    const minQuietMs = 8000;
    const minGapMs = 60000;

    if (quietFor < minQuietMs) return;
    if (now - lastSceneChangeRef.current < minGapMs) return;

    const nextScene = pickVnScene(currentTime, quietFor);
    if (nextScene !== sceneRef.current) {
      setVnScene(nextScene);
      setVnBackground(resolveVnBackground(nextScene, currentTime));
      lastSceneChangeRef.current = now;
    }
  }, [currentTime, aiSpeaking, userSpeaking]);

  // Ref to track if model has been auto-connected (prevents duplicate connections)
  const hasAutoConnectedRef = useRef(false);

  // Auto-Connect Model on Start (Only after Auth and devices loaded)
  useEffect(() => {
    if (isConnected && isAuthenticated && socketConnected && settingsLoaded && micDevices.length > 0 && !hasAutoConnectedRef.current) {
      hasAutoConnectedRef.current = true;

      setTimeout(() => {
        const index = micDevices.findIndex(d => d.deviceId === selectedMicId);
        const queryDevice = micDevices.find(d => d.deviceId === selectedMicId);
        const deviceName = queryDevice ? queryDevice.label : null;

        console.log("Auto-connecting to model with device:", deviceName, "Index:", index);

        setStatus(tRef.current('system.connecting'));
        socket.emit('start_audio', {
          device_index: index >= 0 ? index : null,
          device_name: deviceName,
          muted: isMuted,
          video_mode: visionMode || 'none'
        });
      }, 500);
    }
  }, [isConnected, isAuthenticated, socketConnected, settingsLoaded, micDevices, selectedMicId, isMuted, visionMode]);

  useEffect(() => {
    socket.on('connect', () => {
      setStatus(tRef.current('system.connected'));
      setSocketConnected(true);
      socket.emit('get_settings');
    });

    socket.on('personality_status', (data) => {
      // Update local state for Visualizer layers
      setPersonalityState(prev => ({ ...prev, ...data }));
    });

    socket.on('disconnect', () => {
      setStatus(tRef.current('system.disconnected'));
      setSocketConnected(false);
      setConfirmationQueue([]);
    });

    socket.on('status', (data) => {
      let displayMsg = data.msg;

      // Persona translation for status messages
      if (data.msg === 'MonikAI Started') displayMsg = tRef.current('system.monikai_started');
      else if (data.msg === 'MonikAI Stopped') displayMsg = tRef.current('system.monikai_stopped');

      addMessage('System', displayMsg);
      if (data.msg === 'MonikAI Started') {
        setStatus(tRef.current('system.model_connected'));
      } else if (data.msg === 'MonikAI Stopped') {
        setStatus(tRef.current('system.connected'));
      }
    });

    socket.on('audio_data', (data) => {
      setAiAudioData(data.data);
    });

    socket.on('vision_frame', (data) => {
      if (data && data.data) {
        setVisionFrame(data);
      }
    });

    socket.on('request_camera_frame', () => {
      if (isVideoOnRef.current) {
        sendCameraFrameNow();
      }
    });

    socket.on('auth_status', (data) => {
      console.log("Auth Status:", data);
      setIsAuthenticated(data.authenticated);
      if (!data.authenticated) setIsLockScreenVisible(true);
    });

    socket.on('settings', (settings) => {
      console.log("[Settings] Received:", settings);
      if (settings && typeof settings.face_auth_enabled !== 'undefined') {
        setFaceAuthEnabled(settings.face_auth_enabled);
        localStorage.setItem('face_auth_enabled', settings.face_auth_enabled);
      }
      if (typeof settings.camera_flipped !== 'undefined') {
        console.log("[Settings] Camera flip set to:", settings.camera_flipped);
        setIsCameraFlipped(settings.camera_flipped);
      }
      if (typeof settings.video_mode !== 'undefined') {
        setVisionMode(settings.video_mode || 'none');
        localStorage.setItem('video_mode', settings.video_mode || 'none');
      }
      if (settings.tool_permissions) {
        setToolPermissions(normalizeToolPermissions(settings.tool_permissions));
      }
      if (settings.gemini_model_preset) setGeminiModelPreset(settings.gemini_model_preset);
      if (settings.gemini_voice) setGeminiVoice(settings.gemini_voice);
      setSettingsLoaded(true);
    });

    socket.on('skills', (payload) => {
      const nextSkills = Array.isArray(payload?.skills) ? payload.skills : [];
      setSkills(nextSkills);
      setSkillsLoading(false);
      setSkillsActionBusy(false);
    });

    socket.on('skill_install_result', (payload) => {
      if (payload?.ok) {
        const count = Number(payload?.result?.installed_count || 0);
        const source = payload?.result?.source;
        if (source) {
          pushToast(
            count > 0
              ? `Installed ${count} skill(s) from source.`
              : 'Skill source install finished.',
            'system'
          );
        } else {
          pushToast(`Installed ${count} skill(s).`, 'system');
        }
      } else {
        pushToast(`Skill install failed: ${payload?.error || 'unknown error'}`, 'error');
      }
      setSkillsActionBusy(false);
      setSkillsLoading(false);
    });

    socket.on('skill_uninstall_result', (payload) => {
      if (payload?.ok) {
        pushToast('Skill uninstalled.', 'system');
      } else {
        pushToast(`Skill uninstall failed: ${payload?.error || 'unknown error'}`, 'error');
      }
      setSkillsActionBusy(false);
      setSkillsLoading(false);
    });

    socket.on('error', (data) => {
      console.error("Socket Error:", data);
      pushToast(`Something feels off... (${data.msg})`, 'error');
    });

    socket.on('browser_frame', (data) => {
      setBrowserData(prev => ({
        image: data?.image || prev.image || null,
        logs: [...prev.logs, data?.log].filter(l => l).slice(-300)
      }));
      if (data?.image) {
        // Browser frame is consumed by shell panels via browserData.
      }
    });

    socket.on('transcription', (data) => {
      const rawText = String(data?.text ?? "");
      if (!rawText.trim()) return;

      // Trigger listening state only when text is actually transcribed
      if (data.sender === 'Ty' || data.sender === 'User') {
        setUserSpeaking(true);
        if (userOffTimerRef.current) clearTimeout(userOffTimerRef.current);
        userOffTimerRef.current = setTimeout(() => {
          setUserSpeaking(false);
        }, 3000);

        const wantsStart = shouldStartEatTogether(data.text);
        const wantsStop = shouldStopEatTogether(data.text);
        if (wantsStart) startEatTogether();
        if (wantsStop) stopEatTogether();

        const wantsFinished = detectFinishedMeal(data.text);
        if (wantsFinished && (eatTogetherActiveRef.current || wantsStart)) {
          setEatTogetherMeal("finished");
        } else {
          const mealKey = detectMealKey(data.text);
          if (mealKey && (eatTogetherActiveRef.current || wantsStart)) {
            setEatTogetherMeal(mealKey);
          }
        }
      }

      setMessages(prev => {
        const list = prev || [];
        const lastMsg = list[list.length - 1];

        // Append only if same sender AND not a new turn
        if (lastMsg && lastMsg.sender === data.sender && !data.is_new) {
          if (data.is_correction) {
            return [
              ...list.slice(0, -1),
              { ...lastMsg, text: data.text }
            ];
          }
          return [
            ...list.slice(0, -1),
            { ...lastMsg, text: lastMsg.text + data.text }
          ];
        }

        // Otherwise create new bubble
        return [...list, {
          sender: data.sender,
          text: data.text,
          time: new Date().toLocaleTimeString()
        }];
      });
    });

    socket.on('tool_confirmation_request', (data) => {
      console.log("Received Confirmation Request:", data);
      setConfirmationQueue((prev) => {
        const requestId = data?.id;
        if (requestId && prev.some((item) => item?.id === requestId)) {
          return prev;
        }
        return [...prev, data];
      });
    });

    socket.on('vn_scene', (payload) => {
      const scene = payload?.scene;
      if (!scene || !isValidScene(scene)) return;
      if (eatTogetherActiveRef.current) return;
      const ttl = typeof payload?.ttl_ms === 'number' ? payload.ttl_ms : 180000;
      setVnScene(scene);
      setVnBackground(resolveVnBackground(scene, new Date()));
      setSceneOverrideUntil(Date.now() + ttl);
      lastSceneChangeRef.current = Date.now();
    });

    socket.on('session_mode', (data) => {
      const active = !!(data && data.active);
      const kind = data?.kind || 'auto';
      setSessionMode({ active, kind });
      if (!active) {
        clearSessionPrompts();
      }
      pushToast(active ? `Session mode: ${kind}` : 'Session mode ended', 'system');
    });

    socket.on('session_prompt', (payload) => {
      enqueueSessionPrompt(payload);
    });

    socket.on('session_finalized', (data) => {
      const summary = (data && data.summary) ? String(data.summary) : '';
      if (!summary) return;
      const trimmed = summary.length > 280 ? summary.slice(0, 280).trimEnd() + '…' : summary;
      pushToast(`Podsumowanie sesji: ${trimmed}`, 'system', 12000);
    });

    navigator.mediaDevices.enumerateDevices().then(devs => {
      const audioInputs = devs.filter(d => d.kind === 'audioinput');
      const audioOutputs = devs.filter(d => d.kind === 'audiooutput');
      const videoInputs = devs.filter(d => d.kind === 'videoinput');

      setMicDevices(audioInputs);
      setSpeakerDevices(audioOutputs);
      setWebcamDevices(videoInputs);

      const savedMicId = localStorage.getItem('selectedMicId');
      if (savedMicId && audioInputs.some(d => d.deviceId === savedMicId)) {
        setSelectedMicId(savedMicId);
      } else if (audioInputs.length > 0) {
        setSelectedMicId(audioInputs[0].deviceId);
      }

      const savedSpeakerId = localStorage.getItem('selectedSpeakerId');
      if (savedSpeakerId && audioOutputs.some(d => d.deviceId === savedSpeakerId)) {
        setSelectedSpeakerId(savedSpeakerId);
      } else if (audioOutputs.length > 0) {
        setSelectedSpeakerId(audioOutputs[0].deviceId);
      }

      const savedWebcamId = localStorage.getItem('selectedWebcamId');
      if (savedWebcamId && videoInputs.some(d => d.deviceId === savedWebcamId)) {
        setSelectedWebcamId(savedWebcamId);
      } else if (videoInputs.length > 0) {
        setSelectedWebcamId(videoInputs[0].deviceId);
      }
    });

    return () => {
      socket.off('connect');
      socket.off('disconnect');
      socket.off('status');
      socket.off('audio_data');
      socket.off('vision_frame');
      socket.off('request_camera_frame');
      socket.off('browser_frame');
      socket.off('transcription');
      socket.off('tool_confirmation_request');
      socket.off('vn_scene');
      socket.off('session_mode');
      socket.off('session_prompt');
      socket.off('error');
      socket.off('personality_status');
      socket.off('auth_status');
      socket.off('settings');
      socket.off('skills');
      socket.off('skill_install_result');
      socket.off('skill_uninstall_result');

      stopMicVisualizer();
      stopVideo();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (visionMode === 'camera' && !isVideoOn && webcamDevices.length > 0) {
      startVideo();
    }
  }, [visionMode, isVideoOn, webcamDevices.length]);

  // Initial check in case we are already connected (fix race condition)
  useEffect(() => {
    if (socket.connected) {
      setStatus(t('system.connected'));
      socket.emit('get_settings');
    }
  }, []);

  useEffect(() => {
    if (!showSettings) return;
    if (!socket || !socket.connected) return;
    requestSkills({ includeIneligible: true, includeDisabled: true });
  }, [showSettings, socketConnected]);

  // Persist device selections to localStorage when they change
  useEffect(() => {
    if (selectedMicId) {
      localStorage.setItem('selectedMicId', selectedMicId);
      console.log('[Settings] Saved microphone:', selectedMicId);
    }
  }, [selectedMicId]);

  useEffect(() => {
    if (selectedSpeakerId) {
      localStorage.setItem('selectedSpeakerId', selectedSpeakerId);
      console.log('[Settings] Saved speaker:', selectedSpeakerId);
    }
  }, [selectedSpeakerId]);

  useEffect(() => {
    if (selectedWebcamId) {
      localStorage.setItem('selectedWebcamId', selectedWebcamId);
      console.log('[Settings] Saved webcam:', selectedWebcamId);
    }
  }, [selectedWebcamId]);

  // Start/Stop Mic Visualizer
  useEffect(() => {
    if (selectedMicId) {
      startMicVisualizer(selectedMicId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedMicId]);

  const startMicVisualizer = async (deviceId) => {
    stopMicVisualizer();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { deviceId: { exact: deviceId } }
      });

      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
      analyserRef.current = audioContextRef.current.createAnalyser();
      analyserRef.current.fftSize = 64;

      sourceRef.current = audioContextRef.current.createMediaStreamSource(stream);
      sourceRef.current.connect(analyserRef.current);

      const updateMicData = () => {
        if (!analyserRef.current) return;
        const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
        analyserRef.current.getByteFrequencyData(dataArray);
        setMicAudioData(Array.from(dataArray));
        animationFrameRef.current = requestAnimationFrame(updateMicData);
      };

      updateMicData();
    } catch (err) {
      console.error("Error accessing microphone:", err);
    }
  };

  const stopMicVisualizer = () => {
    if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
    if (sourceRef.current) sourceRef.current.disconnect();
    if (audioContextRef.current) audioContextRef.current.close();
  };

  const startVideo = async () => {
    try {
      const constraints = {
        video: {
          width: { ideal: 1920 },
          height: { ideal: 1080 },
          aspectRatio: 16 / 9
        }
      };

      if (selectedWebcamId) {
        constraints.video.deviceId = { exact: selectedWebcamId };
      }

      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.play();
      }

      if (!transmissionCanvasRef.current) {
        transmissionCanvasRef.current = document.createElement('canvas');
        transmissionCanvasRef.current.width = 640;
        transmissionCanvasRef.current.height = 360;
        console.log("Initialized transmission canvas (640x360)");
      }

      setIsVideoOn(true);
      isVideoOnRef.current = true;

      console.log("Starting video loop with webcam:", selectedWebcamId || "default");
      requestAnimationFrame(predictWebcam);

    } catch (err) {
      console.error("Error accessing camera:", err);
      addMessage('System', t('system.camera_error'));
    }
  };

  const sendCameraFrameNow = () => {
    if (!videoRef.current || videoRef.current.readyState < 2) return;
    if (!transmissionCanvasRef.current) {
      transmissionCanvasRef.current = document.createElement('canvas');
      transmissionCanvasRef.current.width = 320;
      transmissionCanvasRef.current.height = 180;
    }
    const transCanvas = transmissionCanvasRef.current;
    const transCtx = transCanvas.getContext('2d');
    transCtx.drawImage(videoRef.current, 0, 0, transCanvas.width, transCanvas.height);
    transCanvas.toBlob((blob) => {
      if (blob) socket.emit('video_frame', { image: blob });
    }, 'image/jpeg', 0.4);
  };

  const predictWebcam = () => {
    if (!videoRef.current || !isVideoOnRef.current) return;

    if (videoRef.current.readyState < 2 || videoRef.current.videoWidth === 0 || videoRef.current.videoHeight === 0) {
      requestAnimationFrame(predictWebcam);
      return;
    }

    if (isConnected) {
      if (frameCountRef.current % 5 === 0) {
        const transCanvas = transmissionCanvasRef.current;
        if (transCanvas) {
          const transCtx = transCanvas.getContext('2d');
          transCtx.drawImage(videoRef.current, 0, 0, transCanvas.width, transCanvas.height);

          transCanvas.toBlob((blob) => {
            if (blob) socket.emit('video_frame', { image: blob });
          }, 'image/jpeg', 0.6);
        }
      }
    }

    const nowMs = performance.now();
    frameCountRef.current++;
    if (nowMs - lastFrameTimeRef.current >= 1000) {
      setFps(frameCountRef.current);
      frameCountRef.current = 0;
      lastFrameTimeRef.current = nowMs;
    }

    if (isVideoOnRef.current) {
      requestAnimationFrame(predictWebcam);
    }
  };

  const stopVideo = () => {
    if (videoRef.current && videoRef.current.srcObject) {
      videoRef.current.srcObject.getTracks().forEach(track => track.stop());
      videoRef.current.srcObject = null;
    }
    setIsVideoOn(false);
    isVideoOnRef.current = false;
    setFps(0);
  };

  const setVisionModeAndPersist = (mode, extraSettings = {}) => {
    const next = mode || 'none';
    setVisionMode(next);
    localStorage.setItem('video_mode', next);
    socket.emit('update_settings', { video_mode: next, ...extraSettings });
  };

  const toggleVideo = () => {
    if (isVideoOn) {
      stopVideo();
      setVisionModeAndPersist('none', { screen_capture: { stream_to_ai: false } });
    } else {
      startVideo();
      setVisionModeAndPersist('camera', { screen_capture: { stream_to_ai: false } });
    }
  };

  const toggleScreenCapture = () => {
    if (visionMode === 'screen') {
      setVisionModeAndPersist('none', { screen_capture: { stream_to_ai: false } });
    } else {
      if (isVideoOn) stopVideo();
      setVisionModeAndPersist('screen', { screen_capture: { stream_to_ai: true } });
    }
  };

  const addMessage = (sender, text) => {
    const s = String(sender ?? "");
    if (s.toLowerCase() === "system") {
      pushToast(text, "system");
      return;
    }
    setMessages(prev => [...prev, { sender: s, text: String(text ?? ""), time: new Date().toLocaleTimeString() }]);
  };

  useEffect(() => {
    if (!socket || !inputValue) return;
    const now = Date.now();
    if (now - lastTypingEmitRef.current > 2000) {
      lastTypingEmitRef.current = now;
      socket.emit('user_activity', { text: String(inputValue).slice(0, 120) });
    }
  }, [inputValue, socket]);

  const togglePower = () => {
    if (isConnected) {
      socket.emit('stop_audio');
      setIsConnected(false);
      setIsMuted(false);
    } else {
      const index = micDevices.findIndex(d => d.deviceId === selectedMicId);
      socket.emit('start_audio', {
        device_index: index >= 0 ? index : null,
        video_mode: visionMode || 'none'
      });
      setIsConnected(true);
      setIsMuted(false);
    }
  };

  const toggleMute = () => {
    if (!isConnected) return;
    if (isMuted) {
      socket.emit('resume_audio');
      setIsMuted(false);
    } else {
      socket.emit('pause_audio');
      setIsMuted(true);
    }
  };

  const toggleSessionMode = (kind) => {
    if (!isConnected) return;
    const nextActive = !sessionMode.active;
    // On start, the chosen entry tone (reflective | therapy) is passed through;
    // on stop, kind doesn't matter.
    const resolvedKind = nextActive ? (kind || sessionMode.kind || 'auto') : sessionMode.kind;
    socket.emit('session_mode_set', { active: nextActive, kind: resolvedKind });
  };

  const handleSessionPromptSubmit = (payload) => {
    if (!payload) return;
    socket.emit('session_exercise_submit', payload);
  };

  const handleSessionSketchSave = (payload) => {
    if (!payload) return;
    socket.emit('session_sketch_save', payload);
  };

  const isCurrentPageRequest = (raw) => {
    const text = String(raw || '').trim().toLowerCase();
    if (!text) return false;
    if (text.includes('can you see this current page')) return true;
    if (text.includes('can you see the current page')) return true;
    if (text.includes('can you see current page')) return true;
    return false;
  };

  const handleSend = (e) => {
    if (!e || e.key !== 'Enter') return;

    const text = (inputValue || '').trim();
    const attachments = Array.isArray(e.attachments) ? e.attachments : [];

  // pozwól wysłać: (tekst) lub (same załączniki) lub (oba)
  if (!text && attachments.length === 0) return;

    // Treat typed input as activity for VN scene auto-logic
    lastActivityRef.current = Date.now();

    if (text) {
      const wantsStart = shouldStartEatTogether(text);
      const wantsStop = shouldStopEatTogether(text);
      if (wantsStart) startEatTogether();
      if (wantsStop) stopEatTogether();

      const wantsFinished = detectFinishedMeal(text);
      if (wantsFinished && (eatTogetherActiveRef.current || wantsStart)) {
        setEatTogetherMeal("finished");
      } else {
        const mealKey = detectMealKey(text);
        if (mealKey && (eatTogetherActiveRef.current || wantsStart)) {
          setEatTogetherMeal(mealKey);
        }
      }
    }

    const shouldAutoShare = Boolean(showStudyWindow && studyShareRef.current && isCurrentPageRequest(text));
    const sendToBackend = () => socket.emit('user_input', { text, attachments });
    if (shouldAutoShare) {
      try {
        studyShareRef.current();
      } catch {}
      setTimeout(sendToBackend, 250);
    } else {
      sendToBackend();
    }

  // Lokalne dodanie wiadomości użytkownika do UI (bo backend nie zawsze echo-uje usera)
  if (attachments.length > 0) {
    const names = attachments
      .map(a => a?.name)
      .filter(Boolean)
      .slice(0, 8)
      .join(', ');

    const attachLine = names
      ? `\n\n[Załączniki: ${names}${attachments.length > 8 ? ', …' : ''}]`
      : `\n\n[${t('chat.attachments')}: ${attachments.length}]`;

    addMessage(t('chat.you'), (text || `(${t('chat.sent_attachments')})`) + attachLine);
  } else {
    addMessage(t('chat.you'), text);
  }

  setInputValue('');
};

  const handleTogglePermission = (key) => {
    setToolPermissions(prev => {
      const keys = TOOL_PERMISSION_ALIASES[key] || [key];
      const value = !prev[key];
      const next = { ...prev };
      keys.forEach((aliasKey) => {
        next[aliasKey] = value;
      });
      socket.emit('update_settings', { tool_permissions: next });
      return next;
    });
  };

  const requestSkills = (opts = {}) => {
    if (!socket || !socket.connected) return;
    setSkillsLoading(true);
    socket.emit('list_skills', {
      include_ineligible: opts.includeIneligible ?? true,
      include_disabled: opts.includeDisabled ?? true,
    });
  };

  const handleRefreshSkills = () => {
    if (!socket || !socket.connected) return;
    setSkillsLoading(true);
    setSkillsActionBusy(true);
    socket.emit('refresh_skills', {
      include_ineligible: true,
      include_disabled: true,
    });
  };

  const _arrayBufferToBase64 = (buffer) => {
    const bytes = new Uint8Array(buffer);
    const chunkSize = 0x8000;
    let binary = '';
    for (let i = 0; i < bytes.length; i += chunkSize) {
      const chunk = bytes.subarray(i, i + chunkSize);
      binary += String.fromCharCode(...chunk);
    }
    return btoa(binary);
  };

  const handleSkillZipUpload = async (file) => {
    if (!file || !socket || !socket.connected) return;
    const lower = String(file.name || '').toLowerCase();
    if (!lower.endsWith('.zip')) {
      pushToast('Please drop a .zip file for skill install.', 'error');
      return;
    }
    try {
      const arr = await file.arrayBuffer();
      const zipB64 = _arrayBufferToBase64(arr);
      setSkillsActionBusy(true);
      socket.emit('install_skill_zip', {
        filename: file.name,
        zip_b64: zipB64,
        replace: true,
      });
    } catch (err) {
      console.error('Skill ZIP upload failed:', err);
      pushToast('Failed to read skill ZIP file.', 'error');
      setSkillsActionBusy(false);
    }
  };

  const handleInstallSkillSource = (payload = {}) => {
    if (!socket || !socket.connected) return;
    const source = String(payload?.source || '').trim();
    const skillName = String(payload?.skillName || '').trim();
    const agent = String(payload?.agent || 'codex').trim() || 'codex';
    if (!source) {
      pushToast('Skill source is required.', 'error');
      return;
    }
    setSkillsActionBusy(true);
    socket.emit('install_skill_source', {
      source,
      skill_name: skillName || null,
      agent,
      global_scope: !!payload?.globalScope,
      copy_files: payload?.copyFiles !== false,
      replace: true,
    });
  };

  const handleUninstallSkill = (name) => {
    if (!name || !socket || !socket.connected) return;
    if (!window.confirm(`Uninstall skill "${name}"?`)) return;
    setSkillsActionBusy(true);
    socket.emit('uninstall_skill', { name });
  };

  const handleConfirmClose = () => {
    // Intentionally fake: visual-only flow, no AI message and no real close.
  };

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const textContent = event.target.result;
        if (typeof textContent === 'string' && textContent.length > 0) {
          socket.emit('upload_memory', { memory: textContent });
          addMessage('System', t('system.reading_memory'));
        } else {
          addMessage('System', t('system.memory_empty'));
        }
      } catch (err) {
        console.error("Error reading file:", err);
        addMessage('System', t('system.memory_error'));
      }
    };
    reader.readAsText(file);
  };

  const activeConfirmationRequest = confirmationQueue.length ? confirmationQueue[0] : null;

  const handleConfirmTool = () => {
    if (activeConfirmationRequest) {
      socket.emit('confirm_tool', { id: activeConfirmationRequest.id, confirmed: true });
      setConfirmationQueue((prev) => prev.slice(1));
    }
  };

  const handleDenyTool = () => {
    if (activeConfirmationRequest) {
      socket.emit('confirm_tool', { id: activeConfirmationRequest.id, confirmed: false });
      setConfirmationQueue((prev) => prev.slice(1));
    }
  };

  const activeSessionPrompt = sessionPromptQueue.length ? sessionPromptQueue[0] : null;

  const sessionPromptPosition = useMemo(() => {
    const chatX = viewport.w / 2;
    const chatTop = Math.max(140, viewport.h - 380);
    const placeInside = chatTop < 220;
    return {
      x: chatX,
      y: chatTop,
      width: Math.min(760, Math.max(520, Math.round(viewport.w * 0.42))),
      placement: placeInside ? 'inside' : 'above',
      viewportH: viewport.h,
    };
  }, [viewport.w, viewport.h]);

  const PHONE_MONIKA_SCALE_MAX = 1.20;
  const characterShift = 0;
  const viewportAspect = viewport.w / Math.max(viewport.h, 1);
  const isCompactViewport = viewport.h < 1100;
  const stackedViewportFactor = Math.max(0, Math.min(1, (1.02 - viewportAspect) / 0.22));
  const groundedCharacterYBase = Math.max(145, Math.min(310, Math.round(viewport.h * 0.235)));
  const characterY = isPortrait ? groundedCharacterYBase - 50 : groundedCharacterYBase;

  const characterScale = useMemo(() => {
    const refW = 1920;
    const refH = 1080;
    const sizeFactor = Math.min(viewport.w / refW, viewport.h / refH);
    const t = Math.max(0, Math.min(1, (sizeFactor - 0.85) / 0.25));
    const baseScale = 1.05 + 0.15 * t;
    const groundedScale = 1 + (PHONE_MONIKA_SCALE_MAX - 1) * stackedViewportFactor;
    return baseScale * (isCompactViewport ? 0.9 : 1.0) * groundedScale * 1.5;
  }, [viewport.w, viewport.h, isCompactViewport, stackedViewportFactor]);
  const characterBottomOffset = 0;

  {
    return (
      <AudioVideoProvider
        isMuted={isMuted}
        toggleMute={toggleMute}
        isVideoOn={isVideoOn}
        toggleVideo={toggleVideo}
        visionMode={visionMode}
        toggleScreenCapture={toggleScreenCapture}
        isConnected={isConnected}
        togglePower={togglePower}
        onLogout={handleLogout}
        onMonikaTemporaryMood={handleMonikaTemporaryMood}
      >
      <>
        {isLockScreenVisible && (
          <AuthLock
            socket={socket}
            onAuthenticated={() => setIsAuthenticated(true)}
            onAnimationComplete={() => setIsLockScreenVisible(false)}
          />
        )}

        <ToastStack toasts={toasts} onDismiss={dismissToast} />

        <MonikaShell
          // Visualizer props
          audioData={aiAudioData}
          intensity={aiLevel}
          width={viewport.w}
          height={viewport.h}
          backgroundSrc={vnBackground}
          layers={masLayers}
          sprites={{
            idle: isConnected ? "/vn/ai_idle.png" : "/vn/ai_sleeping.png",
            listen: "/vn/ai_listen.png",
            talk: ["/vn/ai_talk_1.png", "/vn/ai_talk_2.png"],
          }}
          isAssistantSpeaking={aiSpeaking}
          isUserSpeaking={userSpeaking}
          characterScale={characterScale}
          characterY={characterY}
          characterX={characterShift}
          characterAnchorBottom={true}
          characterBottomOffset={characterBottomOffset}
          characterTransitionMs={0.35}
          headpatActive={headpatActive}
          petpetSrc="/petpet.gif"
          // Context + personality
          personalityState={personalityState}
          // Chat state (for panels)
          messages={messages}
          inputValue={inputValue}
          setInputValue={setInputValue}
          handleSend={handleSend}
          socket={socket}
          userSpeaking={userSpeaking}
          micAudioData={micAudioData}
          language={language}
          studyCatalog={studyCatalog}
          studySelection={studySelection}
          onSelectStudy={handleSelectStudy}
          onRefreshCatalog={fetchStudyCatalog}
          shareRef={studyShareRef}
          onShareStudyPage={() => studyShareRef.current && studyShareRef.current()}
          agenticLogs={browserData.logs}
          sessionActive={sessionMode.active}
          onToggleSession={toggleSessionMode}
          eatTogetherActive={eatTogetherActive}
          onStartEatTogether={startEatTogether}
          onStopEatTogether={stopEatTogether}
          onHeadpat={triggerHeadpat}
          onToggleMinecraft={() => setShowMinecraftWindow((v) => !v)}
          showMinecraftWindow={showMinecraftWindow}
          onOpenStudy={() => {
            if (!showStudyWindow) {
              setShowStudyWindow(true);
            }
          }}
          visionMode={visionMode}
          visionFrame={visionFrame}
          toggleScreenCapture={toggleScreenCapture}
          isVideoOn={isVideoOn}
          videoRef={videoRef}
          isCameraFlipped={isCameraFlipped}
          toggleVideo={toggleVideo}
        />

        {activeSessionPrompt && (
          <SessionPromptWindow
            prompt={activeSessionPrompt}
            position={sessionPromptPosition}
            onClose={popSessionPrompt}
            onSubmit={(payload) => {
              handleSessionPromptSubmit(payload);
              popSessionPrompt();
            }}
            onSketchSave={(payload) => {
              handleSessionSketchSave(payload);
              popSessionPrompt();
            }}
            zIndex={95}
          />
        )}

        <MinecraftConnectPopup
          socket={socket}
          isOpen={showMinecraftWindow}
          onClose={() => setShowMinecraftWindow(false)}
          onConnected={({ message }) => {
            if (message) pushToast(message, 'system', 3200);
          }}
        />

        {/* Settings Modal (overlay on top of MonikaShell) */}
        {showSettings && (
          <SettingsWindow
            socket={socket}
            micDevices={micDevices}
            speakerDevices={speakerDevices}
            webcamDevices={webcamDevices}
            selectedMicId={selectedMicId}
            setSelectedMicId={setSelectedMicId}
            selectedSpeakerId={selectedSpeakerId}
            setSelectedSpeakerId={setSelectedSpeakerId}
            selectedWebcamId={selectedWebcamId}
            setSelectedWebcamId={setSelectedWebcamId}
            isCameraFlipped={isCameraFlipped}
            setIsCameraFlipped={setIsCameraFlipped}
            toolPermissions={toolPermissions}
            onTogglePermission={handleTogglePermission}
            handleFileUpload={handleFileUpload}
            skills={skills}
            skillsLoading={skillsLoading}
            skillsActionBusy={skillsActionBusy}
            onRefreshSkills={handleRefreshSkills}
            onUploadSkillZip={handleSkillZipUpload}
            onInstallSkillSource={handleInstallSkillSource}
            onUninstallSkill={handleUninstallSkill}
            geminiModelPreset={geminiModelPreset}
            onModelPresetChange={(preset) => {
              setGeminiModelPreset(preset);
              socket.emit('update_settings', { gemini_model_preset: preset });
            }}
            geminiVoice={geminiVoice}
            onVoiceChange={(voice) => {
              setGeminiVoice(voice);
              socket.emit('update_settings', { gemini_voice: voice });
            }}
            onClose={() => setShowSettings(false)}
          />
        )}

        <ConfirmationPopup
          request={activeConfirmationRequest}
          onConfirm={handleConfirmTool}
          onDeny={handleDenyTool}
        />

        {/* Goodbye Popup - app close flow */}
        {showGoodbyePopup && (
          <GoodbyePopup
            initialGenderHint={personalityState?.player_gender || personalityState?.user_gender || personalityState?.gender || null}
            onConfirm={(genderText) => {
              setShowGoodbyePopup(false);
              handleConfirmClose(genderText);
            }}
            onCancel={() => {
              setShowGoodbyePopup(false);
            }}
          />
        )}
      </>
      </AudioVideoProvider>
    );
  }
}

function App() {
  return (
    <LanguageProvider>
      <MonikaContextProvider>
        <SettingsProvider>
          <LayoutProvider>
            <ModeProvider>
              <RealtimeProvider socket={socket}>
            <style>{`
              ::-webkit-scrollbar {
                width: 6px;
                height: 6px;
              }
              ::-webkit-scrollbar-track {
                background: transparent;
              }
              ::-webkit-scrollbar-thumb {
                background: rgba(255, 255, 255, 0.1);
                border-radius: 3px;
                transition: background 0.2s ease;
              }
              ::-webkit-scrollbar-thumb:hover {
                background: rgba(255, 255, 255, 0.4);
              }
              ::-webkit-scrollbar-corner {
                background: transparent;
              }
              * {
                scrollbar-width: thin;
                scrollbar-color: rgba(255, 255, 255, 0.1) transparent;
              }
            `}</style>

            <AppContent />
          </RealtimeProvider>
        </ModeProvider>
      </LayoutProvider>
        </SettingsProvider>
      </MonikaContextProvider>
    </LanguageProvider>
  );
}

export default App;
