"""
Główna pętla bota (wersja LOKALNA, na Twoim Macu):
  monitoruje źródła -> pobiera nowe wideo -> OCR -> kandydaci na kody -> powiadomienie

Wersja chmurowa (24/7, GitHub Actions): xkom/cloud_cycle.py
Ta pętla ma sens, gdy chcesz niższą latencję (polling co 20 s vs co 5 min w chmurze)
i Twój Mac jest włączony. Uwaga: jeśli działają OBA, alerty mogą się dublować
(różne stany) — chmura jest źródłem głównym, lokalny bot to opcjonalny boost.

Uruchomienie:  ./start.sh  (albo: python3 -m xkom.bot)
Zatrzymanie:   ./stop.sh
Sygnał GO:     python3 -m xkom.go KOD [--product URL]
Pełny zakup:   python3 -m xkom.buy URL --code KOD
Status:        ./status.sh
"""
import datetime
import time

from .common import log, load_config, load_state, save_state
from . import sources, notify, blackweeks, alert, pipeline


def _is_old(item, max_age_days=2):
    d = str(item.get("published") or "")
    if not d or len(d) < 8:
        return False
    try:
        pub = datetime.date(int(d[:4]), int(d[4:6]), int(d[6:8]))
        return (datetime.date.today() - pub).days > max_age_days
    except ValueError:
        return False


def run():
    cfg = load_config()
    log("=== xkom-bot start (lokalny) ===")

    first_run = not (load_state("yt_seen", {}) or load_state("ig_seen", {}))

    while True:
        # kalendarz Black Weeks
        try:
            bw = blackweeks.poll_blackweeks()
            if bw and bw["changed"]:
                for ch in bw["changes"]:
                    log(ch)
                    notify.notify(cfg, "xkom-bot: Black Weeks", ch)
        except Exception as e:
            log(f"[blackweeks] wyjątek: {e}")

        for item in sources.poll_all(cfg):
            if first_run and item.get("source", "").startswith("youtube"):
                if _is_old(item):
                    log(f"[pierwszy start] pomijam stary film: {item['id']}")
                    continue

            log(f"NOWY POST: [{item['source']}] {item['title'][:80]}")
            found = pipeline.process_item(item, cfg)
            if found:
                candidates = load_state("candidates", [])
                for c in found:
                    c["found_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    candidates.append(c)
                save_state("candidates", candidates[-100:])
                for c in found:
                    if alert.send_if_new(c):
                        break
            else:
                log(f"bez kandydatów w: {item['id']}")

        interval = (cfg.get("youtube") or {}).get("poll_seconds", 20)
        time.sleep(max(10, interval))


if __name__ == "__main__":
    run()
