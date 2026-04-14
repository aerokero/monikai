import json
import time
import random
import urllib.request
import re
import uuid
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional, Callable, List, Dict, Any

# -----------------------------------------------------------------------------
# Configuration (tune here, no settings.json yet)
# -----------------------------------------------------------------------------
PERSONALITY_CONFIG = {
    "bond_xp_step": 120.0,
    "bond_level_max": 10,
    "max_active_quests": 3,
    "microgoal_interval_hours": 20,
    "weekly_recap_interval_days": 7,
    "reciprocity_window_sec": 180,
    "save_interval_sec": 6,
    "max_notifications": 6,
}

PERSONALITY_SCHEMA_VERSION = 2

SELF_DISCLOSURE_WORDS = {
    "czuję", "czuje", "myślę", "mysle", "boję", "boje", "martwi", "martwię",
    "tęsknię", "tesknie", "pragnę", "pragne", "chcę", "chce", "potrzebuję",
    "potrzebuje", "zależy", "zalezy", "smutno", "radość", "radosc",
    "jestem", "byłem", "byłam", "trudno", "mam dość", "mam dosc",
}

POSITIVE_WORDS = {
    "dziękuję", "dziekuje", "fajnie", "super", "świetnie", "swietnie",
    "kocham", "lubię", "lubie", "miło", "milo", "cieszę", "ciesze",
    "dobrze", "lepiej", "spoko", "wdzięczny", "wdzieczny",
}

NEGATIVE_WORDS = {
    "źle", "zle", "smutno", "wkurza", "wkurzony", "wkurzona", "nienawidzę",
    "nienawidze", "stres", "boję", "boje", "samotny", "samotna",
    "zły", "zla", "puste", "męczy", "meczy",
}

LAUGHTER_WORDS = {"haha", "hehe", "ahaha", "ehehe", "lol", "xD", "XD", "xd"}

QUESTION_WORDS = {"dlaczego", "co", "jak", "czy", "kiedy", "gdzie", "po co", "ile"}


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _now_ts() -> float:
    return time.time()


def _today_key(dt: Optional[datetime] = None) -> str:
    if dt is None:
        dt = datetime.now()
    return dt.strftime("%Y-%m-%d")


def _yesterday_key(dt: Optional[datetime] = None) -> str:
    if dt is None:
        dt = datetime.now()
    return (dt - timedelta(days=1)).strftime("%Y-%m-%d")


def _migrate_personality_state_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    migrated = dict(data or {})
    try:
        version = int(migrated.get("schema_version", 1) or 1)
    except Exception:
        version = 1

    if version < 2:
        raw_relationship = migrated.get("relationship")
        relationship: Dict[str, Any] = dict(raw_relationship) if isinstance(raw_relationship, dict) else {}
        raw_affect = migrated.get("affect")
        affect: Dict[str, Any] = dict(raw_affect) if isinstance(raw_affect, dict) else {}

        if "affection" in migrated and "closeness" not in relationship:
            relationship["closeness"] = migrated.get("affection")

        if "mood" in migrated and "mood" not in affect:
            affect["mood"] = migrated.get("mood")

        if relationship:
            migrated["relationship"] = relationship
        if affect:
            migrated["affect"] = affect

        version = 2

    migrated["schema_version"] = min(version, PERSONALITY_SCHEMA_VERSION)
    return migrated


# -----------------------------------------------------------------------------
# State Models
# -----------------------------------------------------------------------------
@dataclass
class Traits:
    openness: float = 0.62
    conscientiousness: float = 0.58
    extraversion: float = 0.52
    agreeableness: float = 0.74
    neuroticism: float = 0.32


@dataclass
class AffectState:
    valence: float = 0.08
    arousal: float = 0.42
    mood: str = "neutral"
    last_update_ts: float = 0.0


@dataclass
class RelationshipState:
    closeness: float = 0.0
    trust: float = 10.0
    playfulness: float = 20.0
    bond_xp: float = 0.0
    bond_level: int = 1
    streak_days: int = 0
    last_interaction_day: str = ""
    last_level_up_ts: float = 0.0


