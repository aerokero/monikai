# Frontend Progression System Implementation

## 🎨 Components Created

### 1. **ProgressionContext.jsx** - Data Management Layer
Location: `src/contexts/ProgressionContext.jsx`

Provides React context for managing all progression system data:
- **useProgression()** hook for accessing progression state
- **ProgressionProvider** component wraps the app
- Auto-fetches data every 10 seconds
- Manual refresh available

**Exported Data:**
```javascript
{
  profile,                    // User profile data
  metrics,                    // 4-axis metrics + progress
  quests,                     // Array of daily quests
  achievements,               // { unlocked: [], locked: [] }
  unlocks,                    // Array of active unlocks
  notifications,              // Pending system notifications
  isLoading,                  // Loading state
  error,                      // Error messages
  fetchAll(),                 // Manual refresh all data
  fetchProfile(),             // Individual fetchers...
  fetchMetrics(),
  fetchQuests(),
  fetchAchievements(),
  fetchUnlocks(),
  fetchNotifications()
}
```

**API Endpoints Used:**
- `GET /api/progression/profile`
- `GET /api/progression/metrics`
- `GET /api/progression/quests/today`
- `GET /api/progression/achievements`
- `GET /api/progression/unlocks`
- `GET /api/progression/notifications`


### 2. **MetricsPanel.jsx** - Relationship Metrics Display
Location: `src/components/MetricsPanel.jsx`

Displays 4-axis relationship progression:
- **Affection** (czułość) - Pink gradient
- **Comfort** (zaufanie) - Blue gradient
- **Synergy** (harmonia) - Purple gradient
- **Intimacy** (bliskość) - Orange gradient

**Features:**
- Progress bars with next threshold indicators
- Percentage to unlock display
- Streak counter (consecutive days)
- Total XP counter

**Visual Elements:**
- Icons from Lucide: Heart, Shield, Sparkles, Flame
- Tailwind CSS animations
- Polish language labels


### 3. **QuestsPanel.jsx** - Daily Routine Tracking
Location: `src/components/QuestsPanel.jsx`

Organizes quests by time slots:
- **Morning** (6-12) ☀️
- **Afternoon** (12-18) ⚡
- **Evening** (18-23) 🌙

**Features:**
- Quest status indicators (active/completed)
- Individual progress bars per quest
- XP reward display
- Quest count per slot
- Completion tracking

**Quest Card Display:**
- Title + Description
- Progress indicator
- Reward XP
- Time slot icon
- Completion status


### 4. **AchievementsPanel.jsx** - Achievement Tracking
Location: `src/components/AchievementsPanel.jsx`

Displays achievement system with filtering:
- **Unlocked Achievements** (with date)
- **Locked Achievements** (with preview)

**Features:**
- Rarity-based coloring (common/uncommon/rare/epic/legendary)
- Statistics dashboard (total/unlocked/locked)
- Achievement cards with unlock dates
- "More achievements" indicator when > 6 locked

**Rarity Color System:**
- Common: Blue
- Uncommon: Green
- Rare: Purple
- Epic: Pink
- Legendary: Yellow


### 5. **ProgressionWindow.jsx** - Main Dashboard
Location: `src/components/ProgressionWindow.jsx`

Tabbed window combining all progression data:
- **Metryki (Metrics)** tab - RelationshipMetrics display
- **Zadania (Quests)** tab - Daily routine
- **Osiągnięcia (Achievements)** tab - Achievement tree

**Features:**
- Tab navigation with icons
- Notification badge (if new progress events)
- Auto-refresh indicator
- Manual refresh button
- Close button
- Modal backdrop

**Window Styling:**
- Rounded corners (2xl)
- Gradient background (black/80)
- Border with white/10 transparency
- Shadow effects
- Scrollable content (max 90vh)


## 📱 App Integration

### Files Modified:
1. **App.jsx**
   - Added `showProgressionWindow` state
   - Added ProgressionProvider wrapper
   - Imported ProgressionWindow component
   - Added progression window rendering
   - Passed toggle functions to ToolsModule

2. **ToolsModule.jsx**
   - Added TrendingUp icon import
   - Added `onToggleProgression` prop
   - Added `showProgressionWindow` prop
   - Added progression button (between Goals and Daily Briefing)
   - Button shows TrendingUp icon

### Data Flow:
```
App.jsx (shows/hides ProgressionWindow)
  ↓
ProgressionProvider (fetches & caches d)
  ↓
MetricsPanel / QuestsPanel / AchievementsPanel
  ↓
API calls to /api/progression/*
  ↓
Backend progression system
```


## 🎮 Usage

### Opening Progression Window:
1. Click the **TrendingUp** icon in ToolsModule
2. Or use button: `onToggleProgression()` handler

