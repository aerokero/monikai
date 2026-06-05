"""v2 Progression HTTP Router - SQLite and V2 state integration."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from backend.core.runtimes import v2_runtime
from backend.services.user_profile import UserProfileManager
from backend.core.config import UNLOCKS_CATALOG_PATH, UNLOCKS_STATE_PATH
from backend.progression import state as progression_state
from backend.progression.catalog import load_goals, load_rituals, load_discoveries


def get_db_path() -> Path:
    runtime = v2_runtime.get()
    if runtime and hasattr(runtime, "_db_path"):
        return runtime._db_path
    # Fallback to default
    return Path(__file__).parent.parent.parent / "data" / "monika.db"


def register_progression_http_routes(app, *, get_main_loop):
    @app.get("/api/progression/profile")
    async def get_progression_profile():
        """Get user profile from progression system"""
        try:
            manager = UserProfileManager()
            profile = manager.get_profile()
            if not profile:
                return {"error": "No profile loaded"}
            return profile.to_dict()
        except Exception as e:
            return {"error": str(e)}

    @app.post("/api/progression/profile")
    async def update_progression_profile(data: dict):
        """Update user profile"""
        try:
            manager = UserProfileManager()
            profile = manager.get_profile()
            if not profile:
                return {"error": "No profile loaded"}

            # Update allowed fields
            allowed_fields = ["interests", "preferred_activities", "communication_style"]
            for field in allowed_fields:
                if field in data:
                    setattr(profile, field, data[field])

            manager.save_profile(profile)
            return profile.to_dict()
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/progression/metrics")
    async def get_progression_metrics():
        """Get relationship metrics from v2 SQLite state & SoulState"""
        try:
            db_path = get_db_path()
            bond_state = await progression_state.get_bond_state(db_path)
            closeness = bond_state.get("closeness", 0.0)
            streak_days = bond_state.get("streak_days", 0)
            last_interaction = bond_state.get("last_interaction_day", "")

            # Default needs/affect values if runtime isn't active
            autonomy = 0.7
            competence = 0.7
            relatedness = 0.7

            runtime = v2_runtime.get()
            if runtime:
                soul = runtime.soul_state
                if soul:
                    autonomy = soul.needs.autonomy
                    competence = soul.needs.competence
                    relatedness = soul.needs.relatedness

            metrics = [
                {
                    "metric": "affection",
                    "value": closeness,
                    "xp": closeness,
                    "streak_days": streak_days,
                    "last_interaction": last_interaction,
                    "total_xp_earned": {}
                },
                {
                    "metric": "comfort",
                    "value": relatedness * 100.0,
                    "xp": relatedness * 100.0,
                    "streak_days": streak_days,
                    "last_interaction": last_interaction,
                    "total_xp_earned": {}
                },
                {
                    "metric": "synergy",
                    "value": competence * 100.0,
                    "xp": competence * 100.0,
                    "streak_days": streak_days,
                    "last_interaction": last_interaction,
                    "total_xp_earned": {}
                },
                {
                    "metric": "intimacy",
                    "value": autonomy * 100.0,
                    "xp": autonomy * 100.0,
                    "streak_days": streak_days,
                    "last_interaction": last_interaction,
                    "total_xp_earned": {}
                }
            ]

            progress = {
                "affection": [],
                "comfort": [],
                "synergy": [],
                "intimacy": []
            }

            return {"metrics": metrics, "progress": progress}
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/progression/quests/today")
    async def get_progression_quests_today():
        """Get today's quests mapped from active rituals and goals"""
        try:
            db_path = get_db_path()
            goals_catalog = {g.id: g for g in load_goals()}
            rituals_catalog = {r.id: r for r in load_rituals()}

            active_goals = await progression_state.get_active_goals(db_path)
            active_rituals = await progression_state.get_active_rituals(db_path)

            quests = []

            # Map rituals
            for r in active_rituals:
                r_id = r.get("id")
                completed = r.get("completed_today", False)
                catalog_item = rituals_catalog.get(r_id)

                title = catalog_item.title if hasattr(catalog_item, "title") else (catalog_item.kind if catalog_item else r_id)
                description = catalog_item.description if catalog_item else ""
                kind = catalog_item.kind if catalog_item else "ritual"

                # Determine slot
                slot = "afternoon"
                lower_kind = kind.lower()
                if "morning" in lower_kind or "morning" in r_id.lower():
                    slot = "morning"
                elif "evening" in lower_kind or "night" in lower_kind or "evening" in r_id.lower() or "night" in r_id.lower():
                    slot = "evening"

                quests.append({
                    "id": r_id,
                    "template_id": r_id,
                    "title": title,
                    "description": description,
                    "type": "ritual",
                    "status": "completed" if completed else "active",
                    "progress": 1 if completed else 0,
                    "target": 1,
                    "reward_metric": "affection",
                    "reward_xp": 15,
                    "created_at": datetime.now().isoformat(),
                    "completed_at": datetime.now().isoformat() if completed else None,
                    "expires_at": None,
                    "required_bond_level": 0,
                    "slot": slot
                })

            # Map goals
            for g in active_goals:
                g_id = g.get("id")
                progress = g.get("progress", 0.0)
                completed = progress >= 1.0
                catalog_item = goals_catalog.get(g_id)

                title = catalog_item.title if catalog_item else g_id
                description = catalog_item.description if catalog_item else ""
                kind = catalog_item.kind if catalog_item else "shared"

                quests.append({
                    "id": g_id,
                    "template_id": g_id,
                    "title": title,
                    "description": description,
                    "type": "goal",
                    "status": "completed" if completed else "active",
                    "progress": progress,
                    "target": 1.0,
                    "reward_metric": "synergy" if kind == "shared" else ("comfort" if kind == "yours" else "intimacy"),
                    "reward_xp": 30,
                    "created_at": datetime.now().isoformat(),
                    "completed_at": datetime.now().isoformat() if completed else None,
                    "expires_at": None,
                    "required_bond_level": 0,
                    "slot": "afternoon"
                })

            return {"quests": quests, "total": len(quests)}
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/progression/achievements")
    async def get_progression_achievements():
        """Get achievements from v2 discoveries catalog and unlocked SQLite discoveries"""
        try:
            db_path = get_db_path()
            discoveries_catalog = load_discoveries()
            unlocked_ids = set(await progression_state.get_unlocked_discoveries(db_path))

            unlocked_list = []
            locked_list = []

            for entry in discoveries_catalog:
                ach = {
                    "id": entry.id,
                    "title": entry.title,
                    "description": entry.description,
                    "icon": "🏆",
                    "rarity": "common",
                    "hidden": entry.hidden,
                    "type": "event",
                    "unlocked_at": datetime.now().isoformat() if entry.id in unlocked_ids else None,
                    "condition": None,
                    "progress": {}
                }
                if entry.id in unlocked_ids:
                    unlocked_list.append(ach)
                else:
                    locked_list.append(ach)

            return {
                "unlocked": unlocked_list,
                "locked": locked_list,
                "progress": {}
            }
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/progression/unlocks")
    async def get_progression_unlocks():
        """Get unlocks status, linking SQLite achievements to unlocks catalog"""
        try:
            db_path = get_db_path()
            catalog = {"unlocks": []}
            if UNLOCKS_CATALOG_PATH.exists():
                try:
                    with open(UNLOCKS_CATALOG_PATH, "r", encoding="utf-8") as f:
                        catalog = json.load(f)
                except Exception:
                    pass

            active_ids = set()
            story_flags = {}
            if UNLOCKS_STATE_PATH.exists():
                try:
                    with open(UNLOCKS_STATE_PATH, "r", encoding="utf-8") as f:
                        state_data = json.load(f)
                        active_ids = set(state_data.get("active_unlocks", []))
                        story_flags = state_data.get("story_flags", {})
                except Exception:
                    pass

            # Auto-unlock if achievement requirements are met in SQLite
            unlocked_achievements = set(await progression_state.get_unlocked_discoveries(db_path))

            unlocks = catalog.get("unlocks", [])
            newly_unlocked = False

            for u in unlocks:
                u_id = u["id"]
                if u_id in active_ids:
                    continue

                # Check requirements
                requires = u.get("requires", [])
                all_met = True
                for req in requires:
                    if req.get("type") == "achievement":
                        req_id = req.get("id")
                        if req_id not in unlocked_achievements:
                            all_met = False
                            break
                    elif req.get("type") == "flag":
                        flag_name = req.get("name")
                        if not story_flags.get(flag_name, False):
                            all_met = False
                            break

                if all_met and requires:
                    active_ids.add(u_id)
                    newly_unlocked = True

            if newly_unlocked:
                try:
                    UNLOCKS_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
                    with open(UNLOCKS_STATE_PATH, "w", encoding="utf-8") as f:
                        json.dump({
                            "active_unlocks": list(active_ids),
                            "story_flags": story_flags
                        }, f, indent=2)
                except Exception:
                    pass

            active_unlocks = [u for u in unlocks if u["id"] in active_ids]
            available_unlocks = [u for u in unlocks if u["id"] not in active_ids]

            return {
                "active_unlocks": active_unlocks,
                "available_unlocks": available_unlocks,
                "total_active": len(active_unlocks)
            }
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/progression/state")
    async def get_progression_state():
        """Get full progression state"""
        try:
            db_path = get_db_path()

            # Profile
            manager = UserProfileManager()
            profile_data = manager.get_profile().to_dict() if manager.get_profile() else {}

            # Metrics
            metrics_res = await get_progression_metrics()
            metrics_list = metrics_res.get("metrics", []) if "error" not in metrics_res else []

            # Turn Count
            turn_count = await progression_state.get_turn_count(db_path)

            # Quests
            quests_res = await get_progression_quests_today()
            quests_list = quests_res.get("quests", []) if "error" not in quests_res else []

            # Achievements
            achievements_res = await get_progression_achievements()
            achievements_data = achievements_res if "error" not in achievements_res else {"unlocked": [], "locked": [], "progress": {}}

            # Unlocks
            unlocks_res = await get_progression_unlocks()
            unlocks_data = unlocks_res if "error" not in unlocks_res else {"active_unlocks": [], "available_unlocks": [], "total_active": 0}

            return {
                "profile": profile_data,
                "metrics": metrics_list,
                "quests": quests_list,
                "achievements": achievements_data,
                "unlocks": unlocks_data,
                "turn_count": turn_count
            }
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/progression/notifications")
    async def get_progression_notifications():
        """Get pending notifications"""
        return {"notifications": [], "count": 0}
