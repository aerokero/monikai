"""
PHASE D: User Profile Knowledge Graph

Knowledge graph to model user relationships and entities:
- Entities: People, Projects, Locations, Preferences, Skills, Events
- Relationships: works_with, knows, prefers, located_at, experiences, learned
- Confidence scoring for entity assertions
- Storage: SQLite + JSON backup
- Integration: Auto-extract entities from memory entries
"""

import json
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Set
from datetime import datetime
from dataclasses import dataclass, asdict
import re


@dataclass
class KGEntity:
    """Knowledge graph entity (node)"""
    id: str                          # Unique ID (e.g., "person:bartek", "project:feature_x")
    entity_type: str                 # Type: person, project, location, preference, skill, event
    name: str                        # Display name
    properties: Dict[str, Any]       # Type-specific data (title, email for person, etc.)
    confidence: float                # 0.0-1.0, how sure we are about this entity
    created_at: str                  # ISO datetime
    updated_at: str                  # ISO datetime
    status: str = "active"           # active, archived, deleted


@dataclass
class KGRelationship:
    """Knowledge graph relationship (edge)"""
    id: str                          # Unique ID
    source_id: str                   # From entity
    target_id: str                   # To entity
    relation_type: str               # Type: works_with, knows, prefers, etc.
    properties: Dict[str, Any]       # Context: meetings_count, last_contact, etc.
    confidence: float                # 0.0-1.0, how reliable is this connection
    evidence: List[str]              # List of memory entry IDs that support this
    created_at: str                  # ISO datetime
    updated_at: str                  # ISO datetime
    status: str = "active"           # active, archived, deleted


