# Frontend - React Documentation

Complete guide to MonikAI's React frontend.

## Overview

The frontend is built with React 18 + Vite, providing a real-time interface for conversing with Monika. It uses Socket.IO for WebSocket communication with the backend and Framer Motion for smooth animations.

## Technology Stack

- **React 18.2** - UI framework
- **Vite 7.3** - Build tool + dev server
- **Socket.IO Client 4.7** - WebSocket communication
- **Tailwind CSS 3.4** - Styling
- **Framer Motion 11.0** - Animations
- **MediaPipe Vision 0.10** - Computer vision (face/hands)
- **Lucide React 0.300** - Icon library

## Folder Structure

```
src/
├── App.jsx                   # Main entry point
├── index.css                 # Global styles
├── main.jsx                  # React root
│
├── components/              # React components
│   ├── ChatModule.jsx       # Conversation interface
│   ├── PersonalityWindow.jsx # Personality display
│   ├── ProgressionWindow.jsx # Metrics/quests/achievements
│   ├── MinecraftWindow.jsx  # Bot control
│   ├── StudyWindow.jsx      # OCR materials
│   ├── MemoryPrompt.jsx     # Journal interface
│   └── ...
│
├── contexts/                # Context providers
│   ├── RealtimeContext.jsx  # Socket.IO state
│   ├── ProgressionContext.jsx # Progression data
│   ├── MonikaContext.jsx    # Personality state
│   ├── AudioVideoContext.jsx # Media streams
│   ├── LanguageContext.jsx  # i18n
│   ├── SettingsContext.jsx  # User preferences
│   ├── LayoutContext.jsx    # UI layout
│   └── ModeContext.jsx      # Interaction mode
│
├── hooks/                   # Custom React hooks
│   ├── useSocket.js        # Socket.IO connection
│   ├── useAudio.js         # Audio capture/playback
│   ├── useProgression.js   # Progression data
│   └── ...
│
├── layout/                  # Layout components
│   ├── Shell.jsx           # Desktop layout
│   ├── MonikaShell.jsx     # Monika-focused layout
│   └── ...
│
├── styles/                  # CSS files
│   └── tailwind.css        # Tailwind imports
│
└── config/                  # Configuration
    ├── constants.js        # App constants
    └── ...
```

## Context Providers

### RealtimeContext
Manages Socket.IO connection and real-time events:
- Connection state
- Last received event
- Event history

### ProgressionContext
Fetches and caches progression data:
- Profile
- Metrics (4-axis)
- Quests & achievements
- Unlocks & content gates
- Notifications

### MonikaContext
Global personality state:
- Mood
- Affection
- Energy
- Comfort
- Synergy
- Intimacy
- Current sprite selection

### AudioVideoContext
Manages WebRTC streams:
- Microphone capture
- Speaker output
- Camera feed (optional)
- Voice activity detection (VAD)

### LanguageContext
Internationalization:
- Current language
- Translation strings
- Language switching

### SettingsContext
User preferences:
- Theme (light/dark)
- Volume settings
- Tool permissions
- Interaction preferences

## Component Hierarchy

```
App.jsx (connects Socket.IO)
├─ LanguageProvider
├─ SettingsProvider
├─ AudioVideoProvider
├─ RealtimeProvider (socket)
├─ ProgressionProvider (polls REST endpoints)
├─ MonikaContextProvider
├─ Layout (Shell or MonikaShell)
└─ Components
    ├─ ChatModule (conversation)
    ├─ PersonalityWindow (mood display)
    ├─ ProgressionWindow (metrics/quests/achievements)
    ├─ MinecraftWindow (bot control)
    ├─ StudyWindow (OCR materials)
    ├─ MemoryPrompt (journal)
    └─ ...etc
```

## Key Components

### ChatModule

