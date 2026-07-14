"""Gemini function-calling tool declarations and the assembled tools list."""

from ..tools import tools_list

# ---------------------------------------------------------------------------
# Calendar tools
# ---------------------------------------------------------------------------
create_event_tool = {
    "name": "create_event",
    "description": (
        "Creates a new event in the calendar. For all-day and multi-day events, set all_day=true "
        "and use an exclusive end date: an event advertised as 2026-05-15 to 2026-05-17 must use "
        "start_iso='2026-05-15T00:00:00' and end_iso='2026-05-18T00:00:00'. "
        "For timed events, use exact start/end times."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "summary": {"type": "STRING", "description": "The title or summary of the event."},
            "start_iso": {"type": "STRING", "description": "The start time of the event in ISO 8601 format. For all-day events, use midnight on the first day."},
            "end_iso": {"type": "STRING", "description": "The exclusive end time in ISO 8601 format. For all-day events, use midnight on the day after the last included day."},
            "description": {"type": "STRING", "description": "An optional longer description for the event."},
            "all_day": {"type": "BOOLEAN", "description": "Set true for all-day or multi-day events such as conventions."},
        },
        "required": ["summary", "start_iso", "end_iso"],
    },
}

list_events_tool = {
    "name": "list_events",
    "description": "Lists events from the calendar within a specified time range.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "start_range_iso": {"type": "STRING", "description": "The start of the time range in ISO 8601 format."},
            "end_range_iso": {"type": "STRING", "description": "The end of the time range in ISO 8601 format."},
        },
        "required": ["start_range_iso", "end_range_iso"],
    },
}

delete_event_tool = {
    "name": "delete_event",
    "description": "Deletes an event from the calendar by its ID.",
    "parameters": {
        "type": "OBJECT",
        "properties": {"event_id": {"type": "STRING", "description": "The unique ID of the event to delete."}},
        "required": ["event_id"],
    },
}

# ---------------------------------------------------------------------------
# Time / Reminders
# ---------------------------------------------------------------------------
get_time_context_tool = {
    "name": "get_time_context",
    "description": "Returns the current local date/time and time zone. Uses settings.json time_settings: mode=system/manual.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

create_reminder_tool = {
    "name": "create_reminder",
    "description": "Creates a reminder/timer. Use exactly one: 'at' (YYYY-MM-DD HH:MM), 'in_minutes', or 'in_seconds'. Time is interpreted in local time zone (time_settings).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "message": {"type": "STRING", "description": "What to remind about."},
            "at": {"type": "STRING", "description": "When to remind (YYYY-MM-DD HH:MM)."},
            "in_minutes": {"type": "INTEGER", "description": "Remind in N minutes."},
            "in_seconds": {"type": "INTEGER", "description": "Remind in N seconds (useful for timers)."},
            "speak": {"type": "BOOLEAN", "description": "If true, the assistant will speak the reminder aloud.", "default": True},
            "alert": {"type": "BOOLEAN", "description": "If true, the UI can ring/show a notification when the reminder fires.", "default": True},
        },
        "required": ["message"],
    },
}