class UserKnowledgeGraph:
    """
    User knowledge graph: stores entities (people, projects) and relationships.
    
    Purpose:
    - Structural understanding of user's world
    - Relationship queries: "Who does Bartek work with?"
    - Context injection: When user mentions project X, surface related people
    - Proactive recalls: Upcoming meetings with person Y → suggest related memories
    """
    
    def __init__(self, base_dir: Path, memory_engine=None):
        self.base_dir = Path(base_dir).resolve()
        self.memory_engine = memory_engine
        
        # Storage paths
        self.kg_dir = self.base_dir / "kg"
        self.kg_dir.mkdir(parents=True, exist_ok=True)
        
        self.db_path = self.kg_dir / "kg.db"
        self.entities_backup_path = self.kg_dir / "entities.jsonl"
        self.relationships_backup_path = self.kg_dir / "relationships.jsonl"
        
        # Database connection (pooling)
        self._connection = None
        self._connection_timeout = 30.0
        
        # Entity type definitions
        self.ENTITY_TYPES = {
            "person": {"key_props": ["title", "email", "role", "location"]},
            "project": {"key_props": ["status", "start_date", "deadline", "tags"]},
            "location": {"key_props": ["type", "address", "country"]},
            "preference": {"key_props": ["category", "value", "strength"]},
            "skill": {"key_props": ["level", "years_experience", "last_used"]},
            "event": {"key_props": ["date", "type", "location", "participants"]},
        }
        
        # Relationship types (directed edges)
        self.RELATION_TYPES = {
            # Person relationships
            "knows": {"reverse": "known_by", "weight": 0.6},
            "works_with": {"reverse": "works_with", "weight": 0.8},
            "managed_by": {"reverse": "manages", "weight": 0.9},
            "teaches": {"reverse": "learns_from", "weight": 0.7},
            "collaborates_with": {"reverse": "collaborates_with", "weight": 0.8},
            
            # Project relationships
            "works_on": {"reverse": "has_contributor", "weight": 0.85},
            "owns": {"reverse": "owned_by", "weight": 0.9},
            "depends_on": {"reverse": "depended_by", "weight": 0.7},
            
            # Preference relationships
            "prefers": {"reverse": "preferred_by", "weight": 0.5},
            "located_at": {"reverse": "location_of", "weight": 0.8},
            
            # Event relationships
            "attended": {"reverse": "attended_by", "weight": 0.85},
            "organized": {"reverse": "organized_by", "weight": 0.88},
        }
        
        self._init_schema()
    
    # ======================================================================
    # Database Setup
    # ======================================================================
    
    def _connect(self) -> sqlite3.Connection:
        """Return singleton connection with pooling"""
        if self._connection is not None:
            try:
                self._connection.execute("SELECT 1")
                return self._connection
            except Exception:
                self._connection = None
        
        self._connection = sqlite3.connect(str(self.db_path), timeout=self._connection_timeout)
        self._connection.row_factory = sqlite3.Row
        return self._connection
    
    def _init_schema(self) -> None:
        """Create KG tables if not exist"""
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kg_entities (
                    id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    properties TEXT,
                    confidence REAL DEFAULT 0.5,
                    created_at TEXT,
                    updated_at TEXT,
                    status TEXT DEFAULT 'active'
                )
                """
            )
            
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kg_relationships (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    properties TEXT,
                    confidence REAL DEFAULT 0.5,
                    evidence TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    status TEXT DEFAULT 'active'
                )
                """
            )
            
            # Indices for fast queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_type ON kg_entities(entity_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_status ON kg_entities(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_relationships_source ON kg_relationships(source_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_relationships_target ON kg_relationships(target_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_relationships_type ON kg_relationships(relation_type)")
            
            conn.commit()
        except Exception as e:
            print(f"[KG] Schema creation error: {e}")
        finally:
            pass
    
    def __del__(self):
        """Cleanup: close connection on destroy"""
        if hasattr(self, '_connection') and self._connection:
            try:
                self._connection.close()
            except Exception:
                pass
    
    # ======================================================================
    # Entity Management
    # ======================================================================
    
    def add_or_update_entity(
        self,
        entity_type: str,
        name: str,
        properties: Optional[Dict[str, Any]] = None,
        confidence: float = 0.6,
    ) -> str:
        """
        Add or update entity. Creates unique ID from type + name.
        
        Args:
            entity_type: Type of entity (person, project, etc.)
            name: Display name
            properties: Type-specific properties
            confidence: Confidence score (0.0-1.0)
        
        Returns:
            Entity ID
        """
        if entity_type not in self.ENTITY_TYPES:
            raise ValueError(f"Unknown entity type: {entity_type}")
        
        entity_id = self._entity_id(entity_type, name)
        now = datetime.now().isoformat()
        properties = properties or {}
        
        conn = self._connect()
        try:
            # Check if exists
            existing = conn.execute(
                "SELECT id FROM kg_entities WHERE id = ?", (entity_id,)
            ).fetchone()
            
            if existing:
                # Update confidence (take max)
                new_conf = max(confidence, 0.6)
                conn.execute(
                    """UPDATE kg_entities 
                       SET confidence = ?, properties = ?, updated_at = ?, status = 'active'
                       WHERE id = ?""",
                    (new_conf, json.dumps(properties, ensure_ascii=False), now, entity_id),
                )
            else:
                # Insert new
                conn.execute(
                    """INSERT INTO kg_entities (id, entity_type, name, properties, confidence, created_at, updated_at, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'active')""",
                    (entity_id, entity_type, name, json.dumps(properties, ensure_ascii=False), confidence, now, now),
                )
            
            conn.commit()
        finally:
            pass
        
        return entity_id
    
    def _entity_id(self, entity_type: str, name: str) -> str:
        """Generate unique entity ID"""
        normalized = re.sub(r'[^a-z0-9\-_]', '_', name.lower())
        return f"{entity_type}:{normalized}"
    
    def get_entity(self, entity_id: str) -> Optional[KGEntity]:
        """Retrieve entity by ID"""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM kg_entities WHERE id = ? AND status = 'active'",
                (entity_id,),
            ).fetchone()
            
            if row:
                return KGEntity(
                    id=row["id"],
                    entity_type=row["entity_type"],
                    name=row["name"],
                    properties=json.loads(row["properties"] or "{}"),
                    confidence=row["confidence"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    status=row["status"],
                )
        finally:
            pass
        
        return None
    
    def list_entities(self, entity_type: Optional[str] = None, min_confidence: float = 0.0) -> List[KGEntity]:
        """List all entities, optionally filtered by type"""
        conn = self._connect()
        try:
            sql = "SELECT * FROM kg_entities WHERE status = 'active' AND confidence >= ?"
            params = [min_confidence]
            
            if entity_type:
                sql += " AND entity_type = ?"
                params.append(entity_type)
            
            sql += " ORDER BY confidence DESC"
            rows = conn.execute(sql, params).fetchall()
            
            return [
                KGEntity(
                    id=r["id"],
                    entity_type=r["entity_type"],
                    name=r["name"],
                    properties=json.loads(r["properties"] or "{}"),
                    confidence=r["confidence"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                    status=r["status"],
                )
                for r in rows
            ]
        finally:
            pass
    
    # ======================================================================
    # Relationship Management
    # ======================================================================
    
    def add_or_update_relationship(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        properties: Optional[Dict[str, Any]] = None,
        confidence: float = 0.6,
        evidence: Optional[List[str]] = None,
    ) -> str:
        """
        Add or update relationship between entities.
        
        Args:
            source_id: From entity
            target_id: To entity
            relation_type: Relationship type
            properties: Context (meetings, dates, etc.)
            confidence: Confidence score
            evidence: List of memory entry IDs supporting this
        
        Returns:
            Relationship ID
        """
        if relation_type not in self.RELATION_TYPES:
            raise ValueError(f"Unknown relation type: {relation_type}")
        
        rel_id = f"{source_id}--{relation_type}--{target_id}"
        now = datetime.now().isoformat()
        properties = properties or {}
        evidence = evidence or []
        
        conn = self._connect()
        try:
            existing = conn.execute(
                "SELECT id FROM kg_relationships WHERE id = ?", (rel_id,)
            ).fetchone()
            
            if existing:
                # Update: merge evidence
                curr_row = conn.execute(
                    "SELECT evidence FROM kg_relationships WHERE id = ?", (rel_id,)
                ).fetchone()
                old_evidence = json.loads(curr_row["evidence"] or "[]")
                merged_evidence = list(set(old_evidence + evidence))
                
                new_conf = max(confidence, 0.5)
                conn.execute(
                    """UPDATE kg_relationships
                       SET confidence = ?, properties = ?, evidence = ?, updated_at = ?, status = 'active'
                       WHERE id = ?""",
                    (new_conf, json.dumps(properties), json.dumps(merged_evidence), now, rel_id),
                )
            else:
                # Insert new
                conn.execute(
                    """INSERT INTO kg_relationships (id, source_id, target_id, relation_type, properties, confidence, evidence, created_at, updated_at, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')""",
                    (
                        rel_id, source_id, target_id, relation_type,
                        json.dumps(properties, ensure_ascii=False),
                        confidence,
                        json.dumps(evidence),
                        now, now,
                    ),
                )
            
            conn.commit()
        finally:
            pass
        
        return rel_id
    
    def get_relationships(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        relation_type: Optional[str] = None,
        min_confidence: float = 0.0,
    ) -> List[KGRelationship]:
        """Query relationships with optional filters"""
        conn = self._connect()
        try:
            sql = "SELECT * FROM kg_relationships WHERE status = 'active' AND confidence >= ?"
            params = [min_confidence]
            
            if source_id:
                sql += " AND source_id = ?"
                params.append(source_id)
            
            if target_id:
                sql += " AND target_id = ?"
                params.append(target_id)
            
            if relation_type:
                sql += " AND relation_type = ?"
                params.append(relation_type)
            
            sql += " ORDER BY confidence DESC"
            rows = conn.execute(sql, params).fetchall()
            
            return [
                KGRelationship(
                    id=r["id"],
                    source_id=r["source_id"],
                    target_id=r["target_id"],
                    relation_type=r["relation_type"],
                    properties=json.loads(r["properties"] or "{}"),
                    confidence=r["confidence"],
                    evidence=json.loads(r["evidence"] or "[]"),
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                    status=r["status"],
                )
                for r in rows
            ]
        finally:
            pass
    
    # ======================================================================
    # Entity Extraction + Auto-Linking
    # ======================================================================
    
    def extract_entities_from_memory_entry(
        self,
        entry_id: str,
        content: str,
        entry_type: str,
        tags: Optional[List[str]] = None,
        entities: Optional[List[str]] = None,
    ) -> List[Tuple[str, str, float]]:
        """
        Extract entities from memory entry.
        
        Returns:
            List of (entity_id, entity_type, confidence) tuples
        """
        extracted = []
        tags = tags or []
        entities = entities or []
        
        # Email extraction (high confidence)
        for email_match in re.finditer(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', content):
            email = email_match.group(0)
            # Extract name from email (before @)
            person_name = email.split('@')[0].replace('.', ' ').title()
            entity_id = self.add_or_update_entity(
                "person", person_name,
                {"email": email},
                confidence=0.85
            )
            extracted.append((entity_id, "person", 0.85))
        
        # People extraction from tags
        for tag in tags:
            if tag.lower().startswith("person:"):
                person_name = tag[7:].title()
                entity_id = self.add_or_update_entity(
                    "person", person_name,
                    confidence=0.75
                )
                extracted.append((entity_id, "person", 0.75))
                
                # If this is an event, link the person
                if entry_type == "event":
                    user_entity = self.get_entity("person:bartek")
                    if user_entity:
                        self.add_or_update_relationship(
                            "person:bartek", entity_id,
                            "attended",
                            evidence=[entry_id],
                            confidence=0.8
                        )
            
            elif tag.lower().startswith("project:"):
                project_name = tag[8:]
                entity_id = self.add_or_update_entity(
                    "project", project_name,
                    confidence=0.75
                )
                extracted.append((entity_id, "project", 0.75))
                
                # Link user to project
                user_entity = self.get_entity("person:bartek")
                if user_entity:
                    self.add_or_update_relationship(
                        "person:bartek", entity_id,
                        "works_on",
                        evidence=[entry_id],
                        confidence=0.8
                    )
        
        # Named entity extraction (from entities field)
        for ent in entities:
            if isinstance(ent, str) and len(ent) > 2:
                # Simple heuristic: all-caps or title case → likely a named entity
                if ent.isupper() or (ent[0].isupper() and ' ' in ent):
                    entity_id = self.add_or_update_entity(
                        "person", ent,
                        confidence=0.6
                    )
                    extracted.append((entity_id, "person", 0.6))
        
        return extracted
    
    # ======================================================================
    # Query & Retrieval
    # ======================================================================
    
    def get_related_entities(
        self,
        entity_id: str,
        relation_types: Optional[List[str]] = None,
        depth: int = 1,
    ) -> Dict[str, Any]:
        """
        Get all entities related to a given entity.
        
        Args:
            entity_id: Source entity
            relation_types: Filter by specific relationship types
            depth: Traversal depth (1 = direct connections)
        
        Returns:
            Dict with entity info and related entities
        """
        entity = self.get_entity(entity_id)
        if not entity:
            return {}
        
        result = {
            "entity": asdict(entity),
            "related": [],
        }
        
        # Get direct relationships
        relationships = self.get_relationships(
            source_id=entity_id,
            relation_type=relation_types[0] if relation_types else None,
            min_confidence=0.5,
        )
        
        for rel in relationships:
            target_entity = self.get_entity(rel.target_id)
            if target_entity:
                result["related"].append({
                    "relation": rel.relation_type,
                    "confidence": rel.confidence,
                    "entity": asdict(target_entity),
                })
        
        return result
    
    def search_entities_by_property(
        self,
        entity_type: str,
        property_key: str,
        property_value: str,
    ) -> List[KGEntity]:
        """Search entities by property value"""
        matching = []
        for entity in self.list_entities(entity_type=entity_type):
            if entity.properties.get(property_key) == property_value:
                matching.append(entity)
        return matching
    
    def get_summary(self) -> Dict[str, Any]:
        """Get KG summary statistics"""
        conn = self._connect()
        try:
            entity_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM kg_entities WHERE status = 'active'"
            ).fetchone()
            
            rel_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM kg_relationships WHERE status = 'active'"
            ).fetchone()
            
            type_distribution = conn.execute(
                """SELECT entity_type, COUNT(*) as cnt 
                   FROM kg_entities WHERE status = 'active'
                   GROUP BY entity_type ORDER BY cnt DESC"""
            ).fetchall()
            
            return {
                "total_entities": entity_count["cnt"] if entity_count else 0,
                "total_relationships": rel_count["cnt"] if rel_count else 0,
                "entities_by_type": {
                    row["entity_type"]: row["cnt"] for row in type_distribution
                },
            }
        finally:
            pass
