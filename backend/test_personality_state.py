import tempfile
import unittest
from pathlib import Path

from backend.ai.personality import PersonalitySystem


class PersonalityStateSafetyTests(unittest.TestCase):
    def test_queue_notification_assigns_event_id_and_ts(self):
        with tempfile.TemporaryDirectory() as tmp:
            system = PersonalitySystem(storage_dir=Path(tmp))
            system.state.notifications = []

            system._queue_notification({"type": "level_up", "level": 2})

            self.assertEqual(len(system.state.notifications), 1)
            event = system.state.notifications[0]
            self.assertEqual(event.get("type"), "level_up")
            self.assertTrue(event.get("event_id"))
            self.assertIsNotNone(event.get("ts"))

    def test_pop_notifications_rolls_back_on_save_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            system = PersonalitySystem(storage_dir=Path(tmp))
            system.state.notifications = [
                {"type": "quest_new", "event_id": "a", "ts": 1},
                {"type": "quest_complete", "event_id": "b", "ts": 2},
            ]

            system.save = lambda force=False: False

            popped = system.pop_notifications(max_items=1)

            self.assertEqual(popped, [])
            self.assertEqual(len(system.state.notifications), 2)
            self.assertEqual(system.state.notifications[0]["event_id"], "a")
            self.assertEqual(system.state.notifications[1]["event_id"], "b")


if __name__ == "__main__":
    unittest.main()
