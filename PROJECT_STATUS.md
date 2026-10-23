# xkom-bot — status projektu (stan na 23.10.2026)

> Dokument powrotu: co działa, co się NIE udało i DLACZEGO (nie wracać do tych
> ścieżek bez powodu), i co jeszcze zostało do ogarnięcia.

## 1. Co działa (główny tryb — lokalny)

Lokalny bot na Macu jest **źródłem głównym** i jest wystarczający:

- **launchd** `com.borys.xkombot` — autostart przy logowaniu + auto-restart po crashu
  (`install_launchd.sh` / `uninstall_launchd.sh`)
- Monitorowanie: **YouTube** (oficjalny RSS kanału, co 20 s + fallback yt-dlp) i
  **TikTok** (yt-dlp bez logowania, działa z domowego IP, cadence 3 min)
- Detekcja kodów: najpierw skan **opisu wideo** (wzorce „kod: XXX"), potem
  **OCR klatek** (tesseract pol, scoring: duża czcionka + stabilność + kontekst „kod")
- **Alert w Telegramie tylko dla kandydatów `strict`** — format: nazwa produktu z
  kalendarza, cena (JSON-LD), kod, link do produktu, link YT, komenda auto-zakupu.
  Dedup: ten sam kod nie alarmuje 2× w 6 h.
- **Auto-cleanup dysku**: po OCR wideo i klatki są kasowane (zostaje podgląd kandydata,
  ~100 KB). Bez tego burza 23.10 zjadła 3,5 GB — już nie może.
- Zakup: `python3 -m xkom.go KOD [--product URL]` (kod do koszyka) lub
  `python3 -m xkom.buy URL --code KOD [--pay]` (pełny silnik, bramka ENTER przed
  „Zamawiam i płacę", BLIK/3DS czeka na telefon). Profil przeglądarki: `state/browser`.

Stan lokalny: `state/` (yt_seen, tt_seen, bw_state, alerted_codes, candidates,
prices) — w `.gitignore`, nie trafia na GitHub.

## 2. Co zostało do ogarnięcia: INSTAGRAM

IG jest **za login wall** — bez cookies profil @xkompl nie jest czytelny.
Kalendarz Black Weeks przypisuje platformę do każdego dnia (np. 26.10 Logitech
różowy → IG, 27.10 Silver Monkey → IG) — bez IG w te dni bot jest ślepy.

### Jak to zrobić (krok po kroku)

1. **Zostawić konto IG w spokoju (najpierw!)**. Problem: konto tworzone przez
   Facebooka trafia w pętlę checkpointów Mety i jest wyrzucane. Naprawa:
   - rejestracja/logowanie **bez Facebooka** (e-mail),
   - **weryfikacja numeru telefonu** (SMS/WhatsApp) — to w 90% przypadków łamie pętlę,
   - pierwsze logowanie w **apce na telefonie**, potem desktop.
   Jeśli konto nadal nie staje — nie męczyć się; plan B poniżej.
2. **Eksport cookies** (gdy konto działa): rozszerzenie Chrome „Get cookies.txt
   LOCALLY" (getcookiestext.org) → zalogowane na instagram.com → „Get cookies.txt
   LOCALLY" → plik .txt.
   (Jeśli rozszerzenie da JSON — konwersja do Netscape jest banalna, wystarczy
   powiedzieć, gdzie plik leży.)
3. **Wdrożenie** (robione za usera): walidacja pliku (Netscape + cookie sesji
   `ds_user_id`), zapis do `state/ig_cookies.txt`, włączenie
   `instagram.enabled: true` w `config.yaml`. Bot lokalny monitoruje IG co ~90 s
   (moduł już istnieje: `xkom/sources.py::poll_instagram`).

### Plan B (bez konta)

W dni, w których kalendarz pokazuje kod **na IG** (widoczne w `./status.sh`),
zaglądnięcie ręcznie na profil @xkompl w zwykłej przeglądarce. Tracimy minuty,
nie kod.

## 3. Co się NIE udało i DLACZEGO — nie wracać do tych ścieżek

### 3.1. YouTube w chmurze GitHub Actions (OCR wideo) — ZABITE, bez proxy nie ma sensu

Pełna diagnoza (testy 23.10, logi przebiegów 39926177825 → 39939770473):

| Warstwa | Wynik |
|---|---|
| RSS kanału (wykrywanie nowych filmów) | ✅ działa z IP datacenter |
| Pobieranie wideo bez cookies | ❌ „Sign in to confirm you're not a bot" |
| Cookies drugiego (nowego) konta Google | ❌ ta sama blokada — nowe konto nie ma zaufania |
| Cookies GŁÓWNEGO konta (pełna sesja, zweryfikowana lokalnie ✅) | ⚠️ bot-wall przeszła, ale… |
| …lista formatów z IP datacenter | ❌ **PUSTA** — „Requested format is not available" |
| 5 klientów playera (default, tv, web_embedded, ios, android_vr) | ❌ wszyscy to samo |
| deno (runtime JS — yt-dlp go WYMAGA od końca 2025) | ✅ zainstalowany, nie pomógł |
| Najbardziej luźny selektor `bv*+ba/b` | ❌ nadal pusto |

**Wniosek ostateczny:** to blokada **poziomu IP** serwerów GitHuba, nie klienta,
nie cookies, nie tokenu. Potwierdzenie od maintainera yt-dlp (bashonly, issue
#16773, zamknięte jako „invalid" = „nie da się naprawić"): PO tokeny „nie są
rozwiązaniem, gdy IP jest już zablokowane… there is nothing you can do".

**Jedyne drogi, jeśli kiedyś wrócimy do 24/7 w chmurze:**
- proxy rezydencjalne (~2–5 zł/mies.) podpięte pod yt-dlp w workflow (krok:
  `--proxy` w `extract.download_video` + sekret PROXY_URL), LUB
- self-hosted runner na zawsze-włączonym sprzęcie w domu (mini PC/NAS/laptop)
  — domowe IP, za darmo, ale wymaga sprzętu.

### 3.2. TikTok w chmurze — ZABITE

TikTok twardo blokuje IP datacenter (redirect na /404, `Unsupported URL`).
Cookies nie pomogą, to też IP. TikTok działa tylko z domowego IP → tylko lokalnie.

### 3.3. x-kom.pl z IP datacenter — degradacja (403)

Kalendarz Black Weeks (`blackweeks.py`) z IP GitHuba: **HTTP 403** mimo pełnych
nagłówków przeglądarki (UA, Accept, Referer). Blokowanie po IP, nie po UA.
Efekt: w chmurze alerty bez nazwy/ceny produktu (fallback „patrz wideo").
Lokalnie działa bez problemu.

### 3.4. Konto IG przez Facebook — problem po stronie Mety

Pętla checkpointów: login → „zweryfikuj konto" → wyrzucenie → login → …
Przyczyny: brak weryfikacji telefonu (główna), wycofywana ścieżka logowania
przez FB dla nowych kont, niskie zaufanie nowego konta FB. Rozwiązanie: punkt
1 w sekcji 2. Nie próbować kolejnych logowań przez FB.

### 3.5. Mniejsze (naprawione — tu tylko po to, żeby wiedzieć, że to było)

- **Burza alertów** (23.10): chwilowy błąd SSL RSS → fallback yt-dlp zapisywał
  stan pod INNYMI kluczami (`youtube/videos:ID` vs `youtube:ID`) → 40 filmów
  wyglądało na nowe → spam „nowy post" + 2 h OCR. Fix: jednolite klucze + limit 15.
- **Fałszywe „kody"** (STEAM, MOTOROLA, UGREEN…): scoring dawał `strict` za samą
  dużą czcionkę. Fix: `strict` WYMAGA kontekstu „kod" na klatce **i** dużej
  czcionki; reszta max `loose` (cisza). Stopwords promocyjne (RABATOWY, PROMOCJA…).
- **YAML**: dwukropek w niecytowanym `name:` kroku = błąd parsowania workflow
  (GitHub: „does not have workflow_dispatch" — mylące!); `secrets` niedostępne w
  warunku `if` → sprawdzanie w `run`.
- **Dysk**: brak auto-cleanup wideo/klatek (3,5 GB po jednej burzy). Fix: cleanup
  w `pipeline.process_item` (try/finally).
- GitHub po zmianie workflow czasem ~1 min opóźnia indeksację — dispatch 422
  potrafi zniknąć sam, ale NIE zawsze (raz to był błąd parsowania).

## 4. Decyzje operacyjne

- **Chmura GitHub Actions: WYŁĄCZONA** (`gh workflow disable xkom.yml`, stan
  `disabled_manually`). Repo `MrBorys1984/xkom-bot` publiczne (kod bez sekretów;
  `config.yaml` gitignorowany). Sekrety GH istnieją: TELEGRAM_BOT_TOKEN,
  TELEGRAM_CHAT_ID, YT_COOKIES (głównego konta). Przywrócenie ma sens TYLKO
  z proxy rezydencjalnym albo self-hosted runnerem (patrz 3.1).
- **Lokalny bot = jedyny monitor** (launchd). Alerty nie dublują się, bo chmura
  nie chodzi.
- Kody Black Weeks są jednorazowe i spala się je w minuty — więc „pokrycie nocą"
  jest mniej ważne niż myślenie sugeruje: kod z rana trzeba wyłapać w dzień,
  a wtedy Mac zwykle pracuje. To uzasadnia hybrydę (lokal) jako tryb docelowy.

## 5. Szybki start (po powrocie)

```bash
cd ~/xkom-bot
./status.sh                 # co jest monitorowane + kalendarz kodów (dziś/jutro)
./start.sh / ./stop.sh      # ręczny start/stop (launchd robi to sam)
python3 -m xkom.go KOD      # sygnał GO: wklej kod w koszyku
python3 -m xkom.buy URL --code KOD   # pełny zakup (bramka ENTER)
tail -f state/logs/bot.log  # logi
```

Testy: `python3 test_synthetic.py` (OCR, PASS), testy `scan_text` w
`test_pipeline.py`.

## 6. Kluczowe fakty

- Kanał: @xkompl, channel_id `UCmsxFRm1zRgueucG2Pc9Kzg`; TT/IG: @xkompl.
- Format kodu x-kom: 6–8 znaków, A-Z + cyfry, jednorazowy, przypisany do produktu
  i platformy dnia (kalendarz: x-kom.pl/lp/black-weeks, parser w `blackweeks.py`,
  61 produktów w `bw_state.json`).
- Link z „wklejonym" kodem NIE działa (x-kom nie przyjmuje kodu przez parametry
  URL) — alert daje link do produktu + kod.
- Python 3.15 (homebrew): `multiprocessing.spawn` NIE działa w tym setupie —
  używany jest `ThreadPoolExecutor(4)` dla OCR.
- Telegram: bot token w lokalnym `config.yaml` (gitignored) + w sekrecie GH.
- `state/browser` = profil Playwright z sesją x-kom (do zakupów; pierwsze użycie
  `go`/`buy` poprosi o ręczne zalogowanie w otwartym Chromium).