### Viewing Progression Data:
1. **Metrics Tab**: See 4-axis relationship progress
2. **Quests Tab**: See today's routine quests by time slot
3. **Achievements Tab**: See unlocked and locked achievements

### Auto-Refresh:
- Data fetches automatically every 10 seconds
- Manual refresh available via button

### Notifications:
- Shows badge if new progression events occurred
- Click refresh to load new notifications


## 🔧 Technical Details

### Component Tree:
```
App
├─ ProgressionProvider (context)
│  ├─ AppContent
│  │  ├─ ToolsModule
│  │  │  └─ Button (progression)
│  │  └─ ProgressionWindow
│  │     ├─ MetricsPanel (useProgression)
│  │     ├─ QuestsPanel (useProgression)
│  │     └─ AchievementsPanel (useProgression)
```

### State Management:
- **ProgressionContext** manages all progression data
- Each panel uses `useProgression()` hook
- Auto-fetches every 10s with `useEffect`
- Manual fetch available for immediate updates

### Styling:
- **Tailwind CSS** for all styling
- **Lucide React** for icons
- **Dark theme** with white/transparency overlays
- Gradients for visual hierarchy
- Animations for smooth transitions (duration-500, transition-all)


## 🌍 Internationalization (i18n)

### Polish Language Support:
- `useLanguage()` hook integrated
- Translation keys:
  - `tools.progression` (button title)
  - Tab labels in Polish

### Adding New Languages:
Edit language context to add translations for:
- Tab names
- Button labels
- Metric names
- Achievement rarities


## 🚀 Future Enhancements

### Phase 7 (Frontend Extensions):
1. **Achievement Timeline** - Visual progression tree
2. **Story Viewer** - Display story sequences with choices
3. **Unlock Cascade** - Show prerequisite chains
4. **Seasonal Events** - Calendar display with event info
5. **Notifications Panel** - Full notification history
6. **Onboarding Flow** - Interactive 6-step profile creation
7. **Activity Log** - Historical activity tracking
8. **Profile Editor** - Edit user preferences in real-time

### Potential Components:
- AchievementTree.jsx (dag visualization)
- StorySequenceViewer.jsx (narrative display)
- OnboardingFlow.jsx (multi-step form)
- ActivityTimeline.jsx (historical view)
- UnlockCascade.jsx (prerequisite graph)
- NotificationsHistory.jsx (full notification log)


## 📋 Implementation Checklist

Frontend Components:
- [x] ProgressionContext.jsx - Data layer
- [x] MetricsPanel.jsx - Metrics display
- [x] QuestsPanel.jsx - Quests display
- [x] AchievementsPanel.jsx - Achievements display
- [x] ProgressionWindow.jsx - Main dashboard
- [x] App.jsx integration - Window state + rendering
- [x] ToolsModule.jsx integration - Button + toggle
- [x] Build verification - No errors

Next Steps:
- [ ] Test with real backend data
- [ ] Add more detailed achievement info
- [ ] Create story sequence viewer
- [ ] Build achievement tree visualization
- [ ] Implement onboarding flow
- [ ] Add seasonal event calendar


## 🎯 Testing Recommendations

### Manual Testing:
1. Open ProgressionWindow and verify all tabs appear
2. Check data loads from backend (check Network tab)
3. Verify auto-refresh happens every 10s
4. Click refresh button and verify immediate update
5. Test quest slot filtering (morning/afternoon/evening)
6. Check achievement rarity colors display correctly
7. Verify metrics progress bars update

### Edge Cases:
- No profile loaded initially
- No quests available
- No achievements unlocked
- Network latency (data loading)
- Empty sections (showed as "Brak danych")

### Browser DevTools:
- Check Console for errors
- Verify API calls in Network tab
- Check React components in DevTools
- Profile performance with Profiler


## 🔗 API Documentation

All endpoints return JSON data and are called from ProgressionContext.

### GET /api/progression/profile
Returns user profile object

### GET /api/progression/metrics
Returns metrics object with thresholds

### GET /api/progression/quests/today
Returns array of today's quests

### GET /api/progression/achievements
Returns {unlocked: [], locked: []}

### GET /api/progression/unlocks
Returns {active_unlocks: [...]}

### GET /api/progression/notifications
Returns {notifications: [...]}


## 📝 Notes

- All components use React hooks (useState, useEffect, useContext, useMemo)
- Lucide icons provide consistent iconography
- Tailwind CSS ensures responsive design
- Polish language labels match game aesthetic
- Components are fully isolated and reusable
- No external dependencies beyond React, Tailwind, Lucide
- Auto-refresh prevents manual polling overhead
- Error handling gracefully displays messages
