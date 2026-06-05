def register_minecraft_http_routes(app, *, get_minecraft_bot_manager):
    @app.get("/minecraft/state")
    async def minecraft_state():
        """Get current Minecraft bot state from state tracker"""
        minecraft_bot_manager = get_minecraft_bot_manager()
        if not minecraft_bot_manager:
            return {"ok": False, "error": "minecraft bot manager unavailable"}

        try:
            snapshot = minecraft_bot_manager.state_tracker.get_state_snapshot()
            if not snapshot:
                return {"ok": True, "state": None, "message": "No state tracked yet"}

            interesting = minecraft_bot_manager.state_tracker.get_nearby_interesting(top_n=3)
            interesting_data = [
                {
                    "type": b.block_type,
                    "distance": b.distance,
                    "interest": round(b.interestingness, 2),
                    "position": {"x": int(b.position.x), "y": int(b.position.y), "z": int(b.position.z)},
                }
                for b in interesting
            ]

            dangers = minecraft_bot_manager.state_tracker.get_nearby_dangers()
            dangers_data = [
                {
                    "type": e.type,
                    "name": e.name,
                    "distance": e.distance,
                    "position": {"x": int(e.position.x), "y": int(e.position.y), "z": int(e.position.z)},
                }
                for e in dangers
            ]

            return {
                "ok": True,
                "state": snapshot,
                "interesting_nearby": interesting_data,
                "dangers_nearby": dangers_data,
                "latest_scan": minecraft_bot_manager.state_tracker._last_scan_time,
                "debug": minecraft_bot_manager.state_tracker.debug_info(),
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "type": type(e).__name__}