list_reminders_tool = {
    "name": "list_reminders",
    "description": "Lists scheduled reminders.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

cancel_reminder_tool = {
    "name": "cancel_reminder",
    "description": "Cancels a scheduled reminder by id.",
    "parameters": {
        "type": "OBJECT",
        "properties": {"id": {"type": "STRING", "description": "Reminder id."}},
        "required": ["id"],
    },
}

# ---------------------------------------------------------------------------
# Spotify
# ---------------------------------------------------------------------------
spotify_get_auth_url_tool = {
    "name": "spotify_get_auth_url",
    "description": "Returns Spotify OAuth authorization URL. User opens it once to grant access.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

spotify_get_status_tool = {
    "name": "spotify_get_status",
    "description": "Returns Spotify integration status (configured/connected/token state).",
    "parameters": {"type": "OBJECT", "properties": {}},
}

spotify_get_now_playing_tool = {
    "name": "spotify_get_now_playing",
    "description": "Returns currently playing track and playback state from Spotify.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

spotify_list_playlists_tool = {
    "name": "spotify_list_playlists",
    "description": "Lists user Spotify playlists.",
    "parameters": {
        "type": "OBJECT",
        "properties": {"limit": {"type": "INTEGER", "description": "Max playlists (1-50, default 20)."}},
    },
}

spotify_recently_played_tool = {
    "name": "spotify_recently_played",
    "description": "Returns recently played Spotify tracks.",
    "parameters": {
        "type": "OBJECT",
        "properties": {"limit": {"type": "INTEGER", "description": "Max items (1-50, default 20)."}},
    },
}

# ---------------------------------------------------------------------------
# Personality
# ---------------------------------------------------------------------------
update_personality_tool = {
    "name": "update_personality",
    "description": "Updates your internal emotional state and affection level. Use this when the user does something that affects your mood or bond (e.g. compliments, insults, spending time).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "affection_delta": {"type": "NUMBER", "description": "Change in affection (e.g. +0.5, -1.0)."},
            "mood": {"type": "STRING", "description": "New mood (e.g. 'happy', 'reflective')."},
            "energy": {"type": "NUMBER", "description": "New energy level (0.0-1.0)."},
        },
        "required": [],
    },
}

# ---------------------------------------------------------------------------
# Memory (work + long-term)
# ---------------------------------------------------------------------------
get_work_memory_tool = {
    "name": "get_work_memory",
    "description": "Returns the current WORK memory profile (what the assistant is currently tracking about the user) as markdown.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

update_work_memory_tool = {
    "name": "update_work_memory",
    "description": "Updates WORK memory with new or corrected user information. Use this proactively whenever the user reveals stable facts or preferences. No confirmation is required.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "set": {"type": "OBJECT", "description": "Key-value pairs to set/overwrite in the WORK profile."},
            "append_notes": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "Optional bullet notes to append to the WORK profile.",
            },
        },
        "required": [],
    },
}

commit_work_memory_tool = {
    "name": "commit_work_memory",
    "description": "Commits a snapshot of the current WORK memory into LONG-TERM memory. Use automatically when enough stable information has accumulated. No confirmation is required.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "label": {"type": "STRING", "description": "Optional label for the snapshot (e.g. 'auto', 'user_profile_update')."},
        },
        "required": [],
    },
}

clear_work_memory_tool = {
    "name": "clear_work_memory",
    "description": "Clears WORK memory (does not delete long-term snapshots). Use only when explicitly requested by the user.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

memory_add_entry_tool = {
    "name": "memory_add_entry",
    "description": "Adds a structured memory entry (fact, preference, event, journal, reflection, roleplay, etc.) to global memory.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "type": {"type": "STRING", "description": "Entry type: 'semantic' (durable fact/preference about the user or world), 'episodic' (a specific event worth remembering), 'stm' (session-scoped note, relevant only today). Legacy aliases (fact, preference, event, reflection, roleplay_scene, roleplay_insight, memory_note) still accepted."},
            "content": {"type": "STRING", "description": "One short, self-contained sentence in third person. Distilled — never a raw transcript fragment."},
            "tags": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Optional tags."},
            "entities": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Related entities (e.g., user, monika)."},
            "origin": {"type": "STRING", "description": "real or roleplay."},
            "confidence": {"type": "NUMBER", "description": "Confidence 0-1."},
            "stability": {"type": "STRING", "description": "low, medium, high."},
            "source": {"type": "OBJECT", "description": "Optional source metadata (session_id, turn_id)."},
            "data": {"type": "OBJECT", "description": "Optional structured data."},
        },
        "required": ["type", "content"],
    },
}

memory_search_tool = {
    "name": "memory_search",
    "description": "Searches global memory (FTS) and returns the most relevant entries.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "Search query."},
            "types": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Filter by types."},
            "tags": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Filter by tags."},
            "limit": {"type": "INTEGER", "description": "Max results (default 5)."},
        },
        "required": ["query"],
    },
}

memory_get_page_tool = {
    "name": "memory_get_page",
    "description": "Reads a memory markdown page (global).",
    "parameters": {
        "type": "OBJECT",
        "properties": {"path": {"type": "STRING", "description": "Page path relative to memory/pages or absolute."}},
        "required": ["path"],
    },
}

