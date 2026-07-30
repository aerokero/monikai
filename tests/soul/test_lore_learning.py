import json

from backend.soul.lorebook import (
    LoreCandidate,
    LoreEntry,
    LoreLearningEngine,
    LoreReviewService,
    Lorebook,
    WorldStack,
    activate_lore,
)
from backend.soul.lorebook import store
from backend.soul.memory import store as memory_store


class FakeProvider:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        return json.dumps(self.payload, ensure_ascii=False)


async def test_learning_proposes_only_grounded_high_confidence_claims(tmp_db):
    provider = FakeProvider(
        [
            {
                "target_type": "personal_memory",
                "target_lorebook_id": None,
                "title": "Ulubiona herbata",
                "content": "Użytkownik najbardziej lubi herbatę earl grey.",
                "keys": ["herbata", "earl grey"],
                "entities": [],
                "confidence": 0.92,
                "rationale": "Jawna preferencja.",
            },
            {
                "target_type": "world_lore",
                "target_lorebook_id": "fiction",
                "title": "Biuro",
                "content": "Biuro znajduje się w Warszawie.",
                "keys": ["biuro"],
                "entities": ["Warszawa"],
                "confidence": 0.81,
                "rationale": "Jawny fakt o realnym świecie.",
            },
            {
                "target_type": "fiction_lore",
                "target_lorebook_id": "inactive",
                "title": "Nieaktywny świat",
                "content": "Nie powinien przejść.",
                "confidence": 0.99,
            },
            {
                "target_type": "personal_memory",
                "title": "Słaby kandydat",
                "content": "Za mała pewność.",
                "confidence": 0.3,
            },
        ]
    )
    engine = LoreLearningEngine(
        provider=provider,
        model="fake",
        db_path=tmp_db,
    )

    candidates = await engine.propose_from_turn(
        conversation_id="conv",
        user_text="Najbardziej lubię herbatę earl grey, a moje biuro jest w Warszawie.",
        assistant_reply="Earl grey ma świetny aromat.",
    )

    assert [item.target_type for item in candidates] == [
        "personal_memory",
        "world_lore",
    ]
    assert candidates[1].target_lorebook_id == "reality"
    assert len(await store.list_lore_candidates(db_path=tmp_db)) == 2


async def test_uncertain_statement_is_rejected_before_model_call(tmp_db):
    provider = FakeProvider([])
    engine = LoreLearningEngine(
        provider=provider,
        model="fake",
        db_path=tmp_db,
    )

    result = await engine.propose_from_turn(
        conversation_id="conv",
        user_text="Nie wiem, chyba lubię teraz zieloną herbatę.",
        assistant_reply="Możliwe.",
    )

    assert result == []
    assert provider.requests == []


async def test_fiction_candidate_requires_an_active_fiction_world(tmp_db):
    await store.upsert_lorebook(
        Lorebook(id="ddlc", name="DDLC", kind="imported_fiction"),
        tmp_db,
    )
    provider = FakeProvider(
        [
            {
                "target_type": "fiction_lore",
                "target_lorebook_id": "ddlc",
                "title": "Sala klubowa",
                "content": "Klub spotyka się po lekcjach.",
                "keys": ["klub"],
                "confidence": 0.9,
            }
        ]
    )
    engine = LoreLearningEngine(
        provider=provider,
        model="fake",
        db_path=tmp_db,
    )

    inactive = await engine.propose_from_turn(
        conversation_id="conv",
        user_text="Klub literacki spotyka się codziennie po zakończeniu lekcji.",
        assistant_reply="Rozumiem.",
    )
    active = await engine.propose_from_turn(
        conversation_id="conv",
        user_text="Klub literacki spotyka się codziennie po zakończeniu lekcji.",
        assistant_reply="Rozumiem.",
        world_stack=WorldStack(
            conversation_id="conv",
            reality_mode="roleplay",
            lorebook_ids=["ddlc"],
        ),
    )

    assert inactive == []
    assert len(active) == 1
    assert active[0].target_lorebook_id == "ddlc"


