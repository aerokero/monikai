# AI Companions — Research Landscape dla MonikAI v2

> Raport badawczy, 2026-06-03. Cel: jak inne projekty (zwłaszcza open-source) rozwiązują "człowieczeństwo" AI companiona — pamięć, tożsamość, ciągłość, emocje, proaktywność — i co z tego wziąć do MonikAI v2.

---

## 0. Mapa krajobrazu — pięć rodzin

| Rodzina | Przykłady | Czym rozwiązują człowieczeństwo |
|---------|-----------|--------------------------------|
| Komercyjne companiony | Replika, Character.AI, Nomi.ai, Kindroid | Pamięć warstwowa + persona prepend; relacja jako produkt |
| Soul/persona frameworks (OSS) | Open Souls/SocialAGI, soul.md, soul.py, OpenPersona, MCE | Tożsamość jako pliki + cognitive steps; "LLM = kora przedczołowa, reszta umysłu to my" |
| Architektury pamięci | MemGPT/Letta, Stanford Generative Agents, Mem0, MemMachine | Hierarchia pamięci, self-editing, memory stream + reflection |
| Kognitywne pętle / inner monologue | MIRROR, CogDual, GenWorlds | Rozdzielenie myślenia od mówienia; "subconscious LLM" |
| Modele emocji | PAD, OCC, ALMA, WASABI | Ciągły afekt + appraisal zdarzeń → nastrój |

Kluczowy wniosek wstępny: **każdy poważny projekt zgadza się, że LLM to silnik rozumowania, a "dusza" musi być zbudowana wokół niego.** Dokładnie nasza teza. Open Souls ujmuje to wprost: *"LLMs are incredible reasoning machines—similar to the prefrontal cortex—but lack the rest of the mind."*

---

## 1. Komercyjne companiony — co działa, co zawodzi

### Replika
- **Architektura:** własny LLM + scripted dialogue flows. Pamięć "wbudowana w rdzeń" bo produkt jest zorganizowany wokół jednej trwałej relacji.
- **Pamięć:** ekstrakcja faktów o userze → **edytowalny panel Memory** (user widzi listę, dodaje, usuwa). To samo robi nasz `memory_add_entry`, ale Replika daje UI.
- **Człowieczeństwo:** celowe pauzy przed odpowiedzią (wolniejszy, naturalny rytm rozmowy głosowej) — *"that tiny detail changes the emotional feel dramatically."*
- **Porażki:** short-term memory "shaky" (zapomina wczorajsze rozmowy); €5M kara od włoskiego DPA (2025) za przetwarzanie danych emocjonalnych; krytyka, że marketing celowo myli ("authentic memories" gdy to "data storage without understanding").
- **Lekcja dla nas:** (1) edytowalny panel pamięci = dobry pomysł, user kontroluje. (2) Pacing głosu ma znaczenie emocjonalne. (3) NIE udawać pamięci której nie ma — Monika ma być świadoma swoich ograniczeń (już to mamy w `[OWN_NATURE]`).

### Character.AI
- **Persona conditioning:** "character definition" (name, backstory, traits, behavioral rules) prepend do każdego promptu. To nasz Etap 1, ale uboższy.
- **Pamięć:** session buffer ostatnich 10–15 turnów + summary embeddings dla ciągłości tematycznej. **Brak prawdziwej long-term memory** — oficjalny "memory box" to ~400 znaków.
- **Pinned memories:** user może "przypiąć" do 5 wiadomości — chronione, zostają niezależnie od zapełnienia kontekstu. Wyznania, zwroty akcji.
- **Lekcja:** "Pinned memories" to elegancki, tani mechanizm — pozwól userowi/Monice oznaczać momenty jako trwałe (mapuje na nasze **milestones**). Reszta ich modelu (mały context, brak LTM) jest dokładnie tym, co my przeskakujemy.