memory_create_page_tool = {
    "name": "memory_create_page",
    "description": "Creates a memory page (topic, roleplay, journal, etc.) and returns the path.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING", "description": "Page title."},
            "folder": {"type": "STRING", "description": "Folder under memory/pages (e.g., topics, roleplay, journal)."},
            "tags": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Optional tags."},
        },
        "required": ["title"],
    },
}

memory_append_page_tool = {
    "name": "memory_append_page",
    "description": "Appends content to a memory page (global).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "path": {"type": "STRING", "description": "Page path relative to memory/pages or absolute."},
            "content": {"type": "STRING", "description": "Content to append."},
        },
        "required": ["path", "content"],
    },
}

# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------
journal_add_entry_tool = {
    "name": "journal_add_entry",
    "description": "Adds a journal entry to the global journal (also indexed in memory).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "content": {"type": "STRING", "description": "Journal entry text."},
            "topics": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Optional topics."},
            "mood": {"type": "STRING", "description": "Optional mood."},
            "session_id": {"type": "STRING", "description": "Optional session id."},
            "tags": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Optional tags."},
        },
        "required": ["content"],
    },
}

journal_finalize_session_tool = {
    "name": "journal_finalize_session",
    "description": "Finalizes a session with a summary and reflections (writes summary.md and stores reflection entry).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "summary": {"type": "STRING", "description": "Session summary."},
            "reflections": {"type": "STRING", "description": "Optional reflections."},
            "session_id": {"type": "STRING", "description": "Optional session id."},
        },
        "required": ["summary"],
    },
}

# ---------------------------------------------------------------------------
# Session prompt
# ---------------------------------------------------------------------------
session_prompt_tool = {
    "name": "session_prompt",
    "description": "Shows a session prompt window (exercise/question/sketch) to the user during an active session.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "kind": {"type": "STRING", "description": "exercise | question | sketch | info"},
            "title": {"type": "STRING", "description": "Title for the prompt."},
            "text": {"type": "STRING", "description": "Instruction or question text."},
            "exercise_id": {"type": "STRING", "description": "Optional id for exercise tracking."},
            "fields": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "key": {"type": "STRING"},
                        "label": {"type": "STRING"},
                        "type": {"type": "STRING", "description": "text | textarea | scale | select"},
                        "placeholder": {"type": "STRING"},
                        "min": {"type": "NUMBER"},
                        "max": {"type": "NUMBER"},
                        "options": {"type": "ARRAY", "items": {"type": "STRING"}},
                    },
                },
            },
            "notes_enabled": {"type": "BOOLEAN", "description": "Whether to show a notes field."},
            "sketch_label": {"type": "STRING", "description": "Label for sketch, if kind=sketch."},
        },
        "required": ["kind", "title"],
    },
}

# ---------------------------------------------------------------------------
# Web / OpenClaw agents
# ---------------------------------------------------------------------------
run_web_agent = {
    "name": "run_web_agent",
    "description": "Runs Monika OpenClaw fork web agent (browser automation) for the given task.",
    "parameters": {
        "type": "OBJECT",
        "properties": {"prompt": {"type": "STRING", "description": "The detailed instructions for the web browser agent."}},
        "required": ["prompt"],
    },
}

run_openclaw_agent = {
    "name": "run_openclaw_agent",
    "description": "Runs Monika OpenClaw fork for a multi-step browser task (e.g., checking Gmail with user guidance).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "prompt": {"type": "STRING", "description": "Task instructions for OpenClaw agent."},
            "agent": {"type": "STRING", "description": "Optional compatibility field (ignored by local fork)."},
            "thinking": {"type": "STRING", "description": "Optional compatibility field (ignored by local fork)."},
            "timeout_sec": {"type": "INTEGER", "description": "Optional compatibility field (ignored by local fork)."},
        },
        "required": ["prompt"],
    },
}

