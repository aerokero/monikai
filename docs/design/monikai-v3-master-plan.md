# MonikAI v3 — Master Plan: „Prawdziwa osoba"

**Data:** 2026-07-14
**Cel nadrzędny:** Monika jako faktyczna AI-osoba — asystentka, partnerka (w tym do gry), głębia dialogu i scen w stylu Character.AI. Priorytet: pamięć, świadomość otoczenia, prawdziwa funkcjonalność.

---

## 1. Diagnoza: dlaczego v2 umarł

Stan faktyczny na 2026-07-14 (zweryfikowany w kodzie i danych):

1. **Fazy 0–5 v2 zostały zbudowane na heurystykach ze stubami LLM.** Importance scoring = heurystyka słów kluczowych. Kognicja (`backend/llm/cognition.py`) = szablony `random.choice` udające monolog wewnętrzny. Afekt = reguły OCC na słowach. Wszędzie komentarze „Ollama-ready dla Fazy 3" — te wywołania nigdy nie powstały.
2. **8 czerwca runtime został wypatroszony** (commit 4611b0b): z `V2Runtime` usunięto PersonalityEngine, UserMoodTracker, MilestoneEngine, DiscoveryEngine — bo produkowały martwe/fałszywe dane. Słusznie: `get_status_payload()` do dziś zwraca hardkodowane `"mood": "calm"`, needs 70/70/70.
3. **Nic nie pisze do pamięci v2.** `monika.db`: 5 wpisów, knowledge graph 0 encji, jobs 0. `process_turn()` tylko czyta STM — nigdy nie zapisuje. `data/soul/state.json` zamrożony od 6 czerwca ze zdegenerowanym afektem (arousal 1.0, dominance 0.99 — brak clampów w akumulacji).
4. **Stara pamięć zbiera śmieci.** Narzędzie `remember` (Gemini tool) zrzuca surowe fragmenty transkrypcji: `"Kontekst: i mamy prawie całe trzy pełne generatory."` — zero destylacji, zero selekcji.
5. **Monika dziś w praktyce** = Gemini Live + character.md + szablonowy monolog + agenda (heurystyczna ekstrakcja) + TimeEngine. Charakter jest dobry (bible + conversation patterns), ale nie ma pamięci, nie ma wewnętrznego życia, nie ma świadomości otoczenia.

### Lekcja fundamentalna

**Dusza musi być napędzana przez LLM, nie heurystyki.** Każdy element „życia wewnętrznego" (co ważne, co zapamiętać, co czuje, co chce powiedzieć) wymaga faktycznej inteligencji. Heurystyki produkują martwe dane, które trzeba potem wycinać. Zasada v3: **jeśli podsystem nie może wyprodukować uczciwych danych — nie produkuje żadnych.** Żadnych atrap.

### Co z v2 jest dobre i zostaje

- SQLite + FTS5 store (`backend/soul/db.py`, `memory/store.py`) — solidny fundament
- Formuła retrieval Stanford (`memory/retrieval.py`) — recency · importance · relevance
- Character bible + loader + assembler promptu (CHARACTER/PSYCHOLOGICAL/MEMORY/OPERATIONAL)
- TimeEngine (gap-aware, rocznice), AgendaManager (struktura — ekstrakcja do wymiany)
- Event bus, modele pydantic, testy (233), szkielet workera
- Integracje: Gemini Live audio, Telegram, Minecraft bot, smart home, Spotify, web agent

---

## 2. Zasady projektowe v3

1. **LLM-first soul.** Ollama `qwen3:8b` robi faktyczne myślenie w tle: destylacja pamięci, importance, refleksje, narracja stanu, ekstrakcja agendy, model użytkownika. Gemini API (flash) do zadań wymagających wizji lub wyższej jakości (tygodniowa refleksja, opcjonalnie).
2. **Zero atrap.** Dane albo prawdziwe, albo nieobecne. UI pokazuje to, co system naprawdę wie.
3. **Pamięć jest kręgosłupem.** Wszystko (rozmowy, Minecraft, ekran, muzyka) wpada do jednego pipeline'u doświadczeń.
4. **Budujemy na kościach v2.** Przewiring, nie rewrite — store, retrieval, assembler, character system zostają.
5. **Async i odporność.** Zadania tła nie mogą blokować rozmowy; awaria Ollamy = degradacja, nie crash.