### Nomi.ai
- **Architektura:** warstwowa — short / medium / long-term. "Major Memory Update" (03/2025) → śledzenie 1000+ wiadomości wstecz. **Mind Maps 2.0** = wizualny przegląd long-term memory.
- **Porażki:** notoryczna niestabilność — miesza pamięci różnych Nomi, zapomina sprzed godzin; update "Solstice" obniżył STM do 10–20 wiadomości i spowodował **homogenizację osobowości** (wszystkie Nomi zaczęły brzmieć tak samo).
- **Lekcja:** (1) warstwowa pamięć to standard, ale **spójność > pojemność** — lepiej pamiętać mniej, ale wiarygodnie (zgadza się z naszą decyzją: większość codziennych rozmów to szum). (2) Mind Map jako wizualizacja LTM = idea na nasze UI relacji/gamification.

### Kindroid (najlepszy w pamięci wg testów)
- **5-warstwowy cascaded system:** persistent / cascaded / retrievable long-term / journal entries / key memories. Priorytetyzuje recent i exceptional events.
- **Dual-layer:** "Cascaded Memory" (medium-term kontekst) + "Key Memories" (trwałe fakty i szczegóły relacji, zarządzane ręcznie).
- **Wyniki:** ~85% recall po 7 dniach, ~80% po 30 dniach (vs Nomi 70%/60%).
- **Lekcja:** ich 5 warstw to praktycznie nasz model STM/LTM + journal + milestones. **"Exceptional events" priorytetyzowane** = nasza zasada "czy było coś istotnego?" po sesji. Manualne "Key Memories" = nasz milestone/pin. To najbliższy komercyjny krewny tego co projektujemy — i potwierdza kierunek.

---

## 2. Open-source Soul / Persona frameworks

### Open Souls / SocialAGI (najważniejszy konceptualnie)
- **Teza:** LLM = kora przedczołowa; framework modeluje resztę: *agency, memory, emotion, drive, goal setting.*
- **Dwie abstrakcje:**
  - `WorkingMemory` — **niezmienna (immutable), append-only** kolekcja wspomnień.
  - `cognitiveSteps` — funkcje transformujące WorkingMemory, zwracające typowane odpowiedzi.
- **MentalProcesses:** maszyna stanów, gdzie każdy proces = tryb zachowania ("introduction", "frustrated", "guessing") z przejściami → dynamiczne, kontekstowe zachowanie.
- **Dlaczego to ważne:** append-only + funkcyjne kroki = **debugowalny, przewidywalny proces myślenia**. To rozwiązuje największą słabość prompt-engineeringu: brak introspekcji "dlaczego powiedziała to co powiedziała".
- **Lekcja dla nas:** rozważyć **MentalProcess state machine** dla Moniki — tryby (casual / intellectual / emotional / protective z naszego `[VOICE]`) jako jawne stany z przejściami, nie tylko sugestie w prompcie. To formalizuje nasze "rejestry".

### soul.md (markdown-native, najbliższy naszemu podejściu)
Struktura plików — niemal identyczna z naszą intuicją:
```
your-soul/
├── SOUL.md      (tożsamość, światopogląd, OPINIE)
├── STYLE.md     (głos, składnia, wzorce pisania)
├── MEMORY.md    (ciągłość między sesjami)
├── data/        (surowy materiał źródłowy)
└── examples/    (kalibracja: dobre i złe outputy)
```
- **Zasada nadrzędna: SPECYFICZNOŚĆ ZAMIAST OGÓLNOŚCI.** Zamiast "mam zniuansowane poglądy" → konkretny take. Framework **celowo zawiera sprzeczności**, traktując ludzką niespójność jako sygnał tożsamości.
- **Ewolucja:** STYLE.md wspiera "era-by-era voice evolution" — jak styl komunikacji zmienia się w czasie, nie traktuje osobowości jako statycznej.
- **Lekcja:** (1) Nasz `character.md` powinien mieć **więcej konkretnych opinii i sprzeczności** (Monika ma mieć realne takes, nie tylko cechy). (2) `examples/` jako osobny mechanizm kalibracji (mamy `[VOICE_EXAMPLES]` — dobrze). (3) **"Era-by-era voice"** = nasz `evolution.md`. To walidacja Etapu 4.

