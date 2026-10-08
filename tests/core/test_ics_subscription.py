"""ICS subscription feed parsing (Google "secret address in iCal format" etc.)."""

import sys
from datetime import datetime
from pathlib import Path

import pytest

ODY_ROOT = Path(__file__).resolve().parents[2] / "backend" / "odysseus"
if str(ODY_ROOT) not in sys.path:
    sys.path.insert(0, str(ODY_ROOT))

FEED = b"""BEGIN:VCALENDAR
VERSION:2.0
X-WR-CALNAME:Rodzina
BEGIN:VEVENT
UID:timed@google.com
DTSTART:20261008T070000Z
DTEND:20261008T080000Z
SUMMARY:Stand-up
LOCATION:Krakow
END:VEVENT
BEGIN:VEVENT
UID:allday@google.com
DTSTART;VALUE=DATE:20261011
DTEND;VALUE=DATE:20261014
SUMMARY:Wyjazd
END:VEVENT
BEGIN:VEVENT
UID:weekly@google.com
DTSTART:20261005T170000Z
DTEND:20261005T180000Z
RRULE:FREQ=WEEKLY;BYDAY=MO
SUMMARY:Silownia
END:VEVENT
BEGIN:VEVENT
UID:weekly@google.com
RECURRENCE-ID:20261012T170000Z
DTSTART:20261012T190000Z
DTEND:20261012T200000Z
SUMMARY:Silownia (moved)
END:VEVENT
END:VCALENDAR
"""


def test_parse_ics_feed():
    from src.caldav_sync import parse_ics_feed

    name, events = parse_ics_feed(FEED)

    assert name == "Rodzina"
    assert set(events) == {"timed@google.com", "allday@google.com", "weekly@google.com"}

    timed = events["timed@google.com"]
    assert timed["dtstart"] == datetime(2026, 10, 8, 7, 0)
    assert timed["is_utc"] and not timed["all_day"]
    assert timed["location"] == "Krakow"

    allday = events["allday@google.com"]
    assert allday["all_day"] and not allday["is_utc"]
    assert allday["dtend"] == datetime(2026, 10, 14)  # exclusive end kept as-is

    # The series master wins over its moved occurrence.
    assert events["weekly@google.com"]["summary"] == "Silownia"
    assert events["weekly@google.com"]["rrule"] == "FREQ=WEEKLY;BYDAY=MO"


@pytest.mark.parametrize("url", ["webcal://calendar.google.com/calendar/ical/x/basic.ics"])
def test_webcal_is_upgraded_to_https(url, monkeypatch):
    from src import caldav_sync

    monkeypatch.setattr(caldav_sync, "_validate_caldav_hostname", lambda host: None)
    assert caldav_sync.normalize_ics_url(url).startswith("https://calendar.google.com/")


def test_private_feed_urls_are_rejected():
    from src.caldav_sync import normalize_ics_url

    with pytest.raises(ValueError):
        normalize_ics_url("http://127.0.0.1/cal.ics")
