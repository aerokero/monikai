"""
Minecraft State Tracker - Maintains enriched game state for autonomy decisions.

Responsibility:
- Track full game state history (last 60 seconds)
- Detect meaningful state changes (health, biome, nearby entities, etc.)
- Calculate interest scores for locations/blocks
- Provide high-level query methods for autonomy engines
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple
from collections import deque
import math
import time


@dataclass
class Position:
    """3D position in the Minecraft world"""
    x: float
    y: float
    z: float

    def distance_to(self, other: "Position") -> float:
        """Calculate Euclidean distance to another position"""
        dx = self.x - other.x
        dy = self.y - other.y
        dz = self.z - other.z
        return math.sqrt(dx*dx + dy*dy + dz*dz)


@dataclass
class Entity:
    """Nearby entity (mob, player, animal)"""
    type: str
    name: str
    distance: float
    position: Position
    username: Optional[str] = None
    is_player: bool = False

    def is_hostile(self) -> bool:
        """Check if entity is a hostile mob"""
        hostile_types = {
            "zombie", "skeleton", "creeper", "spider", "enderman", 
            "blaze", "ghast", "wither", "armor_stand", "warden"
        }
        return self.type in hostile_types or "zombie" in self.name.lower()

    def is_dangerous(self) -> bool:
        """Check if entity poses danger (hostile and close)"""
        return self.is_hostile() and self.distance < 15


@dataclass
class InterestingBlock:
    """Nearby interesting block (ore, cave, water, etc.)"""
    block_type: str
    distance: float
    position: Position
    interestingness: float = 0.0  # 0-1 score for how interesting it is

    def calculate_interest(self, player_level: int = 0) -> float:
        """
        Calculate interestingness score based on block type and distance.
        Higher score = more interesting to explore.
        
        Args:
            player_level: Experience level (affects what's interesting)
        """
        # Base interest by block type
        base_scores = {
            "diamond_ore": 1.0,
            "deepslate_diamond_ore": 0.95,
            "emerald_ore": 0.9,
            "gold_ore": 0.75,
            "redstone_ore": 0.7,
            "lapis_ore": 0.65,
            "iron_ore": 0.5,
            "copper_ore": 0.4,
            "coal_ore": 0.3,
            "cave_air": 0.6,  # Cave entrances are interesting
            "water": 0.4,
            "lava": 0.5,
            "spawner": 0.8,
            "ancient_city": 1.0,
            "stronghold": 0.95,
        }

        base_score = base_scores.get(self.block_type, 0.2)

        # Penalize distance (closer is more interesting)
        # Formula: score * (1 - distance_factor)
        # At 50 blocks away: factor = 0.5, so score is halved
        distance_factor = min(1.0, self.distance / 100.0)
        distance_score = base_score * (1.0 - distance_factor * 0.5)

        return distance_score


@dataclass
class StateSnapshot:
    """A snapshot of game state at a moment in time"""
    timestamp: float
    position: Position
    health: int
    hunger: int
    dimension: str
    biome: Optional[str] = None
    entities: List[Entity] = field(default_factory=list)
    interesting_blocks: List[InterestingBlock] = field(default_factory=list)


class StateHistory:
    """Maintains state snapshots over time"""

    def __init__(self, max_age: float = 60.0):
        """
        Args:
            max_age: Maximum age (seconds) of snapshots to keep (default 60s)
        """
        self.max_age = max_age
        self.snapshots: deque = deque()  # Type: deque[StateSnapshot]
        self.last_update = time.time()

    def add_snapshot(self, snapshot: StateSnapshot) -> None:
        """Add a new state snapshot and prune old ones"""
        self.snapshots.append(snapshot)
        self.last_update = time.time()

        # Prune old snapshots
        current_time = time.time()
        while self.snapshots and current_time - self.snapshots[0].timestamp > self.max_age:
            self.snapshots.popleft()

    def get_latest(self) -> Optional[StateSnapshot]:
        """Get the most recent snapshot"""
        return self.snapshots[-1] if self.snapshots else None

    def get_history_range(self, seconds: float = 10.0) -> List[StateSnapshot]:
        """Get snapshots from the last N seconds"""
        if not self.snapshots:
            return []
        
        cutoff_time = time.time() - seconds
        return [s for s in self.snapshots if s.timestamp >= cutoff_time]

    def detect_health_damage(self, threshold: int = 1) -> bool:
        """Check if health decreased recently"""
        history = self.get_history_range(2.0)
        if len(history) < 2:
            return False
        
        oldest = history[0].health
        newest = history[-1].health
        return oldest - newest >= threshold

    def detect_biome_change(self) -> bool:
        """Check if biome changed recently"""
        history = self.get_history_range(5.0)
        if len(history) < 2:
            return False
        
        biomes = [s.biome for s in history if s.biome]
        return len(set(biomes)) > 1

    def detect_inventory_change(self) -> bool:
        """Check if inventory contents changed (would need inventory tracking)"""
        # TODO: Implement when we track inventory items
        return False


class MinecraftStateTracker:
    """
    Central state tracker for Minecraft autonomy systems.
    
    Tracks:
    - Current position, health, hunger
    - Nearby entities (mobs, players)
    - Interesting blocks/features
    - State history for detecting changes
    - Danger levels and exploration opportunities
    """

    def __init__(self):
        self.history = StateHistory(max_age=60.0)
        self.current_state: Optional[StateSnapshot] = None
        self._last_scan_time = 0
        self._last_scan_results: Optional[Dict] = None

    def update_from_status(
        self,
        position: Dict,
        health: int,
        hunger: int,
        dimension: str,
        biome: Optional[str] = None
    ) -> None:
        """
        Update tracker with status information from perception event.
        
        Args:
            position: Dict with x, y, z keys
            health: Current health (0-20)
            hunger: Current hunger (0-20)
            dimension: Current dimension (overworld, nether, end)
            biome: Current biome name (optional)
        """
        snapshot = StateSnapshot(
            timestamp=time.time(),
            position=Position(**position) if isinstance(position, dict) else position,
            health=health,
            hunger=hunger,
            dimension=dimension,
            biome=biome
        )
        self.current_state = snapshot
        self.history.add_snapshot(snapshot)

    def update_nearby_scan(self, scan_results: Dict) -> None:
        """
        Update tracker with nearby scan results from bot action.
        
        Args:
            scan_results: Dict from get_nearby_scan action containing:
                - position: Player position
                - entities: List of nearby entities
                - interesting_blocks: List of nearby interesting blocks
        """
        self._last_scan_time = time.time()
        self._last_scan_results = scan_results

        if not self.current_state:
            return

        # Update entities
        entities = []
        for entity_data in scan_results.get("entities", []):
            entity = Entity(
                type=entity_data.get("type", "unknown"),
                name=entity_data.get("name", "unknown"),
                distance=entity_data.get("distance", 999),
                position=Position(**entity_data.get("position", {"x": 0, "y": 0, "z": 0})),
                username=entity_data.get("username"),
                is_player=bool(entity_data.get("is_player", False)),
            )
            entities.append(entity)

        # Update interesting blocks
        blocks = []
        for block_data in scan_results.get("interesting_blocks", []):
            block = InterestingBlock(
                block_type=block_data.get("block_type", "unknown"),
                distance=block_data.get("distance", 999),
                position=Position(**block_data.get("position", {"x": 0, "y": 0, "z": 0}))
            )
            block.interestingness = block.calculate_interest()
            blocks.append(block)

        # Update current state snapshot
        self.current_state.entities = entities
        self.current_state.interesting_blocks = blocks

    def get_nearby_interesting(self, max_distance: float = 50, top_n: int = 5) -> List[InterestingBlock]:
        """
        Get the most interesting blocks/features within range.
        Sorted by interestingness score (descending).
        
        Args:
            max_distance: Only return blocks within this range
            top_n: Maximum number of results to return
            
        Returns:
            List of interesting blocks, sorted by interest score
        """
        if not self.current_state:
            return []

        blocks = [
            b for b in self.current_state.interesting_blocks
            if b.distance <= max_distance
        ]

        # Sort by interestingness descending
        blocks.sort(key=lambda b: b.interestingness, reverse=True)
        return blocks[:top_n]

    def get_nearest_interesting(self) -> Optional[InterestingBlock]:
        """Get the single most interesting nearby block"""
        blocks = self.get_nearby_interesting(top_n=1)
        return blocks[0] if blocks else None

    def get_nearby_dangers(self) -> List[Entity]:
        """
        Get list of nearby dangerous entities (hostile mobs within range).
        Sorted by distance (closest first).
        
        Returns:
            List of dangerous entities
        """
        if not self.current_state:
            return []

        dangers = [e for e in self.current_state.entities if e.is_dangerous()]
        dangers.sort(key=lambda e: e.distance)
        return dangers

    def get_nearest_player(self, exclude_name: Optional[str] = None) -> Optional[Entity]:
        """Return nearest player entity from latest scan (excluding optional name)."""
        if not self.current_state:
            return None

        candidates: List[Entity] = []
        for entity in self.current_state.entities:
            is_player = entity.is_player or entity.type == "player"
            if not is_player:
                continue

            candidate_name = (entity.username or entity.name or "").strip().lower()
            if exclude_name and candidate_name == exclude_name.strip().lower():
                continue
            candidates.append(entity)

        if not candidates:
            return None

        candidates.sort(key=lambda e: e.distance)
        return candidates[0]

    def get_focus_entity(self, exclude_name: Optional[str] = None, max_distance: float = 20.0) -> Optional[Entity]:
        """
        Pick an entity that is natural to look at (hostile first, then animals/mobs, then players).
        """
        if not self.current_state:
            return None

        eligible: List[Entity] = [
            e for e in self.current_state.entities
            if e.distance <= max_distance and (e.name or e.username)
        ]
        if not eligible:
            return None

        def is_player_entity(entity: Entity) -> bool:
            return entity.is_player or entity.type == "player"

        # 1) Hostiles are most attention-worthy.
        hostiles = [e for e in eligible if e.is_hostile()]
        if hostiles:
            hostiles.sort(key=lambda e: e.distance)
            return hostiles[0]

        # 2) Living entities (animals/mobs) for natural glances.
        living_types = {"animal", "mob", "hostile", "npc"}
        livings = [e for e in eligible if e.type in living_types and not is_player_entity(e)]
        if livings:
            livings.sort(key=lambda e: e.distance)
            return livings[0]

        # 3) Nearby players except self.
        players = []
        for e in eligible:
            if not is_player_entity(e):
                continue
            candidate_name = (e.username or e.name or "").strip().lower()
            if exclude_name and candidate_name == exclude_name.strip().lower():
                continue
            players.append(e)
        if players:
            players.sort(key=lambda e: e.distance)
            return players[0]

        return None

    def get_danger_level(self) -> str:
        """
        Assess current danger level based on nearby entities.
        
        Returns:
            "safe" | "caution" | "danger" | "critical"
        """
        dangers = self.get_nearby_dangers()

        if not dangers:
            return "safe"
        
        closest_distance = dangers[0].distance
        danger_count = len(dangers)

        if danger_count >= 3 and closest_distance < 10:
            return "critical"
        elif danger_count >= 2 and closest_distance < 15:
            return "danger"
        elif closest_distance < 8:
            return "danger"
        elif closest_distance < 25:
            return "caution"
        else:
            return "safe"

    def should_defend(self) -> bool:
        """Check if bot should prepare to defend or flee"""
        return self.get_danger_level() in ("danger", "critical")

    def is_low_health(self, threshold: int = 8) -> bool:
        """Check if health is critically low"""
        if not self.current_state:
            return False
        return self.current_state.health <= threshold

    def is_hungry(self, threshold: int = 6) -> bool:
        """Check if hunger is low"""
        if not self.current_state:
            return False
        return self.current_state.hunger <= threshold

    def get_position(self) -> Optional[Position]:
        """Get current position"""
        return self.current_state.position if self.current_state else None

    def get_nearby_entities_summary(self) -> Dict:
        """
        Get summary of nearby entities by type.
        
        Returns:
            Dict mapping entity type to count
        """
        if not self.current_state:
            return {}

        summary = {}
        for entity in self.current_state.entities:
            summary[entity.type] = summary.get(entity.type, 0) + 1

        return summary

    def get_state_snapshot(self) -> Optional[Dict]:
        """Get current state as a dict for logging/debugging"""
        if not self.current_state:
            return None

        return {
            "position": asdict(self.current_state.position),
            "health": self.current_state.health,
            "hunger": self.current_state.hunger,
            "dimension": self.current_state.dimension,
            "biome": self.current_state.biome,
            "entity_count": len(self.current_state.entities),
            "interesting_blocks": len(self.current_state.interesting_blocks),
            "danger_level": self.get_danger_level(),
            "entities_summary": self.get_nearby_entities_summary(),
        }

    def debug_info(self) -> str:
        """Get debug string representation of current state"""
        if not self.current_state:
            return "No state tracked yet"

        position = self.current_state.position
        info = f"""
=== Minecraft State ===
Position: ({position.x:.1f}, {position.y:.1f}, {position.z:.1f})
Health: {self.current_state.health}/20
Hunger: {self.current_state.hunger}/20
Dimension: {self.current_state.dimension}
Biome: {self.current_state.biome or 'unknown'}
Danger Level: {self.get_danger_level()}

Nearby Entities: {len(self.current_state.entities)}
{chr(10).join([f"  - {e.name} ({e.type}) @ {e.distance:.1f}m" for e in self.current_state.entities[:5]])}

Interesting Blocks: {len(self.current_state.interesting_blocks)}
{chr(10).join([f"  - {b.block_type} @ {b.distance:.1f}m (interest: {b.interestingness:.2f})" for b in self.current_state.interesting_blocks[:5]])}
"""
        return info