```jsx
function ChatModule() {
  const { socket } = useContext(RealtimeContext);
  const { audioStream } = useContext(AudioVideoContext);
  
  const handleSendMessage = async (text) => {
    socket.emit('audio_input', audioChunks);
  }
  
  useEffect(() => {
    socket.on('text_output', (data) => {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.text
      }]);
    });
  }, [socket]);
  
  return (
    <div className="chat-container">
      <div className="messages">
        {messages.map(msg => (
          <div key={msg.id} className={`message ${msg.role}`}>
            {msg.content}
          </div>
        ))}
      </div>
      <input 
        type="text" 
        onSubmit={handleSendMessage}
        placeholder="Type or speak..."
      />
    </div>
  );
}
```

### PersonalityWindow

```jsx
function PersonalityWindow() {
  const { personality } = useContext(MonikaContext);
  
  const getSpriteClass = () => {
    if (personality.mood > 0.7 && personality.energy > 60) 
      return 'monika_happy';
    if (personality.mood < -0.5) 
      return 'monika_sad';
    if (personality.affection > 80) 
      return 'monika_intimate';
    return 'monika_neutral';
  }
  
  return (
    <div className={`personality-window ${getSpriteClass()}`}>
      <div className="stats">
        <StatBar label="Mood" value={personality.mood} />
        <StatBar label="Affection" value={personality.affection} />
        <StatBar label="Energy" value={personality.energy} />
      </div>
    </div>
  );
}
```

### ProgressionWindow

```jsx
function ProgressionWindow() {
  const { progression } = useContext(ProgressionContext);
  
  return (
    <Tabs>
      <Tab label="Quests">
        {progression.quests.map(quest => (
          <QuestCard key={quest.id} quest={quest} />
        ))}
      </Tab>
      <Tab label="Achievements">
        {progression.achievements.map(ach => (
          <AchievementCard key={ach.id} achievement={ach} />
        ))}
      </Tab>
      <Tab label="Metrics">
        <MetricsChart data={progression.metrics} />
      </Tab>
    </Tabs>
  );
}
```

## Socket.IO Event Handling

```jsx
useEffect(() => {
  if (!socket) return;
  
  // Listen for text output
  socket.on('text_output', (data) => {
    addMessage('assistant', data.text);
  });
  
  // Listen for audio chunks
  socket.on('audio_output', (data) => {
    playAudio(data.chunk);
  });
  
  // Listen for personality state changes
  socket.on('personality_state', (state) => {
    updatePersonality(state);
  });
  
  // Listen for notifications
  socket.on('notification', (notif) => {
    showNotification(notif);
  });
  
  // Cleanup
  return () => {
    socket.offAny();
  };
}, [socket]);
```

## Styling with Tailwind

All styling uses Tailwind CSS utility classes. Key theme:
- Dark background (zinc-900)
- Accent colors for personality states
- Smooth transitions
- Responsive grid layouts

Example:
```jsx
<div className="p-4 bg-zinc-900 rounded-lg border border-zinc-800 hover:border-cyan-500 transition-colors duration-200">
  Content
</div>
```

## State Management

### Local State
- Component-level state for UI elements
- Form inputs, toggles, temporary data

### Context State
- Global personality state
- Progression data
- Settings & preferences
- Socket.IO connection

### Server State
- User memory
- Session data
- Conversation history

## Performance Optimization

1. **Memoization**
   - `React.memo()` for expensive components
   - `useMemo()` for expensive calculations
   
2. **Lazy Loading**
   - `React.lazy()` for route-based code splitting
   - Image lazy loading
   
3. **Event Throttling**
   - Debounce socket event handlers
   - Rate-limit UI updates
   
4. **Animation Performance**
   - Framer Motion uses GPU-accelerated transforms
   - Prefer `transform` over `top/left` properties

## Development

### Running Dev Server

```bash
cd src
npm run dev  # Vite dev server on http://localhost:5173
```

### Building for Production

```bash
npm run build  # Creates optimized bundle
```

### Testing

```bash
npm test
```

---

**Next Read:** [Integrations](./Integrations.md) | [Progression System](./Progression-System.md)
