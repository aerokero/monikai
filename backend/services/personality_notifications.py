from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


def _as_utc_iso(ts: Any) -> str:
    try:
        value = float(ts)
    except Exception:
        value = datetime.now(timezone.utc).timestamp()
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _event_type_for(notification_type: str) -> str:
    mapping = {
        "level_up": "relationship.level_up",
        "weekly_recap_due": "relationship.weekly_recap_due",
    }
    return mapping.get(notification_type, "relationship.unknown")


def to_frontend_personality_event(notification: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize backend personality notification into a stable frontend contract."""
    n = notification or {}
    ntype = str(n.get("type") or "unknown")

    priority = "normal"
    if ntype == "level_up":
        priority = "high"
    elif ntype == "quest_complete":
        priority = "medium"

    payload = {
        key: value
        for key, value in n.items()
        if key not in {"type", "ts"}
    }

    return {
        "version": 1,
        "event_id": str(n.get("event_id") or ""),
        "event_type": _event_type_for(ntype),
        "type": ntype,
        "timestamp_utc": _as_utc_iso(n.get("ts")),
        "ui_priority": priority,
        "payload": payload,
    }


def build_relationship_notification_lines(notifications: List[Dict[str, Any]]) -> Tuple[List[str], bool]:
    """Map personality notifications to short relationship summary lines.

    Returns:
    - lines: user-facing summary fragments for the relationship system message
    - weekly_recap_due: whether weekly recap generation should be triggered
    """
    lines: List[str] = []
    weekly_recap_due = False

    for notification in notifications or []:
        n = notification or {}
        ntype = n.get("type")

        if ntype == "weekly_recap_due":
            weekly_recap_due = True
            continue

        if ntype == "level_up":
            lvl = n.get("level")
            if lvl:
                lines.append(f"Relacja awansowała na poziom {lvl}.")

    return lines, weekly_recap_due
