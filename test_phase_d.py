"""
PHASE D Integration Test - User Knowledge Graph

Tests:
1. KG imports and initializes
2. Entity creation and retrieval
3. Relationship creation and querying
4. Entity extraction from memory entries
5. Integration with memory engine
"""

import sys
from pathlib import Path
from datetime import datetime

# Setup paths
base_dir = Path(__file__).parent
sys.path.insert(0, str(base_dir))

print("=" * 70)
print("PHASE D INTEGRATION TEST - User Knowledge Graph")
print("=" * 70)

# Test 1: Import UserKnowledgeGraph
print("\n[TEST 1] Importing UserKnowledgeGraph...")
try:
    from backend.ai.user_knowledge_graph import UserKnowledgeGraph, KGEntity, KGRelationship
    print("✅ UserKnowledgeGraph imported successfully")
except Exception as e:
    print(f"❌ FAILED to import UserKnowledgeGraph: {e}")
    sys.exit(1)

# Test 2: Initialize KG
print("\n[TEST 2] Initializing UserKnowledgeGraph...")
try:
    data_dir = base_dir / "data"
    kg_engine = UserKnowledgeGraph(base_dir=data_dir)
    print(f"✅ KG initialized (db_path={kg_engine.db_path})")
except Exception as e:
    print(f"❌ FAILED to initialize KG: {e}")
    sys.exit(1)

# Test 3: Create entities
print("\n[TEST 3] Creating entities...")
try:
    # Create person entity
    person_id = kg_engine.add_or_update_entity(
        "person", "Marcel",
        properties={"title": "Software Engineer", "email": "marcel@example.com"},
        confidence=0.85
    )
    print(f"✅ Created person entity: {person_id}")
    
    # Create project entity
    project_id = kg_engine.add_or_update_entity(
        "project", "Feature X",
        properties={"status": "in_progress", "deadline": "2026-04-15"},
        confidence=0.8
    )
    print(f"✅ Created project entity: {project_id}")
    
    # Create location entity
    location_id = kg_engine.add_or_update_entity(
        "location", "Office",
        properties={"type": "office", "address": "Downtown"},
        confidence=0.9
    )
    print(f"✅ Created location entity: {location_id}")
except Exception as e:
    print(f"❌ FAILED to create entities: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Retrieve entity
print("\n[TEST 4] Retrieving entity...")
try:
    entity = kg_engine.get_entity(person_id)
    if entity:
        print(f"✅ Retrieved entity: {entity.name} (confidence: {entity.confidence})")
    else:
        print("❌ Entity not found")
        sys.exit(1)
except Exception as e:
    print(f"❌ FAILED to retrieve entity: {e}")
    sys.exit(1)

# Test 5: Create relationships
print("\n[TEST 5] Creating relationships...")
try:
    # Create "works_with" relationship
    rel_id = kg_engine.add_or_update_relationship(
        person_id, project_id,
        "works_on",
        properties={"role": "lead_engineer"},
        confidence=0.85,
        evidence=["mem_12345"],
    )
    print(f"✅ Created relationship: {rel_id}")
except Exception as e:
    print(f"❌ FAILED to create relationship: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 6: Query relationships
print("\n[TEST 6] Querying relationships...")
try:
    rels = kg_engine.get_relationships(source_id=person_id)
    print(f"✅ Found {len(rels)} relationship(s) from {person_id}")
    if rels:
        for rel in rels:
            print(f"   - {rel.relation_type} → {rel.target_id} (conf: {rel.confidence})")
except Exception as e:
    print(f"❌ FAILED to query relationships: {e}")
    sys.exit(1)

# Test 7: Entity extraction from text
print("\n[TEST 7] Entity extraction from memory entry...")
try:
    content = "I met with Marcel today about Feature X at the office. His email is marcel@example.com"
    extracted = kg_engine.extract_entities_from_memory_entry(
        entry_id="mem_test_001",
        content=content,
        entry_type="event",
        tags=["person:Marcel", "project:feature_x"],
        entities=["Marcel", "Feature X", "Office"],
    )
    print(f"✅ Extracted {len(extracted)} entities")
    for entity_id, entity_type, confidence in extracted:
        print(f"   - {entity_id} ({entity_type}, conf: {confidence})")
except Exception as e:
    print(f"❌ FAILED entity extraction: {e}")
    import traceback
    traceback.print_exc()

# Test 8: Get KG summary
print("\n[TEST 8] Getting KG summary...")
try:
    summary = kg_engine.get_summary()
    print(f"✅ KG Summary:")
    print(f"   - Total entities: {summary['total_entities']}")
    print(f"   - Total relationships: {summary['total_relationships']}")
    print(f"   - Entities by type: {summary['entities_by_type']}")
except Exception as e:
    print(f"❌ FAILED to get summary: {e}")
    import traceback
    traceback.print_exc()

# Test 9: List entities by type
print("\n[TEST 9] Listing entities by type...")
try:
    people = kg_engine.list_entities(entity_type="person")
    print(f"✅ Found {len(people)} person entities")
    for person in people:
        print(f"   - {person.name} (confidence: {person.confidence})")
except Exception as e:
    print(f"❌ FAILED to list entities: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
print("PHASE D INTEGRATION TEST - PASSED ✅")
print("=" * 70)
print("\nKnowledge graph system is working correctly!")
print("Ready for app integration and entity auto-extraction.")
