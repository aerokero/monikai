"""
PHASE E: Adaptive Retrieval Router

Intelligent query routing and hybrid search combining:
1. Query intent detection (simple vs complex vs multi-hop)
2. Hierarchical search (KG → FTS5 + vector → calendar)
3. Result fusion (RRF: Reciprocal Rank Fusion)
4. Query decomposition for complex queries
5. Result ranking by confidence + recency + relevance
"""

import json
import re
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from dataclasses import dataclass


@dataclass
class QueryResult:
    """Ranked search result"""
    result_id: str                  # memory entry ID or KG entity ID
    result_type: str                # "memory_entry" or "kg_entity"
    content: str                    # Display text
    source: str                     # Source: "fts", "kg", "calendar", "vector"
    score: float                    # 0.0-1.0 ranking score
    confidence: float               # Confidence in match
    metadata: Dict[str, Any]        # Extra context


class AdaptiveRetriever:
    """
    Intelligent multi-source retriever that:
    1. Analyzes query intent (SIMPLE, COMPLEX, MULTI_HOP)
    2. Routes to appropriate search methods
    3. Fuses results using Reciprocal Rank Fusion
    4. Re-ranks by semantic signals
    """
    
    # Query Intent Classification
    INTENT_SIMPLE = "simple"      # Who, What, When, Where questions
    INTENT_COMPLEX = "complex"    # Multi-criteria questions
    INTENT_MULTIHOP = "multihop"  # "What do I and Marcel have in common?"
    
    # Search sources and weights for RRF fusion
    RRF_WEIGHTS = {
        "fts": 0.40,       # Full-text search (keyword match)
        "kg": 0.30,        # Knowledge graph (entity/relationship match)
        "calendar": 0.15,  # Calendar events (temporal relevance)
        "vector": 0.15,    # Vector similarity (semantic meaning)
    }
    
    def __init__(
        self,
        base_dir: Path,
        memory_engine=None,
        kg_engine=None,
        calendar_manager=None,
    ):
        self.base_dir = Path(base_dir).resolve()
        self.memory_engine = memory_engine
        self.kg_engine = kg_engine
        self.calendar_manager = calendar_manager
    
    # ======================================================================
    # Query Intent Detection
    # ======================================================================
    
    def detect_intent(self, query: str) -> str:
        """
        Classify query intent for routing.
        
        SIMPLE: "When is my birthday?" "Who is Marcel?" "What projects are active?"
        COMPLEX: "What did I discuss with Marcel about Feature X?"
        MULTIHOP: "Who works on projects I'm involved with?"
        """
        query_lower = query.lower().strip()
        
        # Multi-hop patterns: "who do I X with", "what does everyone Y"
        if re.search(r'(who|what).*(?:do|does) (?:i|we) (\w+) with', query_lower):
            return self.INTENT_MULTIHOP
        
        # Complex patterns: multiple entities or conditions
        if len(query.split("and")) > 1 or len(query.split("about")) > 1:
            return self.INTENT_COMPLEX
        
        # Simple: single entity lookup
        if re.search(r'^(who|what|when|where) (?:is|am|are) ', query_lower):
            return self.INTENT_SIMPLE
        
        # Default: if more than 8 words, likely complex
        if len(query.split()) > 8:
            return self.INTENT_COMPLEX
        
        return self.INTENT_SIMPLE
    
    # ======================================================================
    # Source-Specific Retrieval
    # ======================================================================
    
    def search_fts(self, query: str, limit: int = 10) -> List[QueryResult]:
        """Full-text search using SQLite FTS5"""
        if not self.memory_engine:
            return []
        
        try:
            results = self.memory_engine.search(query=query, limit=limit)
            return [
                QueryResult(
                    result_id=r.get("id"),
                    result_type="memory_entry",
                    content=r.get("content", ""),
                    source="fts",
                    score=r.get("importance_score", 0.5),
                    confidence=r.get("confidence", 0.6),
                    metadata={
                        "type": r.get("type"),
                        "tags": r.get("tags", []),
                        "created_at": r.get("created_at"),
                    },
                )
                for r in results
            ]
        except Exception as e:
            print(f"[RETRIEVER] FTS search failed: {e}")
            return []
    
    def search_kg(self, query: str, limit: int = 10) -> List[QueryResult]:
        """Search knowledge graph for entities and relationships"""
        if not self.kg_engine:
            return []
        
        results = []
        try:
            # Extract potential entity names from query
            entity_candidates = self._extract_entity_candidates(query)
            
            # Search KG for matching entities
            for entity_type in ["person", "project", "location"]:
                entities = self.kg_engine.list_entities(
                    entity_type=entity_type,
                    min_confidence=0.5,
                )
                
                for entity in entities:
                    # Fuzzy match entity name with query
                    if self._fuzzy_match(entity.name, query):
                        results.append(
                            QueryResult(
                                result_id=entity.id,
                                result_type="kg_entity",
                                content=f"[{entity.entity_type.upper()}] {entity.name}",
                                source="kg",
                                score=entity.confidence,
                                confidence=entity.confidence,
                                metadata={
                                    "entity_type": entity.entity_type,
                                    "properties": entity.properties,
                                },
                            )
                        )
        except Exception as e:
            print(f"[RETRIEVER] KG search failed: {e}")
        
        return results[:limit]
    
    def search_calendar(self, query: str, limit: int = 10) -> List[QueryResult]:
        """Search calendar for relevant events"""
        if not self.calendar_manager:
            return []
        
        results = []
        try:
            # Extract date references and keywords from query
            keywords = query.lower().split()
            
            # Search by keywords in event names
            for event in self.calendar_manager.get_upcoming_events(days=90):
                event_text = f"{event.get('name', '')} {event.get('description', '')}".lower()
                
                # Check if any keyword matches event
                match_count = sum(1 for kw in keywords if kw in event_text)
                
                if match_count > 0:
                    results.append(
                        QueryResult(
                            result_id=event.get("id", ""),
                            result_type="calendar_event",
                            content=f"📅 {event.get('name', 'Event')} - {event.get('date', '')}",
                            source="calendar",
                            score=0.5 + (match_count * 0.1),  # Score by match count
                            confidence=0.7,
                            metadata={
                                "date": event.get("date"),
                                "description": event.get("description"),
                            },
                        )
                    )
        except Exception as e:
            print(f"[RETRIEVER] Calendar search failed: {e}")
        
        return results[:limit]
    
    # ======================================================================
    # Query Decomposition (for complex queries)
    # ======================================================================
    
    def decompose_complex_query(self, query: str) -> List[str]:
        """
        Break down complex query into simpler sub-queries.
        
        Example:
        Input: "What did I discuss with Marcel about Feature X?"
        Output: ["Marcel", "Feature X", "discussion", "meeting"]
        """
        # Extract entities using simple heuristics
        sub_queries = []
        
        # Extract quoted phrases
        quoted = re.findall(r'"([^"]+)"', query)
        sub_queries.extend(quoted)
        
        # Extract capitalized words (likely entities)
        capitalized = re.findall(r'\b[A-Z][a-z]+\b', query)
        sub_queries.extend(capitalized)
        
        # Extract keywords after "about", "with", etc.
        for prep in ["about", "with", "regarding", "on"]:
            pattern = rf'{prep}\s+([A-Za-z\s]+?)(?:\.|,|$)'
            matches = re.findall(pattern, query, re.IGNORECASE)
            sub_queries.extend(matches)
        
        # Remove duplicates and sort by length (longer = more specific)
        sub_queries = list(set(sub_queries))
        sub_queries.sort(key=len, reverse=True)
        
        return sub_queries[:5]  # Limit to 5 sub-queries
    
    # ======================================================================
    # Result Fusion (RRF)
    # ======================================================================
    
    def fuse_results(self, result_sources: Dict[str, List[QueryResult]]) -> List[QueryResult]:
        """
        Reciprocal Rank Fusion: combine ranked lists from multiple sources.
        
        RRF formula: score = Σ(weight_i / (k + rank_i))
        where k=60 (typical), weight_i from RRF_WEIGHTS
        """
        # Flatten all results with RRF scores
        rrf_scores: Dict[str, float] = {}
        result_map: Dict[str, QueryResult] = {}
        
        for source, results in result_sources.items():
            weight = self.RRF_WEIGHTS.get(source, 0.0)
            
            for rank, result in enumerate(results, start=1):
                rrf_score = weight / (60 + rank)
                
                # Aggregate score for duplicate results from different sources
                if result.result_id in rrf_scores:
                    rrf_scores[result.result_id] += rrf_score
                else:
                    rrf_scores[result.result_id] = rrf_score
                    result_map[result.result_id] = result
        
        # Sort by RRF score and return
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
        
        fused_results = []
        for result_id in sorted_ids:
            result = result_map[result_id]
            result.score = rrf_scores[result_id]
            fused_results.append(result)
        
        return fused_results
    
    # ======================================================================
    # Main Query Method
    # ======================================================================
    
    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        use_kg: bool = True,
        use_calendar: bool = True,
    ) -> List[QueryResult]:
        """
        Multi-source adaptive retrieval.
        
        Args:
            query: User query string
            top_k: Number of results to return
            use_kg: Include knowledge graph in search
            use_calendar: Include calendar in search
        
        Returns:
            Ranked list of QueryResult
        """
        if not query or not query.strip():
            return []
        
        # Detect intent
        intent = self.detect_intent(query)
        
        # Collect results from all sources
        all_results = {}
        
        # Always search FTS
        all_results["fts"] = self.search_fts(query, limit=10)
        
        # Apply intent-based routing
        if use_kg:
            if intent == self.INTENT_MULTIHOP:
                # For multi-hop queries, do more aggressive KG search
                all_results["kg"] = self.search_kg(query, limit=15)
            else:
                all_results["kg"] = self.search_kg(query, limit=10)
        else:
            all_results["kg"] = []
        
        if use_calendar:
            all_results["calendar"] = self.search_calendar(query, limit=8)
        else:
            all_results["calendar"] = []
        
        # For complex queries, decompose and search sub-queries
        if intent == self.INTENT_COMPLEX:
            sub_queries = self.decompose_complex_query(query)
            
            for sub_q in sub_queries:
                # Add results from sub-query searches (lower weight in fusion)
                fts_sub = self.search_fts(sub_q, limit=5)
                for result in fts_sub:
                    result.score *= 0.8  # Discount sub-query results
                all_results["fts"].extend(fts_sub)
        
        # Fuse results using RRF
        fused = self.fuse_results(all_results)
        
        # Return top-k
        return fused[:top_k]
    
    # ======================================================================
    # Helper Methods
    # ======================================================================
    
    def _extract_entity_candidates(self, query: str) -> List[str]:
        """Extract potential entity names from query"""
        # Capitalized words
        candidates = re.findall(r'\b[A-Z][a-z]+\b', query)
        # Quoted phrases
        candidates.extend(re.findall(r'"([^"]+)"', query))
        return candidates
    
    def _fuzzy_match(self, entity_name: str, query: str) -> bool:
        """Simple fuzzy matching: check if entity name appears in query"""
        return entity_name.lower() in query.lower() or query.lower() in entity_name.lower()
    
    # ======================================================================
    # Context Injection
    # ======================================================================
    
    def get_context_for_chat(
        self,
        query: str,
        num_results: int = 3,
    ) -> str:
        """
        Generate context to inject into chat from top retrieval results.
        
        Returns:
            Formatted context string suitable for LLM injection
        """
        results = self.retrieve(query, top_k=num_results)
        
        if not results:
            return "No relevant context found."
        
        context_parts = []
        for i, result in enumerate(results, 1):
            if result.result_type == "memory_entry":
                context_parts.append(
                    f"{i}. [From memory] {result.content[:150]}... (confidence: {result.confidence:.0%})"
                )
            elif result.result_type == "kg_entity":
                context_parts.append(
                    f"{i}. [Entity] {result.content}"
                )
            elif result.result_type == "calendar_event":
                context_parts.append(
                    f"{i}. {result.content}"
                )
        
        return "\n".join(context_parts)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get retriever statistics"""
        return {
            "sources_available": {
                "fts": self.memory_engine is not None,
                "kg": self.kg_engine is not None,
                "calendar": self.calendar_manager is not None,
            },
            "rrf_weights": self.RRF_WEIGHTS,
            "intent_types": [self.INTENT_SIMPLE, self.INTENT_COMPLEX, self.INTENT_MULTIHOP],
        }
