"""Alarm clock and Home Assistant shopping-list tools for native Odysseus chat."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional


def _args(content: str) -> Dict[str, Any]:
    try:
        data = json.loads(content or "{}")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _result(text: str, ok: bool = True) -> Dict[str, Any]:
    return {"output": text, "exit_code": 0 if ok else 1}


async def do_manage_alarms(content: str, owner: Optional[str] = None) -> Dict[str, Any]:
    from src.voice_runtime import get_alarm_manager

    mgr = get_alarm_manager()
    if mgr is None:
        return _result("Budzik jest niedostępny (menedżer alarmów nie działa).", ok=False)
    args = _args(content)
    action = str(args.get("action") or "list").strip().lower()
    alarm_id = str(args.get("alarm_id") or "").strip()
    try:
        if action == "list":
            alarms = mgr.list()
            if not alarms:
                return _result("Brak ustawionych budzików.")
            return _result("\n".join(mgr.describe(a) for a in alarms))
        if action in ("set", "edit"):
            if action == "edit" and alarm_id not in mgr.alarms:
                return _result(f"Nie ma budzika {alarm_id!r}.", ok=False)
            prev = mgr.alarms.get(alarm_id)
            a = mgr.set(
                time=args.get("time") or (prev.time if prev else ""),
                days=args.get("days") if "days" in args else (prev.days if prev else None),
                date_str=args.get("date") or "",
                label=args.get("label") if "label" in args else (prev.label if prev else ""),
                sound=args.get("sound") if "sound" in args else (prev.sound if prev else ""),
                greeting=bool(args.get("greeting", prev.greeting if prev else True)),
                alarm_id=alarm_id if prev else "",
            )
            return _result(f"Ustawiono budzik: {mgr.describe(a)}")
        if action == "delete":
            return _result("Usunięto budzik." if mgr.delete(alarm_id) else f"Nie ma budzika {alarm_id!r}.")
        if action in ("enable", "disable"):
            a = mgr.set_enabled(alarm_id, action == "enable")
            return _result(mgr.describe(a) if a else f"Nie ma budzika {alarm_id!r}.", ok=bool(a))
        if action == "stop":
            return _result("Wyłączono dzwoniący budzik." if mgr.stop() else "Żaden budzik teraz nie dzwoni.")
        if action == "snooze":
            minutes = args.get("minutes")
            ok = mgr.snooze(int(minutes) if minutes else None)
            return _result("Drzemka ustawiona." if ok else "Żaden budzik teraz nie dzwoni.")
    except (ValueError, TypeError) as exc:
        return _result(f"Błąd: {exc}", ok=False)
    return _result(f"Nieznana akcja {action!r}.", ok=False)


async def do_manage_shopping_list(content: str, owner: Optional[str] = None) -> Dict[str, Any]:
    from src.home_assistant_runtime import get_home_assistant_agent

    ha = get_home_assistant_agent()
    if ha is None:
        return _result("Home Assistant nie jest skonfigurowany.", ok=False)
    args = _args(content)
    action = str(args.get("action") or "list").strip().lower()
    items = args.get("items") or ([args["item"]] if args.get("item") else [])
    items = [str(i).strip() for i in items if str(i).strip()]
    if action == "list":
        current = await ha.get_shopping_list()
        return _result("Lista zakupów (HA):\n" + "\n".join(f"- {i}" for i in current) if current else "Lista zakupów (HA) jest pusta.")
    if action in ("add", "remove"):
        if not items:
            return _result("Podaj co najmniej jedną pozycję.", ok=False)
        op = ha.add_shopping_item if action == "add" else ha.remove_shopping_item
        failed = [i for i in items if not await op(i)]
        done = [i for i in items if i not in failed]
        verb = "Dodano" if action == "add" else "Usunięto"
        text = f"{verb}: {', '.join(done)}." if done else ""
        if failed:
            text += f" Nie udało się: {', '.join(failed)}."
        return _result(text.strip(), ok=not failed)
    return _result(f"Nieznana akcja {action!r}.", ok=False)