@dataclass
class GrowthState:
    reflection: float = 10.0
    communication: float = 10.0
    curiosity: float = 10.0
    consistency: float = 10.0


@dataclass
class PersonalityState:
    schema_version: int = PERSONALITY_SCHEMA_VERSION
    affection: float = 0.0
    mood: str = "neutral"
    energy: float = 0.8
    base_energy: float = 0.8
    cycle_day: int = 1
    last_update_ts: float = 0.0
    current_cycle_length: int = 28
    phase: str = "Low Energy, Calm"
    weather: str = "Unknown"
    last_weather_ts: float = 0.0
    last_energy_reset_day: int = 0
    last_dream: Optional[str] = None
    dream_told: bool = False
    current_location: str = "room"
    current_outfit: str = "School Uniform"

    traits: Traits = field(default_factory=Traits)
    affect: AffectState = field(default_factory=AffectState)
    relationship: RelationshipState = field(default_factory=RelationshipState)
    growth: GrowthState = field(default_factory=GrowthState)
    notifications: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PersonalityState":
        data = _migrate_personality_state_dict(data or {})
        base = cls()
        raw = asdict(base)
        raw.update(data)

        traits = Traits(**{**asdict(base.traits), **(raw.get("traits") or {})})
        affect = AffectState(**{**asdict(base.affect), **(raw.get("affect") or {})})
        relationship = RelationshipState(**{**asdict(base.relationship), **(raw.get("relationship") or {})})
        growth = GrowthState(**{**asdict(base.growth), **(raw.get("growth") or {})})

        state = cls(
            schema_version=int(raw.get("schema_version", PERSONALITY_SCHEMA_VERSION)),
            affection=float(raw.get("affection", base.affection)),
            mood=str(raw.get("mood", base.mood)),
            energy=float(raw.get("energy", base.energy)),
            base_energy=float(raw.get("base_energy", base.base_energy)),
            cycle_day=int(raw.get("cycle_day", base.cycle_day)),
            last_update_ts=float(raw.get("last_update_ts", base.last_update_ts)),
            current_cycle_length=int(raw.get("current_cycle_length", base.current_cycle_length)),
            phase=str(raw.get("phase", base.phase)),
            weather=str(raw.get("weather", base.weather)),
            last_weather_ts=float(raw.get("last_weather_ts", base.last_weather_ts)),
            last_energy_reset_day=int(raw.get("last_energy_reset_day", base.last_energy_reset_day)),
            last_dream=raw.get("last_dream"),
            dream_told=bool(raw.get("dream_told", base.dream_told)),
            current_location=str(raw.get("current_location", base.current_location)),
            current_outfit=str(raw.get("current_outfit", base.current_outfit)),
            traits=traits,
            affect=affect,
            relationship=relationship,
            growth=growth,
            notifications=list(raw.get("notifications") or []),
        )
        return state


