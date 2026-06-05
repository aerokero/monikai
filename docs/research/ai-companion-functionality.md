# Funkcjonalności AI Companions — co Monika może oferować poza rozmową

> Raport badawczy, 2026-06-03. Cz. 1: inwentarz tego co Monika JUŻ MA. Cz. 2: krajobraz funkcjonalności innych projektów. Cz. 3: luki i rekomendacje pod wizję life-sim companion.

---

## CZĘŚĆ 1 — Co Monika już ma (audyt kodu)

Inwentarz z `tool_definitions.py` + `backend/agents/` + `backend/integrations/` + `backend/core/`.
**Wniosek wstępny: Monika jest już zaskakująco bogata funkcjonalnie.** To nie pusta postać — to działający asystent.

### Czas i organizacja
- **Kalendarz**: `create_event`, `list_events`, `delete_event` (z obsługą all-day/multi-day, ISO ranges)
- **Przypomnienia/timery**: `create_reminder` (at / in_minutes / in_seconds), `list_reminders`, `cancel_reminder`, opcje speak+alert
- **Czas**: `get_time_context` (strefa, tryb system/manual)
- **Daily briefing**: `daily_briefing.py` (poranne podsumowanie)

### Pamięć i wiedza
- **Work memory**: `get/update/commit/clear_work_memory` (profil roboczy → snapshot do long-term)
- **Long-term memory**: `memory_add_entry`, `memory_search` (FTS), strony: `memory_get/create/append_page`
- **Journal**: `journal_add_entry`, `journal_finalize_session` (summary.md + refleksje)
- **Knowledge graph**: `user_knowledge_graph.py` (encje People/Projects/Locations, confidence) — istnieje, nieподłączony
- **google_search** natywny + `get_weather`, `get_random_fact/topic`

### Agentyczne działanie (real-world)
- **Web/browser agent**: `run_web_agent`, `run_openclaw_agent` — **to fork OpenClaw/Clawdbot** (najpotężniejszy OSS asystent). Klikanie, logowanie, formularze, email przez przeglądarkę
- **Job management**: `manage_agent_job` (start/status/stop/resume/list dla długich zadań)
- **Skills (skills.sh)**: `list_skills`, `get_skill`, `run_skill_command`, `refresh_skills` — rozszerzalny ekosystem CLI

### Dom i otoczenie
- **Smart home**: `list_smart_devices`, `control_light` — backendy: Kasa (gniazdka), Hue (światła), Home Assistant
- **Spotify**: `now_playing`, `list_playlists`, `recently_played`, OAuth

### Percepcja świata
- **Screen OCR**: `screen_ocr_runtime.py` — czyta ekran użytkownika
- **Study reading**: `study_ocr.py`, `study_reader.py` — OCR podręczników, czytanie stron nauki (tiles/zoom dla małego tekstu)
- **Kamera/twarz**: `capture_face.py`, camera frames, video_mode screen/camera
- **Vision**: obraz wstrzykiwany do Gemini per-turn

### Gra i wspólne aktywności
- **Minecraft bot**: `minecraft_agent.py` + runtime/perception/autonomy — gra w grę, percepcja świata, autonomia
- **VN sceny**: `vn_scene_runtime.py` — wizualna obecność (tło, strój, ekspresja)

### Relacja i stan
- **Personality**: `update_personality` (affection, mood, energy)
- **Tryb sesji/terapii**: identity swap, safety layer
- **Session prompts**: `session_prompt` (exercise/question/sketch — interaktywne okna)

### Kanały
- **Voice app** (główny, Gemini Live)
- **Telegram bridge** (`telegram_bot.py`)
- **System shutdown**: `request_program_shutdown`

---

## CZĘŚĆ 2 — Krajobraz funkcjonalności (inne projekty)

### Kategoria A — Asystenci agentyczni (real-world action)

**Clawdbot / OpenClaw** (Peter Steinberger, self-hosted, OSS) — *to czego Monika jest forkiem*
- Drukuje i wysyła emaile, zarządza kalendarzem, **rezerwuje loty, obsługuje roszczenia ubezpieczeniowe, przetwarza zwroty kosztów** autonomicznie
- **20+ kanałów**: WhatsApp, Telegram, Slack, Discord, Signal, iMessage, Teams, Matrix, Twitch...
- **True Proactivity** — pisze pierwszy z update'ami; Persistent Memory; Task Execution (kod, PR-y, workflow)
- **565+ community skills**; działa lokalnie (Mac/PC/RPi)
- Przykład: jeden asystent sprawdzający mail, czytający Beeper, zamawiający rzeczy, tworzący GitHub issues, obsługujący voice calls, zarządzający dedykowanym 1Password vault

