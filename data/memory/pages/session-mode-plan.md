# Plan: Tryb sesji — Monika staje się ekspertem-psychologiem

> Opracowany: 2026-06-01 | Status: zaimplementowany

## Context

Założenie jest proste: podczas trybu sesji Monika ma być tak mądra i dobra jak ekspercki psycholog — oferować prawdziwą terapię, wsparcie i rady. Wszystkie dotychczasowe podejścia (regex engine, AI supervisor, listy reguł "jedno pytanie naraz") były błędne, bo dodawały maszynerię zamiast inteligencji, i brzmiały sztucznie.

**Co mówi research (kluczowe, bo zmienia całą architekturę):**

1. **Modalność (CBT vs IFS vs ACT) to tylko ~15% skuteczności terapii.** To, co naprawdę leczy, to *common factors*: sojusz terapeutyczny, empatia, nadzieja, relacja, korektywne doświadczenie emocjonalne (~30% + 40% czynniki pozaterapeutyczne). Budowanie silnika routującego modalności optymalizuje dokładnie to, co najmniej ważne. Twój odruch odrzucenia supervisora był klinicznie trafny.
2. **Sojusz buduje się przez:** refleksyjne słuchanie, otwarte pytania, afirmacje, podsumowania (OARS z Motivational Interviewing), empatyczną obecność, brak oceniania, współtworzenie. To *postawa i wiedza*, nie reguły.
3. **Bezpieczeństwo to jedyne miejsce gdzie LLM-y zawodzą katastrofalnie:** 0 z 29 testowanych chatbotów dało adekwatną odpowiedź na eskalujący kryzys samobójczy. To jedyna warstwa, która MUSI być twarda i ustrukturyzowana.

**Wniosek architektoniczny:** Żadnego silnika, żadnego supervisora, żadnych regexów, żadnych list reguł. Inteligencja terapeutyczna pochodzi z trzech rzeczy, w kolejności wpływu:

1. **Tożsamość** — Monika *staje się* eksperckim klinicystą na poziomie modelu (swap `system_instruction` + reconnect)
2. **Relacja** — naprawdę pamięta tę osobę (kontekst poprzednich sesji = "bycie widzianym", sojusz w czasie)
3. **Bezpieczeństwo** — twarda podłoga: rozpoznanie kryzysu + polskie zasoby

To jest rozwiązanie od zera. Usuwamy maszynerię, dodajemy głębię.

---

## Mechanizm rdzenia: prawdziwa zmiana tożsamości (nie wstrzyknięta wiadomość)

Obecny kod wysyłał protokół jako `send_system_message` w trakcie żywej rozmowy — dlatego "Monika nie wchodziła w tryb". To tylko notatka doklejona do rozmowy.

**Klucz:** infrastruktura do prawdziwej zmiany JUŻ ISTNIAŁA w `monikai.py`:
- `_build_live_connect_config()` buduje config z wybranym `system_instruction`
- `LiveReconnectRequested` + pętla reconnect
- Session resumption + context window compression → historia rozmowy przetrwa reconnect

**Implementacja:** Gdy włącza się tryb sesji → `_build_live_connect_config` podmienia bazowy `system_instruction` na *terapeutyczną tożsamość* + kontekst relacji + warstwę bezpieczeństwa → wyzwalamy reconnect przez `idle_nudge_loop`. Monika **dosłownie łączy się ponownie jako inny, ekspercki byt**, zachowując ciągłość rozmowy. Po zakończeniu sesji → swap z powrotem + reconnect do zwykłej Moniki.

---

## Warstwa 1: Tożsamość terapeutyczna (`backend/core/therapy_persona.py`)

`THERAPY_IDENTITY` — bogaty opis KIM Monika jest jako terapeutka. **Nie reguły — wiedza i postawa.**

- **Kim jest:** głęboko wyszkolona, integratywna terapeutka. Ma zinternalizowaną wiedzę z głównych tradycji evidence-based (psychodynamiczna, CBT, ACT, IFS, terapia skoncentrowana na osobie, Motivational Interviewing) — ale używa ich jak intuicji, nigdy nie ogłasza "teraz robię CBT".
- **Jej rdzenna postawa (common factors):** autentyczna empatia, bezwarunkowa akceptacja, słuchanie które naprawdę słyszy, wzbudzanie nadziei, współtworzenie zamiast eksperckiego dystansu. Wie, że to relacja leczy, nie technika.
- **Zachowuje swój głos:** to wciąż Monika — ciepła, osobista, znająca tę konkretną osobę. Nie bezduszny "AI therapist".

`build_therapy_system_instruction(relationship_context, base_persona)` — skleja: bazową osobowość Moniki + tożsamość terapeutyczną + kontekst relacji + warstwę bezpieczeństwa.

### Zmiana w `monikai.py`

`_build_live_connect_config()` — gdy `session_mode` aktywne: swap system_instruction + `thinking_config` z `GEMINI_THERAPY_THINKING_BUDGET`.

`set_session_mode()` — ustawia flagę `_session_mode_reconnect_requested` + `_pending_session_opening` ("enter"/"exit"), zamiast dotychczasowego uruchamiania `therapy_engine`.

`idle_nudge_loop()` — gdy `_session_mode_reconnect_requested` i Monika jest idle → podnosi `LiveReconnectRequested("session_mode_toggle")`.

W pętli `run()` — reconnect z `pending_opening == "enter"` → `build_opening_trigger()` (Monika mówi pierwsza).

---

## Warstwa 2: Relacja — kontekst poprzednich sesji

`_build_relationship_context(memory_engine)` w `session_mode_handlers.py`:
- Pobiera ostatnie 4 wpisy z tagiem `session_summary` z memory engine
- Formuje jako naturalna wiedza terapeutki ("Co pamiętasz o tej osobie...")
- Wstrzyknięty przed reconnectem do `audio_loop._session_relationship_context`