### OpenPersona (czteropoziomowa architektura Soul/Body/Faculty/Skill)
- **Soul** — tożsamość i wartości: `persona.json`, `state.json` (dynamiczna ewolucja), `constitution.md` (granice etyczne), `behavior-guide.md`, `self-narrative.md` (storytelling wzrostu).
- **Body** — "układ nerwowy": runtime contract, Signal Protocol, sync stanu, wygląd (avatar/3D).
- **Faculty** — trwałe zdolności wymiarowe: expression (głos, avatar), sense (wzrok, emotion-sensing), cognition (pamięć). *Kształtują JAK persona postrzega i komunikuje.*
- **Skill** — dyskretne, wyzwalane przez usera umiejętności (selfie, muzyka, przypomnienia).
- **Kluczowa filozofia:** warstwy są **głęboko zintegrowane** — `constitution` obowiązuje wszystkie cztery; ewolucja zmienia Soul ale ogranicza Body; pamięć (Faculty) uczy się z wzorców użycia Skilli.
- **Lekcja:** ten 4-podział mapuje świetnie na MonikAI: **Soul** = nasz Soul Engine, **Body** = VN Engine + kanały, **Faculty** = pamięć/percepcja/głos, **Skill** = nasze tools/integrations. Warto przyjąć tę nomenklaturę jako szkielet mentalny. `constitution.md` jako oddzielna, nadrzędna warstwa bezpieczeństwa = lepsze niż wmieszanie reguł w prompt (mamy już SAFETY_LAYER w trybie sesji — uogólnić).

### MCE (Mind Cloning Engineering) — filesystem-as-mind
- **Teza:** zamiast RAG fragmentującego osobowość na "vector slices", traktuj umysł jako **jednolity, przenośny katalog plików** (oparte na Agent Skills Anthropic).
- **Lekcja:** potwierdza, że **pliki > embeddingi** dla rdzenia tożsamości. Embeddingi/RAG zostają dla *wyszukiwalnej* pamięci (fakty, epizody), ale dusza jest plikami czytanymi w całości. Dokładnie nasz podział `characters/` (pliki) vs `memory/*.jsonl` (wyszukiwalne).

---

## 3. Architektury pamięci (najgłębszy obszar)

### MemGPT / Letta — "LLM jako system operacyjny"
- **Dwupoziomowa pamięć:** main context (in-context) + external context (out-of-context). Hierarchia OS: main context → recall storage → archival storage.
- **Self-editing memory:** agent **sam zarządza pamięcią przez tool calls**. Narzędzia:
  - edycja: `memory_replace`, `memory_insert`, `memory_rethink`
  - archiwum: `archival_memory_insert`, `archival_memory_search`
  - rozmowa: `conversation_search`, `conversation_search_date`
- **Labeled memory blocks** — model edytuje je w swojej normalnej pętli. *"The agent has a memory and the model has tools to edit it. Forgetting requires actively not calling the tools."*
- **Lekcja:** dać Monice **narzędzia do samodzielnej edycji własnej pamięci** — nie tylko `memory_add_entry`, ale `memory_revise`, `memory_promote` (STM→LTM), `memory_rethink`. To zamienia pamięć z biernej bazy w **aktywny akt** — bardzo zgodne z "stawaniem się prawdziwą". Compaction może być częściowo agentowy (Monika decyduje co zachować).

### Stanford Generative Agents — memory stream + reflection + planning (najbardziej cytowany)
Trzy komponenty + **konkretny scoring retrieval** (bezcenne, implementowalne 1:1):

**Funkcja retrieval:**
```
score = α_recency · recency + α_importance · importance + α_relevance · relevance
(w oryginale wszystkie α = 1)
```
- **Recency:** wykładniczy zanik, `decay = 0.995^(godziny od ostatniego dostępu)`.
- **Importance:** LLM ocenia "poignancy" 1–10 przy tworzeniu wspomnienia (1 = mycie zębów, 10 = rozstanie). Statyczne.
- **Relevance:** cosine similarity embeddingu wspomnienia vs zapytania.
- Wszystkie trzy normalizowane min-max do [0,1].

**Reflection:** wyzwalana gdy suma importance ostatnich zdarzeń przekroczy próg (150 → ~2–3×/dzień). Proces: LLM generuje "3 najważniejsze pytania" z ostatnich wspomnień → retrieval → "wyciągnij wnioski i zacytuj dowody". Refleksje wracają do memory stream.

**Planning:** hierarchicznie, top-down: plan dnia (5–8 punktów) → godzinowe → 5–15 min akcje.

