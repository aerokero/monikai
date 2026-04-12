"""
PHASE B: Calendar Unification

Calendar + Memory integration:
- Single source of truth for birthday (profile.md)
- Event-to-memory linking with bidirectional references
- Session-end recap generation
- Proactive memory recall (20-min intervals)
"""

import json
from pathlib import Path
from typing import Optional, Tuple, Dict, List, Any
from datetime import datetime, timedelta
import re


class UnifiedCalendarEngine:
    """
    Unified calendar + memory system.
    - Birthday: single source (profile.md)
    - Events: calendar.json + dynamic holidays
    - Memory linking: events ↔ memory entries
    """
    
    def __init__(self, base_dir: Path, memory_engine=None, calendar_manager=None):
        self.base_dir = Path(base_dir).resolve()
        self.memory_engine = memory_engine
        self.calendar_manager = calendar_manager
        
        self.profile_path = self.base_dir / "long_term_memory" / "profile.md"
        self.calendar_path = self.base_dir / "user_memory" / "calendar.json"
        
    # ======================================================================
    # Birthday (Source: profile.md only)
    # ======================================================================
    
    def get_birthday_from_profile(self) -> Optional[Tuple[int, int]]:
        """Extract birthday from profile.md (master source)."""
        if not self.profile_path.exists():
            return None
        
        try:
            content = self.profile_path.read_text(encoding='utf-8')
            # Match: - **birthday**:\n```json\n{"month": X, "day": Y}\n```
            match = re.search(
                r'-\s*\*\*birthday\*\*:.*?\{.*?"month":\s*(\d+).*?"day":\s*(\d+)',
                content,
                re.DOTALL | re.IGNORECASE
            )
            if match:
                return int(match.group(1)), int(match.group(2))
        except Exception as e:
            print(f"[CALENDAR] Error reading birthday from profile: {e}")
        
        return None
    
    def set_birthday_in_profile(self, month: int, day: int) -> bool:
        """
        Update birthday in profile.md (master source).
        Also syncs to calendar_manager and creates memory entry.
        """
        if not self.profile_path.exists():
            print(f"[CALENDAR] Profile not found: {self.profile_path}")
            return False
        
        try:
            content = self.profile_path.read_text(encoding='utf-8')
            
            # Update or create birthday field
            birthday_json = json.dumps({"month": month, "day": day})
            pattern = (
                r'(-\s*\*\*birthday\*\*:.*?\n```json\n)\{[^}]*\}(\n```)'
            )
            
            if re.search(pattern, content, re.DOTALL):
                # Replace existing
                new_content = re.sub(
                    pattern,
                    rf'\g<1>{birthday_json}\g<2>',
                    content,
                    flags=re.DOTALL
                )
            else:
                # Add new field (after project_focus_preference)
                insert_pattern = r'(- \*\*project_focus_preference\*\*:.*?\n)'
                new_field = f'- **birthday**:\n```json\n{birthday_json}\n```\n'
                if re.search(insert_pattern, content):
                    new_content = re.sub(
                        insert_pattern,
                        rf'\g<1>{new_field}',
                        content
                    )
                else:
                    # Fallback: append after ## Profile
                    new_content = content.replace(
                        '## Profile\n',
                        f'## Profile\n- **birthday**:\n```json\n{birthday_json}\n```\n'
                    )
            
            # Update timestamp
            now = datetime.now().isoformat(timespec='seconds')
            new_content = re.sub(
                r'_Updated: [^_]+_',
                f'_Updated: {now}_',
                new_content
            )
            
            # Write back
            self.profile_path.write_text(new_content, encoding='utf-8')
            print(f"[CALENDAR] ✓ Birthday updated in profile: {month}-{day}")
            
            # Sync to calendar manager
            if self.calendar_manager:
                self.calendar_manager.set_user_birthday(month, day)
            
            # Create memory entry
            if self.memory_engine:
                self.memory_engine.add_entry(
                    type="fact",
                    content=f"Urodziny: {month}-{day:02d}",
                    tags=["birthday", "personal"],
                    entities=["user"],
                    confidence=0.99,
                    origin="profile_master",
                    data={"birthday": f"{month}-{day:02d}", "source": "profile_master"}
                )
            
            return True
        except Exception as e:
            print(f"[CALENDAR] Error updating birthday in profile: {e}")
            return False
    
    # ======================================================================
    # Event-to-Memory Linking
    # ======================================================================
    
    def link_event_to_memory(
        self,
        event_id: str,
        event_summary: str,
        event_start: str,
        memory_entry_id: Optional[str] = None
    ) -> bool:
        """
        Create bidirectional link between calendar event and memory entry.
        
        If memory_entry_id is None, creates a new memory entry about the event.
        """
        if not self.memory_engine:
            return False
        
        try:
            # Create memory entry if not provided
            if not memory_entry_id:
                memory_entry_id, op = self.memory_engine.add_entry(
                    type="event",
                    content=event_summary,
                    tags=["calendar", "event"],
                    entities=[],
                    confidence=0.85,
                    origin="calendar",
                    data={
                        "event_id": event_id,
                        "event_summary": event_summary,
                        "event_start": event_start,
                    }
                )
            else:
                # Update existing entry with event link
                self.memory_engine.update_entry(
                    memory_entry_id,
                    {"data": {"event_id": event_id}}
                )
            
            return True
        except Exception as e:
            print(f"[CALENDAR] Error linking event to memory: {e}")
            return False
    
    # ======================================================================
    # Session-End Recap Generation
    # ======================================================================
    
    def generate_session_recap(
        self,
        session_start: str,
        session_end: str,
        session_summary: Optional[str] = None
    ) -> Optional[str]:
        """
        Generate recap at session end with:
        1. Events that happened in session
        2. Important memories triggered
        3. Calendar notifications (birthdays, holidays)
        4. Quick summary
        """
        if not self.memory_engine or not self.calendar_manager:
            return None
        
        try:
            start_dt = datetime.fromisoformat(session_start.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(session_end.replace('Z', '+00:00'))
            
            # 1. Get events in session window
            session_events = self.calendar_manager.list_events(
                session_start,
                (end_dt + timedelta(days=1)).isoformat()
            )
            session_events = [
                e for e in session_events 
                if start_dt <= datetime.fromisoformat(e.start_iso.replace('Z', '+00:00')) < end_dt
            ]
            
            # 2. Get important memories from session
            recent_memories = self.memory_engine.list_recent(
                limit=10,
                start_time=session_start,
                end_time=session_end
            )
            high_importance = [
                m for m in recent_memories 
                if m.get("importance_score", 0) > 0.7
            ]
            
            # 3. Check for upcoming birthdays/holidays (next 7 days)
            upcoming_end = end_dt + timedelta(days=7)
            upcoming = self.calendar_manager.list_events(
                end_dt.isoformat(),
                upcoming_end.isoformat()
            )
            
            # Generate recap markdown
            recap_lines = [
                f"# Session Recap ({session_start} - {session_end})",
                "",
                "## What Happened in Session",
                f"- {session_summary if session_summary else 'Normal chat session'}",
                "",
                "## Key Memories"
            ]
            
            if high_importance:
                for m in high_importance:
                    content = m.get('content', '')[:60]
                    importance = m.get('importance_score', 0.5)
                    recap_lines.append(f"- {content} (importance: {importance:.0%})")
            else:
                recap_lines.append("- No high-importance memories recorded")
            
            recap_lines.extend([
                "",
                "## Events Today"
            ])
            
            if session_events:
                for e in session_events:
                    recap_lines.append(f"- {e.summary} ({e.start_iso})")
            else:
                recap_lines.append("- No events")
            
            recap_lines.extend([
                "",
                "## Upcoming (Next 7 Days)"
            ])
            
            if upcoming:
                for e in upcoming[:5]:
                    recap_lines.append(f"- {e.summary} ({e.start_iso})")
            else:
                recap_lines.append("- Nothing scheduled")
            
            recap_lines.extend([
                "",
                "---",
                f"Generated: {datetime.now().isoformat()}"
            ])
            
            recap = "\n".join(recap_lines)
            
            # Save recap
            recap_dir = self.base_dir / "data" / "sessions"
            recap_dir.mkdir(parents=True, exist_ok=True)
            recap_file = recap_dir / f"recap_{end_dt.strftime('%Y%m%d_%H%M%S')}.md"
            recap_file.write_text(recap, encoding='utf-8')
            
            print(f"[CALENDAR] ✓ Session recap saved: {recap_file}")
            return recap
        
        except Exception as e:
            print(f"[CALENDAR] Error generating recap: {e}")
            return None
    
    # ======================================================================
    # Proactive Memory Recall
    # ======================================================================
    
    def get_proactive_recalls(
        self,
        current_time: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get memories to proactively mention (every 20 min of conversation).
        
        Selection criteria:
        1. Birthday upcoming (within 7 days)
        2. Anniversary events
        3. High-importance but not recently mentioned
        4. Context-relevant memories based on current activity
        """
        if not self.memory_engine:
            return []
        
        recalls = []
        now = datetime.now()
        
        try:
            # 1. Check birthday
            birthday = self.get_birthday_from_profile()
            if birthday:
                month, day = birthday
                days_until = self._days_until_date(month, day)
                if 0 <= days_until <= 7:
                    recalls.append({
                        "type": "birthday_reminder",
                        "content": f"Birthday coming up in {days_until} days!",
                        "priority": 0.95,
                        "days_until": days_until
                    })
            
            # 2. Get important memories not mentioned recently
            recent = self.memory_engine.list_recent(limit=100)
            for memory in recent:
                if memory.get("importance_score", 0) > 0.8:
                    # Skip if mentioned in last 2 hours
                    last_mentioned = memory.get("updated_at", "")
                    if last_mentioned:
                        try:
                            last_time = datetime.fromisoformat(last_mentioned)
                            hours_ago = (now - last_time).total_seconds() / 3600
                            if hours_ago > 2:  # Not mentioned in 2+ hours
                                recalls.append({
                                    "type": "memory_recall",
                                    "content": memory.get("content", ""),
                                    "priority": min(0.9, memory.get("importance_score", 0.5) + hours_ago / 12),
                                    "entry_id": memory.get("id")
                                })
                        except Exception:
                            pass
            
            # Sort by priority
            recalls.sort(key=lambda x: x["priority"], reverse=True)
            return recalls[:3]  # Top 3 recalls
        
        except Exception as e:
            print(f"[CALENDAR] Error getting proactive recalls: {e}")
            return []
    
    def _days_until_date(self, month: int, day: int) -> int:
        """Calculate days until next occurrence of month-day."""
        today = datetime.now().date()
        target = datetime(today.year, month, day).date()
        if target < today:
            target = datetime(today.year + 1, month, day).date()
        delta = target - today
        return delta.days
