"""
Jednorazowy cykl monitorowania — GitHub Actions (chmura 24/7).

Użycie:  python -m xkom.cloud_cycle
Env:
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID  — nadpisują config (sekrety repo)
  XKOM_STATE_DIR                        — katalog stanu (domyślnie ./state)

Przy pierwszym uruchomieniu (brak stanu) wszystkie obecne posty są tylko
oznaczane jako widziane — bez pobierania wideo i OCR (nie skanujemy archiwum).
"""
import datetime
import os
import time

from .common import STATE, log, load_config, load_state, save_state
from . import sources, blackweeks, alert, notify, pipeline

# pliki stanu, które muszą istnieć po cyklu (artifact upload)
STATE_FILES = ["yt_seen", "tt_seen", "tt_seen_cadence", "ig_seen",
               "bw_state", "alerted_codes", "candidates", "prices"]


def _is_old(item, max_age_days=2):
    d = str(item.get("published") or "")
    if not d or len(d) < 8:
        return False
    try:
        pub = datetime.date(int(d[:4]), int(d[4:6]), int(d[6:8]))
        return (datetime.date.today() - pub).days > max_age_days
    except ValueError:
        return False


def main():
    cfg = load_config()

    # sekrety z GitHub Actions nadpisują config
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    tg = cfg.setdefault("telegram", {})
    if tok:
        tg["token"] = tok
    if chat:
        tg["chat_id"] = chat

    # Instagram: włączamy, jeśli workflow dostarczył plik cookies
    ig = cfg.setdefault("instagram", {})
    ig["enabled"] = (STATE / "ig_cookies.txt").exists()

    first_run = not load_state("yt_seen", {})
    log(f"=== xkom-cloud start ({'PIERWSZY' if first_run else 'kolejny'} przebieg) ===")

    # 1) kalendarz Black Weeks
    try:
        bw = blackweeks.poll_blackweeks()
        if bw and bw["changed"]:
            for ch in bw["changes"]:
                log(ch)
                notify.notify(cfg, "xkom-bot: Black Weeks", ch)
    except Exception as e:
        log(f"[blackweeks] wyjątek: {e}")

    # 2) nowe posty
    new_items = sources.poll_all(cfg)
    log(f"nowych postów: {len(new_items)}")
    for item in new_items:
        if first_run and item.get("source", "").startswith("youtube") and _is_old(item):
            log(f"[pierwszy przebieg] pomijam stary film: {item['id']}")
            continue

        log(f"NOWY POST: [{item['source']}] {item['title'][:80]}")
        found = pipeline.process_item(item, cfg)
        if found:
            candidates = load_state("candidates", [])
            for c in found:
                c["found_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                candidates.append(c)
            save_state("candidates", candidates[-100:])  # ograniczamy rozmiar
            for c in found:
                if alert.send_if_new(c):
                    break
        else:
            log(f"bez kandydatów w: {item['id']}")

    # 3) upewnij się, że wszystkie pliki stanu istnieją (dla artifactu)
    for name in STATE_FILES:
        save_state(name, load_state(name, {}))

    log("=== xkom-cloud koniec przebiegu ===")


if __name__ == "__main__":
    main()
