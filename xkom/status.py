"""Pokaż kandydatów na kody, stan monitoringu i dzisiejsze produkty z Black Weeks."""
import datetime

from .common import load_state


def main():
    cands = load_state("candidates", [])
    if cands:
        print(f"Kandydaci na kody ({len(cands)}):\n")
        for c in cands[-15:][::-1]:
            print(f"  {c['code']}   ({c.get('found_at')}) [{c.get('level', '?')}]")
            print(f"    źródło: {c.get('source')} | {c.get('title', '')[:70]}")
            print(f"    klatka: {c.get('shot')}")
            print()
    else:
        print("Brak kandydatów na kody (bot jeszcze nic nie wyłapał).\n")

    # dzisiejsze produkty z kalendarza Black Weeks
    bw = load_state("bw_state", {})
    if bw:
        today = datetime.date.today().strftime("%d.%m")
        todays = [(k, v) for k, v in bw.items()
                  if isinstance(v, dict) and v.get("date") == today]
        if todays:
            print(f"Black Weeks — DZIŚ ({today}) kody na:")
            for url, v in todays:
                status = "WYKORZYSTANY" if v.get("used") else "aktywny"
                print(f"  • {v.get('name', url)[:60]}  [{status}] {v.get('platform', '')}")
                print(f"    {url}")
            print()
        else:
            print(f"Black Weeks: dziś ({today}) brak produktów w kalendarzu "
                  f"(niedziela? akcja pon–pt).")
            print()

    yt = load_state("yt_seen", {})
    tt = load_state("tt_seen", {})
    ig = load_state("ig_seen", {})
    print(f"Zmonitorowane pozycje: YouTube {len(yt)} | TikTok {len(tt)} | Instagram {len(ig)}")


if __name__ == "__main__":
    main()
