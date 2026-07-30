# Handoff: naprawa Conversation Lab i panelu restartu (2026-07-30)

Dokument dla następnej sesji Claude'a, uruchamianej **z pełnym dostępem SSH** do serwera.
Poprzednia sesja postawiła diagnozę, ale nie mogła jej wdrożyć: kod do naprawy nie leży
w tym repo, a próba `ssh` została zablokowana przez classifier uprawnień.

Wszystkie fakty poniżej zostały zweryfikowane empirycznie 2026-07-30 ok. 15:00 czasu
lokalnego. Stan runtime mógł się od tego czasu zmienić — **zacznij od kroku 0**.

---

## 1. Topologia (przeczytaj to najpierw)

Najdroższa pomyłka w tym projekcie to diagnozowanie lokalnego kodu, gdy UI rozmawia
z inną maszyną. Tak zaczęła się ta sesja.

- **Backend MonikAI działa wyłącznie na serwerze `192.168.1.10`**, jako kontener Docker
  o nazwie `monikai`. Lokalnie (Windows, `c:\AI\monikai`) uruchamiamy **tylko klienta**.
  To decyzja właściciela, nie stan przejściowy — nie proponuj stawiania backendu lokalnie.
- Klient: `npm run dev:client` ustawia `MONIKAI_CLIENT_ONLY=true`, co w
  `electron/main.js:237-241` pomija start lokalnego Pythona. Adres backendu pochodzi
  z `.env.local` → `VITE_MONIKAI_SERVER_URL=http://192.168.1.10:8000`.
- `backend/core/server.py:680-683` bindouje `host="127.0.0.1"`. Backend uruchomiony
  lokalnie **nie jest widoczny w LAN** — to nie jest błąd do „naprawienia".
- `home.tosutosu.pl` → DNS na `192.168.1.10`, za **Caddy**. Stoją tam **dwie różne aplikacje**:
  - **gethomepage** (Next.js) obsługuje wszystko poza `/api/monikai-control/*`;
  - **MonikAIControl** — mały serwis na stdlib `http.server`, przedstawia się nagłówkiem
    `Server: MonikAIControl/1.0 Python/3.13.14`, obsługuje `/api/monikai-control/*`.
- **Źródeł gethomepage ani MonikAIControl NIE MA w tym repo.** Żyją w kontenerach
  na serwerze. Nie trać czasu na szukanie ich lokalnie.

Jak w każdej chwili sprawdzić, z czym gada klient:

```powershell
Get-NetTCPConnection | Where-Object { $_.RemotePort -eq 8000 } |
  Select-Object State,RemoteAddress,OwningProcess
```

---

## 2. Krok 0 — odtwórz stan przed jakąkolwiek zmianą

```bash
# MonikAIControl: /status działa, /panel nie istnieje
curl -s -i http://home.tosutosu.pl/api/monikai-control/status
curl -s -i http://home.tosutosu.pl/api/monikai-control/panel

# granica routingu Caddy: to powinno dać HTML-owe 404 od Next.js
curl -s -I http://home.tosutosu.pl/api/definitely-not-a-route-xyz123

# integracja docker w gethomepage (działa, zwraca pełne dane)
curl -s http://home.tosutosu.pl/api/docker/status/monikai/my-docker
curl -s http://home.tosutosu.pl/api/docker/stats/monikai/my-docker
```

Oczekiwane wyniki zmierzone poprzednio:

| Żądanie | Wynik |
|---|---|
| `GET /api/monikai-control/status` | `200` `{"ok": true, "container": "monikai", "status": "running", "running": true, "health": "healthy"}` |
| `GET /api/monikai-control/panel` | `404` `{"ok": false, "error": "not found"}` |
| `GET /api/monikai-control/{/,health,index.html,ui}` | `404`, ten sam JSON |
| `POST /api/monikai-control/{nieistniejąca}` | `404`, ten sam JSON → **`do_POST` istnieje** |
| `PUT` / `OPTIONS` na cokolwiek | `501` HTML od stdlib → istnieją **tylko** `do_GET` i `do_POST` |
| `GET /api/docker/stats/monikai/my-docker` | `200`, pełny payload: `cpu_stats` + `precpu_stats` (oba z `system_cpu_usage`), `memory_stats` (~195 MB / 15,0 GB), `networks.eth0` |