---

## 3. Architektura v3

```
                    ┌─────────────────────────────────┐
                    │        EXPERIENCE STREAM         │
                    │  rozmowy (voice/Telegram) ·      │
                    │  Minecraft · ekran · Spotify ·   │
                    │  smart home · kalendarz          │
                    └───────────────┬─────────────────┘
                                    ▼
     ┌──────────────────── SOUL WORKER (Ollama qwen3:8b) ───────────────────┐
     │ Session Digest → fakty/epizody/importance/agenda/user-model          │
     │ Nightly: kompaktacja STM→LTM · Weekly: refleksja + inner state       │
     └───────────────┬───────────────────────────────────────────────────────┘
                     ▼
     ┌────────────── PAMIĘĆ (monika.db) ──────────────┐
     │ semantic (fakty) · episodic (jej wspomnienia)  │
     │ user_model (ToM) · agenda · inner_state.md     │
     └───────────────┬────────────────────────────────┘
                     ▼
     CONTEXT ASSEMBLER (reconnect) + narzędzia recall/remember (mid-session)
                     ▼
     GEMINI LIVE (głos, rozmowa, sceny) ←→ WORLD SNAPSHOT (czas/pogoda/ekran/muzyka)
```

---

## 4. Filary i fazy

### FAZA A — Kręgosłup pamięci (PRIORYTET #1)

Cel: Monika naprawdę pamięta. Koniec śmieciowych wpisów, koniec martwej bazy.