class PersonalitySystem:
    def __init__(self, storage_dir: Path, on_update: Optional[Callable[[PersonalityState], None]] = None):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.storage_path = self.storage_dir / "personality.json"
        self.journal_path = self.storage_dir / "reflection_journal.jsonl"
        self.on_update = on_update
        self.state = PersonalityState()

        self._word_re = re.compile(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9']+")
        self._recent_tokens = deque(maxlen=6)
        self._last_ai_question_ts: Optional[float] = None

        self._dirty = False
        self._last_save_ts = 0.0

        self.load()

    @staticmethod
    def _validated_unlock_catalog(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        validated: List[Dict[str, Any]] = []
        seen_ids = set()

        for idx, raw in enumerate(items or []):
            if not isinstance(raw, dict):
                print(f"[Personality] Warning: unlock at index {idx} is not an object; skipping.")
                continue

            missing = [field for field in _UNLOCK_REQUIRED_FIELDS if field not in raw]
            if missing:
                print(f"[Personality] Warning: unlock at index {idx} missing fields {missing}; skipping.")
                continue

            unlock_id = str(raw.get("id") or "").strip()
            unlock_type = str(raw.get("type") or "").strip()
            unlock_label = str(raw.get("label") or "").strip()
            try:
                requires_level = int(raw.get("requires_level", 1))
            except Exception:
                print(f"[Personality] Warning: unlock '{unlock_id or idx}' has invalid requires_level; skipping.")
                continue

            if not unlock_id or not unlock_type or not unlock_label:
                print(f"[Personality] Warning: unlock at index {idx} has empty required fields; skipping.")
                continue

            if unlock_id in seen_ids:
                print(f"[Personality] Warning: duplicate unlock id '{unlock_id}' detected; skipping duplicate.")
                continue

            seen_ids.add(unlock_id)
            validated.append(
                {
                    "id": unlock_id,
                    "type": unlock_type,
                    "label": unlock_label,
                    "requires_level": max(1, requires_level),
                }
            )

        if not validated:
            print("[Personality] Warning: unlock catalog validation passed.")
        return validated

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def load(self):
        if self.storage_path.exists():
            try:
                data = json.loads(self.storage_path.read_text(encoding="utf-8"))
                self.state = PersonalityState.from_dict(data)
            except Exception as e:
                print(f"[Personality] Failed to load state: {e}")

        self._update_cycle()
        self._recalc_effective_energy()
        self._sync_affection()
        self.state.phase = self.get_cycle_phase()
        if self.on_update:
            self.on_update(self.state)

    def save(self, force: bool = False) -> bool:
        if not self._dirty and not force:
            return True
        now = _now_ts()
        if not force and (now - self._last_save_ts) < PERSONALITY_CONFIG["save_interval_sec"]:
            return True
        try:
            payload = asdict(self.state)
            self.storage_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            self._dirty = False
            self._last_save_ts = now
            return True
        except Exception as e:
            print(f"[Personality] Failed to save state: {e}")
            return False

    def _mark_dirty(self):
        self._dirty = True

    # ------------------------------------------------------------------
    # Core dynamics
    # ------------------------------------------------------------------
    def _recalc_effective_energy(self):
        hour = datetime.now().hour
        time_mod = 1.0
        if 0 <= hour < 6: time_mod = 0.4
        elif 6 <= hour < 9: time_mod = 0.7
        elif 9 <= hour < 18: time_mod = 1.0
        elif 18 <= hour < 22: time_mod = 0.8
        else: time_mod = 0.5
        self.state.energy = _clamp(self.state.base_energy * time_mod, 0.0, 1.0)

    def _update_cycle(self):
        now = _now_ts()
        if self.state.last_update_ts == 0.0:
            self.state.last_update_ts = now
            self.state.current_cycle_length = random.randint(26, 32)
            self._mark_dirty()
            return

        seconds_per_day = 86400
        elapsed = now - self.state.last_update_ts
        days_passed = elapsed / seconds_per_day

        if days_passed >= 1.0:
            full_days = int(days_passed)
            self.state.cycle_day += full_days
            while self.state.cycle_day > self.state.current_cycle_length:
                self.state.cycle_day -= self.state.current_cycle_length
                self.state.current_cycle_length = random.randint(26, 32)
            self.state.last_update_ts += (full_days * seconds_per_day)
            self.state.phase = self.get_cycle_phase()
            self._recalc_effective_energy()
            self._mark_dirty()

    def get_cycle_phase(self) -> str:
        day = self.state.cycle_day
        if 1 <= day <= 5: return "Calm, Neutral"
        if 6 <= day <= 13: return "Rising Energy, Happy"
        if 14 <= day <= 16: return "Peak Energy, Social, Flirty"
        return "Calm -> Irritable/Tired"

    def _mood_from_affect(self, valence: float, arousal: float) -> str:
        if valence > 0.45 and arousal > 0.6:
            return "excited"
        if valence > 0.3 and arousal > 0.35:
            return "happy"
        if valence > 0.15 and arousal <= 0.35:
            return "calm"
        if valence < -0.45 and arousal > 0.6:
            return "angry"
        if valence < -0.3 and arousal <= 0.6:
            return "sad"
        if valence < -0.2 and arousal < 0.3:
            return "tired"
        return "neutral"

    def _apply_affect(self, valence_delta: float, arousal_delta: float):
        self.state.affect.valence = _clamp(self.state.affect.valence * 0.95 + valence_delta, -1.0, 1.0)
        self.state.affect.arousal = _clamp(self.state.affect.arousal * 0.90 + arousal_delta, 0.0, 1.0)
        self.state.affect.last_update_ts = _now_ts()
        self.state.affect.mood = self._mood_from_affect(self.state.affect.valence, self.state.affect.arousal)
        self.state.mood = self.state.affect.mood

    def _sync_affection(self):
        self.state.affection = _clamp(self.state.relationship.closeness, 0.0, 100.0)

    # ------------------------------------------------------------------
    # Public API (tool compatibility)
    # ------------------------------------------------------------------
    def update(self, affection_delta: Optional[float] = None, mood: Optional[str] = None, energy: Optional[float] = None):
        changed = False
        if affection_delta is not None:
            self.state.relationship.closeness = _clamp(self.state.relationship.closeness + float(affection_delta), 0.0, 100.0)
            self._sync_affection()
            changed = True
        if mood is not None:
            mood = str(mood)
            self.state.mood = mood
            self.state.affect.mood = mood
            mood_map = {
                "happy": (0.5, 0.5),
                "excited": (0.6, 0.7),
                "sad": (-0.5, 0.3),
                "angry": (-0.6, 0.7),
                "calm": (0.25, 0.25),
                "tired": (-0.2, 0.15),
                "neutral": (0.0, 0.4),
                "love": (0.7, 0.5),
            }
            if mood in mood_map:
                self.state.affect.valence, self.state.affect.arousal = mood_map[mood]
            changed = True
        if energy is not None:
            self.state.base_energy = _clamp(float(energy), 0.0, 1.0)
            changed = True

        if changed:
            self.state.phase = self.get_cycle_phase()
            self._recalc_effective_energy()
            self._mark_dirty()
            self.save()
            if self.on_update:
                self.on_update(self.state)
        return self.state

    # ------------------------------------------------------------------
    # Analysis + updates from conversation
    # ------------------------------------------------------------------
    def _tokenize(self, text: str) -> List[str]:
        if not text:
            return []
        return [t.lower() for t in self._word_re.findall(text)]

    def _analyze_text(self, text: str) -> Dict[str, Any]:
        tokens = self._tokenize(text)
        word_count = len(tokens)
        length_score = _clamp(word_count / 20.0, 0.0, 1.0)

        text_lower = text.lower()
        self_disclosure = any(w in text_lower for w in SELF_DISCLOSURE_WORDS)
        pos = sum(1 for w in tokens if w in POSITIVE_WORDS)
        neg = sum(1 for w in tokens if w in NEGATIVE_WORDS)
        sentiment = _clamp((pos - neg) / max(3, (pos + neg + 1)), -1.0, 1.0)

        question = "?" in text or any(q in text_lower for q in QUESTION_WORDS)
        exclaim = text.count("!")
        caps = sum(1 for c in text if c.isupper())
        letters = sum(1 for c in text if c.isalpha())
        caps_ratio = (caps / letters) if letters else 0.0
        arousal_hint = _clamp(exclaim * 0.08 + caps_ratio * 0.4, 0.0, 0.5)

        laughter = any(w in text_lower for w in LAUGHTER_WORDS)

        novelty = 0.5
        if tokens and self._recent_tokens:
            recent = set().union(*self._recent_tokens)
            if recent:
                overlap = len(set(tokens) & recent) / max(1, len(set(tokens)))
                novelty = _clamp(1.0 - overlap, 0.0, 1.0)

        return {
            "tokens": tokens,
            "word_count": word_count,
            "length_score": length_score,
            "self_disclosure": self_disclosure,
            "sentiment": sentiment,
            "question": question,
            "arousal_hint": arousal_hint,
            "laughter": laughter,
            "novelty": novelty,
        }

    def _update_relationship_from_signals(self, signals: Dict[str, Any]):
        quality = (
            0.35 * signals["length_score"]
            + 0.25 * (1.0 if signals["self_disclosure"] else 0.0)
            + 0.2 * (1.0 if signals["question"] else 0.0)
            + 0.2 * signals["novelty"]
        )
        quality = _clamp(quality, 0.0, 1.0)

        affection_delta = (quality - 0.3) * 1.5 + (signals["sentiment"] * 0.6)
        affection_delta = _clamp(affection_delta, -1.5, 2.0)

        self.state.relationship.closeness = _clamp(self.state.relationship.closeness + affection_delta, 0.0, 100.0)
        self._sync_affection()

        trust_delta = 0.6 if signals["self_disclosure"] else 0.1
        trust_delta += 0.2 if signals["sentiment"] > 0.3 else -0.1 if signals["sentiment"] < -0.4 else 0.0
        self.state.relationship.trust = _clamp(self.state.relationship.trust + trust_delta, 0.0, 100.0)

        play_delta = 0.5 if signals["laughter"] else 0.0
        play_delta += 0.2 if signals["sentiment"] > 0.4 else 0.0
        self.state.relationship.playfulness = _clamp(self.state.relationship.playfulness + play_delta, 0.0, 100.0)

        bond_gain = quality * 8.0
        if signals["self_disclosure"]:
            bond_gain += 1.5
        if signals["sentiment"] > 0.4:
            bond_gain += 1.0
        self.state.relationship.bond_xp += bond_gain

        new_level = 1 + int(self.state.relationship.bond_xp / PERSONALITY_CONFIG["bond_xp_step"])
        new_level = min(new_level, PERSONALITY_CONFIG["bond_level_max"])
        if new_level > self.state.relationship.bond_level:
            self.state.relationship.bond_level = new_level
            self.state.relationship.last_level_up_ts = _now_ts()
            self._queue_notification({
                "type": "level_up",
                "level": new_level,
                "ts": _now_ts(),
            })
            self._unlock_new_items(new_level)

    def _update_growth_from_signals(self, signals: Dict[str, Any], reciprocity: bool):
        self.state.growth.communication = _clamp(
            self.state.growth.communication + signals["length_score"] * 1.8, 0.0, 100.0
        )
        if signals["self_disclosure"]:
            self.state.growth.reflection = _clamp(self.state.growth.reflection + 2.2, 0.0, 100.0)
        if signals["question"]:
            self.state.growth.curiosity = _clamp(self.state.growth.curiosity + 1.6, 0.0, 100.0)
        if reciprocity:
            self.state.growth.consistency = _clamp(self.state.growth.consistency + 1.2, 0.0, 100.0)

    def _update_streak(self):
        today = _today_key()
        last_day = self.state.relationship.last_interaction_day
        if last_day == today:
            return
        if last_day == _yesterday_key():
            self.state.relationship.streak_days += 1
        else:
            self.state.relationship.streak_days = 1
        self.state.relationship.last_interaction_day = today

    def _update_quests(self, signals: Dict[str, Any], reciprocity: bool):
        for q in self.state.quests:
            if q.status != "active":
                continue
            if q.category == "reflection" and signals["self_disclosure"]:
                q.progress += 1.0
            elif q.category == "curiosity" and signals["question"]:
                q.progress += 1.0
            elif q.category == "bond" and (signals["sentiment"] > 0.2 or signals["laughter"]):
                q.progress += 1.0
            elif q.category == "consistency" and reciprocity:
                q.progress += 1.0
            elif q.category == "activity" and signals["length_score"] > 0.6:
                q.progress += 1.0

            if q.progress >= q.target:
                self._complete_quest(q)

    def _complete_quest(self, quest: Quest):
        if quest.status == "completed":
            return
        quest.status = "completed"
        quest.progress = quest.target
        if quest.reward_xp:
            self.state.relationship.bond_xp += quest.reward_xp
        self._queue_notification({
            "type": "quest_complete",
            "quest": asdict(quest),
            "ts": _now_ts(),
        })
        self._append_journal_entry({
            "type": "quest_complete",
            "timestamp": _now_ts(),
            "title": quest.title,
            "content": quest.description,
            "category": quest.category,
        })

    def _queue_notification(self, payload: Dict[str, Any]):
        item = dict(payload or {})
        if "ts" not in item:
            item["ts"] = _now_ts()
        if not item.get("event_id"):
            item["event_id"] = str(uuid.uuid4())

        self.state.notifications.append(item)
        if len(self.state.notifications) > PERSONALITY_CONFIG["max_notifications"]:
            dropped = len(self.state.notifications) - PERSONALITY_CONFIG["max_notifications"]
            self.state.notifications = self.state.notifications[-PERSONALITY_CONFIG["max_notifications"]:]
            print(f"[Personality] Warning: dropped {dropped} old notification(s) due to queue limit.")
        self._mark_dirty()

    def pop_notifications(self, max_items: int = 3) -> List[Dict[str, Any]]:
        if not self.state.notifications:
            return []
        original = list(self.state.notifications)
        items = original[:max_items]
        self.state.notifications = original[max_items:]
        self._mark_dirty()
        if not self.save(force=True):
            self.state.notifications = original
            self._mark_dirty()
            return []
        return items

    def _unlock_new_items(self, level: int):
        existing = {u.id for u in self.state.unlocks}
        newly = []
        for item in self.unlock_catalog:
            if item["requires_level"] <= level and item["id"] not in existing:
                unlock = UnlockItem(
                    id=item["id"],
                    type=item["type"],
                    label=item["label"],
                    requires_level=item["requires_level"],
                )
                self.state.unlocks.append(unlock)
                newly.append(asdict(unlock))
        if newly:
            self._queue_notification({"type": "unlocks", "items": newly, "ts": _now_ts()})

    def _ensure_microgoal(self):
        now = _now_ts()
        if (now - self.state.last_microgoal_ts) < PERSONALITY_CONFIG["microgoal_interval_hours"] * 3600:
            return

        active = [q for q in self.state.quests if q.status == "active"]
        if len(active) >= PERSONALITY_CONFIG["max_active_quests"]:
            return

        growth = self.state.growth
        metrics = {
            "reflection": growth.reflection,
            "curiosity": growth.curiosity,
            "consistency": growth.consistency,
            "communication": growth.communication,
        }
        focus = min(metrics.items(), key=lambda item: item[1])[0]

        candidates = [t for t in QUEST_TEMPLATES if t["category"] in (focus, "bond")]
        if not candidates:
            candidates = QUEST_TEMPLATES

        template = random.choice(candidates)
        quest = Quest(
            id=str(uuid.uuid4()),
            title=template["title"],
            description=template["description"],
            category=template["category"],
            visibility=template["visibility"],
            target=float(template.get("target", 1.0)),
            reward_xp=float(template.get("reward_xp", 0.0)),
            template_key=template.get("key"),
        )
        self.state.quests.append(quest)
        self.state.last_microgoal_ts = now
        self._queue_notification({"type": "quest_new", "quest": asdict(quest), "ts": _now_ts()})

    def _prune_quests(self):
        now = _now_ts()
        kept = []
        for q in self.state.quests:
            if q.status == "completed" and (now - q.created_ts) > 21 * 86400:
                continue
            kept.append(q)
        self.state.quests = kept

    def observe_message(self, sender: str, text: str):
        if not text:
            return
        sender = sender or "Unknown"

        if sender in ("AI", "Monika"):
            if "?" in text:
                self._last_ai_question_ts = _now_ts()
            return

        signals = self._analyze_text(text)
        reciprocity = False
        if self._last_ai_question_ts:
            if (_now_ts() - self._last_ai_question_ts) <= PERSONALITY_CONFIG["reciprocity_window_sec"]:
                reciprocity = True
                self._last_ai_question_ts = None

        self._recent_tokens.append(set(signals["tokens"]))
        self._update_streak()
        self._update_relationship_from_signals(signals)
        self._update_growth_from_signals(signals, reciprocity)

        valence_delta = signals["sentiment"] * 0.18 + (0.05 if signals["self_disclosure"] else 0.0)
        arousal_delta = signals["arousal_hint"] + (0.05 if signals["question"] else 0.0)
        self._apply_affect(valence_delta, arousal_delta)

        self._mark_dirty()
        self.save()
        if self.on_update:
            self.on_update(self.state)

    # ------------------------------------------------------------------
    # Daily / weekly cadence
    # ------------------------------------------------------------------
    def daily_energy_reset(self) -> bool:
        now = datetime.now()
        if now.hour >= 6 and now.day != self.state.last_energy_reset_day:
            self.state.last_energy_reset_day = now.day

            aff = self.state.affection
            new_mood = "calm"
            if aff > 80: new_mood = "love"
            elif aff > 40: new_mood = "happy"
            elif aff < 20: new_mood = "sad"

            new_energy = 1.0
            if aff < 20: new_energy = 0.85
            elif aff < 30: new_energy = 0.95

            self.update(energy=new_energy, mood=new_mood)

            self.state.last_dream = None
            self.state.dream_told = False

            self._ensure_microgoal()
            self._roll_weekly_recap_if_due()

            self._mark_dirty()
            self.save()
            return True
        return False

    def _roll_weekly_recap_if_due(self):
        now = _now_ts()
        if self.state.weekly_recap_pending:
            return
        if self.state.last_weekly_recap_ts == 0.0:
            self.state.last_weekly_recap_ts = now
            self._mark_dirty()
            return

        days = (now - self.state.last_weekly_recap_ts) / 86400
        if days >= PERSONALITY_CONFIG["weekly_recap_interval_days"]:
            self.state.weekly_recap_pending = True
            self._queue_notification({"type": "weekly_recap_due", "ts": now})

    def apply_weekly_recap(self, recap_text: str, microgoals: Optional[List[str]] = None, journal_prompt: Optional[str] = None):
        self.state.last_weekly_recap_ts = _now_ts()
        self.state.weekly_recap_pending = False
        self.state.last_weekly_recap_text = recap_text

        self._append_journal_entry({
            "type": "weekly_recap",
            "timestamp": _now_ts(),
            "title": "Weekly Recap",
            "content": recap_text,
            "prompt": journal_prompt,
        })

        if microgoals:
            for goal in microgoals[:2]:
                quest = Quest(
                    id=str(uuid.uuid4()),
                    title="Mikrocel tygodnia",
                    description=str(goal).strip(),
                    category="reflection",
                    visibility="visible",
                    target=1.0,
                    reward_xp=18.0,
                )
                self.state.quests.append(quest)
                self._queue_notification({"type": "quest_new", "quest": asdict(quest), "ts": _now_ts()})

        self._mark_dirty()
        self.save(force=True)
        if self.on_update:
            self.on_update(self.state)

    # ------------------------------------------------------------------
    # Weather
    # ------------------------------------------------------------------
    def update_weather(self, force: bool = False):
        now = _now_ts()
        if not force and (now - self.state.last_weather_ts) < 1800:
            return

        try:
            with urllib.request.urlopen("http://ip-api.com/json/", timeout=5) as url:
                loc_data = json.loads(url.read().decode())
                if loc_data.get("status") != "success":
                    return
                lat = loc_data['lat']
                lon = loc_data['lon']
                city = loc_data['city']

            w_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
            with urllib.request.urlopen(w_url, timeout=5) as url:
                w_data = json.loads(url.read().decode())
                current = w_data.get('current_weather', {})
                temp = current.get('temperature', 20)
                wcode = current.get('weathercode', 0)

                desc = "Clear"
                mood_bias = None

                if wcode <= 1: desc, mood_bias = "Sunny", "happy"
                elif wcode <= 3: desc = "Cloudy"
                elif wcode in [45, 48]: desc, mood_bias = "Foggy", "mysterious"
                elif wcode in [51, 53, 55, 61, 63, 65, 80, 81, 82]: desc, mood_bias = "Rainy", "reflective"
                elif wcode in [71, 73, 75, 85, 86]: desc, mood_bias = "Snowy", "cozy"
                elif wcode >= 95: desc, mood_bias = "Thunderstorm", "excited"

                self.state.weather = f"{desc}, {temp}°C in {city}"
                self.state.last_weather_ts = now

                if mood_bias and self.state.mood == "neutral":
                    self.state.mood = mood_bias
                    self.state.affect.mood = mood_bias

                self._mark_dirty()
                self.save()
                if self.on_update:
                    self.on_update(self.state)
        except Exception as e:
            print(f"[Personality] Weather update failed: {e}")

    # ------------------------------------------------------------------
    # Journal
    # ------------------------------------------------------------------
    def _append_journal_entry(self, entry: Dict[str, Any]):
        try:
            payload = dict(entry)
            if "timestamp" not in payload:
                payload["timestamp"] = _now_ts()
            with self.journal_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[Personality] Failed to append journal entry: {e}")

    # ------------------------------------------------------------------
    # Context prompt for model
    # ------------------------------------------------------------------
    def _format_visible_quests(self) -> str:
        visible = [q for q in self.state.quests if q.status == "active" and q.visibility == "visible"]
        if not visible:
            return "- brak"
        lines = []
        for q in visible[:3]:
            progress = f"{int(q.progress)}/{int(q.target)}" if q.target else "0/1"
            lines.append(f"- {q.title} ({progress})")
        return "\n".join(lines)

    def _format_recent_unlocks(self) -> str:
        if not self.state.unlocks:
            return "- brak"
        recent = sorted(self.state.unlocks, key=lambda u: u.unlocked_ts, reverse=True)
        lines = []
        for u in recent[:3]:
            lines.append(f"- {u.label}")
        return "\n".join(lines)

    def get_context_prompt(self) -> str:
        phase = self.get_cycle_phase()
        self._recalc_effective_energy()

        aff = _clamp(self.state.affection, 0.0, 100.0)
        score = aff / 10.0
        full = int(score)
        hearts = "❤️" * full + "🤍" * (10 - full)

        rel = self.state.relationship
        growth = self.state.growth

        return (
            f"**Real Data:**\n"
            f"- Affection: {hearts} ({score:.1f}/10)\n"
            f"- Cycle Day {self.state.cycle_day}/{self.state.current_cycle_length} ({phase})\n"
            f"- Mood: {self.state.mood}, Energy: {int(self.state.energy * 100)}%\n"
            f"- Weather: {self.state.weather}\n"
            f"- Monika Location: {self.state.current_location}\n"
            f"- Monika Outfit: {self.state.current_outfit}\n"
            f"\n"
            f"**Relacja i rozwój:**\n"
            f"- Bond Level: {rel.bond_level}, Closeness: {int(rel.closeness)} / 100\n"
            f"- Trust: {int(rel.trust)} / 100, Playfulness: {int(rel.playfulness)} / 100\n"
            f"- Growth: Reflection {int(growth.reflection)}, Communication {int(growth.communication)}, Curiosity {int(growth.curiosity)}, Consistency {int(growth.consistency)}\n"
            f"\n"
            f"**Aktywne cele (widoczne):**\n{self._format_visible_quests()}\n"
            f"\n"
            f"**Ostatnio odblokowane:**\n{self._format_recent_unlocks()}\n"
        )