manage_agent_job_tool = {
    "name": "manage_agent_job",
    "description": "Manages long-running agent jobs (start/status/stop/resume/list).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "One of: start, status, stop, resume, list"},
            "job_id": {"type": "STRING", "description": "Optional target job id for status/stop/resume."},
            "prompt": {"type": "STRING", "description": "Prompt when action=start."},
            "provider": {"type": "STRING", "description": "Optional provider alias (all aliases map to local openclaw fork)."},
            "agent": {"type": "STRING", "description": "Optional compatibility field for start (ignored)."},
            "thinking": {"type": "STRING", "description": "Optional compatibility field for start (ignored)."},
            "timeout_sec": {"type": "INTEGER", "description": "Optional compatibility field for start (ignored)."},
        },
        "required": ["action"],
    },
}

# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------
list_openclaw_skills_tool = {
    "name": "list_openclaw_skills",
    "description": "Lists installed skills (skills.sh-compatible) available on this machine.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "include_ineligible": {"type": "BOOLEAN", "description": "If true, also include skills that are missing dependencies for this environment."},
            "include_disabled": {"type": "BOOLEAN", "description": "If true, include skills marked as disableModelInvocation."},
        },
    },
}

list_skills_tool = {"name": "list_skills", "description": "Lists installed skills (skills.sh-compatible) available on this machine.", "parameters": list_openclaw_skills_tool["parameters"]}

get_openclaw_skill_tool = {
    "name": "get_openclaw_skill",
    "description": "Reads a specific installed skill instruction (SKILL.md content).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "name": {"type": "STRING", "description": "Skill name from list_skills."},
            "max_chars": {"type": "INTEGER", "description": "Optional max characters (default 12000)."},
        },
        "required": ["name"],
    },
}

get_skill_tool = {"name": "get_skill", "description": "Reads a specific installed skill instruction (SKILL.md content).", "parameters": get_openclaw_skill_tool["parameters"]}

refresh_openclaw_skills_tool = {"name": "refresh_openclaw_skills", "description": "Rescans installed skill directories after installing/removing skills.", "parameters": {"type": "OBJECT", "properties": {}}}

refresh_skills_tool = {"name": "refresh_skills", "description": "Rescans installed skill directories after installing/removing skills.", "parameters": refresh_openclaw_skills_tool["parameters"]}

run_openclaw_skill_command_tool = {
    "name": "run_openclaw_skill_command",
    "description": "Runs a command for an installed skill (e.g., gog CLI).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "skill_name": {"type": "STRING", "description": "Installed skill name (e.g., 'gog')."},
            "command": {"type": "STRING", "description": "Full CLI command to run (must start with allowed skill binary)."},
            "timeout_sec": {"type": "INTEGER", "description": "Optional timeout in seconds (default 120, max 600)."},
            "max_output_chars": {"type": "INTEGER", "description": "Optional max returned output chars (default 8000)."},
        },
        "required": ["skill_name", "command"],
    },
}

run_skill_command_tool = {"name": "run_skill_command", "description": "Runs a command for an installed skill (e.g., gog CLI).", "parameters": run_openclaw_skill_command_tool["parameters"]}

# ---------------------------------------------------------------------------
# Smart home
# ---------------------------------------------------------------------------
list_smart_devices_tool = {
    "name": "list_smart_devices",
    "description": "Lists all available smart home devices (lights, plugs, etc.) on the network.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

control_light_tool = {
    "name": "control_light",
    "description": "Controls a smart light device.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "target": {"type": "STRING", "description": "The IP address of the device to control. Always prefer the IP address over the alias for reliability."},
            "action": {"type": "STRING", "description": "The action to perform: 'turn_on', 'turn_off', or 'set'."},
            "brightness": {"type": "INTEGER", "description": "Optional brightness level (0-100)."},
            "color": {"type": "STRING", "description": "Optional color name (e.g., 'red', 'cool white') or 'warm'."},
        },
        "required": ["target", "action"],
    },
}