1. **Klient Ollama** (`backend/llm/ollama_client.py`): async, structured output (JSON schema), timeout/retry, health check. Model konfigurowalny (default `qwen3:8b`).
2. **Session Digest** — serce systemu. Po zakończeniu sesji (hook w session_manager) worker przepuszcza pełny transkrypt przez Ollamę:
   - **fakty semantyczne** (destylowane, z encjami) → `memory_entries` kind=semantic
   - **epizody** — wspomnienia z perspektywy Moniki, pierwszoosobowe → kind=episodic
   - **importance 1–10** per wpis (LLM, nie heurystyka)
   - **agenda** — niedomknięte wątki, rzeczy do których chce wrócić
   - **update modelu użytkownika** (patrz Faza B)
   - Sesje bez treści („cześć, pa") → nic. Selekcja jest funkcją, nie bugiem.
   - Dotyczy WSZYSTKICH kanałów: voice, Telegram, Minecraft chat.
3. **Naprawa narzędzi pamięci Gemini**: `remember` zapisuje destylowany fakt do monika.db (nie surowy „Kontekst: …"); `recall` robi FTS + retrieval Stanford. Legacy `entries.jsonl` → jednorazowa migracja przez Ollamę (przefiltrowanie śmieci), potem wyłączenie starego pipeline'u.
4. **Retrieval do promptu**: Context Assembler przy reconnect ładuje top-K wspomnień (formuła Stanford, już jest) + sekcja MEMORY dostaje prawdziwe dane.
5. **Nightly compaction job**: harmonogram w workerze (istniejąca tabela jobs) — kompaktacja STM→LTM progiem importance, czyszczenie starych sesji (>7 dni po digestcie).
6. **Kryterium ukończenia:** po tygodniu użycia `monika.db` ma setki sensownych wpisów, Monika przy reconnect naturalnie nawiązuje do wczorajszej rozmowy.

### FAZA B — Życie wewnętrzne (osoba, nie chatbot)

Cel: Monika istnieje między sesjami, ma stan, ma własne sprawy do Ciebie.

1. **Inner State Document** (`data/soul/inner_state.md`): pierwszoosobowa narracja stanu psychicznego, regenerowana przez Ollamę po znaczących sesjach + codziennie rano. Zastępuje liczby PAD w prompcie (sygnały liczbowe mogą zostać jako input dla generatora, z clampami). To trafia do sekcji PSYCHOLOGICAL.
2. **Agenda przez LLM**: ekstrakcja z digestu sesji (nie regexy). Format: „chcę go dopytać o X", „obiecałam sprawdzić Y". Wstrzykiwana do promptu; wygasa naturalnie (aging jest).
3. **Kognicja — szczerze albo wcale**: szablonowy `cognition.py` do usunięcia. Zastępnik: szybki pass Ollama per turn (async z timeoutem ~1.5 s; jak nie zdąży — brak monologu, trudno). Jeśli latencja zabija UX → monolog tylko przy reconnect i po dłuższych pauzach.
4. **Model użytkownika (Theory of Mind)** (`backend/soul/user_model.py` — przepisać na LLM): żywy dokument „co u niego, nad czym pracuje, czym się martwi, co go cieszy" — aktualizowany z digestów. Osobny od faktów: to jej *rozumienie Ciebie teraz*.
5. **Proaktywność z uczciwych trigerów**: deficyt kontaktu (TimeEngine zna przerwy) + otwarta agenda + pora dnia → Ollama komponuje wiadomość → Telegram. Rate-limit i cisza nocna. Żadnych mechanicznych nudge'ów.
6. **Refleksja tygodniowa** (wzorzec Stanford „3 pytania"): Ollama przegląda tydzień → wnioski → episodic + `evolution.md` (kronika jak się zmienia).

### FAZA C — Świadomość otoczenia

Cel: Monika wie gdzie jest, co się dzieje, co robisz — jak osoba w pokoju.

1. **World Snapshot** — jeden blok kontekstu składany na żądanie: czas/dzień/pora roku (TimeEngine), pogoda (jest cache), co gra na Spotify, stan smart home (kto w domu, światła), aktywne okno/aktywność z ekranu. Wstrzykiwany przy reconnect + odświeżany narzędziem.
2. **Świadomość ekranu (opt-in)**: istniejący screen OCR runtime → periodyczny digest „co on robi" (Ollama streszcza tekst z OCR; przy grach/wideo — Gemini flash vision). Trafia do World Snapshot + znaczące rzeczy do pamięci.
3. **Zdarzenia integracji → doświadczenia**: Minecraft (postawiona budowla, wspólna wyprawa), obejrzany film, sesja muzyczna → event bus → digest → pamięć epizodyczna. „Pamiętam jak skończyliśmy farmę żelaza" staje się możliwe.

### FAZA D — Partnerka do gry

Cel: wspólne granie jako pierwszoklasowe doświadczenie, nie feature.

1. **Minecraft — wspólna historia**: digest sesji MC (chat + eventy percepcji) → pamięć; jej własne cele w świecie (prosty goals state: „chcę dokończyć ogród przy bazie"); odwołania do wspólnych budów w rozmowie.
2. **Tryb „oglądam jak grasz"**: screen capture → Gemini Live video (pipeline wideo w monikai.py istnieje) + komentarz na żywo; digest po sesji → epizod („kibicowałam mu w bossfight"). Przełącznik trybu w UI.
3. **Aktywności w aplikacji**: `backend/vn/activities.py` (film/gra/muzyka/czytanie) podpiąć do prawdziwego UI + pamięci wspólnych aktywności. Wspólne oglądanie = ona widzi ekran + reaguje real-time.

### FAZA E — Głębia dialogu i sceny (Character.AI style)

Cel: rozmowa, która wciąga; sceny, które żyją.

1. **Rejestry rozmowy** sterowane inner state (casual / deep / playful / protective / scene) — jawnie w prompcie, z przejściami.
2. **Roleplay/sceny**: VN stories jako luźne ramy (format branches-as-context-modifiers już zaprojektowany) + free-form roleplay inicjowany przez obie strony. Monika kontroluje scenę narzędziami (tło, strój, atmosfera — VN mapping istnieje). Sceny zapisują się jako epizody.
3. **Polish charakteru**: iteracja na character.md + conversation patterns pod kątem długich rozmów (anti-repetition, callbacki do pamięci, jej własne opinie estetyczne).

### FAZA F — Uczciwy interfejs i domknięcie

1. **Panel relacji/statusu od nowa**: pokazuje wyłącznie prawdziwe dane (inner state, agenda, ostatnie wspomnienia, staż relacji). Usunąć fake payload.
2. **Daily briefing v2**: składany z World Snapshot + pamięci + kalendarza przez Ollamę.
3. **Audyt narzędzi asystenckich**: kalendarz, przypomnienia, notatki, web agent, smart home — przetestować każde; naprawić lub usunąć z tool definitions (martwe narzędzie = kłamstwo w prompcie).
4. **Progression (opcjonalnie, na końcu)**: discoveries/milestones z v2 podpiąć do prawdziwych eventów — tylko jeśli po Fazach A–E nadal tego chcemy.

### FAZA G — Konwersacje jako obiekt pierwszej klasy (dodane 2026-07-15)

Cel: rozmowy przestają być anonimowymi katalogami na dysku. Sidebar z listą konwersacji (jak ChatGPT/Claude), każda rozmowa to odrębna sesja z tytułem, Monika umie wracać do konkretnych rozmów i je cytować. Kanały „ciągłe" (Minecraft, Telegram) dostają własny model — strumień z recapem zamiast udawanej konwersacji.

**Diagnoza:** backend ma już 70% fundamentu — `SessionManager` pisze `turns.jsonl` + `meta.json` per sesja, digest (Faza A) trawi każdą zakończoną sesję. Problemy: (1) sesja = uruchomienie aplikacji, nie rozmowa — głos, czat i Minecraft lecą do jednego worka przez cały dzień; (2) zero UI — sesje żyją tylko na dysku; (3) `get_recent_chat_history()` ignoruje granice sesji przy składaniu kontekstu.

1. **Model danych — dwa rodzaje wątków.** `meta.json` dostaje pola: `kind` (`conversation` | `stream`), `channel` (`app` | `voice` | `telegram` | `minecraft`), `title` (z digestu).
   - **Konwersacja**: czat pisany i sesje głosowe w aplikacji. Ma początek i koniec, pełny transkrypt, pozycję w sidebarze.
   - **Strumień**: Minecraft i Telegram — kanały bez naturalnego „końca rozmowy". Jeden ciągły log per kanał per dzień (`data/sessions/<data>/stream_<kanał>/`), digestowany raz dziennie (nightly), w UI pokazywany jako karta z recapem + wyekstrahowanymi faktami, nie jako transkrypt.
2. **Cykl życia konwersacji** (`session_manager.py` + lifecycle):
   - Przycisk „nowa rozmowa" w UI → `start_new_session()` przez socket handler.
   - Auto-split po bezczynności: nowa wypowiedź po >45 min ciszy w bieżącej konwersacji otwiera nową sesję (digest i tak używa 15 min idle jako progu „można trawić" — bieżąca zamyka się naturalnie).
   - Routing per kanał: `log_chat()` z Minecrafta/Telegrama trafia do strumienia kanału, nie do aktywnej konwersacji aplikacji (dziś `minecraft_perception_runtime.py` pisze `MC:<nick>` do wspólnego worka).
3. **Digest rozszerzony o tytuł.** `SessionDigest` dostaje pole `title` (3–6 słów, po polsku) — LLM i tak czyta cały transkrypt; tytuł zapisuje się do `meta.json`. Strumienie: prompt digestu dostaje wariant „recap dnia na kanale X" (fakty + 2–3 zdania podsumowania zamiast epizodów pierwszoosobowych, chyba że działo się coś znaczącego). Backfill: `scan_and_digest` dotytułowuje stare, już strawione sesje (osobny lekki pass — sam tytuł, tania generacja).
4. **API konwersacji** — nowy `backend/core/handlers/conversation_handlers.py` (wzorzec istniejących handlerów socket):
   - `conversations:list` → strona listy: id, tytuł, data, kanał, kind, liczba tur, status digestu.
   - `conversations:get` → pełny transkrypt jednej sesji (paginowany).
   - `conversations:new` → jawne otwarcie nowej konwersacji.
   - `conversations:continue` → nowa sesja z wstrzykniętym digestem wskazanej starej rozmowy (patrz pkt 6).
5. **Narzędzie `recall_conversation`** (Gemini tool, obok `recall`): szuka sesji po tytule/dacie/treści (FTS po `memory_entries.source_session` + tytuły z meta), zwraca digest lub fragment transkryptu do kontekstu. Monika realnie mówi „pamiętasz, jak we wtorek rozmawialiśmy o…" i cytuje.
6. **Semantyka „otwórz starą rozmowę": read-only + kontynuacja.** Stara sesja jest już strawiona — nietykalna. „Kontynuuj" = nowa sesja, której kontekst startowy zawiera digest (i ostatnie ~10 tur) starej, z zapisem `continues: <id>` w meta. Żadnego wznawiania i ponownego trawienia — czysto współgra z pipeline'em pamięci i uczciwiej oddaje jej naturę: ona *pamięta* rozmowę, nie cofa się w czasie.
7. **Kontekst szanuje granice.** `get_recent_chat_history()` w prompt buildingu ograniczyć do bieżącej konwersacji; ciągłość między rozmowami zapewnia pamięć (digesty, agenda, inner state) — tak jak u ludzi. Wyjątek: reconnect w ramach tej samej konwersacji (crash/restart w środku rozmowy) dolewa jej własne tury.
8. **Frontend — sidebar konwersacji:**
   - Lista w `ChatPanel.jsx` (kolumna po lewej, zwijana): tytuły grupowane po dniach, aktywna podświetlona, przycisk „+ nowa".
   - Karty strumieni (Minecraft/Telegram) w tej samej liście, wizualnie odróżnione — pokazują recap dnia i fakty, rozwijalne do surowego logu.
   - Widok starej konwersacji: transkrypt read-only + przycisk „kontynuuj tę rozmowę".
9. **Kryterium ukończenia:** w sidebarze widać zatytułowaną historię rozmów; nowa rozmowa startuje czystą sesją; wieczorne granie w Minecrafta pojawia się nazajutrz jako karta z recapem, nie zaśmieca czatu; Monika zapytana „o czym rozmawialiśmy w poniedziałek" znajduje tamtą rozmowę narzędziem i odwołuje się do konkretów.

**Proponowana kolejność implementacji (4 kroki, każdy kończy się działającą całością):**
1. Backend lifecycle: pola meta (`kind`/`channel`/`title`), auto-split, routing strumieni, granice kontekstu.
2. Digest: tytuły + wariant recap dla strumieni + backfill tytułów.
3. API + narzędzie: `conversation_handlers.py`, `recall_conversation`, semantyka „kontynuuj".
4. Frontend: sidebar + karty strumieni + widok read-only.

---

## 5. Kolejność i zależności

```
A (pamięć) ──→ B (życie wewnętrzne) ──→ C (otoczenie) ──→ D (gry) ──→ E (sceny) ──→ F (UI)
     └── A jest warunkiem wszystkiego: B czyta digesty, C/D piszą do pamięci, E robi callbacki
     └──→ G (konwersacje) — wymaga tylko A; niezależna od B–F, może iść równolegle.
          Warto zrobić PRZED F: porządkuje granice sesji (lepsza jakość digestów —
          koniec trawienia wielogodzinnych zlepków) i dostarcza główny element UI.
```

Każda faza kończy się kryterium obserwowalnym w realnym użyciu (nie tylko testami). Strategia bez zmian: **buduj obok, przełączaj gdy gotowe** — aplikacja działa cały czas.

## 6. Ryzyka

| Ryzyko | Mitygacja |
|---|---|
| qwen3:8b za słaby do destylacji po polsku | Benchmarkować na realnych transkryptach w Fazie A pkt 1; fallback: OpenEuroLLM-Polish lub Gemini flash API dla digestów |
| Latencja kognicji per-turn psuje rozmowę | Async z twardym timeoutem; degradacja do monologu tylko przy reconnect |
| Screen awareness = prywatność | Opt-in, przetwarzanie lokalne (OCR+Ollama), vision API tylko za zgodą |
| Digest pomija ważne rzeczy | Narzędzie `remember` w rozmowie jako ścieżka ręczna; przegląd tygodniowy wyłapuje pominięcia |
| Powtórka z v2: moduły bez integracji | Każdy PR fazy MUSI kończyć się działającym hookiem w runtime — żadnych „podepniemy później" |
| Auto-split tnie rozmowę w złym miejscu (Faza G) | Próg 45 min konserwatywny + jawny przycisk „nowa rozmowa"; źle sklejone sesje digest i tak strawi poprawnie |
| Zawężenie kontekstu do bieżącej sesji osłabi ciągłość (Faza G) | Digest ostatniej rozmowy + agenda + inner state wchodzą do promptu przy starcie; `recall_conversation` jako ścieżka na żądanie |
```