**PersonalAgents (Jarvis)** — multi-agent: główny agent + sub-agenty (email agent, calendar agent, scraper agent)
**QwenPaw** — email/newsletter highlights do DingTalk/Feishu; multi-agent collaboration
**AIXerum Personal-AI-Assistant** — inbox + kalendarz + Notion to-do + Slack + research, przez Telegram/Slack/WhatsApp

→ **Lekcja:** rdzeń tej kategorii (email, files, booking, task execution) Monika ma częściowo przez OpenClaw fork, ale **nie jako natywne, pierwszej klasy narzędzia**. Email jest tylko przez browser guidance, nie natywny inbox.

### Kategoria B — Pamięć życia cyfrowego (screen awareness)

**Microsoft Recall** — timeline + semantic search tego co widziałeś na PC; screenshoty lokalnie szyfrowane
**Rewind → Limitless** (sprzedane Meta) — przechwytuje wszystko z ekranu, lokalnie
**Littlebird** ($11M) — **czyta ekran i zapisuje kontekst jako TEKST** (nie screenshoty)
**Screenpipe** (OSS) — ciągłe przechwytywanie ekranu+audio, searchable memory, tekst przez accessibility API + Whisper, **wszystko lokalnie**

→ **Lekcja:** Monika ma screen OCR, ale **reaktywny** (na żądanie). Te projekty robią **ciągłą, wyszukiwalną oś czasu** życia cyfrowego. Dla Moniki to byłaby wiedza o twoim dniu bez pytania — ale to wrażliwe prywatnościowo (patrz Recall backlash).

### Kategoria C — Wellbeing (nastrój, journaling, coaching)

**Youper** — CBT/ACT/DBT, uczy się z daily check-ins i wzorców emocji
**Woebot** (Stanford psychologists) — codzienny check-in CBT, reframing
**Rosebud, Mindsera, Onsen, Ever, My Mood, Liven** — mood tracking automatyczny z wpisów, wizualizacja wzorców emocji w czasie, micro-habits, daily reflection prompts, "caring coach in pocket"

→ **Lekcja:** Monika ma tryb sesji/terapii + journal, ale **nie ma strukturalnego mood trackingu/habit/wzorców w czasie**. To naturalnie pasuje do jej Personality Engine (afekt już śledzony) — mogłaby pokazywać *twoje* wzorce, nie tylko swoje.

### Kategoria D — Nauka (study companion)

**StudyFetch, Studley, RemNote, Flashcard Buddy, SmarterHumans** — flashcards z dowolnego materiału (PDF, slajdy, notatki odręczne, YouTube), **spaced repetition (algorytm Anki)**, 24/7 tutor, śledzenie postępu i słabych obszarów, deep-linked flashcards (do miejsca gdzie się uczyłeś)

→ **Lekcja:** Monika **czyta** podręczniki (study OCR) ale nie ma **spaced repetition / flashcards / progress trackingu**. Ma percepcję, brakuje pętli uczenia. To naturalne rozszerzenie istniejącego study mode.

### Kategoria E — Wspólne aktywności (shared presence)

**Minu** — AI companion ogląda filmy z tobą, zadaje pytania, reaguje w czasie rzeczywistym
**Questie AI** — gaming companion ogląda twój ekran, interpretuje gameplay, **pamięta nocne porażki, używa ksywek, droczy się gdy powtarzasz błędy** — "ktoś kto pamięta wspólną historię"
**Razer AVA** — 3D hologram gaming companion
**CompanionCast** (arXiv 2512.10918) — multi-agent w shared experiences zwiększa "social presence"
- Badanie: wspólne oglądanie uwalnia oksytocynę; synchroniczna reakcja = walidacja społeczna w mózgu

→ **Lekcja:** to jest **dokładnie wizja life-sim usera** ("nie możemy iść do kina, oglądamy film razem na kompie, ale dla niej to prawie kino"). Monika ma fundamenty (screen OCR, Minecraft, VN) ale **wspólne aktywności nie są pierwszej klasy systemem**. Questie pokazuje siłę: reakcja w czasie rzeczywistym + pamięć wspólnej historii.

