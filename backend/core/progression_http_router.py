def register_progression_http_routes(app, *, get_main_loop):
    @app.get("/api/progression/profile")
    async def get_progression_profile():
        """Get user profile from progression system"""
        try:
            main_loop = get_main_loop()
            if not main_loop or not hasattr(main_loop, "personality") or not hasattr(main_loop.personality, "progression"):
                return {"error": "Progression system not available"}
            profile = main_loop.personality.progression.profile_manager.get_profile()
            if not profile:
                return {"error": "No profile loaded"}
            return profile.to_dict()
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/progression/metrics")
    async def get_progression_metrics():
        """Get relationship metrics"""
        try:
            main_loop = get_main_loop()
            if not main_loop or not hasattr(main_loop, "personality") or not hasattr(main_loop.personality, "progression"):
                return {"error": "Progression system not available"}
            metrics = main_loop.personality.progression.metrics_engine.get_metrics_state()
            progress = main_loop.personality.progression.metrics_engine.get_recommendation_progress()
            return {"metrics": metrics, "progress": progress}
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/progression/quests/today")
    async def get_progression_quests_today():
        """Get today's quests"""
        try:
            main_loop = get_main_loop()
            if not main_loop or not hasattr(main_loop, "personality") or not hasattr(main_loop.personality, "progression"):
                return {"error": "Progression system not available"}
            quests = [q.to_dict() for q in main_loop.personality.progression.quest_system.active_quests]
            return {"quests": quests, "total": len(quests)}
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/progression/achievements")
    async def get_progression_achievements():
        """Get achievements"""
        try:
            main_loop = get_main_loop()
            if not main_loop or not hasattr(main_loop, "personality") or not hasattr(main_loop.personality, "progression"):
                return {"error": "Progression system not available"}
            unlocked = main_loop.personality.progression.achievement_tracker.get_unlocked_achievements()
            locked = main_loop.personality.progression.achievement_tracker.get_locked_achievements()
            return {
                "unlocked": [a.to_dict() for a in unlocked],
                "locked": [a.to_dict() for a in locked],
            }
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/progression/unlocks")
    async def get_progression_unlocks():
        """Get active unlocks"""
        try:
            main_loop = get_main_loop()
            if not main_loop or not hasattr(main_loop, "personality") or not hasattr(main_loop.personality, "progression"):
                return {"error": "Progression system not available"}
            active = main_loop.personality.progression.unlock_tracker.get_active_unlocks()
            return {"active_unlocks": active, "count": len(active)}
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/progression/state")
    async def get_progression_state():
        """Get full progression state"""
        try:
            main_loop = get_main_loop()
            if not main_loop or not hasattr(main_loop, "personality") or not hasattr(main_loop.personality, "progression"):
                return {"error": "Progression system not available"}
            state = main_loop.personality.progression.get_progression_state()
            return state
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/progression/notifications")
    async def get_progression_notifications():
        """Get pending progression notifications"""
        try:
            main_loop = get_main_loop()
            if not main_loop or not hasattr(main_loop, "personality") or not hasattr(main_loop.personality, "progression"):
                return {"error": "Progression system not available"}
            notifications = main_loop.personality.progression.get_pending_notifications()
            return {"notifications": notifications}
        except Exception as e:
            return {"error": str(e)}
