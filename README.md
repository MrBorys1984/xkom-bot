# xkom-bot 🤖

Bot do akcji **„sprzęt za 1 zł w x-kom”**: monitoruje kanały x-kom,
wyłapuje ukryte kody rabatowe z wideo (OCR klatek), powiadamia i —
gdy dasz sygnał **GO** — sam aplikuje kod w koszyku x-kom.

## Jak działa akcja x-kom
- x-kom codziennie (pon–pt) ukrywa kody na FB / IG / TikTok / YouTube / X / Threads.
- Każdy kod dotyczy konkretnego produktu i **działa tylko raz**.
- Wygrywa najszybszy: wpisujesz kod w koszyku i płacisz 1 zł.

## Architektura

```
┌─────────────┐   co 20–45 s   ┌──────────────────┐
│  YouTube    │ ─────────────► │  bot.py          │
│  (yt-dlp)   │  nowe posty    │  (pętla)         │
│  Instagram* │                └────────┬─────────┘
└─────────────┘                         │ pobierz wideo (720p)
                                        ▼
                                 ┌──────────────┐   OCR tesseract
                                 │  extract.py  │   klatki co 0.1 s
                                 └──────┬───────┘
                                        │ kandydat na kod
                                        ▼
                                 ┌──────────────┐
                                 │ notify.py    │  Telegram + macOS
                                 └──────────────┘
                                        │
              TY DASZ SYGNAŁ GO ────────┤
              (python3 -m xkom.go KOD)  ▼
                                 ┌──────────────┐
                                 │  apply.py    │  Playwright (Chromium)
                                 └──────────────┘  logowanie → koszyk
                                                   → kod → rabat → TY finalizujesz
```

* Instagram jest opcjonalny i wymaga cookies z drugiego konta (ryzyko BANa).
  YouTube jest źródłem głównym, bo x-kom krzyżuje tam ten sam content
  (m.in. Shorts z tej samej akcji).

## Instalacja

```bash
cd ~/xkom-bot
./install.sh
```

Potrzebne: `ffmpeg`, `tesseract`, `yt-dlp`, Python 3 (wszystko postawi install.sh).

## Użycie

```bash
# 1. Start monitorowania (w osobnym terminalu, zostaw działający)
python3 -m xkom.bot

# 2. Sprawdź, co wyłapał
python3 -m xkom.status

# 3. SYGNAŁ GO — zastosuj kod w koszyku (otwiera się Chromium z Twoim profilem)
python3 -m xkom.go XKOM-9F2KQ1
# albo z produktem do dodania do koszyka:
python3 -m xkom.go 482913 --product "https://www.x-kom.pl/p/1520216-...html"
python3 -m xkom.go 482913 --search "HyperX Cloud Mini"

# 4. PEŁNY ZAKUP (silnik zakupów) — produkt -> kod -> kasa -> "Zamawiam i płacę"
#    Domyślnie bot STANIE przed finalnym kliknięciem i czeka na ENTER (potwierdzenie).
python3 -m xkom.buy "https://www.x-kom.pl/p/1520216-...html" --code XKOM-9F2KQ1
#    pełna automatyzacja (skacze potwierdzenie ENTER — używaj świadomie):
python3 -m xkom.buy "https://www.x-kom.pl/p/1520216-...html" --code XKOM-9F2KQ1 --pay
```

### Pierwsze uruchomienie `go`
Przeglądarka otworzy x-kom **bez logowania** — zaloguj się tam ręcznie
raz na zawsze (sesja zostaje w `state/browser/`), a potem bot będzie
aplikował kody w Twoim zalogowanym koszyku. Bot **nie finalizuje
zamówienia ani nie płaci** — po aktywowaniu rabatu zostawia otwartą
przeglądarkę na 10 min, żebyś dokończył checkout sam.

## Powiadomienia
- Domyślnie: dźwięk + powiadomienie macOS + log w `state/logs/bot.log`.
- Telegram (zalecane, bo możesz być z dala od komputera):
  1. napisz do **@BotFather** → `/newbot` → token
  2. w **@userinfobot** weź swój chat id
  3. wklej oba do `config.yaml` → sekcja `telegram:`

## Pliki
| Plik | Rola |
|---|---|
| `config.yaml` | źródła, częstotliwość, OCR, Telegram, sklep |
| `xkom/bot.py` | pętla główna: monitorowanie + ekstrakcja + powiadomienia |
| `xkom/sources.py` | YouTube (yt-dlp) + Instagram (opcjonalnie) |
| `xkom/extract.py` | pobieranie wideo, ffmpeg → klatki, tesseract OCR, filtry kodów |
| `xkom/notify.py` | Telegram, macOS notification, dźwięk |
| `xkom/apply.py` | Playwright: koszyk → kod → weryfikacja rabatu |
| `xkom/checkout.py` | silnik zakupów: kod → kasa → adres/dostawa/płatność (z konta) → finalny klik |
| `xkom/go.py` | komenda sygnału GO (kod do koszyka) |
| `xkom/buy.py` | komenda pełnego zakupu (`--pay` = auto) |
| `xkom/status.py` | podgląd kandydatów |
| `state/` | sesje, kandydaci, logi, zrzuty ekranu (w .gitignore) |

## Instrukcja Instagram (10 min, drugie konto!)

**Nigdy nie używaj głównego konta** — scrapowanie może je obciążyć.

1. Przygotuj drugie konto IG (zapasowe lub nowe, prywatne).
2. W **Chrome** zaloguj się na nie na https://www.instagram.com/
3. Zainstaluj rozszerzenie: **„Get cookies.txt LOCALLY"** (Chrome Web Store,
   szukaj tej nazwy — wtyczka z żółtą ikoną).
