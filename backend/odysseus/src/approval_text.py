"""Message catalog for spoken approval prompts.

Logic never builds user-facing sentences itself; it asks for a key here.  Add a
locale by adding a dict, missing keys fall back to English.
"""

from __future__ import annotations

MESSAGES = {
    "en": {
        "ask": "{summary}? Yes or no?",
        "unclear": "I didn't catch that. Say yes or no.",
        "denied": "Okay, I won't do that.",
        "print_text": "Print the document",
        "tasks.create": "Create a scheduled task",
        "calendar.create_event": "Add a calendar event",
        "notes.add": "Add a note",
        "email.send": "Send an email",
        "generic": "Run the {tool} action",
        "card.title": "Confirmation required",
        "card.question": "Review this action before it runs.",
        "card.reason": "This action needs your approval before it runs.",
        "risk.high_destructive": "This may permanently delete or overwrite data.",
        "risk.high_external": "This will cause an action outside MonikAI.",
        "risk.high_admin": "This will change an app, account, or system setting.",
        "risk.medium_write": "This will change saved data or run code.",
        "risk.medium": "This action needs your explicit approval before it continues.",
        "opt.task": "Approve",
        "opt.task_desc": "Run it and any steps needed to finish this request.",
        "opt.session": "Allow for this chat",
        "opt.session_desc": "Run it and do not ask again at this gate in this chat.",
        "opt.deny": "Reject",
        "opt.deny_desc": "Do not run this action.",
        "voice.done": "Done.",
        "voice.error": "Sorry, something went wrong.",
    },
    "pl": {
        "ask": "{summary}? Tak czy nie?",
        "unclear": "Nie zrozumiałam. Powiedz tak lub nie.",
        "denied": "Dobrze, nie wykonam tej czynności.",
        "print_text": "Wydrukować dokument",
        "tasks.create": "Utworzyć zaplanowane zadanie",
        "calendar.create_event": "Dodać wydarzenie do kalendarza",
        "notes.add": "Dodać notatkę",
        "email.send": "Wysłać e-mail",
        "generic": "Wykonać akcję {tool}",
        "card.title": "Wymagane potwierdzenie",
        "card.question": "Sprawdź tę akcję, zanim zostanie wykonana.",
        "card.reason": "Ta akcja wymaga Twojej zgody, zanim zostanie wykonana.",
        "risk.high_destructive": "Może trwale usunąć lub nadpisać dane.",
        "risk.high_external": "Wykona działanie poza MonikAI.",
        "risk.high_admin": "Zmieni ustawienia aplikacji, konta lub systemu.",
        "risk.medium_write": "Zmieni zapisane dane lub uruchomi kod.",
        "risk.medium": "Ta akcja wymaga Twojej wyraźnej zgody, żeby kontynuować.",
        "opt.task": "Zatwierdź",
        "opt.task_desc": "Wykonaj ją i kroki potrzebne do dokończenia tej prośby.",
        "opt.session": "Zezwól w tej rozmowie",
        "opt.session_desc": "Wykonaj i nie pytaj ponownie o to w tej rozmowie.",
        "opt.deny": "Odrzuć",
        "opt.deny_desc": "Nie wykonuj tej akcji.",
        "voice.done": "Gotowe.",
        "voice.error": "Przepraszam, coś poszło nie tak.",
    },
}


def default_locale() -> str:
    try:
        from src.settings import load_settings

        return str(load_settings().get("tts_language") or "en").strip().lower()[:2]
    except Exception:
        return "en"


def t(key: str, locale: str | None = None, **values) -> str:
    messages = MESSAGES.get(locale or default_locale(), MESSAGES["en"])
    return (messages.get(key) or MESSAGES["en"][key]).format(**values)
