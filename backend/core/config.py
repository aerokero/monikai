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

# Session data (conversation history)
SESSIONS_DIR = DATA_DIR / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

# Memory engine (full-text search index)
MEMORY_DIR = DATA_DIR / "memory"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

# Localization files
LOCALES_DIR = DATA_DIR / "locales"
LOCALES_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# File Paths
# ============================================================================

# Settings
SETTINGS_PATH = DATA_DIR / "settings.json"

# User profile and personality
PROFILE_PATH = USER_MEMORY_DIR / "profile.json"
PERSONALITY_PATH = USER_MEMORY_DIR / "personality.json"
CALENDAR_PATH = USER_MEMORY_DIR / "calendar.json"
REMINDERS_PATH = USER_MEMORY_DIR / "reminders.json"

# ============================================================================
# Database Paths
# ============================================================================

# Memory engine database (full-text search)
MEMORY_DB_PATH = MEMORY_DIR / "index" / "memory.db"
MEMORY_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# ============================================================================
# Workspace Directory (for generated outputs)
# ============================================================================

WORKSPACE_DIR = DATA_DIR / "workspace"
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