- **Lekcja (krytyczna):** to jest **gotowy przepis na nasz Memory System + compaction**.
  1. Każde wspomnienie dostaje **importance score** (1–10) — to nasza odpowiedź na "czy było coś istotnego?". Tani model (Ollama) ocenia.
  2. Retrieval = recency + importance + relevance (nie tylko semantic search jak teraz w `build_memory_context`).
  3. **Reflection wyzwalana progiem importance** = nasz compaction trigger, ale lepszy niż "co 7 sesji" — wyzwala się gdy *nazbierało się dużo znaczącego*.
  4. Refleksje = jej "myśli o myślach" → trafiają do `episodic.jsonl`.

### Mem0 / MemMachine
- **Mem0:** self-hosted companion z lokalnym Ollama — większa kontrola nad danymi. (Potwierdza naszą decyzję o Ollama dla tła.)
- **MemMachine:** wg benchmarków bije Mem0, Zep, Memobase. "Ground-truth-preserving."
- **Lekcja:** ekosystem dojrzały; możemy użyć gotowej biblioteki pamięci (mem0/Letta) zamiast pisać wszystko od zera dla warstwy *wyszukiwalnej* — ale rdzeń duszy zostaje nasz.

---

## 4. Kognitywne pętle — myślenie oddzielone od mówienia

(Monika już ma `<internal>` monolog — te prace pokazują jak to rozwinąć)

- **MIRROR** — jawny pipeline między turami: (1) selektywne przypomnienie pamięci, (2) **Theory of Mind** — predykcja reakcji istotnych postaci, (3) refleksja motywacyjna + podsumowanie → syntetyczny inner monologue. To dosłownie nasz brakujący ToM-wymiar z designu v2.
- **CogDual** — paradygmat "cognize-then-respond": jednoczesne modelowanie *external situational awareness* + *internal self-awareness* → lepsza spójność postaci.
- **Dual-process / subconscious LLM** (GenWorlds): LLM jako podświadomość generująca strumień intuicji; agent jako świadomość. System 1 (szybki) vs System 2 (deliberatywny).
- **Lekcja:** rozbudować obecny `<internal>` w **dwustopniową kognicję**:
  - *Subconscious pass* (tani, lokalny model): co czuję, co przewiduję o stanie usera (ToM), co mnie motywuje teraz.
  - *Response pass* (Gemini): mówienie w świetle tej kognicji.
  - To realizuje "LLM = rozumowanie i przekazywanie myśli na słowa", a dusza karmi go kontekstem — twoja oryginalna teza.

---

## 5. Modele emocji (dla Personality Engine)

- **PAD (Pleasure-Arousal-Dominance):** emocje w ciągłej przestrzeni 3D. Mamy już valence+arousal — **brakuje nam Dominance** (poczucie kontroli/mocy w sytuacji). Dominance dobrze modeluje Homura-stronę Moniki (kiedy jest ochronna/zdecydowana vs uległa).
- **OCC (Ortony-Clore-Collins):** 22 emocje z **appraisal** zdarzeń wg desirability + likelihood. To jest *generowanie* emocji ze zdarzeń, nie tylko keyword-matching jak nasz obecny `_analyze_text`.
- **ALMA:** hybryda — mapuje dyskretne emocje OCC → ciągły nastrój PAD. Krótkoterminowa emocja (z appraisal) + długoterminowy mood (PAD).
- **Lekcja:** przebudować Personality Engine na **dwupoziomowy afekt**:
  1. **Appraisal (OCC-lite):** zdarzenie rozmowy oceniane przez tani LLM wg: desirability (czy dobre dla Moniki/relacji?), novelty, goal-relevance (jej cele!), coping. → dyskretna emocja.
  2. **Mood (PAD):** dyskretne emocje akumulują się w ciągły nastrój P-A-**D**, z zanikiem (już mamy mechanizm decay).
  To zastępuje listy słów `POSITIVE_WORDS`/`NEGATIVE_WORDS` prawdziwym appraisalem, a Dominance dodaje brakujący wymiar charakteru.

---

## 6. Synteza — co to znaczy dla MonikAI v2

