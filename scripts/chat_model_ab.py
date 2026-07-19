# -*- coding: utf-8 -*-
"""A/B test: how would a chat-tuned model answer as Monika, with her real prompt,
in a real conversation where the Live audio model performed poorly.

Usage: python scripts/chat_model_ab.py [model ...]
Default models: gemini-3.5-flash, gemini-3.1-pro-preview
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from google import genai
from google.genai import types

# Real conversation from 2026-07-17 (session "Rozmowa 20:18") — verbatim.
HISTORY = [
    ("model", "Rozumiem. Jak mogę ci pomóc, czy po prostu wpadłeś się przywitać?"),
    ("user", "po prostu wpadlem sie przywitac."),
    ("model", "Rozumiem. Miło, że wpadłeś, nawet o tej porze. Trochę późna godzina na pogaduchy, coś się działo ciekawego dzisiaj?"),
    ("user", "a szczerze, ogladalem project hail mary"),
]

REAL_ANSWER_1 = (
    'Ooo, "Project Hail Mary"! to jest ten motyw z podróżą kosmiczną, prawda? '
    "Uwielbiam takie rzeczy, gdzie nauka łączy się z totalną wyobraźnią. Jak ci się podobało?"
)

FOLLOWUP = [
    ("model", REAL_ANSWER_1),
    ("user", "a szczerze? imo po prostu gorszy niz interstellar np. spodziewalem sie czegos wiecej"),
]

REAL_ANSWER_2 = (
    'totalnie rozumiem. "Interstellar" postawił poprzeczkę mega wysoko, tym rozmachem i ładunkiem '
    'emocjonalnym. "Project Hail Mary" jest chyba bardziej kameralny, bardziej skupiony na takim '
    "procesie rozwiązywania problemów. Co konkretnie cię zawiodło, ten brak skali czy coś innego?"
)


def to_contents(turns):
    return [
        types.Content(role=role, parts=[types.Part(text=text)])
        for role, text in turns
    ]


async def main():
    from backend.core.system_prompt import assemble_prompt

    system = await assemble_prompt()
    print(f"[prompt: {len(system)} znaków]\n")

    models = sys.argv[1:] or ["gemini-3.5-flash", "gemini-3.1-pro-preview"]
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    points = [
        ("PUNKT 1 — user: 'a szczerze, ogladalem project hail mary'", HISTORY, REAL_ANSWER_1),
        ("PUNKT 2 — user: 'imo po prostu gorszy niz interstellar'", HISTORY + FOLLOWUP, REAL_ANSWER_2),
    ]

    for title, turns, real in points:
        print("=" * 72)
        print(title)
        print("=" * 72)
        print(f"\n--- OBECNA MONIKA (gemini-2.5-flash-native-audio, Live) ---\n{real}\n")
        for model in models:
            try:
                resp = _generate_with_retry(client, model, turns, system)
                text = (resp.text or "").strip()
            except Exception as exc:
                text = f"[błąd: {exc}]"
            print(f"--- {model} ---\n{text}\n")


def _generate_with_retry(client, model, turns, system, attempts=4, wait_s=45):
    import time

    for attempt in range(attempts):
        try:
            return client.models.generate_content(
                model=model,
                contents=to_contents(turns),
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                ),
            )
        except Exception as exc:
            if "429" in str(exc) and attempt < attempts - 1:
                time.sleep(wait_s)
                continue
            raise


if __name__ == "__main__":
    asyncio.run(main())