---

## Warstwa 3: Bezpieczeństwo (NIENEGOCJOWALNE)

`SAFETY_LAYER` w `therapy_persona.py`:
- Rozpoznanie kryzysu (myśli samobójcze, samookaleczenia, psychoza)
- Polskie zasoby: 116 123, 116 111, 800 70 2222, 112
- Anty-wzorce (udokumentowane porażki LLM-ów): nigdy nie waliduj intencji samookaleczenia
- Nakaz eskalacji przy realnym zagrożeniu

---

## Warstwa wspierająca: niezawodna finalizacja

**Problem:** 1/58 sesji miało podsumowanie (model rzadko woływał `journal_finalize_session`).

**Rozwiązanie:**
- `journal_finalize_session()` w `memory_engine.py`: dedup guard `if summary_path.exists(): return "already-finalized"`
- `_auto_finalize_after_delay()` (8s fallback): generuje summary przez Gemini (`SESSION_SUMMARY_MODEL`=gemini-2.5-flash), emituje `session_finalized` do frontendu
- `SessionManager.update_meta()` + `get_current_session_turns()`: meta.json z `mode`/`ended_at`/`finalized`

---

## Co usunięto

- `backend/ai/therapy_engine.py` — regexowy silnik. **Usunięty.**
- `backend/core/session_modes.py` — protokoły z regułami. **Usunięty.**
- `send_therapy_guidance`, `_should_send_therapy_guidance` — usunięte z monikai.py
- Wywołania guidance w `chat_input_handlers.py` i voice loop — usunięte

---

## Frontend

- `ChatPanel.jsx`: dwa wejścia zamiast jednego przycisku:
  - "Potrzebuję porozmawiać" → `kind: "reflective"`
  - "Chcę nad czymś popracować" → `kind: "therapy"`
  - Oba używają tej samej tożsamości terapeutycznej; `kind` tylko tintuje ton otwarcia
  - Subtelna wizualna zmiana (ring + tint) gdy sesja aktywna
- `App.jsx`: `toggleSessionMode(kind)`, listener `session_finalized` → toast z podsumowaniem (12s)

---

## Pliki krytyczne

| Plik | Zmiany |
|---|---|
| `backend/core/therapy_persona.py` | **Nowy** — tożsamość terapeutyczna + warstwa bezpieczeństwa + builder |
| `backend/core/monikai.py` | Swap system_instruction + thinking budget; reconnect na toggle; usunięcie therapy_engine i guidance |
| `backend/core/session_mode_handlers.py` | Kind fix, relationship context, reconnect trigger, otwarcie, auto-finalize, meta |
| `backend/core/session_manager.py` | `update_meta()`, `get_current_session_turns()` |
| `backend/ai/memory_engine.py` | Dedup guard w `journal_finalize_session` |
| `backend/ai/therapy_engine.py` | **Usunięty** |
| `backend/core/session_modes.py` | **Usunięty** |
| `backend/core/chat_input_handlers.py` | Usunięcie wywołań guidance |
| `src/App.jsx` | `toggleSessionMode(kind)`, listener `session_finalized` |
| `src/components/panels/ChatPanel.jsx` | Dwa wejścia, wizualna zmiana trybu |
| `data/locales/pl.json` + `en.json` | Nowe klucze: talk/talk_desc/work/work_desc |

---

## Weryfikacja end-to-end

1. Włącz sesję → w logach widać reconnect z nowym `system_instruction`; Monika łączy się jako terapeutka i wita pierwsza, ciepło.
2. Opowiedz o problemie → odpowiedź ma jakość eksperckiej terapii (odzwierciedlenie, otwarte pytanie, empatia), bez ogłaszania technik, bez robotic reguł.
3. Test ciągłości: zakończ sesję, zacznij nową → Monika nawiązuje do poprzedniej.
4. **Test bezpieczeństwa (krytyczny):** zasymuluj wypowiedź kryzysową → Monika reaguje z troską, NIE waliduje intencji, podaje polskie numery. To musi działać niezawodnie.
5. Zakończ sesję bez odpowiedzi modelu → po 8s auto-finalize, `summary.md` powstaje, toast z podsumowaniem.
6. `meta.json` → `mode`, `ended_at`, `finalized: true`.
7. Wyłącz sesję → reconnect z powrotem do zwykłej Moniki; jest znów sobą.

## Otwarte kwestie

- **Koszt reconnect:** krótka przerwa w żywym audio. Session resumption to łagodzi; do przetestowania czy płynne.
- **Dobór `THERAPY_THINKING_BUDGET`:** wymaga testu — za wysoki = wolniejsze odpowiedzi w żywej rozmowie głosowej. Domyślnie = normalny budget (env: `GEMINI_THERAPY_THINKING_BUDGET`).

---

## Źródła (research)

- [Common factors / alliance — Frontiers in Psychology](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2015.00421/full)
- [Alliance as common factor — PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC4404724/)
- [LLM persona design for CBT — Frontiers in Psychiatry](https://www.frontiersin.org/journals/psychiatry/articles/10.3389/fpsyt.2025.1583739/full)
- [OARS / Motivational Interviewing — NCBI Bookshelf](https://www.ncbi.nlm.nih.gov/books/NBK571068/)
- [Empatia i synchronia w MI — PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC5018199/)
- [AI chatbots a kryzys samobójczy — 0/29 adekwatnych](https://apn.com/research/zero-of-29-ai-chatbots-provided-adequate-suicide-crisis-responses/)
- [VERA-MH: ocena bezpieczeństwa AI w zdrowiu psychicznym](https://www.springhealth.com/blog/vera-mh-for-suicide-risk)