# ---------------------------------------------------------------------------
# Knowledge / misc
# ---------------------------------------------------------------------------
get_random_fact_tool = {"name": "get_random_fact", "description": "Gets a random fact from Monika's knowledge base to enrich conversations.", "parameters": {"type": "OBJECT", "properties": {}}}
get_random_greeting_tool = {"name": "get_random_greeting", "description": "Gets a random greeting from Monika's personality database.", "parameters": {"type": "OBJECT", "properties": {}}}
get_random_farewell_tool = {"name": "get_random_farewell", "description": "Gets a random farewell from Monika's personality database.", "parameters": {"type": "OBJECT", "properties": {}}}
get_random_topic_tool = {"name": "get_random_topic", "description": "Gets a random conversation topic from Monika's knowledge.", "parameters": {"type": "OBJECT", "properties": {}}}

get_weather_tool = {"name": "get_weather", "description": "Gets the current weather information for the user's location.", "parameters": {"type": "OBJECT", "properties": {}}}

get_world_snapshot_tool = {
    "name": "get_world_snapshot",
    "description": "Returns a fresh snapshot of the world around you right now: time of day, weather, how long since the last conversation, what's playing on Spotify, whether you can see the user's screen/camera. Use when you want to re-orient yourself mid-conversation.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

request_program_shutdown_tool = {
    "name": "request_program_shutdown",
    "description": (
        "Closes the MonikAI program after the assistant says goodbye. Use only after the user has clearly "
        "confirmed they want the program closed."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "reason": {"type": "STRING", "description": "Short reason for shutdown, e.g. 'user is going to sleep'."},
        },
    },
}

# ---------------------------------------------------------------------------
# Assemble tools list
# ---------------------------------------------------------------------------
_RESERVED_TOOL_NAMES = {
    "run_web_agent", "run_openclaw_agent", "manage_agent_job",
    "list_openclaw_skills", "get_openclaw_skill", "refresh_openclaw_skills", "run_openclaw_skill_command",
    "list_skills", "get_skill", "refresh_skills", "run_skill_command",
    "list_smart_devices", "control_light", "get_print_status",
    "get_time_context", "create_event", "list_events", "delete_event",
    "create_reminder", "list_reminders", "cancel_reminder",
    "spotify_get_auth_url", "spotify_get_status", "spotify_get_now_playing",
    "spotify_list_playlists", "spotify_recently_played",
    "get_work_memory", "update_personality", "update_work_memory",
    "commit_work_memory", "clear_work_memory",
    "get_weather", "request_program_shutdown",
}

_extra_decls: list = []
try:
    if tools_list and isinstance(tools_list, list):
        base = tools_list[0] if tools_list else {}
        decls = base.get("function_declarations") or []
        for _d in decls:
            if isinstance(_d, dict) and _d.get("name") and _d["name"] not in _RESERVED_TOOL_NAMES:
                _extra_decls.append(_d)
except Exception:
    _extra_decls = []

tools = [
    {
        "function_declarations": [
            run_web_agent,
            run_openclaw_agent,
            manage_agent_job_tool,
            list_openclaw_skills_tool,
            list_skills_tool,
            get_openclaw_skill_tool,
            get_skill_tool,
            refresh_openclaw_skills_tool,
            refresh_skills_tool,
            run_openclaw_skill_command_tool,
            run_skill_command_tool,
            list_smart_devices_tool,
            control_light_tool,
            get_time_context_tool,
            create_reminder_tool,
            list_reminders_tool,
            cancel_reminder_tool,
            spotify_get_auth_url_tool,
            spotify_get_status_tool,
            spotify_get_now_playing_tool,
            spotify_list_playlists_tool,
            spotify_recently_played_tool,
            get_work_memory_tool,
            update_personality_tool,
            update_work_memory_tool,
            commit_work_memory_tool,
            clear_work_memory_tool,
            memory_add_entry_tool,
            memory_search_tool,
            memory_get_page_tool,
            memory_create_page_tool,
            memory_append_page_tool,
            journal_add_entry_tool,
            journal_finalize_session_tool,
            session_prompt_tool,
            get_random_fact_tool,
            get_random_greeting_tool,
            get_random_farewell_tool,
            get_random_topic_tool,
            get_weather_tool,
            get_world_snapshot_tool,
            request_program_shutdown_tool,
        ]
        + _extra_decls
        + [create_event_tool, list_events_tool, delete_event_tool]
    },
    {"google_search": {}},
]
