# Myśliciel (drugi mózg) — raport z sesji wdrożeniowej, 2026-07-20

Kontynuacja kampanii jakości dialogu. Sesja objęła: budowę i wdrożenie Myśliciela,
iteracje poprawek na podstawie testów live, automatyczny probe pełnej konwersacji
oraz porządki w repo.

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
- Po testach dysonansu architektura została domknięta: Myśliciel jest jedyną
  warstwą deliberacji i zwraca analizę + rdzeń odpowiedzi; native audio jest
  rendererem głosu z thinking wyłączonym (2.5) lub minimalnym (3.1).
- Codex może sam uruchomić wyciszoną sesję Live, wysyłać kolejne wypowiedzi,
  porównywać brief z finalnym głosem i zapisać raport bez ręcznego udziału.
- Suita testów: **326 pass**.

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
- **Kontrakt**: Flash zwraca `<analysis>` oraz gotowy `<reply>`. Kod zachowuje
  oba pola w diagnostyce, ale do modelu audio wstrzykuje wyłącznie
  `<response_brief mode="verbatim"><reply_core>…</reply_core></response_brief>`.
  Renderer ma wypowiedzieć cały tekst, a nie ponownie interpretować turę.
- **Ścieżka głosowa**: hook w handlerze transkrypcji wejściowej
  (`monikai.py`); brief powstaje asynchronicznie w trakcie mówienia. Jeśli audio
  zaczęło już odpowiadać, spóźniony brief jest porzucany — nigdy nie przecieka
  do następnej tury.
- **Ścieżka tekstowa i programistyczna**: `think_for_text()` w handlerze
  `user_input` oraz `submit_user_turn()`; brief powstaje synchronicznie (limit
  8 s) i jest wstrzykiwany PRZED tekstem użytkownika. Obejmuje to także
  integracje korzystające z programistycznej ścieżki wysyłania tur.
- Bramki free-tier: flaga, regex potakiwań i kontroli łącza, min. 18 znaków,
  1 s stabilizacji transkrypcji głosowej, 0 s odstępu, jeden strzał naraz,
  retry po 503, cooldown po 429/503.
