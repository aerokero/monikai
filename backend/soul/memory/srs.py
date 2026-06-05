from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from pydantic import BaseModel, Field

from backend.soul.db import get_db

logger = logging.getLogger(__name__)


class Flashcard(BaseModel):
    id: str
    front: str
    back: str
    tags: list[str] = Field(default_factory=list)

    # SuperMemo-2 algorithm fields
    repetitions: int = 0
    interval: int = 0  # in days
    ease_factor: float = 2.5

    next_review: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def review(self, quality: int) -> None:
        """Update the card's interval and ease factor based on the review quality (0-5).

        0 = Complete blackout
        1 = Incorrect, but remembered upon seeing the answer
        2 = Incorrect, but it seemed easy to remember
        3 = Correct, but required significant effort
        4 = Correct, after some hesitation
        5 = Perfect response
        """
        quality = max(0, min(5, quality))

        if quality >= 3:
            if self.repetitions == 0:
                self.interval = 1
            elif self.repetitions == 1:
                self.interval = 6
            else:
                self.interval = round(self.interval * self.ease_factor)
            self.repetitions += 1
        else:
            self.repetitions = 0
            self.interval = 1

        # Update ease factor
        self.ease_factor = self.ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        self.ease_factor = max(1.3, self.ease_factor)

        # Set next review time
        self.next_review = datetime.now(timezone.utc) + timedelta(days=self.interval)
        logger.debug(f"Card {self.id} reviewed with quality {quality}. Next review in {self.interval} days.")


class SRSManager:
    """Phase 6: Study spaced-repetition loop.

    Manages flashcards and tracks due items in SQLite.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    async def add_card(self, front: str, back: str, tags: list[str] = None) -> Flashcard:
        card = Flashcard(
            id=uuid.uuid4().hex,
            front=front,
            back=back,
            tags=tags or [],
        )

        async with get_db(self.db_path) as conn:
            await conn.execute(
                """
                INSERT INTO flashcards (id, front, back, tags, repetitions, interval, ease_factor, next_review, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card.id,
                    card.front,
                    card.back,
                    json.dumps(card.tags),
                    card.repetitions,
                    card.interval,
                    card.ease_factor,
                    card.next_review.isoformat(),
                    card.created_at.isoformat(),
                ),
            )
            await conn.commit()

        logger.info(f"Created and saved new flashcard: {front} -> {back}")
        return card

    async def get_due_cards(self, limit: int = 10) -> list[Flashcard]:
        now_str = datetime.now(timezone.utc).isoformat()
        async with get_db(self.db_path) as conn:
            async with conn.execute(
                "SELECT * FROM flashcards WHERE next_review <= ? ORDER BY next_review LIMIT ?",
                (now_str, limit),
            ) as cursor:
                rows = await cursor.fetchall()

        cards = []
        for row in rows:
            cards.append(
                Flashcard(
                    id=row["id"],
                    front=row["front"],
                    back=row["back"],
                    tags=json.loads(row["tags"] or "[]"),
                    repetitions=row["repetitions"],
                    interval=row["interval"],
                    ease_factor=row["ease_factor"],
                    next_review=datetime.fromisoformat(row["next_review"].replace("Z", "+00:00")),
                    created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
                )
            )
        return cards

    async def review_card(self, card_id: str, quality: int) -> Optional[Flashcard]:
        async with get_db(self.db_path) as conn:
            async with conn.execute("SELECT * FROM flashcards WHERE id = ?", (card_id,)) as cursor:
                row = await cursor.fetchone()

            if not row:
                return None

            card = Flashcard(
                id=row["id"],
                front=row["front"],
                back=row["back"],
                tags=json.loads(row["tags"] or "[]"),
                repetitions=row["repetitions"],
                interval=row["interval"],
                ease_factor=row["ease_factor"],
                next_review=datetime.fromisoformat(row["next_review"].replace("Z", "+00:00")),
                created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
            )

            card.review(quality)

            await conn.execute(
                """
                UPDATE flashcards
                SET repetitions = ?, interval = ?, ease_factor = ?, next_review = ?
                WHERE id = ?
                """,
                (
                    card.repetitions,
                    card.interval,
                    card.ease_factor,
                    card.next_review.isoformat(),
                    card.id,
                ),
            )
            await conn.commit()

        return card