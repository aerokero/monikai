import asyncio


def register_control_handlers(sio, *, shutdown_and_exit):

    @sio.event
    async def shutdown(sid, data=None):
        """Gracefully shutdown the server when the application closes."""
        print("[SERVER] ========================================")
        print("[SERVER] SHUTDOWN SIGNAL RECEIVED FROM FRONTEND")
        print("[SERVER] ========================================")
        asyncio.create_task(shutdown_and_exit("[SERVER] Frontend requested shutdown."))
        return {"ok": True}
