#!/usr/bin/env python3
"""Quick test of PHASE B calendar unification."""

import sys
from pathlib import Path

try:
    print("[TEST] Starting PHASE B test...")
    from backend.core import monikai
    from backend.ai.calendar_unification import UnifiedCalendarEngine
    print("[TEST] ✓ Imports successful")
    
    # Test CalendarManager
    base_dir = Path("data")
    cal_mgr = monikai.CalendarManager(storage_dir=base_dir / "user_memory")
    cal_mgr.load()
    print("[TEST] ✓ CalendarManager initialized")
    
    # Test UnifiedCalendarEngine
    unified = UnifiedCalendarEngine(
        base_dir=base_dir,
        memory_engine=None,
        calendar_manager=cal_mgr
    )
    print("[TEST] ✓ Calendar unification initialized")
    
    # Test birthday reading
    bd = unified.get_birthday_from_profile()
    print(f"[TEST] ✓ Birthday read: {bd}")
    
    # Test proactive recalls
    recalls = unified.get_proactive_recalls()
    print(f"[TEST] ✓ Proactive recalls: {len(recalls)} items")
    
    print("[TEST] ✅ All PHASE B tests passed!")
    
except Exception as e:
    print(f"[TEST] ❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
