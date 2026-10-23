"""Monitorowanie strony Black Weeks x-kom (lp/black-weeks).

Strona zawiera sekcję „Szukaj kodów na produkty za złotówkę”:
każdy produkt ma datę („Szukaj kodu DD.MM”) i platformę, gdzie jest ukryty kod.
Bot porównuje stan strony (które produkty/ dni są nowe, które „wykorzystane”)
i powiadamia o zmianach.
"""
import re
import urllib.request

from .common import log, load_state, save_state

BW_URL = "https://www.x-kom.pl/lp/black-weeks"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def _fetch(url=BW_URL):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def parse_products(html):
    """Zwraca listę produktów z sekcji kodów: {name, url, date, platform, used}."""
    # strona ma HTML częściowo uciekany w JSON — odwróć
    html = html.replace("\\u003c", "<").replace("\\u003e", ">")
    html = html.replace("\\n", "\n").replace("\\u0026", "&")
    items = []
    # blok produktu: od <div class="product-box ..."> do następnego takiego
    for m in re.finditer(r'<div class="product-box[^"]*"[^>]*>(.*?)(?=<div class="product-box|</section>)',
                         html, flags=re.S):
        block = m.group(1)
        name = ""
        nm = re.search(r'aria-label="Zobacz produkt ([^"]+)"', block)
        if nm:
            name = nm.group(1)
        else:
            h4 = re.search(r"<h4[^>]*>(.*?)</h4>", block, flags=re.S)
            if h4:
                name = re.sub(r"<[^>]+>", "", h4.group(1)).strip()
        url = ""
        um = re.search(r'href="(https://www\.x-kom\.pl/p/\d+-[^"]+)"', block)
        if um:
            url = um.group(1)
        date = ""
        dm = re.search(r"Szukaj kodu\s*(\d{2}\.\d{2})", block)
        if dm:
            date = dm.group(1)
        platform = ""
        for p, link in (("TikTok", r"tiktok\.com/(\S+)"),
                        ("YouTube", r"youtube\.com/(\S+)"),
                        ("Instagram", r"instagram\.com/(\S+)"),
                        ("Facebook", r"facebook\.com/(\S+)"),
                        ("Threads", r"threads\.net/(\S+)"),
                        ("X", r"twitter\.com/(\S+)")):
            pm = re.search(link, block)
            if pm:
                platform = f"{p} ({pm.group(1).rstrip('\"')})"
                break
        used = "Kod wykorzystany" in block or 'data-found="true"' in m.group(0)
        if name or url:
            items.append({"name": name.strip(), "url": url,
                          "date": date, "platform": platform, "used": used})
    return items


def poll_blackweeks():
    """Zwraca dict {changed, items, changes:[]} — zmiany względem poprzedniego stanu."""
    try:
        html = _fetch()
    except Exception as e:
        log(f"[blackweeks] błąd pobierania: {e}")
        return None
    items = parse_products(html)
    if not items:
        return None
    prev = load_state("bw_state", {})
    changes = []
    new_state = {}
    for it in items:
        key = it["url"] or it["name"]
        new_state[key] = {"date": it["date"], "used": it["used"],
                          "platform": it["platform"], "name": it["name"]}
        old = prev.get(key)
        if old is None:
            changes.append(f"NOWY produkt w akcji: {it['name']} ({it['date']}, {it['platform']})")
        elif old.get("used") != it["used"] and it["used"]:
            changes.append(f"KOD WYKORZYSTANY: {it['name']} ({it['date']})")
        elif old.get("date") != it["date"] or old.get("platform") != it["platform"]:
            changes.append(f"ZMIANA: {it['name']} -> {it['date']} / {it['platform']}")
    save_state("bw_state", new_state)
    log(f"[blackweeks] produktów: {len(items)}, zmian: {len(changes)}")
    return {"changed": bool(changes), "items": items, "changes": changes}
