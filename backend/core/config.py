"""
Central configuration for MonikAI data directories and paths.
This is the single source of truth for all data paths.
"""
import os
from pathlib import Path

# ============================================================================
# Data Directory Configuration
# ============================================================================

# Get the base directory (backend/core/)
BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

# Main data directory (project_root/data/)
# All user data, catalogs, and runtime files go here
DATA_DIR = BASE_DIR.parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# Subdirectories
# ============================================================================

# User-specific data (personality, calendar, reminders, etc.)
USER_MEMORY_DIR = DATA_DIR / "user_memory"
USER_MEMORY_DIR.mkdir(parents=True, exist_ok=True)

# Long-term memory (snapshots and historical data)
LONG_TERM_MEMORY_DIR = DATA_DIR / "long_term_memory"
LONG_TERM_MEMORY_DIR.mkdir(parents=True, exist_ok=True)

# Session data (conversation history)
SESSIONS_DIR = DATA_DIR / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

# Memory engine (full-text search index)
MEMORY_DIR = DATA_DIR / "memory"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

# Knowledge graph database
KG_DIR = DATA_DIR / "kg"
KG_DIR.mkdir(parents=True, exist_ok=True)

# Catalogs (achievements, quests, unlocks, etc.)
ACHIEVEMENTS_DIR = DATA_DIR / "achievements"
ACHIEVEMENTS_DIR.mkdir(parents=True, exist_ok=True)

QUESTS_DIR = DATA_DIR / "quests"
QUESTS_DIR.mkdir(parents=True, exist_ok=True)

UNLOCKS_DIR = DATA_DIR / "unlocks"
UNLOCKS_DIR.mkdir(parents=True, exist_ok=True)

STORIES_DIR = DATA_DIR / "stories"
STORIES_DIR.mkdir(parents=True, exist_ok=True)

SEASONAL_EVENTS_DIR = DATA_DIR / "seasonal_events"
SEASONAL_EVENTS_DIR.mkdir(parents=True, exist_ok=True)

# Localization files
LOCALES_DIR = DATA_DIR / "locales"
LOCALES_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# File Paths
# ============================================================================

# Settings
SETTINGS_PATH = DATA_DIR / "settings.json"

# Catalogs
ACHIEVEMENTS_CATALOG_PATH = ACHIEVEMENTS_DIR / "achievements_catalog.json"
QUESTS_CATALOG_PATH = QUESTS_DIR / "quest_catalog.json"
UNLOCKS_CATALOG_PATH = UNLOCKS_DIR / "unlocks_catalog.json"
STORIES_CATALOG_PATH = STORIES_DIR / "stories_catalog.json"
SEASONAL_EVENTS_CATALOG_PATH = SEASONAL_EVENTS_DIR / "events_calendar.json"

# User profile and personality
PROFILE_PATH = USER_MEMORY_DIR / "profile.json"
PERSONALITY_PATH = USER_MEMORY_DIR / "personality.json"
CALENDAR_PATH = USER_MEMORY_DIR / "calendar.json"
REMINDERS_PATH = USER_MEMORY_DIR / "reminders.json"

# State files
ACHIEVEMENTS_STATE_PATH = USER_MEMORY_DIR / "achievements.json"
UNLOCKS_STATE_PATH = USER_MEMORY_DIR / "unlocks_state.json"
NARRATIVE_STATE_PATH = USER_MEMORY_DIR / "narrative_state.json"
METRICS_STATE_PATH = USER_MEMORY_DIR / "metrics_state.json"
SEASONAL_EVENTS_STATE_PATH = USER_MEMORY_DIR / "seasonal_events_state.json"
ACTIVITY_LOG_PATH = USER_MEMORY_DIR / "activity_log.json"

# Knowledge and memory
MAS_KNOWLEDGE_PATH = DATA_DIR / "mas_knowledge.json"
PERSONALITY_UNLOCKS_PATH = DATA_DIR / "personality_unlocks.json"

# ============================================================================
# Database Paths
# ============================================================================

# Memory engine database (full-text search)
MEMORY_DB_PATH = MEMORY_DIR / "index" / "memory.db"
MEMORY_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Knowledge graph database
KG_DB_PATH = KG_DIR / "kg.db"
KG_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# ============================================================================
# Workspace Directory (for generated outputs)
# ============================================================================

WORKSPACE_DIR = DATA_DIR / "workspace"
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