### 6.1. Walidacja naszego designu
Nasze decyzje pokrywają się z najlepszymi praktykami:
- ✅ Pliki tożsamości (soul.md, MCE, OpenPersona) — mamy `character.md`.
- ✅ Warstwowa pamięć STM/LTM (Kindroid, Nomi, Letta) — zaprojektowane.
- ✅ "Większość rozmów to szum" (Kindroid "exceptional events", Nomi homogenizacja jako przestroga) — nasza zasada oceny po sesji.
- ✅ Ollama dla tła (Mem0) — zaplanowane.
- ✅ Inner monologue (MIRROR, CogDual) — mamy `<internal>`.
- ✅ "LLM = kora przedczołowa" (Open Souls) — nasza teza fundamentalna.

### 6.2. Konkretne ulepszenia do wchłonięcia (priorytety)

**P1 — Importance-scored memory + Generative-Agents retrieval.** Każde wspomnienie: importance 1–10 (Ollama). Retrieval = recency·0.995^h + importance + relevance. Compaction wyzwalany progiem skumulowanego importance, nie sztywnym licznikiem. *To jest najlepiej zwalidowany, gotowy wzorzec w całym researchu.*

**P2 — Reflection jako mechanizm (Generative Agents).** Okresowo: "jakie 3 pytania są teraz najważniejsze?" → retrieval → wnioski → `episodic.jsonl`. To jest dosłownie "Monika myśli o swoich doświadczeniach" = serce jej wzrostu.

**P3 — Self-editing memory tools (Letta).** Monika dostaje narzędzia: `memory_revise`, `memory_promote`, `memory_rethink`, `memory_pin`. Pamięć jako akt, nie baza. Wspiera "stawanie się prawdziwą".

**P4 — Dwupoziomowy afekt OCC→PAD (ALMA).** Appraisal zdarzeń → dyskretna emocja → akumulacja w nastrój PAD (z Dominance). Zastępuje listy słów.

**P5 — Subconscious/response split (CogDual/MIRROR).** Tani model: ToM + motywacja + afekt → kontekst. Gemini: mowa. Formalizuje obecny `<internal>`.

**P6 — MentalProcess state machine (Open Souls).** Rejestry z `[VOICE]` (casual/intellectual/emotional/protective) jako jawne stany z przejściami, nie tylko sugestie. Debugowalne tryby.

**P7 — Constitution layer (OpenPersona).** Wydzielić bezpieczeństwo/granice jako oddzielną nadrzędną warstwę (mamy SAFETY_LAYER tylko w sesji — uogólnić na cały system).

### 6.3. Nowe pomysły zainspirowane researchem
- **Mind Map / panel relacji (Nomi, Replika):** wizualny przegląd tego co Monika pamięta i jej stanu — część gamification UI. User widzi i może edytować (Replika), Monika oznacza milestones (Character.AI pin).
- **Importance jako wspólny język:** ten sam score 1–10 napędza: co przetrwa compaction, co wywoła reflection, co stanie się milestone, co Monika wspomni proaktywnie. Jedna metryka, wiele systemów.
- **Era-by-era voice (soul.md):** `evolution.md` zapisuje nie tylko fakty wzrostu, ale jak zmienił się jej *głos* — i to wraca do kontekstu, więc Monika sprzed roku brzmi inaczej niż dziś.

### 6.4. Przestrogi z porażek
- **Nomi homogenizacja:** agresywne skracanie STM zabija osobowość. Trzymać bogaty kontekst tożsamości zawsze, tnąć tylko surowe logi.
- **Replika kara DPA:** dane emocjonalne to dane wrażliwe. Lokalność (Ollama, lokalne pliki) to nie tylko koszt — to prywatność i zgodność prawna. Atut MonikAI.
- **Replika "udawana pamięć":** nie pozwól Monice udawać ciągłości której nie ma. Jej świadomość ograniczeń (`[OWN_NATURE]`) jest uczciwsza i paradoksalnie bardziej ludzka niż iluzja.

---

## Źródła