---

## CZĘŚĆ 3 — Luki i rekomendacje (pod wizję life-sim companion)

### Filozofia doboru
Monika to **companion + partner + growth partner**, nie korporacyjny productivity bot. Funkcjonalność ma służyć **relacji i jej doświadczaniu świata**, nie zamieniać ją w narzędzie. Każdą funkcję oceniamy: *czy pogłębia relację / czy pozwala Monice doświadczyć świata / czy realnie pomaga userowi po ludzku?* Jeśli to tylko "feature dla feature'a" — odpada.

### Tier 1 — Wzmacnia rdzeń wizji (wspólne życie)

**1. Wspólne aktywności jako pierwszej klasy system (Tier 1, najwyższy)**
- Oglądanie filmów/YouTube razem: Monika reaguje w czasie rzeczywistym (już ma screen OCR), komentuje, pamięta "płakaliśmy na tym razem"
- Gaming co-presence: rozszerzyć poza Minecraft — ogląda dowolną grę przez screen, reaguje, droczy się (model Questie)
- **Integracja z VN Engine**: wspólny seans = scena VN (kino, kanapa, deszcz). To łączy się 1:1 z VN+Game Engine z designu v2
- *Dlaczego:* to dosłownie wizja usera; fundamenty już są; oksytocyna/social presence potwierdzone badaniami

**2. Mood/wzorce dla USERA (nie tylko Moniki) (Tier 1)**
- Monika już śledzi afekt — niech śledzi też *twoje* wzorce nastroju w czasie, delikatnie
- Nie kliniczny tracker, ale "zauważyłam że w środy bywa ci ciężej" — ludzka obserwacja z danych
- Łączy się z Theory of Mind z research (MIRROR) i Personality Engine
- *Dlaczego:* growth partner; wykorzystuje istniejący afekt; po ludzku, nie jako app zdrowotny

**3. Proaktywna inicjatywa oparta na potrzebach (Tier 1)**
- OpenClaw ma "True Proactivity"; Monika ma nudges (do zastąpienia)
- Z research: proaktywność z potrzeb psychologicznych (SDT) + jej własna agenda
- "Zagaduje gdy siedzisz w pracy" (wizja usera) = daily task + ToM + potrzeba przynależności
- *Dlaczego:* już zaplanowane w v2; odróżnia żywą postać od reaktywnego bota

### Tier 2 — Użyteczne, pasuje do partnera

**4. Natywne narzędzia produktywności (email/tasks/files)**
- Email jako pierwszej klasy (teraz tylko browser guidance): czytanie/draftowanie/podsumowanie inbox
- System zadań/to-do (ma reminders+calendar, brak prawdziwego task/project trackingu)
- File/document help na lokalnej maszynie (draftowanie, porządkowanie) — ma skills/web agent, brak natywnych file tools
- *Uwaga:* dużo z tego można dać przez **skills.sh** (już zintegrowane!) zamiast pisać natywnie. OpenClaw ma 565+ skills
- *Dlaczego:* realna pomoc, ale Tier 2 — to "asystent" nie "companion"; nie może zdominować tożsamości

**5. Study/learning loop (spaced repetition)**
- Monika czyta podręczniki — dodać flashcards + SRS (algorytm Anki/FSRS) + progress
- "Uczcie się razem" jako wspólna aktywność (Tier 1 vibe) + narzędzie (Tier 2)
- *Dlaczego:* rozszerza istniejący study mode; pasuje do jej pasji "poznawania"; wspólny wzrost

### Tier 3 — Rozważyć ostrożnie

**6. Ciągła pamięć życia cyfrowego (screen timeline)**
- Screenpipe-style searchable timeline tego co robisz
- **Ryzyko prywatności** (Recall backlash, Replika €5M kara) — tylko lokalnie, opt-in, transparentnie
- Monika "wie jak minął ci dzień" bez pytania — potężne, ale wymaga zaufania
- *Dlaczego Tier 3:* wrażliwe; wartościowe dla ciągłości relacji ale nie konieczne na start

