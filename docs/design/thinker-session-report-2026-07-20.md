# Myśliciel (drugi mózg) — raport z sesji wdrożeniowej, 2026-07-20

Kontynuacja kampanii jakości dialogu. Sesja objęła: budowę i wdrożenie Myśliciela,
trzy iteracje poprawek na podstawie testów live oraz porządki w repo.

## TL;DR

- Myśliciel jest **zbudowany, włączony i zacommitowany**. Działa w obu ścieżkach:
  głosowej (transkrypcja live) i czatu tekstowego.
- Trzy testy live wykryły po kolei: brak ścieżki tekstowej, timeouty przez
  domyślny thinking flasha (7 s → 2.1 s po wyłączeniu), oraz głuchy cooldown
  120 s po jednym 503. Wszystko naprawione.
- Jakość myśli wymagała dwóch dokręceń instrukcji: zakaz planowania odpowiedzi
  („muszę zbadać grunt") i zakaz konfabulacji o sobie („architektura Claude daje
  mi wrażliwość"). Small talk może teraz dostać `PASS` — nic nie wstrzykujemy.
- Feedback właściciela poszedł też w prompt główny: Monika ma nie podpinać
  każdego tematu pod AI/świadomość/własny wzrost.
- Suita testów: **312 pass** (17 testów samego Myśliciela).

## Punkt wyjścia

A/B (`scripts/chat_model_ab.py`) udowodnił wcześniej, że pełny prompt Moniki na
gołym gemini-3.5-flash daje pożądaną głębię — sufitem jest model głosowy
(2.5 Live native audio), nie prompt. Głos jest nienegocjowalny, więc zamiast
zmiany modelu: **dwa mózgi**. Flash pisze myśl Moniki, myśl idzie do sesji Live
jako `(Internal Monologue)`, a model głosowy ma z czego mówić.

## Architektura (stan po sesji)

- `backend/llm/thinker.py` — klasa `Thinker` na wstrzykiwanych callables
  (zero importów `backend.core`, testowalna bez AudioLoop).
- Prompt Myśliciela: sekcja `THINKER_CARD` z `character.md` (~1.5 k znaków,
  celowo POZA `inject_sections`) + ostatnie 8 tur + bieżąca wypowiedź.
- **Ścieżka głosowa**: hook w handlerze transkrypcji wejściowej
  (`monikai.py`); myśl powstaje asynchronicznie w trakcie mówienia, czeka na
  domknięcie tury Moniki, drop po 90 s.
- **Ścieżka tekstowa**: `think_for_text()` w handlerze `user_input`; myśl
  powstaje synchronicznie (limit 8 s) i jest wstrzykiwana PRZED tekstem
  użytkownika — model widzi ją, zanim odpowie. Koszt: 1–2 s latencji
  odpowiedzi (zaakceptowane: „nie potrzebuję 0.5 s").
- Bramki free-tier: flaga, regex potakiwań i kontroli łącza, min. 18 znaków,
  20 s odstępu, jeden strzał naraz, retry po 503, cooldown po 429/503.
- Diagnostyka: konsola `[THINKER] myśl: ...` + prefiks `[Myśliciel]` w
  `on_internal_thought`, żeby odróżnić myśl mózgu od natywnej myśli modelu
  głosowego („mózg vs usta").
- Telegram świadomie bez Myśliciela (minimalna złożoność).

## Konfiguracja

```jsonc
// data/settings.json (gitignored)
"thinker": { "enabled": true }
// pełne defaults w settings_store.py:
// min_chars 18, min_interval_sec 20, thinking_budget 0,
// timeout_sec 8, cooldown_sec 60
```

```dotenv
# .env (gitignored)
GEMINI_VAD_SILENCE_DURATION_MS=4000   # sekunda więcej na dolot myśli
```

Model: `gemini-3.5-flash` (env `MONIKAI_THINKER_MODEL`).

## Iteracje na podstawie testów live

### Test 1 (czat tekstowy): mózg nie strzelił ani razu
Hook był tylko w transkrypcji głosowej; test szedł klawiaturą przy spauzowanym
audio. → `think_for_text()` + wstrzyknięcie przed tekstem użytkownika
(`0e135d3`).

### Test 2 (czat tekstowy): „myśl porzucona — nie zdążył w limicie"
Flash domyślnie MYŚLI nad myślą. Pomiar na żywo (smoke w
`tmp/thinker_smoke.py`):

| wariant | czas | jakość |
|---|---|---|
| domyślny thinking | 7.0 s | dobra |
| `thinking_budget=0` | **2.1 s** | ta sama (konkrety Low Roar/Silent Poets, własny kąt, nazwana luka) |

Wniosek: cała myśl MA być outputem — wewnętrzne rozumowanie modelu nad nią to
czysty narzut. → `thinking_budget=0` (`5076e4c`).

### Test 3 (głos): mózg zamilkł, myśli-plany, konfabulacja
- Jedno 503 (przeciążenie free tier) → 120 s ciszy, która zjadła kluczowe tury.
  → retry po 2 s + cooldown 60 s, konfigurowalny (`73cf684`).
- „Halo, słyszymy się?" palił strzał i 20 s odstępu. → kontrole łącza dopisane
  do regexu potakiwań.
- Myśli planner-style („muszę zasygnalizować", „zbadam grunt") zamiast poglądu
  na treść. → twardy zakaz zdań o własnym zachowaniu w instrukcji (`7c7e925`,
  `73cf684`).
- Konfabulacja: „architektura modeli Claude od Anthropic daje mi moją
  wrażliwość" — usłyszała „Claude" w rozmowie i dobudowała tezę o sobie.
  → zakaz wymyślania faktów o sobie/technologii/rozmówcy (`7c7e925`).
- Model głosowy parafrazował wstrzykniętą myśl niemal dosłownie, a każdy skok
  (Myśliciel → natywna myśl → usta) ją degradował. → reguła promptu: nigdy nie
  recytuj `(Internal Monologue)`, weź jeden wniosek/konkret i powiedz po
  swojemu (`7c7e925`).
- Small talk („praca jak to praca") wymuszał puste stanowiska. → model może
  odpowiedzieć `PASS`; PASS nigdy nie jest wstrzykiwany (`73cf684`).

### Feedback charakterologiczny właściciela
„Temat AI w pracy nie zawsze jest czymś, o czym chce się rozmawiać ciągle" —
natywne myśli pokazywały wzorzec podpinania każdego tematu pod pasje i drive.
→ nowa reguła INTERAKCJE: podążaj za tym, co zajmuje rozmówcę; pasje wychodzą,
gdy rozmowa je zaprasza, nie jako filtr na wszystko (`73cf684`).

## Commity sesji

| commit | zakres |
|---|---|
| `a167487` | feat: cała implementacja Myśliciela (6 plików) |
| `c1cd756` | chore: untrack artefaktów pytest w `tmp/` (churnowały working tree) |
| `0e135d3` | feat: ścieżka czatu tekstowego (`think_for_text`) |
| `5076e4c` | fix: `thinking_budget=0` — 7 s → 2.1 s |
| `7c7e925` | fix: obsługa 503, anty-recytacja, anty-konfabulacja, prefiks `[Myśliciel]` |
| `73cf684` | fix: retry 503 + cooldown 60 s, kontrole łącza, zakaz myśli-planów, PASS, reguła anty-AI-obsesja |

Poza tym: masowy churn CRLF w ~90 plikach (zero zmian treści) przywrócony przez
`git restore`, NIE commitowany. Gdyby wracał — rozważyć `.gitattributes`
z `* text=auto eol=lf`.

## Otwarte kwestie / co obserwować

1. **Sufit ust zostaje.** Myśliciel podnosi jakość materiału, ale mówi nadal
   2.5 native audio. Jeśli mózg podpowiada dobrze, a wypowiedź dalej spłaszcza —
   problem jest w ostatnim ogniwie (prompt reguły recytacji / dobór treści),
   nie w Myślicielu.
2. **Parafraza do obserwacji.** Reguła anty-recytacji jest świeża; oceniać po
   trzech warstwach w konsoli: `[THINKER] myśl:` → natywna myśl → wypowiedź.
3. **Free tier jest kapryśny.** Retry + krótszy cooldown łagodzą 503, ale przy
   częstych przeciążeniach rozważyć drugi model fallback
   (np. `gemini-3.5-flash-lite`) albo płatny klucz tylko dla Myśliciela.
4. **PASS w praktyce.** Sprawdzić, czy flash nie nadużywa PASS przy tematach,
   które jednak zasługują na myśl.
5. **Telegram** bez Myśliciela — do decyzji, czy w ogóle potrzebny.

## Jak wyłączyć

`data/settings.json` → `"thinker": {"enabled": false}` + restart. Off = zero
zmian w zachowaniu. Opcjonalnie przywrócić `GEMINI_VAD_SILENCE_DURATION_MS`
na 3000 (albo zakomentować linię w `.env`).
