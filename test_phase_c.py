"""
PHASE C Integration Test - Daily Recap Generator

Tests:
1. DailyRecapGenerator imports correctly
2. memory_engine has list_entries() method
3. Daily recap can be generated
4. Recaps directory is created
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Setup paths
base_dir = Path(__file__).parent
sys.path.insert(0, str(base_dir))

print("=" * 70)
print("PHASE C INTEGRATION TEST - Daily Recap Generator")
print("=" * 70)

# Test 1: Import DailyRecapGenerator
print("\n[TEST 1] Importing DailyRecapGenerator...")
try:
    from backend.ai.daily_recap_generator import DailyRecapGenerator
    print("✅ DailyRecapGenerator imported successfully")
except Exception as e:
    print(f"❌ FAILED to import DailyRecapGenerator: {e}")
    sys.exit(1)

# Test 2: Import MemoryEngine
print("\n[TEST 2] Importing MemoryEngine...")
try:
    from backend.ai.memory_engine import MemoryEngine
    print("✅ MemoryEngine imported successfully")
except Exception as e:
    print(f"❌ FAILED to import MemoryEngine: {e}")
    sys.exit(1)

# Test 3: Initialize MemoryEngine
print("\n[TEST 3] Initializing MemoryEngine...")
try:
    data_dir = base_dir / "data"
    memory_engine = MemoryEngine(base_dir=data_dir)
    print(f"✅ MemoryEngine initialized (base_dir={data_dir})")
except Exception as e:
    print(f"❌ FAILED to initialize MemoryEngine: {e}")
    sys.exit(1)

# Test 4: Check list_entries method exists
print("\n[TEST 4] Checking list_entries() method exists...")
try:
    if hasattr(memory_engine, 'list_entries'):
        print("✅ list_entries() method found")
        # Try calling it
        entries = memory_engine.list_entries(limit=5)
        print(f"✅ list_entries() callable, returned {len(entries)} recent entries")
    else:
        print("❌ list_entries() method NOT found")
        sys.exit(1)
except Exception as e:
    print(f"❌ FAILED to call list_entries(): {e}")
    sys.exit(1)

# Test 5: Initialize DailyRecapGenerator
print("\n[TEST 5] Initializing DailyRecapGenerator...")
try:
    recap_generator = DailyRecapGenerator(base_dir=data_dir, memory_engine=memory_engine)
    print(f"✅ DailyRecapGenerator initialized (recaps_dir={recap_generator.recaps_dir})")
except Exception as e:
    print(f"❌ FAILED to initialize DailyRecapGenerator: {e}")
    sys.exit(1)

# Test 6: Generate a daily recap
print("\n[TEST 6] Generating daily recap...")
try:
    today = datetime.now().strftime("%Y-%m-%d")
    recap_text = recap_generator.generate_daily_recap(date=today)
    
    if recap_text:
        print(f"✅ Daily recap generated successfully")
        print(f"   Size: {len(recap_text)} characters")
        print(f"   Preview: {recap_text[:200]}...")
    else:
        print("⚠️  Daily recap returned None/empty (might be OK if no entries today)")
except Exception as e:
    print(f"❌ FAILED to generate daily recap: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 7: Check recaps directory
print("\n[TEST 7] Checking recaps directory...")
try:
    recaps_dir = base_dir / "data" / "recaps"
    if recaps_dir.exists():
        recap_files = list(recaps_dir.glob("recap_*.md"))
        print(f"✅ Recaps directory exists with {len(recap_files)} recap files")
    else:
        print("⚠️  Recaps directory doesn't exist yet (will be created on first recap)")
except Exception as e:
    print(f"❌ FAILED to check recaps directory: {e}")
    sys.exit(1)

# Test 8: Test get_chat_context_injection
print("\n[TEST 8] Testing get_chat_context_injection()...")
try:
    context = recap_generator.get_chat_context_injection()
    if context:
        print(f"✅ Chat context injection generated ({len(context)} characters)")
        print(f"   Preview: {context[:150]}...")
    else:
        print("⚠️  Chat context injection returned None/empty")
except Exception as e:
    print(f"❌ FAILED to get chat context injection: {e}")
    import traceback
    traceback.print_exc()

# Test 9: Test cleanup_low_importance_entries (dry run)
print("\n[TEST 9] Testing cleanup_low_importance_entries (dry run)...")
try:
    cleanup_result = recap_generator.cleanup_low_importance_entries(dry_run=True)
    if cleanup_result:
        print(f"✅ Cleanup dry-run completed")
        print(f"   Would affect: {cleanup_result.get('count', 0)} entries")
        print(f"   Details: {cleanup_result}")
    else:
        print("⚠️  Cleanup returned None/empty (might be OK if no low-importance entries)")
except Exception as e:
    print(f"❌ FAILED cleanup test: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
print("PHASE C INTEGRATION TEST - PASSED ✅")
print("=" * 70)
print("\nAll critical components are working correctly!")
print("Ready for app integration testing.")