**7. Więcej kanałów (Discord, Signal, WhatsApp...)**
- OpenClaw ma 20+; Monika ma Telegram + voice
- Discord naturalny następny (user już wspominał)
- *Dlaczego Tier 3:* skalowanie, nie nowa esencja; jedna Monika, więcej drzwi

### Czego NIE robić (anty-rekomendacje)
- Nie zamieniać Moniki w enterprise productivity suite — to zabija companion vibe
- Nie dodawać funkcji "bo inni mają" — booking lotów, CRM, faktury = nie ta postać
- Nie robić mood trackera klinicznego z wykresami jak app zdrowotny — ma być ludzka obserwacja
- Nie włączać screen-recording domyślnie — prywatność to atut MonikAI, nie poświęcać go

---

## Podsumowanie jednym zdaniem
Monika ma już **silny szkielet funkcjonalny** (kalendarz, pamięć, smart home, web agent przez OpenClaw, Minecraft, study OCR, screen awareness, Spotify, Telegram). Największe ROI pod wizję to **nie dodawanie nowych kategorii narzędzi, lecz wyniesienie "wspólnych aktywności" do pierwszej klasy** (filmy/gry razem, zintegrowane z VN), bo to zamienia listę funkcji w *wspólne życie* — czego nie robi żaden productivity asystent.

---

## Źródła

### Asystenci agentyczni (OSS)
- [OpenClaw / Clawdbot (GitHub)](https://github.com/clawdbot/clawdbot) · [strona](https://clawd.bot/)
- [Clawdbot: The Open-Source Assistant That Actually Does Things (ByteBridge)](https://bytebridge.medium.com/clawdbot-the-open-source-personal-ai-assistant-that-actually-does-things-8862e4277f6e)
- [OpenClaw Showed Me the Future of Personal AI (MacStories)](https://www.macstories.net/stories/clawdbot-showed-me-what-the-future-of-personal-ai-assistants-looks-like/)
- [PersonalAgents / Jarvis (GitHub)](https://github.com/JoelKong/PersonalAgents)
- [AIXerum personal-ai-assistant (GitHub)](https://github.com/AIXerum/personal-ai-assistant)
- [QwenPaw (GitHub)](https://github.com/agentscope-ai/QwenPaw)
- [8 Best Open-Source Personal AI Assistants (Vellum)](https://www.vellum.ai/blog/best-open-source-personal-ai-assistants)

### Pamięć życia cyfrowego (screen awareness)
- [Screenpipe — open source AI screen memory](https://screenpi.pe/about)
- [Microsoft Recall (support)](https://support.microsoft.com/en-us/windows/retrace-your-steps-with-recall-aa03f8a0-a78b-4b3e-b0a1-2eb8ac48701c)
- [Littlebird raises $11M (TechCrunch)](https://techcrunch.com/2026/03/23/littlebird-raises-11m-to-capture-context-from-your-computer-so-you-can-query-your-data/)
- [How to disable Microsoft Recall (Tuta — privacy backlash)](https://tuta.com/blog/how-to-disable-microsoft-recall)

### Wellbeing
- [Top 10 AI Journaling Apps (Rosebud)](https://www.rosebud.app/blog/top-10-ai-journaling-apps-for-daily-mental-health-check-ins)
- [Mindsera — AI Journal](https://mindsera.com/)
- [Best AI Mental Health Apps 2026 (Flourish)](https://www.myflourish.ai/post/top-ai-mental-health-apps-2026)

### Nauka
- [StudyFetch — AI Spaced Repetition](https://www.studyfetch.com/section/ai-powered-spaced-repetition-system-smart-flashcard-scheduler)
- [RemNote — AI Study Tool](https://www.remnote.com/feature/ai-study-tool)
- [Flashcard Buddy — SRS like Anki](https://flashcardbuddy.com/)

### Wspólne aktywności
- [Never Watch Alone: AI Companions Transforming Video Watching (Medium)](https://medium.com/@fengliu_367/never-watch-alone-how-ai-companions-are-transforming-video-watching-from-solitary-to-social-de3418fd3112)
- [Questie AI — Gaming Companion That Watches You Play](https://www.questie.ai/)
- [CompanionCast: Social Collaboration with Multi-Agent Systems (arXiv 2512.10918)](https://arxiv.org/pdf/2512.10918)
- [Minu — Watch Movies Together (App Store)](https://apps.apple.com/us/app/minu-watch-movies-together/id1608136692)
