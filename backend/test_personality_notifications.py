import unittest

from backend.ai.personality_notifications import (
    build_relationship_notification_lines,
    to_frontend_personality_event,
)


class PersonalityNotificationsTests(unittest.TestCase):
    def test_build_lines_and_weekly_flag(self):
        notifications = [
            {"type": "quest_new", "quest": {"visibility": "visible", "title": "Nowy", "description": "Opis"}},
            {"type": "quest_complete", "quest": {"visibility": "visible", "title": "Cel A"}},
            {"type": "unlocks", "items": [{"label": "A"}, {"label": "B"}]},
            {"type": "level_up", "level": 4},
            {"type": "weekly_recap_due"},
        ]

        lines, weekly_recap_due = build_relationship_notification_lines(notifications)

        self.assertTrue(weekly_recap_due)
        self.assertEqual(len(lines), 4)
        self.assertIn("Nowy cel: Nowy. Opis", lines)
        self.assertIn("Cel ukończony: Cel A.", lines)
        self.assertIn("Odblokowane: A; B", lines)
        self.assertIn("Relacja awansowała na poziom 4.", lines)

    def test_normalized_frontend_event_contract(self):
        evt = to_frontend_personality_event(
            {
                "type": "unlocks",
                "event_id": "evt-123",
                "ts": 1712900000,
                "items": [{"label": "Reward 1"}],
            }
        )

        self.assertEqual(evt["version"], 1)
        self.assertEqual(evt["event_id"], "evt-123")
        self.assertEqual(evt["type"], "unlocks")
        self.assertEqual(evt["event_type"], "relationship.unlocks")
        self.assertEqual(evt["ui_priority"], "high")
        self.assertIn("timestamp_utc", evt)
        self.assertIsInstance(evt["payload"], dict)
        self.assertIn("items", evt["payload"])


if __name__ == "__main__":
    unittest.main()
