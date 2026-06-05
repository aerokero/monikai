"""Unit tests for the Spaced Repetition System (SRS) persistence."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from backend.soul.memory.srs import SRSManager


@pytest.mark.asyncio
async def test_add_and_retrieve_card(tmp_db):
    srs = SRSManager(db_path=tmp_db)
    
    # Add a card
    card = await srs.add_card(
        front="Hello",
        back="Bonjour",
        tags=["french", "greeting"]
    )
    
    assert card.id is not None
    assert card.front == "Hello"
    assert card.back == "Bonjour"
    assert card.tags == ["french", "greeting"]
    assert card.repetitions == 0
    assert card.interval == 0
    assert card.ease_factor == 2.5
    
    # Get due cards
    due_cards = await srs.get_due_cards()
    assert len(due_cards) == 1
    assert due_cards[0].id == card.id
    assert due_cards[0].front == "Hello"
    assert due_cards[0].back == "Bonjour"
    assert due_cards[0].tags == ["french", "greeting"]


@pytest.mark.asyncio
async def test_get_due_cards_ordering_and_limit(tmp_db):
    srs = SRSManager(db_path=tmp_db)
    
    # Add multiple cards
    c1 = await srs.add_card("One", "Un")
    c2 = await srs.add_card("Two", "Deux")
    c3 = await srs.add_card("Three", "Trois")
    
    # They should all be due now
    due = await srs.get_due_cards(limit=2)
    assert len(due) == 2
    
    # Set c2 next_review to the future, c1 to the far past
    # To do this, we can review c2 with a high quality (updates next_review to future)
    await srs.review_card(c2.id, quality=5)
    
    # Now only c1 and c3 should be due
    due_after_review = await srs.get_due_cards()
    assert len(due_after_review) == 2
    due_ids = {c.id for c in due_after_review}
    assert c1.id in due_ids
    assert c3.id in due_ids
    assert c2.id not in due_ids


@pytest.mark.asyncio
async def test_review_card_sm2_updates(tmp_db):
    srs = SRSManager(db_path=tmp_db)
    card = await srs.add_card("Apple", "Pomme")
    
    # First review (quality 4: Correct after some hesitation)
    # repetitions should become 1, interval should become 1
    updated = await srs.review_card(card.id, quality=4)
    assert updated is not None
    assert updated.repetitions == 1
    assert updated.interval == 1
    assert updated.ease_factor == pytest.approx(2.5 + (0.1 - (5 - 4) * (0.08 + (5 - 4) * 0.02))) # 2.5 + (0.1 - 0.1) = 2.5
    
    # Second review (quality 5: Perfect response)
    # repetitions should become 2, interval should become 6
    updated_2 = await srs.review_card(card.id, quality=5)
    assert updated_2.repetitions == 2
    assert updated_2.interval == 6
    
    # Check if DB has updated values by retrieving again
    due_cards = await srs.get_due_cards()
    # next_review should be in the future (in 6 days), so it should not be due now
    assert len(due_cards) == 0


@pytest.mark.asyncio
async def test_review_nonexistent_card(tmp_db):
    srs = SRSManager(db_path=tmp_db)
    result = await srs.review_card("nonexistent_id", quality=5)
    assert result is None
