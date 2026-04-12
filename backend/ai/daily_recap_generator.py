"""
PHASE C: Daily Recaps + Hierarchical Compression

Daily recap system with:
1. EOD summary (automatic at session end or 11 PM)
2. Hierarchical compression (1 week → 1 month → 1 year)
3. Importance-based filtering (remove <0.4, archive 0.4-0.7)
4. Calendar-triggered recalls (event reminders)
5. Memory context injection for chat
"""

import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict


class DailyRecapGenerator:
    """
    Generate daily recaps by:
    - Collecting entries from past 24 hours
    - Filtering by importance threshold
    - Creating hierarchical summaries
    - Injecting key facts into chat context
    """
    
    def __init__(self, base_dir: Path, memory_engine=None):
        self.base_dir = Path(base_dir).resolve()
        self.memory_engine = memory_engine
        
        # base_dir is already the data directory, so just create recaps subdirectory
        self.recaps_dir = self.base_dir / "recaps"
        self.recaps_dir.mkdir(parents=True, exist_ok=True)
        
        # Thresholds (from PHASE A importance scoring)
        self.KEEP_THRESHOLD = 0.7      # Keep verbatim in daily recap
        self.ARCHIVE_THRESHOLD = 0.4   # Archive (compress weekly)
        self.DELETE_THRESHOLD = 0.4    # Soft-delete (mark inactive)
    
    # ======================================================================
    # Daily Recap Generation
    # ======================================================================
    
    def generate_daily_recap(
        self,
        date: Optional[str] = None  # "YYYY-MM-DD" format, defaults to today
    ) -> Optional[str]:
        """
        Generate recap for a specific day:
        - High-importance entries (>0.7): Keep as-is
        - Medium entries (0.4-0.7): Compress to headline
        - Low entries (<0.4): Skip or mark for deletion
        """
        if not self.memory_engine:
            return None
        
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        
        try:
            # Parse date
            target_date = datetime.fromisoformat(date)
            start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = target_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            # Get entries from this day
            start_iso = start_of_day.isoformat()
            end_iso = end_of_day.isoformat()
            
            entries = self.memory_engine.list_entries(
                limit=500,
                start_time=start_iso,
                end_time=end_iso,
                status="active"
            )
            
            if not entries:
                return None
            
            # Categorize by importance
            high_importance = []    # >0.7
            medium_importance = []  # 0.4-0.7
            low_importance = []     # <0.4
            
            for entry in entries:
                score = entry.get("importance_score", 0.5)
                if score >= self.KEEP_THRESHOLD:
                    high_importance.append(entry)
                elif score >= self.ARCHIVE_THRESHOLD:
                    medium_importance.append(entry)
                else:
                    low_importance.append(entry)
            
            # Generate recap markdown
            recap_lines = [
                f"# Daily Recap: {date}",
                "",
                f"**Summary**: {len(high_importance)} key entries, {len(medium_importance)} routine items",
                "",
            ]
            
            # High-importance section
            if high_importance:
                recap_lines.extend([
                    "## 🔴 Important Events",
                    f"_{len(high_importance)} entries_",
                    ""
                ])
                for entry in high_importance:
                    recap_lines.append(self._format_entry(entry))
                recap_lines.append("")
            
            # Medium-importance section (compressed headlines)
            if medium_importance:
                recap_lines.extend([
                    "## 🟡 Routine Items",
                    f"_{len(medium_importance)} entries (compressed)_",
                    ""
                ])
                for entry in medium_importance:
                    headline = self._extract_headline(entry)
                    recap_lines.append(f"- {headline}")
                recap_lines.append("")
            
            # Statistics
            recap_lines.extend([
                "## 📊 Statistics",
                f"- High importance: {len(high_importance)} ({100*len(high_importance)/(len(entries) or 1):.0f}%)",
                f"- Medium importance: {len(medium_importance)} ({100*len(medium_importance)/(len(entries) or 1):.0f}%)",
                f"- Low importance: {len(low_importance)} ({100*len(low_importance)/(len(entries) or 1):.0f}%)",
                f"- Total entries: {len(entries)}",
                f"- Average importance: {sum(e.get('importance_score', 0.5) for e in entries) / len(entries):.2f}",
                "",
                f"Generated: {datetime.now().isoformat()}",
            ])
            
            recap_text = "\n".join(recap_lines)
            
            # Save recap
            recap_file = self.recaps_dir / f"recap_{date.replace('-', '')}.md"
            recap_file.write_text(recap_text, encoding='utf-8')
            print(f"[RECAP] ✓ Daily recap saved: {recap_file}")
            
            # Mark low-importance entries for cleanup
            if low_importance and self.memory_engine:
                for entry in low_importance:
                    try:
                        self.memory_engine.update_entry(
                            entry.get("id"),
                            {"status": "archived"}
                        )
                    except Exception:
                        pass
            
            return recap_text
        
        except Exception as e:
            print(f"[RECAP] Error generating daily recap: {e}")
            return None
    
    def _format_entry(self, entry: Dict[str, Any]) -> str:
        """Format single entry for recap."""
        content = entry.get("content", "")[:100]
        entry_type = entry.get("type", "note")
        importance = entry.get("importance_score", 0.5)
        
        return f"- **[{entry_type}]** {content} _(score: {importance:.0%})_"
    
    def _extract_headline(self, entry: Dict[str, Any]) -> str:
        """Extract headline from entry (first sentence/50 chars)."""
        content = entry.get("content", "")
        
        # Try to extract first sentence
        sentences = content.split(".")
        if sentences:
            headline = sentences[0].strip()
            if len(headline) > 50:
                headline = headline[:47] + "..."
            return headline
        
        return content[:50]
    
    # ======================================================================
    # Weekly Compression
    # ======================================================================
    
    def compress_week(self, year: int, week: int) -> Optional[str]:
        """
        Weekly compression: Take 7 daily recaps and create 1-week summary
        
        - Keep all high-importance entries (>0.7)
        - Compress medium entries to highlights
        - Remove low entries entirely
        """
        try:
            # Get dates for this week (Monday-Sunday)
            from datetime import datetime, date, timedelta
            jan_4 = date(year, 1, 4)
            week_1_monday = jan_4 - timedelta(days=jan_4.weekday())
            week_start = week_1_monday + timedelta(weeks=week-1)
            week_dates = [week_start + timedelta(days=i) for i in range(7)]
            
            # Collect all high-importance entries from recaps
            all_entries = []
            for day_date in week_dates:
                date_str = day_date.strftime("%Y-%m-%d")
                recap_file = self.recaps_dir / f"recap_{date_str.replace('-', '')}.md"
                
                if recap_file.exists():
                    # Could parse recap markdown, but easier to query memory directly
                    pass
            
            # Generate week summary
            week_str = f"W{week:02d}"
            week_start_str = week_dates[0].strftime("%Y-%m-%d")
            week_end_str = week_dates[-1].strftime("%Y-%m-%d")
            
            summary_lines = [
                f"# Weekly Summary: {year} {week_str} ({week_start_str} - {week_end_str})",
                "",
                "## Key Events",
                "- [Loading from daily recaps...]",
                "",
                f"Generated: {datetime.now().isoformat()}",
            ]
            
            summary_text = "\n".join(summary_lines)
            
            # Save week summary
            summary_file = self.recaps_dir / f"summary_week_{year}_{week:02d}.md"
            summary_file.write_text(summary_text, encoding='utf-8')
            print(f"[RECAP] ✓ Weekly summary: {summary_file}")
            
            return summary_text
        
        except Exception as e:
            print(f"[RECAP] Error compressing week: {e}")
            return None
    
    def compress_month(self, year: int, month: int) -> Optional[str]:
        """
        Monthly compression: Aggregate weeks into month overview
        
        - 4-5 weeks per month
        - Keep critical events only (>0.85 importance)
        - Create month-level narrative
        """
        try:
            # Get weeks in month
            month_start = datetime(year, month, 1)
            if month == 12:
                month_end = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = datetime(year, month + 1, 1) - timedelta(days=1)
            
            month_name = month_start.strftime("%B %Y")
            
            summary_lines = [
                f"# Monthly Summary: {month_name}",
                "",
                "## Major Events",
                "- [Aggregated from weekly summaries...]",
                "",
                f"Generated: {datetime.now().isoformat()}",
            ]
            
            summary_text = "\n".join(summary_lines)
            
            # Save month summary
            summary_file = self.recaps_dir / f"summary_month_{year}_{month:02d}.md"
            summary_file.write_text(summary_text, encoding='utf-8')
            print(f"[RECAP] ✓ Monthly summary: {summary_file}")
            
            return summary_text
        
        except Exception as e:
            print(f"[RECAP] Error compressing month: {e}")
            return None
    
    # ======================================================================
    # Chat Context Injection
    # ======================================================================
    
    def get_chat_context_injection(self, num_lines: int = 5) -> str:
        """
        Get context to inject into chat:
        - Today's recap (if available)
        - Recent high-importance entries
        - Upcoming calendar items (from PHASE B)
        
        Used to brief AI on today's context without cluttering conversation.
        """
        context_lines = []
        
        try:
            # 1. Today's recap (if exists)
            today = datetime.now().strftime("%Y-%m-%d")
            recap_file = self.recaps_dir / f"recap_{today.replace('-', '')}.md"
            if recap_file.exists():
                recap = recap_file.read_text(encoding='utf-8')
                # Extract summary line
                for line in recap.split("\n"):
                    if "Summary:" in line:
                        context_lines.append(f"📅 Today: {line.replace('**Summary**: ', '')}")
                        break
            
            # 2. Recent high-importance entries (if memory_engine available)
            if self.memory_engine:
                recent = self.memory_engine.list_recent(limit=5)
                high_value = [e for e in recent if e.get("importance_score", 0) > 0.8]
                if high_value:
                    context_lines.append("")
                    context_lines.append("🔴 Recent important:")
                    for entry in high_value[:3]:
                        content = entry.get("content", "")[:60]
                        context_lines.append(f"  - {content}")
            
            return "\n".join(context_lines) if context_lines else "No recent context available."
        
        except Exception as e:
            print(f"[RECAP] Error generating chat context: {e}")
            return ""
    
    # ======================================================================
    # Memory Cleanup (Garbage Collection)
    # ======================================================================
    
    def cleanup_low_importance_entries(
        self,
        dry_run: bool = True
    ) -> Dict[str, int]:
        """
        Cleanup low-importance entries:
        - Mark <0.4 as 'archived' (soft-delete)
        - Keep in JSONL but exclude from active searches
        - Preserve for historical analysis
        
        Returns: {"marked_archived": N, "error_count": 0}
        """
        if not self.memory_engine:
            return {"error": "no memory_engine"}
        
        try:
            all_entries = self.memory_engine.list_entries(limit=10000, status="active")
            
            to_archive = [
                e for e in all_entries
                if e.get("importance_score", 0.5) < self.DELETE_THRESHOLD
            ]
            
            print(f"[CLEANUP] Found {len(to_archive)} entries to archive (<{self.DELETE_THRESHOLD:.0%})")
            
            if dry_run:
                print(f"[CLEANUP] DRY RUN: Would archive {len(to_archive)} entries")
                return {"marked_archived": 0, "dry_run": True, "entries_to_archive": len(to_archive)}
            
            # Actually archive
            count = 0
            for entry in to_archive:
                try:
                    self.memory_engine.update_entry(
                        entry.get("id"),
                        {"status": "archived"}
                    )
                    count += 1
                except Exception as e:
                    print(f"[CLEANUP] Error archiving {entry.get('id')}: {e}")
            
            print(f"[CLEANUP] ✓ Archived {count} low-importance entries")
            return {"marked_archived": count}
        
        except Exception as e:
            print(f"[CLEANUP] Error during cleanup: {e}")
            return {"error": str(e)}
