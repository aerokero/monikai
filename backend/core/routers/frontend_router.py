"""Socket.IO frontend routing helpers for MonikAI."""

from __future__ import annotations

import asyncio


ACTIVE_FRONTEND_SID = None
SIO = None


def register_socketio(sio):
    global SIO
    SIO = sio


def set_active_frontend_sid(sid):
    global ACTIVE_FRONTEND_SID
    ACTIVE_FRONTEND_SID = sid


def clear_active_frontend_sid(sid=None):
    global ACTIVE_FRONTEND_SID
    if sid is None or ACTIVE_FRONTEND_SID == sid:
        ACTIVE_FRONTEND_SID = None


def get_active_frontend_sid():
    return ACTIVE_FRONTEND_SID


def is_active_frontend_sid(sid):
    return bool(sid and sid == ACTIVE_FRONTEND_SID)


async def emit_to_frontend(event: str, payload, room: str = None):
    if SIO is None:
        return
    target_room = room if room is not None else ACTIVE_FRONTEND_SID
    if target_room:
        await SIO.emit(event, payload, room=target_room)
    else:
        await SIO.emit(event, payload)


def schedule_emit_to_frontend(event: str, payload, room: str = None):
    asyncio.create_task(emit_to_frontend(event, payload, room=room))
