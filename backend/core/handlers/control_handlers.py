import asyncio


def register_control_handlers(sio, *, get_audio_loop, shutdown_and_exit):
    @sio.event
    async def confirm_tool(sid, data):
        # data: { "id": "...", "confirmed": True/False }
        request_id = data.get("id")
        confirmed = data.get("confirmed", False)

        print(f"[SERVER DEBUG] Received confirmation response for {request_id}: {confirmed}")

        audio_loop = get_audio_loop()
        if audio_loop:
            audio_loop.resolve_tool_confirmation(request_id, confirmed)
        else:
            print("Audio loop not active, cannot resolve confirmation.")

    @sio.event
    async def shutdown(sid, data=None):
        """Gracefully shutdown the server when the application closes."""
        print("[SERVER] ========================================")
        print("[SERVER] SHUTDOWN SIGNAL RECEIVED FROM FRONTEND")
        print("[SERVER] ========================================")
        asyncio.create_task(shutdown_and_exit("[SERVER] Frontend requested shutdown."))
        return {"ok": True}