4. Będąc zalogowanym na instagram.com: kliknij ikonę rozszerzenia
   → **„Export as Netscape txt file”**.
5. Zapisany plik przenieś do:
   ```bash
   mv ~/Desktop/instagram_cookies.txt ~/xkom-bot/state/ig_cookies.txt
   ```
   (nazwa pliku po eksporcie może się różnić — wklej to, co się zapisze)
6. W `config.yaml`: `instagram:` → `enabled: true`
7. Restarc bota: `./stop.sh && ./start.sh`
8. Sprawdź: `grep -i instagram state/logs/bot.log | tail` —
   powinny pojawić się linie `[instagram] N pozycji`.

**Utrzymanie:**
- Cookies wygasają zwykle po 2–4 tygodniach. Jeśli w logach pojawi się
  powtarzające się `[instagram] yt-dlp failed`, wyeksportuj je ponownie (kroki 3–7).
- Jeśli IG pokaże „checkpoint” (prośba o SMS/zmianę hasła) na tym koncie,
  rozwiąż to w przeglądarce, zanim bot ponownie spróbuje.
- Bot pyta o IG co 90 s (celowo rzadziej niż YT — IG agresywnie limituje).

## Autostart (launchd)

```bash
./install_launchd.sh    # start przy logowaniu + auto-restart po crashu/resecie
./uninstall_launchd.sh  # wracasz do ręcznego start.sh/stop.sh
```

Launchd NIE budzi Maca ze snu — w dni, w których możesz wypaść kod
(pon–pt, patrz `./status.sh` — kalendarz), ustaw:
**Ustawienia systemowe > Bateria > Opcje... > „Zapobiegaj automatycznemu
uśpieniu Maca, gdy wyświetlacz jest wyłączony”** (albo App Amphetamine).

## Źródła i 1:1 (YT vs IG)
- **YouTube + TikTok**: pełne monitorowanie BEZ logowania (yt-dlp). TikTok działa
  anonimowo i jest włączony domyślnie.
- **Instagram**: wymaga logowania (cały profil i pojedyncze reelsy są za login wall).
  Włącz w `config.yaml` + cookies z **drugiego** konta w `state/ig_cookies.txt`.
- Czy YT = IG 1:1? Nie da się tego zweryfikować anonimowo (IG blokuje), ale
  oficjalny kalendarz Black Weeks **przypisuje konkretną platformę do każdego
  kodu dnia** (np. dziś: Razer → YouTube, Norton → TikTok). Content promocyjny
  jest w dużej mierze krzyżowany (Twój reel = ten sam short na YT), ale
  kody mogą być publikowane tylko na jednej platformie — dlatego bot monitoruje
  YT + TikTok i czyta kalendarz (`xkom.status` pokaże, na której platformie
  jest dziś kod danego produktu).

## Ważne zastrzeżenia
- **Silnik zakupów nie przechowuje danych karty** — używa metod płatności
  zapisanych w Twoim koncie x-kom (z ostatniego zamówienia). Przy BLIK/3DS
  bot zaczeka, aż zatwierdzisz na telefonie.
- **Domyślne potwierdzenie**: bez `--pay` bot staje przed „Zamawiam i płacę”
  i czeka na ENTER. Pieniądze idą tylko po Twoim świadomym skinieniu.
- **Kody jednorazowe**: jak kod się spali, bot powie (screenshot + komunikat sklepu).
- **OCR nie jest idealny**: kandydaci to *kandydaci* — przed GO rzuć okiem
  na podgląd klatki w `state/shots/`. W config.yaml możesz dopisywać stopwords.
- **Nie kupujesz automatycznie** — bot nigdy nie klika „Przejdź do kasy”
  i nie podaje danych karty. Finalizacja jest Twoja, świadomie.
- **Instagram**: użyj drugiego konta (cookies), nie głównego —
  nieoficjalne scrapowanie może je obciążyć.
- Przy każdym uruchomieniu `bot` na nowo przetwarza tylko posty
  po ostatniej sesji (stan w `state/yt_seen.json`).

## Workflow „na dziś” (z Twojego posta)
1. `./start.sh` — bot zostaje w tle.
2. Bot: 📢 alarm w Telegramie + dźwięk, format:
   ```
   🔑 KOD: A2C3E4L
   🎯 Razer Huntsman V3 Pro TKL Black
   💰 449,00 zł  (oryg. 899,00 zł)  → 1 zł z kodem
   🛒 https://www.x-kom.pl/p/1215501-...
   📺 https://youtu.be/VIDEO
   ⚡ auto: python3 -m xkom.buy "URL" --code A2C3E4L
   ```
   Produkt i ceny dobierane automatycznie z kalendarza Black Weeks
   (dzisiejszy produkt pasującej platformy — ceny z JSON-LD strony produktu).
3. Ty: klikasz link 🛒 (w Twojej zalogowanej przeglądarce) → „Do koszyka” →
   wklejasz kod z wiadomości. Albo od razu: `python3 -m xkom.buy URL --code KOD`
   (bot robi wszystko do „Zamawiam i płacę”, bez `--pay` czeka na Twój ENTER).

### Dlaczego alarmy są czyste
- alarm tylko dla kandydatów **strict** (duża czcionka + powtarzalność klatek,
  albo kod przy słowie „kod” w opisie),
- opisy: tylko wzorce `kod: XXX` / `kod XXX` (URL-e wycinane),
- lista stopwords (polskie słowa bez diakrytyk: LATACH, PREMIERY...),
- dedup: ten sam kod nie alarmuje dwa razy w 6h.