### Odczyt runtime settings serwera

Użyj Pythona z conda env `monikai` (ma `python-socketio` 5.16.3 i `aiohttp`).
Token weź z `.env.local` → `VITE_MONIKAI_SOCKET_TOKEN`.
**Nie wpisuj tokenu do żadnego pliku w repo** — `.env` i `.env.local` są w `.gitignore`,
ale `docs/` już nie.

```python
# uruchom: C:/Users/Bartosz/miniconda3/envs/monikai/python.exe ten_plik.py
import asyncio, json, os, socketio
from dotenv import dotenv_values

TOKEN = (os.getenv("MONIKAI_SOCKET_TOKEN")
         or dotenv_values(r"c:\AI\monikai\.env.local").get("VITE_MONIKAI_SOCKET_TOKEN") or "")

async def main():
    sio = socketio.AsyncClient(reconnection=False)
    got = {}
    @sio.on("settings")
    async def _(data): got["s"] = data
    await sio.connect("http://192.168.1.10:8000", auth={"token": TOKEN},
                      transports=["websocket"], wait_timeout=15)
    print("probe_status:", await sio.call("conversation_probe_status", timeout=10))
    await sio.emit("get_settings")
    for _ in range(40):
        if "s" in got: break
        await asyncio.sleep(0.25)
    s = got.get("s") or {}
    print("thinker:", json.dumps(s.get("thinker")))
    print("speech:", json.dumps(s.get("speech")))
    await sio.disconnect()

asyncio.run(main())
```

Zmierzone wcześniej: `thinker.enabled = false`, `speech.delivery_mode = "dedicated_tts"`,
sesja Live `running/ready`. Zwykłe połączenie **nie** przejmuje aktywnego frontendu —
`set_active_frontend_sid` woła się tylko w `start_audio`, więc sonda jest bezpieczna.

---

## 3. Zadanie A — napraw Conversation Lab (małe, zrób najpierw)

**Objaw:** w UI baner „CONVERSATION LAB — Dedicated text author is disabled".

**Przyczyna:** gate `_dedicated_speech_enabled()` w `backend/core/monikai.py:1237-1243`
wymaga **obu** warunków: `thinker.enabled == true` **oraz**
`speech.delivery_mode == "dedicated_tts"`. Handler `conversation_draft_turn`
(`backend/core/handlers/chat_input_handlers.py:96-97`) odrzuca żądanie, gdy gate nie
przechodzi. Na serwerze `thinker.enabled` to `false`.

Lokalne `data/settings.json` ma `true` — **dlatego lokalna inspekcja myli**. Plik na
serwerze jest starszy: zawiera legacy klucz `thinking_budget: 0`, usunięty z
`DEFAULT_SETTINGS` commitem z 2026-07-30 12:30, i nadpisuje nowy default `enabled: true`.

**Co zrobić** — w `data/settings.json` **na serwerze** (wewnątrz kontenera `monikai`
albo w zamontowanym volume):

```json
"thinker": { "enabled": true }
```

Przy okazji usuń martwy `thinking_budget` (Gemini 3.x używa `thinking_level`).
Potem **zrestartuj kontener** — patrz Zadanie B; bez restartu zmiana nie wejdzie
(uzasadnienie w sekcji 5).

Tego **nie da się zrobić z UI**: handler `update_settings`
(`backend/core/handlers/settings_profile_handlers.py:25`) nie obsługuje kluczy
`thinker` ani `speech`. Nie dorabiaj do tego przełącznika w UI, jeśli właściciel
o to nie poprosi.