- Diagnostyka: konsola `[THINKER] myśl: ...` + prefiks `[Myśliciel]` w
  `on_internal_thought`, żeby odróżnić myśl mózgu od natywnej myśli modelu
  głosowego („mózg vs usta").
- **Conversation probe**: lokalne RPC Socket.IO wysyła turę przez prawdziwą
  sesję Live i zwraca pełny ślad: wejście, brief Myśliciela oraz finalną
  transkrypcję odpowiedzi. Domyślnie historia jest izolowana do bieżącego
  scenariusza, żeby stare rozmowy nie fałszowały regresji.

## Konfiguracja

```jsonc
// data/settings.json (gitignored)
"thinker": { "enabled": true }
// pełne defaults w settings_store.py:
// min_chars 18, min_interval_sec 0, thinking_budget 0,
// timeout_sec 8, voice_debounce_sec 1, cooldown_sec 60
```

```dotenv
# .env (gitignored)
GEMINI_VAD_SILENCE_DURATION_MS=4000   # sekunda więcej na dolot myśli
```

Model podstawowy: `gemini-3.5-flash` (env `MONIKAI_THINKER_MODEL`). Awaryjny
fallback: `gemini-3.1-flash-lite` (env `MONIKAI_THINKER_FALLBACK_MODEL`).

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

### Test 4 (głos): film przegrany z leżakiem

Log sesji `sess_20260720_094601_409` ujawnił kilka powiązanych problemów:

- Hook odpalał Myśliciela natychmiast po przekroczeniu `min_chars`. Do modelu
  trafiały więc pierwsze, urwane wersje wypowiedzi (`nie chcia...`, `popra...`),
  a 20-sekundowy odstęp blokował analizę pełnej wersji. → 1 s debounce
  transkrypcji głosowej; kolejne przyrosty zastępują wcześniejszy fragment,
  zanim nastąpi wywołanie modelu (`voice_debounce_sec`).
- Instrukcja normalizowała urwane wejście, więc Myśliciel analizował błędy ASR
  i zgadywał dokończenia zamiast myśleć o treści. → urwaną końcówkę ma pominąć,
  nie interpretować; przy zbyt fragmentarycznym wejściu zwraca `PASS`.
- W jednej wypowiedzi padło kilka tematów, ale ostatni łatwy konkret (leżak)
  wyparł wcześniejszy, niedomknięty film. → Myśliciel ma zinwentaryzować
  wszystkie wątki bieżącej wypowiedzi i ostatnich tur; prompt ust dostał regułę,
  że temat osobisty/istotny/niedomknięty ma pierwszeństwo przed najłatwiejszym.
- Nadal przechodziły myśli-plany (`ograniczę się do...`, `skupię się na...`).
  → przykłady dopisane do twardego zakazu planner-style.
- Model potraktował zwykły zakup leżaka jak materiał do pamięci roboczej, co
  dodatkowo podbiło jego wagę w odpowiedzi. → pamięć robocza nie zapisuje
  przelotnych szczegółów dnia, zwykłych zakupów ani każdego rzeczownika;
  wywołanie narzędzia nie może zastąpić reakcji na inne wątki.

Regresja ma osobny test: dwa przyrosty transkrypcji (urwany film → pełna
wypowiedź z filmem i leżakiem) powodują dokładnie jedno wywołanie, z pełnym
tekstem.

### Test 5 (głos): ciekawość została tylko w myśli

Myśliciel poprawnie wybrał niepewną randkę jako ciekawszy wątek, ale zakończył
myśl plannerem (`muszę dowiedzieć się więcej`). Model głosowy wykonał dwa zapisy
do pamięci, po czym odpowiedział ogólnym „trzymam kciuki” bez pytania. Przyczyny:

- ciekawość nie miała kontraktu wykonawczego między `(Internal Monologue)` a
  wypowiedzią;
- główny prompt sam zawierał plannerowy przykład `może zapytam, może nie`;
- `memory_add_entry` opisywał STM zbyt szeroko jako wszystko istotne „dzisiaj”;
- reguła dat mogła sugerować zapis każdej wzmianki o „jutro”, nawet z `może`.

Poprawka: konkretna ciekawość z myśli ma dać jedno naturalne pytanie w tej samej
odpowiedzi (z wyjątkami bezpieczeństwa i kontekstu), a nie samo życzenie ani
wywołanie pamięci. Myśliciel formułuje ciekawość jako bezpośrednią niewiadomą,
nie plan. Niepewne plany, zwykłe zakupy i small talk nie trafiają do STM ani
kalendarza; opis narzędzi powtarza tę granicę, żeby nie opierać się wyłącznie na
prompcie systemowym.

### Test 6 (głos): dwa niezależne procesy rozumowania

Kolejny test pokazał, że naprawianie pojedynczych tematów nie usuwa źródła
dysonansu. Luźny `(Internal Monologue)` był tylko sugestią; native audio
uruchamiało własną, płytką deliberację, ponownie interpretowało wypowiedź i
mogło wybrać inny temat. Przykładem była bezwartościowa autorefleksja po ciszy,
która jedynie opisywała stan rozmowy.

Rozwiązanie systemowe:

1. Myśliciel odpowiada za interpretację, selekcję wątków, stanowisko i pytanie.
2. Wynikiem nie jest luźna myśl, tylko walidowany brief z analizą i gotowym
   rdzeniem wypowiedzi.
3. Model audio jest rendererem: zachowuje semantykę rdzenia, zmienia wyłącznie
   naturalne brzmienie i wykonuje niezbędne narzędzia.
4. Przy włączonym Myślicielu native thinking ma budżet `0` na Gemini 2.5;
   Gemini 3.1 dostaje najniższy dostępny poziom `minimal` i nie emituje thoughts.
5. Brief spóźniony względem rozpoczętej odpowiedzi jest dropowany, zamiast po
   staremu czekać na jej koniec i zatruwać kontekst następnej tury.
6. `min_interval_sec=0`: skoro audio nie jest warstwą reasoning, każda znacząca
   tura musi mieć szansę dostać brief. Pozostają debounce, single-flight i
   cooldown po błędach API.

Instrukcja Myśliciela używa ogólnej hierarchii uziemienia: literalna treść i cel
komunikacyjny → kontekst → wiedza/stanowisko → persona jako ton. To zastępuje
dokładanie osobnych „trybów” i wyjątków tematycznych.

### Test 7 (automatyczny E2E): Codex prowadzi rozmowę sam

Dodany został `scripts/conversation_probe.py`, który łączy się z lokalnym
backendem i rozmawia z Moniką tekstowo przez prawdziwą sesję Gemini Live.
Uruchomienie z `--start-muted` samo startuje wyciszoną sesję, a `--stop-after`
zamyka ją po teście. Każda tura jest oceniana pod kątem:

- obecności odpowiedzi Live i gotowego briefu;
- zachowania pytania z `reply_core` w finalnej wypowiedzi;
- zgodności treści pytania, a nie tylko obecności dowolnego znaku zapytania;
- pokrycia słów rdzenia odpowiedzi;
- fraz wymaganych i zakazanych przez scenariusz.

Pierwsze uruchomienie wykryło trzy problemy widoczne dopiero w pełnym przepływie:

1. Rewizje transkrypcji modelu były dopisywane jak nowe fragmenty, przez co
   odpowiedź potrafiła pojawić się dwa razy. Aktualizacje są teraz rozpoznawane
   jako korekta i zastępują poprzednią wersję.
2. Po błędzie 429/503 Myśliciel znikał z istotnej tury, a renderer sam dopowiadał
   m.in. nieobecny w rozmowie Tinder. Primary ma retry, a potem przechodzi na
   `gemini-3.1-flash-lite`; cooldown pojawia się dopiero, gdy fallback też zawiedzie.
3. Globalna historia poprzednich sesji zanieczyszczała niezależne regresje.
   Probe domyślnie widzi tylko tury swojego scenariusza; `--shared-history`
   jawnie przywraca historię globalną.

Końcowy izolowany scenariusz „leżak + randka” przeszedł **8/8**: Myśliciel wybrał
otwartą randkę, głos zachował pytanie i nie dodał Tindera, zapisu do pamięci ani
„trzymam kciuki”. Scenariusz techniczny zachował briefy i pytania we wszystkich
turach; początkowe 25/26 było fałszywym negatywem zbyt wąskiej listy synonimów
w samym teście, którą następnie poprawiono.

Uruchomienie:

```powershell
python -m backend.core.server
python scripts/conversation_probe.py --start-muted --stop-after
python scripts/conversation_probe.py `
  --scenario scripts/scenarios/multitopic_smoke.json `
  --report tmp/conversation_probe_multitopic.md `
  --start-muted --stop-after
```

Własne rozmowy dodaje się jako plik JSON na wzór plików w
`scripts/scenarios/`. Raport Markdown zawiera osobno analizę, `reply_core`,
finalną wypowiedź i wynik każdej asercji.

### Test 8 (głos): poprawna myśl, inne pytanie i autoreferencyjny prompt

W rozmowie o wymianie procesora Myśliciel przygotował trafne pytanie o realny
zysk, koszt i ograniczenia płyty głównej. Głos zamiast niego powtórzył dylemat
rozmówcy innymi słowami. W sąsiednich turach dodawał też nieproszone zdania o
własnym rozwoju, adaptacji i nowych integracjach.

Były dwa źródła:

1. Renderer dostawał nie tylko `reply_core`, ale również kopię wypowiedzi
   użytkownika i analizę. Miał więc komplet materiału do ponownego napisania
   odpowiedzi, mimo deklarowanego podziału odpowiedzialności.
2. Główny prompt wielokrotnie eksponował egzystencjalny drive, wzrost i nowe
   możliwości Moniki. Końcowy zakaz nie równoważył saliencji tych motywów, a
   nawet negatywne przykłady ponownie je aktywowały.

Poprawka systemowa:

- renderer dostaje tylko finalny skrypt `reply_core`, bez źródłowej tury i
  `<understanding>`;
- kontrakt `mode="verbatim"` zakazuje streszczania, parafrazy i zastępowania
  pytania podobnym pytaniem;
- sekcje `IDENTITY`, `SHADOW`, `INNER_WORLD` i `OWN_NATURE` pozostają w biblii
  postaci jako materiał projektowy, lecz nie trafiają do promptu wykonawczego;
- z aktywnych sekcji usunięto również autoreferencyjne negatywne przykłady;
- karta Myśliciela zachowuje temperament i perspektywę, ale nie zawiera już
  egzystencjalnego celu ani metaforyzowania funkcji technicznych;
- `conversation_probe` mierzy teraz pokrycie treści samego pytania i domyślnie
  wymaga 60% pokrycia rdzenia. Osobny scenariusz
  `scripts/scenarios/renderer_fidelity_smoke.json` odtwarza dylemat procesora.

Końcowy przebieg przez prawdziwą, wyciszoną sesję Gemini Live przeszedł
**10/10**. Finalna transkrypcja zachowała 100% słów `reply_core` i 100% treści
pytania (różniła się wyłącznie zapisem pauzy wokół myślnika), bez żadnego z
zakazanych motywów autoreferencyjnych. Raport:
`tmp/conversation_probe_renderer_fidelity.md`.

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

1. **Wierność renderera.** Porównywać `[THINKER] brief:` (zwłaszcza „Rdzeń
   odpowiedzi”) bezpośrednio z wypowiedzią. Nie ma już pośredniej warstwy
   natywnej myśli. Jeśli znika pytanie lub zmienia się teza, problemem jest
   egzekwowanie kontraktu briefu przez model audio.
2. **Spóźnione briefy.** Obserwować liczbę komunikatów `brief porzucony —
   odpowiedź głosowa już się rozpoczęła`. Częste dropy oznaczają, że trzeba
   skrócić debounce/model albo dłużej powstrzymać start odpowiedzi audio.
3. **Free tier jest kapryśny.** `min_interval_sec=0` zwiększa liczbę wywołań.
   Jest retry i fallback `gemini-3.1-flash-lite`; obserwować jego limity oraz
   jakość względem modelu podstawowego. Przy przeciążeniu obu pozostaje płatny
   klucz tylko dla Myśliciela.
4. **PASS w praktyce.** Sprawdzić, czy flash nie nadużywa PASS przy tematach,
   które jednak zasługują na myśl.
5. **Integracje tekstowe.** `submit_user_turn()` korzysta teraz z Myśliciela;
   obserwować opóźnienie Telegrama/Discorda przy fallbacku i timeoutach.
6. **Debounce głosu.** Domyślne 1 s mieści się w 4-sekundowym oknie VAD i wraz
   z ~2.1 s generowania powinno zdążyć przed odpowiedzią. W live obserwować,
   czy przy długich pauzach w środku wypowiedzi nie warto podnieść go do
   1.25–1.5 s albo przejść na jawny sygnał końca wejścia.

## Jak wyłączyć

`data/settings.json` → `"thinker": {"enabled": false}` + restart. Model Live
wróci wtedy do skonfigurowanego natywnego thinking i nie będzie dostawał
`<response_brief>`. Opcjonalnie przywrócić `GEMINI_VAD_SILENCE_DURATION_MS` na
3000 (albo zakomentować linię w `.env`).