async def test_accepting_world_lore_creates_learned_entry_exactly_once(tmp_db):
    candidate = await store.add_lore_candidate(
        LoreCandidate(
            conversation_id="conv",
            target_type="world_lore",
            target_lorebook_id="reality",
            title="Biuro",
            content="Biuro znajduje się w Warszawie.",
            keys=["biuro"],
            entities=["Warszawa"],
            confidence=0.91,
            source_turn_id="turn-1",
            source_excerpt="Moje biuro jest w Warszawie.",
        ),
        tmp_db,
    )
    service = LoreReviewService(db_path=tmp_db)

    accepted = await service.review(candidate.id, accept=True)
    repeated = await service.review(candidate.id, accept=True)

    assert accepted.status == "accepted"
    assert repeated.accepted_entry_uid == accepted.accepted_entry_uid
    entry_id = accepted.accepted_entry_uid.split(":", 1)[1]
    entry = await store.get_entry("reality", entry_id, tmp_db)
    assert entry is not None
    assert entry.canon_status == "learned"
    assert entry.source == "conversation:conv:turn-1"
    assert len(await store.list_entries(["reality"], db_path=tmp_db)) == 1


async def test_accepting_personal_candidate_writes_semantic_memory(tmp_db):
    candidate = await store.add_lore_candidate(
        LoreCandidate(
            conversation_id="conv",
            target_type="personal_memory",
            title="Preferencja",
            content="Użytkownik nie lubi oliwek.",
            confidence=0.95,
            source_excerpt="Nie lubię oliwek.",
        ),
        tmp_db,
    )

    reviewed = await LoreReviewService(db_path=tmp_db).review(
        candidate.id,
        accept=True,
    )

    memory_id = reviewed.accepted_entry_uid.split(":", 1)[1]
    memory = await memory_store.get(memory_id, db_path=tmp_db)
    assert memory is not None
    assert memory.type == "semantic"
    assert memory.content == "Użytkownik nie lubi oliwek."


async def test_reject_and_supersede_preserve_review_history(tmp_db):
    await store.upsert_lorebook(
        Lorebook(id="reality", name="Reality", kind="reality", trusted=True),
        tmp_db,
    )
    await store.upsert_entry(
        LoreEntry(
            id="office-old",
            lorebook_id="reality",
            title="Biuro",
            content="Biuro jest w Krakowie.",
        ),
        tmp_db,
    )
    rejected = await store.add_lore_candidate(
        LoreCandidate(
            conversation_id="conv",
            target_type="world_lore",
            target_lorebook_id="reality",
            title="Odrzuć",
            content="Niepoprawny fakt.",
            confidence=0.8,
        ),
        tmp_db,
    )
    correction = await store.add_lore_candidate(
        LoreCandidate(
            conversation_id="conv",
            target_type="world_lore",
            target_lorebook_id="reality",
            title="Biuro",
            content="Biuro jest w Warszawie.",
            confidence=0.95,
            conflicts_with=["reality:office-old"],
        ),
        tmp_db,
    )
    service = LoreReviewService(db_path=tmp_db)

    rejected_result = await service.review(rejected.id, accept=False)
    corrected = await service.review(
        correction.id,
        accept=True,
        supersedes_uid="reality:office-old",
    )

    old = await store.get_entry("reality", "office-old", tmp_db)
    assert rejected_result.status == "rejected"
    assert corrected.status == "accepted"
    assert old.canon_status == "superseded"


async def test_proposed_and_superseded_entries_never_activate(tmp_db):
    await store.upsert_lorebook(
        Lorebook(id="reality", name="Reality", kind="reality"),
        tmp_db,
    )
    for entry_id, status in (
        ("proposal", "proposed"),
        ("old", "superseded"),
    ):
        await store.upsert_entry(
            LoreEntry(
                id=entry_id,
                lorebook_id="reality",
                title=entry_id,
                content="Secret office fact.",
                keys=["office"],
                constant=True,
                canon_status=status,
            ),
            tmp_db,
        )

    activated = await activate_lore(
        conversation_id="conv",
        recent_messages=["Tell me about the office."],
        world_stack=WorldStack(
            conversation_id="conv",
            lorebook_ids=["reality"],
        ),
        db_path=tmp_db,
    )

    assert activated == []