**Kryterium odbioru:** sonda z sekcji 2 pokazuje `thinker.enabled = true`, a wysłanie
wiadomości z włączonym Conversation Lab zwraca warianty odpowiedzi zamiast błędu.

---

## 4. Zadanie B — panel restartu w homepage

### Stan obecny

W konfiguracji gethomepage (najpewniej `services.yaml` w kontenerze; zweryfikuj) usługa
MonikAI w grupie „AI" wygląda tak:

```json
{ "name": "MonikAI", "id": "monikai-service", "icon": "mdi-robot-love",
  "href": "http://192.168.1.10:8000/status",
  "description": "Lokalny backend asystentki",
  "server": "my-docker", "container": "monikai", "showStats": true, "weight": 100,
  "widgets": [{ "type": "iframe",
    "src": "http://home.tosutosu.pl/api/monikai-control/panel",
    "classes": "h-24 sm:h-24 md:h-24 lg:h-24 xl:h-24 2xl:h-24",
    "referrerPolicy": "same-origin", "loadingStrategy": "eager",
    "allowScrolling": "no" }] }
```

Iframe celuje w `/panel`, którego MonikAIControl nie ma → renderuje surowy JSON błędu.
**To nie jest błąd MonikAI** — stringu `"not found"` w tym formacie nie ma w `backend/`.

### Kolejność prac

1. **Znajdź serwis na serwerze.** Szukaj procesu z nagłówkiem `MonikAIControl/1.0`
   i konfiguracji Caddy kierującej `/api/monikai-control/*`. Zacznij od
   `docker ps`, reverse-proxy config Caddy, potem `docker inspect` / `docker exec`.
2. **Przeczytaj jego kod** i wypisz istniejące trasy w `do_GET` i `do_POST`.
   Wiemy, że `do_POST` istnieje — bardzo prawdopodobne, że akcja restartu jest już
   napisana i brakuje tylko UI. **Ustal jej realną ścieżkę z kodu, nie zgaduj.**
3. **Sprawdź politykę restartu kontenera** — to determinuje, czy „restart" jest w ogóle
   możliwy, czy tylko „wyłączenie":
   ```bash
   docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' monikai
   ```
   Jeśli `no`, zaproponuj właścicielowi `unless-stopped`. Bez tego każde ubicie procesu
   zostawia backend martwy do ręcznego podniesienia po SSH.
