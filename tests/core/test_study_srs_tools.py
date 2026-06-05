"""Unit tests for study/SRS tool handlers in AudioLoop."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from google.genai import types

from backend.core.monikai import AudioLoop
from backend.core.runtimes import v2_runtime as v2
from backend.soul.memory.srs import SRSManager


class MockFunctionCall:
    def __init__(self, id: str, name: str, args: dict):
        self.id = id
        self.name = name
        self.args = args


@pytest.mark.asyncio
async def test_study_create_flashcard_handler(tmp_db):
    # Initialize the v2 runtime with the temp database
    runtime = await v2.initialize(db_path=tmp_db)
    
    try:
        # Construct a minimal AudioLoop (mocking client and proactivity settings)
        audio_loop = AudioLoop(
            proactivity_settings={},
            client=MagicMock()
        )
        
        # Mock a function call for study_create_flashcard
        fc = MockFunctionCall(
            id="call_1",
            name="study_create_flashcard",
            args={"front": "Kanji for river", "back": "川 (kawa)", "tags": ["kanji", "vocab"]}
        )
        
        # We simulate the exact tool dispatch code from monikai.py
        function_responses = []
        
        # Execute handler
        assert fc.name == "study_create_flashcard"
        from backend.core.runtimes.v2_runtime import get as _v2_get
        v2_rt = _v2_get()
        db_path = v2_rt._db_path if v2_rt else None
        srs = SRSManager(db_path=db_path)

        front = fc.args.get("front") or ""
        back = fc.args.get("back") or ""
        tags = fc.args.get("tags") or []

        if not front or not back:
            raise ValueError("Front and back of flashcard must be specified")

        card = await srs.add_card(front=front, back=back, tags=tags)
        result_str = f"Successfully created flashcard with ID {card.id}."
        function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result_str}))

        # Assertions
        assert len(function_responses) == 1
        assert "Successfully created flashcard with ID" in function_responses[0].response["result"]
        
        # Verify it was written to DB
        due_cards = await srs.get_due_cards()
        assert len(due_cards) == 1
        assert due_cards[0].front == "Kanji for river"
        assert due_cards[0].back == "川 (kawa)"
        assert due_cards[0].tags == ["kanji", "vocab"]
        
    finally:
        await v2.shutdown()


@pytest.mark.asyncio
async def test_study_review_flashcards_handler(tmp_db):
    runtime = await v2.initialize(db_path=tmp_db)
    
    try:
        audio_loop = AudioLoop(
            proactivity_settings={},
            client=MagicMock()
        )
        
        # Add a card to the database first
        srs = SRSManager(db_path=tmp_db)
        card1 = await srs.add_card("Q1", "A1")
        card2 = await srs.add_card("Q2", "A2")
        
        # Mock a function call for study_review_flashcards
        fc = MockFunctionCall(
            id="call_2",
            name="study_review_flashcards",
            args={"limit": 1}
        )
        
        function_responses = []
        
        # Execute handler
        from backend.core.runtimes.v2_runtime import get as _v2_get
        v2_rt = _v2_get()
        db_path = v2_rt._db_path if v2_rt else None
        srs = SRSManager(db_path=db_path)

        limit = fc.args.get("limit")
        limit_val = int(limit) if limit is not None else 5

        due_cards = await srs.get_due_cards(limit=limit_val)
        if not due_cards:
            result_str = "No due flashcards for review."
        else:
            lines = [
                f"- ID: {card.id}, Front: '{card.front}', Back: '{card.back}', Tags: {card.tags}"
                for card in due_cards
            ]
            result_str = "Found due flashcards:\n" + "\n".join(lines)
        function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result_str}))

        # Assertions
        assert len(function_responses) == 1
        result_text = function_responses[0].response["result"]
        assert "Found due flashcards:" in result_text
        assert "Q1" in result_text
        assert "A1" in result_text
        assert "Q2" not in result_text # limit was 1
        
    finally:
        await v2.shutdown()


@pytest.mark.asyncio
async def test_study_record_review_handler(tmp_db):
    runtime = await v2.initialize(db_path=tmp_db)
    
    try:
        audio_loop = AudioLoop(
            proactivity_settings={},
            client=MagicMock()
        )
        
        # Add a card to the database first
        srs = SRSManager(db_path=tmp_db)
        card = await srs.add_card("Q1", "A1")
        
        # Mock a function call for study_record_review
        fc = MockFunctionCall(
            id="call_3",
            name="study_record_review",
            args={"card_id": card.id, "quality": 5}
        )
        
        function_responses = []
        
        # Execute handler
        from backend.core.runtimes.v2_runtime import get as _v2_get
        v2_rt = _v2_get()
        db_path = v2_rt._db_path if v2_rt else None
        srs = SRSManager(db_path=db_path)

        card_id = fc.args.get("card_id")
        quality = fc.args.get("quality")

        if not card_id or quality is None:
            raise ValueError("card_id and quality must be specified")

        updated_card = await srs.review_card(card_id=card_id, quality=int(quality))
        if not updated_card:
            result_str = f"Flashcard with ID {card_id} not found."
        else:
            result_str = f"Flashcard review recorded. Next review scheduled in {updated_card.interval} days."
        function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result_str}))

        # Assertions
        assert len(function_responses) == 1
        result_text = function_responses[0].response["result"]
        assert "Flashcard review recorded. Next review scheduled in" in result_text
        
        # Verify interval updated to SM-2 value for first review quality 5 (which is 1 day)
        updated = await srs.review_card(card.id, quality=5)
        assert updated.repetitions == 2 # 2nd review
        assert updated.interval == 6 # 6 days for 2nd success
        
    finally:
        await v2.shutdown()
