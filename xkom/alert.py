"""
Powiadomienia o kodach — format zgodny z UX:
  1) nazwa sprzętu
  2) oryginalna cena
  3) cena po promocji (z kodem -> 1 zł)
  4) kod
  5) link do zakupu
  + link do wideo (źródło) + komenda auto-zakupu

Produkt dobierany z kalendarza Black Weeks (dzisiejszy, niezużyty,
pasująca platforma źródła kodu).
"""
import datetime
import json
import re
import time
import urllib.request

from .common import log, load_state, save_state

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
PRICE_TTL = 600  # cache cen 10 min


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


def get_product(url):
    """Zwraca {name, price, list_price} ze strony produktu (JSON-LD), z cache."""
    cache = load_state("prices", {})
    now = time.time()
    hit = cache.get(url)
    if hit and now - hit.get("t", 0) < PRICE_TTL:
        return hit.get("data")
    data = {"name": None, "price": None, "list_price": None}
    try:
        html = _fetch(url)
        for m in re.finditer(
                r'<script type="application/ld\+json">(.*?)</script>', html, flags=re.S):
            try:
                d = json.loads(m.group(1))
            except Exception:
                continue
            if isinstance(d, dict) and d.get("@type") == "Product":
                data["name"] = d.get("name")
                offers = d.get("offers") or {}
                if isinstance(offers, dict):
                    data["price"] = offers.get("price")
                    for ps in offers.get("priceSpecification") or []:
                        if "ListPrice" in str(ps.get("priceType", "")):
                            data["list_price"] = ps.get("price")
                break
    except Exception as e:
        log(f"[alert] błąd pobierania produktu {url}: {e}")
        if hit:
            return hit.get("data")
    cache[url] = {"t": now, "data": data}
    save_state("prices", cache)
    return data


def fmt_price(v):
    if v is None:
        return None
    try:
        v = float(v)
        s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", " ")
        return f"{s.rstrip()} zł"
    except Exception:
        return f"{v} zł"


def today_products(active_only=False):
    """Dzisiejsze produkty z kalendarza Black Weeks (z nazwą i URL-em)."""
    bw = load_state("bw_state", {})
    today = datetime.date.today().strftime("%d.%m")
    out = []
    for key, v in bw.items():
        if not isinstance(v, dict) or v.get("date") != today:
            continue
        if active_only and v.get("used"):
            continue
        out.append(v)
    return out


PLATFORM_MAP = {
    "youtube": "YouTube",
    "youtube/videos": "YouTube",
    "youtube/shorts": "YouTube",
    "tiktok": "TikTok",
    "instagram": "Instagram",
    "facebook": "Facebook",
}


def build_alert(cand):
    """Zwraca (tytuł, treść) powiadomienia dla kandydata na kod."""
    code = cand["code"]
    src = cand.get("source", "")
    plat = PLATFORM_MAP.get(src)

    acts = today_products(active_only=True)
    # dopasowanie po platformie źródła (kalendarz przypisuje platformę do produktu)
    matched = [a for a in acts if plat and str(a.get("platform", "")).startswith(plat)]
    pool = matched if matched else acts

    lines = []
    product_names = []
    for a in pool[:2]:
        prod = get_product(a.get("url") or "") or {}
        name = a.get("name") or prod.get("name") or "?"
        product_names.append(name)
        price = fmt_price(prod.get("price"))
        list_price = fmt_price(prod.get("list_price"))
        lines.append(f"🎯 {name}")
        price_line = f"💰 {price or '?'}"
        if list_price and (prod.get("list_price") != prod.get("price")):
            price_line += f"  (oryg. {list_price})"
        price_line += "  → 1 zł z kodem"
        lines.append(price_line)
        lines.append(f"🛒 {a.get('url')}")
        if a.get("used"):
            lines.append("⚠️ na kalendarzu już jako wykorzystany — spróbuj szybko!")
        lines.append("")

    lines.insert(0, f"🔑 KOD: {code}")
    if cand.get("shot") and cand["shot"] != "opis wideo":
        lines.insert(1, f"🎬 {cand['shot']}")
    if not pool:
        lines.append("🎯 produkt: patrz wideo (dzisiaj brak aktywnych pozycji w kalendarzu)")
        lines.append("")
    if cand.get("url"):
        lines.append(f"📺 {cand['url']}")
    # komenda auto-zakupu — tylko dla pierwszego produktu
    first_url = (pool[0].get("url") if pool else None)
    if first_url:
        lines.append(f"⚡ auto: python3 -m xkom.buy \"{first_url}\" --code {code}")

    title = f"xkom-bot: KOD {code}"
    if product_names:
        title += f" — {product_names[0][:60]}"
    return title, "\n".join(lines)


def send_if_new(cand):
    """Wysyła alert tylko dla nowych, pewnych (strict) kandydatów."""
    from .common import load_config
    from . import notify
    if cand.get("level") != "strict":
        log(f"[alert] pomijam kandydata loose: {cand.get('code')}")
        return False
    sent = load_state("alerted_codes", {})
    key = cand["code"]
    if key in sent and time.time() - sent[key] < 6 * 3600:
        log(f"[alert] kod {key} już alarmowany 6h temu, pomijam")
        return False
    try:
        title, msg = build_alert(cand)
    except Exception as e:
        log(f"[alert] błąd budowania alertu: {e}")
        title, msg = "xkom-bot: ZNALEZIONO KOD", f"KOD: {cand['code']}\n{cand.get('url','')}"
    sent[key] = time.time()
    save_state("alerted_codes", sent)
    log(f"[alert] WYSYŁAM: {title}")
    notify.notify(load_config(), title, msg)
    return True