4. **Dodaj `GET /panel`** zwracające kompaktowy, samodzielny HTML. Wymagania wynikające
   z konfiguracji widgetu:
   - wysokość `h-24` (~96 px) i `allowScrolling: no` → wszystko musi się zmieścić bez scrolla;
   - gethomepage ma **ciemny motyw** → tło przezroczyste lub ciemne, jasny tekst;
   - `referrerPolicy: same-origin`, a oba adresy idą przez ten sam host, więc `fetch()`
     z panelu na `/api/monikai-control/...` jest same-origin — bez CORS;
   - przycisk musi wysyłać **POST** (patrz ostrzeżenie niżej), pokazywać stan
     („restartuję…", sukces, błąd) i najlepiej odpytywać `/status` po akcji.
5. **Zweryfikuj** i dopiero wtedy uznaj zadanie za zrobione.

### Ostrzeżenia

- **Nigdy nie wystawiaj restartu na GET.** Linki i bookmarki w gethomepage robią GET,
  więc to kusi jako skrót — ale wtedy prefetch przeglądarki, skaner sieci albo crawler
  może ubić backend. Dokładnie dlatego właściwym rozwiązaniem jest iframe z przyciskiem,
  a nie zamiana widgetu na link.
- **Nie sonduj endpointu restartu na ślepo.** Poprzednia sesja świadomie tego nie zrobiła:
  gdyby restart wisiał na GET, żądanie ubiłoby żywą sesję Moniki. Najpierw przeczytaj kod,
  potem testuj — i najlepiej uzgodnij moment testu z właścicielem, bo restart zrywa
  trwającą rozmowę.
- Zamiana widgetu `iframe` na `customapi` przeciwko `/status` usunie komunikat błędu,
  ale odbierze przycisk. To krok w tył — intencją był interaktywny panel.

**Kryterium odbioru:** `GET /api/monikai-control/panel` zwraca `200 text/html`, w dashboardzie
widać zwarty panel z działającym przyciskiem, kliknięcie restartuje kontener `monikai`,
a panel sam pokazuje, że usługa wróciła.

---

## 5. Dlaczego restart jest w ogóle potrzebny

`load_settings()` woła się **dokładnie raz**, przy imporcie
(`backend/core/server.py:660`), a `SETTINGS` to moduł-level dict. **Nie ma żadnego eventu
przeładowania ustawień** — sprawdzone. Zmiana `data/settings.json` wymaga więc pełnego
restartu procesu.

Istniejące ścieżki wyjścia procesu (przy polityce `unless-stopped` każda z nich = restart):

| Droga | Gdzie | Uwaga |
|---|---|---|
| event `shutdown` | `backend/core/handlers/control_handlers.py:19-26` | zwraca `{"ok": true}`, nic nie zamyka po stronie klienta — najczystsza |
| event `kill_server` | `backend/core/handlers/system_frontend_handlers.py:201` | podpięty pod logout w `src/App.jsx:184-192`, zamyka też okno klienta |
| narzędzie `request_program_shutdown` | `backend/core/monikai.py:3159` | domyślnie `False` w uprawnieniach; po włączeniu można **poprosić Monikę głosem, żeby się zrestartowała** |

Jeśli chodzi tylko o odświeżenie **sesji**, a nie procesu, restart jest zbędny: handler
`disconnect` (`backend/core/handlers/audio_lifecycle_handlers.py:397-413`) zatrzymuje
AudioLoop przy odejściu aktywnego frontendu, a `start_audio` tworzy go od nowa.

---

## 6. Zadanie C (opcjonalne, niska waga) — kafelki CPU/MEM/RX/TX pokazują „-"

**To nie jest brak danych.** Endpointy gethomepage zwracają wszystko, co potrzebne do
wyliczenia wszystkich czterech metryk (patrz tabela w sekcji 2). Przyczyny dashy
**nie ustalono** — może to być zwykły stan ładowania na zrzucie ekranu. Sprawdź ponownie
po naprawie panelu i nie wymyślaj przyczyny bez dowodu.

---

## 7. Pułapka, na którą już raz wpadliśmy

Osierocony backend potrafi udawać, że żyje. Poprzednia sesja znalazła lokalnie proces
`python -u -m backend.core.server` (PID 19400) z martwym procesem rodzicielskim:
`GET /status` odpowiadał w 2 ms, ale socket.io nigdy nie potwierdzał połączenia —
wysłany pakiet `0{}` zostawał bez odpowiedzi 30 s, na pollingu i na WebSocket.

Najprawdopodobniejsze wyjaśnienie (wniosek, nie fakt potwierdzony debuggerem): handler
`connect` w `backend/core/handlers/audio_lifecycle_handlers.py:364` zaczyna od `print(...)`,
a przy `-u` zapis idzie prosto do potoku stdout, którego nikt już nie czyta — i blokuje się
na zawsze. Trasy HTTP nic nie drukują, dlatego działały.

Ten konkretny proces został ubity. Ale gdy coś odpowiada po HTTP i milczy po socket.io,
sprawdź to jako pierwsze. Zwróć też uwagę, że `electron/main.js:243-246` przy zajętym
porcie 8000 zakłada, że backend już działa, i po prostu się do niego podłącza — czyli
przyklei się do takiego zombie.