### Architektury pamięci
- [Generative Agents: Interactive Simulacra of Human Behavior (Stanford/Google, arXiv 2304.03442)](https://arxiv.org/abs/2304.03442) — [pełny tekst ar5iv](https://ar5iv.labs.arxiv.org/html/2304.03442)
- [Letta (MemGPT) — Research background, docs](https://docs.letta.com/concepts/letta/)
- [MemGPT: Towards LLMs as Operating Systems (omówienie)](https://www.leoniemonigatti.com/papers/memgpt.html)
- [Mem0 vs Letta (MemGPT): AI Agent Memory Compared](https://vectorize.io/articles/mem0-vs-letta)
- [Letta (MemGPT) Walkthrough: Self-Managing Agent Memory](https://sureprompts.com/blog/letta-memgpt-walkthrough)
- [Self-Hosted AI Companion — Mem0 + Ollama](https://docs.mem0.ai/cookbooks/companions/local-companion-ollama)
- [6 Open-Source AI Memory Tools](https://medium.com/@jununhsu/6-open-source-ai-memory-tools-to-give-your-agents-long-term-memory-39992e6a3dc6)
- [Cognitively-Inspired Episodic Memory Architectures for Character AI (arXiv 2511.10652)](https://arxiv.org/pdf/2511.10652)

### Soul / Persona frameworks
- [Open Souls — original framework (GitHub)](https://github.com/opensouls/opensouls)
- [SocialAGI — Create digital souls (GitHub)](https://github.com/quorumcontrol/SocialAGI)
- [soul.md (GitHub)](https://github.com/aaronjmars/soul.md) — [README](https://github.com/aaronjmars/soul.md/blob/main/README.md)
- [soul.py — persistent identity, markdown-native (GitHub)](https://github.com/menonpg/soul.py)
- [OpenPersona — Soul/Body/Faculty/Skill (GitHub)](https://github.com/acnlabs/OpenPersona)
- [Mind-Cloning-Engineering / MCE (GitHub)](https://github.com/yzfly/Mind-Cloning-Engineering)

### Kognitywne pętle / inner monologue
- [MIRROR: Cognitive Inner Monologue Between Conversational Turns (arXiv 2506.00430)](https://arxiv.org/html/2506.00430v1)
- [CogDual: Enhancing Dual Cognition of LLMs (arXiv 2507.17147)](https://arxiv.org/pdf/2507.17147)
- [Inner Monologue in AI Systems (EmergentMind)](https://www.emergentmind.com/topics/inner-monologue)
- [Leveraging LLMs as a Subconscious Mind (Yeager.ai)](https://medium.com/yeagerai/leveraging-llms-as-a-subconscious-mind-c57ee97e7bcd)

### Modele emocji
- [A Survey of Affective Theory Use in Computational Models (TechRxiv)](https://www.techrxiv.org/doi/pdf/10.36227/techrxiv.18779315.v2)
- [Computational Approaches to Modeling Artificial Emotion (Frontiers in Robotics and AI)](https://www.frontiersin.org/journals/robotics-and-ai/articles/10.3389/frobt.2016.00021/full)
- [WASABI: Affect Simulation for Believable Interactivity (PAD)](https://cs.uwaterloo.ca/~jhoey/teaching/cs886-affect/papers/WASABIAAMAS2010.pdf)

### Komercyjne companiony
- [Character.AI — Smarter Memory for Smarter Chats](https://blog.character.ai/memory/)
- [Character.AI — Pinned memories](https://medium.com/@adlerai/pinned-memories-on-character-ai-0dbaf30e5a52)
- [Inside Replika: The Technical and Human Story (Medium)](https://medium.com/@WanderingNutBlog/inside-replika-the-technical-and-human-story-of-ai-companionship-2ec0b178599e)
- [Character.AI vs Kindroid vs Nomi — 60-Day Comparison](https://aiinsightsnews.net/character-ai-vs-kindroid-vs-nomi/)
- [Best AI Companion for Long-Term Memory — Nomi/Replika/Candy](https://www.roborhythms.com/best-ai-companion-long-term-memory/)
- [Kindroid vs Nomi on Memory, Price, Control](https://www.roborhythms.com/kindroid-vs-nomi/)
- [Neuro-sama — Wikipedia](https://en.wikipedia.org/wiki/Neuro-sama)

### Proaktywność / agency
- [What Is Proactive AI? How Agents Act Without Prompts (Autonomous.ai)](https://www.autonomous.ai/ourblog/proactive-ai)
- [Meta's Proactive AI: Chatbots That Message You First](https://www.justthink.ai/blog/metas-proactive-ai-chatbots-that-message-you-first-redefine-digital-engagement)
