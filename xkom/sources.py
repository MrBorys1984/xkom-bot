"""Źródła: YouTube (yt-dlp, oficjalny i bezpieczny) + Instagram (opcjonalnie, cookies)."""
import re
import subprocess
import time
from pathlib import Path

from .common import ROOT, STATE, log, load_state, save_state


def _run(cmd, timeout=180):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _yt_cookies():
    """Ścieżka do cookies YouTube (state/yt_cookies.txt), jeśli istnieje.

    W chmurze (GitHub Actions, IP datacenter) YouTube wymaga logowania —
    cookies z DRUGIEGO konta Google rozwiązują 'Sign in to confirm you're
    not a bot'. Lokalnie (IP domowe) zwykle nie są potrzebne.
    """
    from .common import STATE
    p = STATE / "yt_cookies.txt"
    return p if p.exists() else None


# ---------------- YouTube ----------------

import urllib.request

RSS_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
CHANNEL_ID = "UCmsxFRm1zRgueucG2Pc9Kzg"  # @xkompl


def _yt_rss(limit=15):
    """
    Oficjalny feed RSS kanału — 1 HTTP call, najnowsze 15 wideo
    (Shorty i długie filmy razem) z dokładnymi datami publikacji.
    Zwraca listę {id, title, published, url}.
    """
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
    req = urllib.request.Request(url, headers={"User-Agent": RSS_UA})
    import re as _re
    with urllib.request.urlopen(req, timeout=20) as r:
        xml = r.read().decode("utf-8", errors="replace")
    items = []
    for m in _re.finditer(
            r"<entry>.*?<yt:videoId>([^<]+)</yt:videoId>.*?"
            r"<title>(.*?)</title>.*?<published>([^<]+)</published>",
            xml, flags=_re.S):
        vid, title, pub = m.group(1), m.group(2), m.group(3)
        # publish_date w formacie YYYYMMDD dla porównań
        d = _re.sub(r"[^\d]", "", pub)[:8]
        items.append({
            "id": vid,
            "title": title,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "published": d,
            "published_iso": pub,
        })
    return items[:limit]


def _yt_cookies_args():
    p = _yt_cookies()
    return ["--cookies", str(p)] if p else []


def _yt_clients():
    """Łańcuch klientów odtwarzacza YouTube — fallback na IP datacenter.

    Z serwerów (GitHub Actions) domyślny klient często dostaje 'Sign in to
    confirm you're not a bot', nawet z cookies nowego konta. Klienci
    'tv' (Smart TV) i 'web_embedded' zazwyczaj przechodzą bez problemu.
    """
    return [
        [],
        ["--extractor-args", "youtube:player_client=tv"],
        ["--extractor-args", "youtube:player_client=web_embedded"],
    ]


def _yt_videos(url, tab, limit=40):
    """Fallback: lista z taba kanału przez yt-dlp (flat)."""
    cmd = [
        "yt-dlp", "--flat-playlist", "-J", "--no-warnings",
        f"--playlist-items=1-{limit}",
        *_yt_cookies_args(),
        f"{url}/shorts" if tab == "shorts" else f"{url}/videos",
    ]
    r = None
    for attempt in range(3):
        r = _run(cmd, timeout=120)
        if r.returncode == 0:
            break
        log(f"[youtube/{tab}] próba {attempt + 1} nieudana: {r.stderr[:200]}")
        time.sleep(10)
    if r is None or r.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {r.stderr[:300] if r else 'brak odpowiedzi'}")
    data = json_loads(r.stdout)
    entries = data.get("entries") or []
    out = []
    for e in entries:
        vid = e.get("id")
        if not vid:
            continue
        out.append({
            "id": vid,
            "title": e.get("title") or "",
            "url": f"https://www.youtube.com/watch?v={vid}",
            "published": e.get("upload_date") or e.get("timestamp") or 0,
        })
    return out


def json_loads(s):
    import json
    return json.loads(s)





def poll_youtube(cfg, state_name="yt_seen"):
    """
    Zwraca nowe filmy/shorty od ostatniego uruchomienia.
    Źródło główne: oficjalny RSS kanału (szybki, z datami).
    Fallback: yt-dlp flat na /videos i /shorts.
    """
    y = cfg.get("youtube") or {}
    if not y.get("enabled"):
        return []
    seen = load_state(state_name, {})
    new_items = []
    now = time.time()

    items = None
    try:
        items = _yt_rss(limit=15)
    except Exception as e:
        log(f"[youtube] RSS niedostępny: {e}")
    if items:
        for it in items:
            key = f"youtube:{it['id']}"
            if key in seen:
                continue
            seen[key] = now
            it["source"] = "youtube"
            new_items.append(it)
        log(f"[youtube/RSS] {len(items)} pozycji, nowych: {len(new_items)}")
    else:
        for tab in y.get("tabs", ["videos", "shorts"]):
            try:
                tab_items = _yt_videos(y["channel"], tab)
            except Exception as e:
                log(f"[youtube/{tab}] błąd: {e}")
                continue
            for it in tab_items:
                key = f"youtube/{tab}:{it['id']}"
                if key in seen:
                    continue
                seen[key] = now
                it["source"] = f"youtube/{tab}"
                new_items.append(it)
            log(f"[youtube/{tab}/yt-dlp] {len(tab_items)} pozycji")
    save_state(state_name, seen)
    return new_items


def is_promo_video(title, desc=""):
    """Szybki filtr: czy tytuł/opis sugerują akcję z kodami."""
    t = (title or "").lower() + " " + (desc or "").lower()
    keywords = ["kod", "1 zł", "za 1", "ukryt", "rabat", "okazj", "promocj", "sprzęt za 1"]
    return any(k in t for k in keywords)


# ---------------- Instagram (opcjonalne) ----------------

def _ig_cookies_file(cfg):
    y = cfg.get("instagram") or {}
    f = y.get("cookies_file")
    p = ROOT / f if f else None
    return p if p and p.exists() else None


def poll_instagram(cfg, state_name="ig_seen"):
    """
    Pobiera najnowsze posty profilu przez yt-dlp (potrzebne cookies do IG).
    Wymaga: brew install yt-dlp + plik cookies Netscape w state/ig_cookies.txt
    """
    y = cfg.get("instagram") or {}
    if not y.get("enabled"):
        return []
    ck = _ig_cookies_file(cfg)
    if not ck:
        log("[instagram] pominięte: brak cookies (włącz w config.yaml i dodaj state/ig_cookies.txt)")
        return []
    url = f"https://www.instagram.com/{y.get('handle', 'xkompl')}/"
    cmd = ["yt-dlp", "--flat-playlist", "-J", "--no-warnings",
           "--playlist-items=1-30", "--cookies", str(ck), url]
    try:
        r = _run(cmd, timeout=120)
        if r.returncode != 0:
            log(f"[instagram] yt-dlp failed: {r.stderr[:300]}")
            return []
        data = json_loads(r.stdout)
    except Exception as e:
        log(f"[instagram] błąd: {e}")
        return []

    seen = load_state(state_name, {})
    new_items = []
    for e in data.get("entries") or []:
        pid = e.get("id")
        if not pid or f"ig:{pid}" in seen:
            continue
        seen[f"ig:{pid}"] = time.time()
        title = e.get("title") or ""
        new_items.append({
            "id": pid,
            "title": title[:200],
            "url": f"https://www.instagram.com/reel/{pid}/",
            "published": e.get("timestamp") or 0,
            "source": "instagram",
        })
    save_state(state_name, seen)
    return new_items


# ---------------- TikTok ----------------

def poll_tiktok(cfg, state_name="tt_seen", min_interval_sec=180):
    """TikTok działa w yt-dlp BEZ logowania — pełne źródło.

    TikTok agresywnie rate-limituje (redirect na /404), więc pytamy
    nie częściej niż co min_interval_sec (domyślnie 3 minuty).
    """
    y = cfg.get("tiktok") or {}
    if not y.get("enabled"):
        return []
    cadence = load_state(f"{state_name}_cadence", {})
    last = cadence.get("last", 0)
    if time.time() - last < min_interval_sec:
        return []
    cadence["last"] = time.time()
    save_state(f"{state_name}_cadence", cadence)
    url = f"https://www.tiktok.com/{y.get('handle', 'xkompl')}"
    cmd = ["yt-dlp", "--flat-playlist", "-J", "--no-warnings",
           "--playlist-items=1-30", url]
    data = None
    for attempt in range(3):  # TikTok czasem rzuca przejściowy redirect na /404
        try:
            r = _run(cmd, timeout=120)
            if r.returncode == 0:
                data = json_loads(r.stdout)
                break
            log(f"[tiktok] próba {attempt + 1} nieudana: {r.stderr[:200]}")
        except Exception as e:
            log(f"[tiktok] próba {attempt + 1} wyjątek: {e}")
        time.sleep(15)
    if data is None:
        return []

    seen = load_state(state_name, {})
    new_items = []
    for e in data.get("entries") or []:
        pid = e.get("id")
        if not pid or f"tt:{pid}" in seen:
            continue
        seen[f"tt:{pid}"] = time.time()
        new_items.append({
            "id": pid,
            "title": (e.get("title") or "")[:200],
            "url": f"https://www.tiktok.com/@{y.get('handle', 'xkompl')}/video/{pid}",
            "published": e.get("timestamp") or 0,
            "source": "tiktok",
        })
    save_state(state_name, seen)
    return new_items


def get_description(url):
    """Szybki opis wideo (kody bywają w opisie!). Zwraca tekst.

    Próbuje kolejno klientów z _yt_clients() (datacenter IP).
    """
    base = ["yt-dlp", "-J", "--no-warnings", "--no-playlist", *_yt_cookies_args()]
    for extra in _yt_clients():
        try:
            r = _run(base + extra + [url], timeout=90)
        except Exception:
            continue
        if r.returncode == 0:
            data = json_loads(r.stdout)
            desc = data.get("description") or ""
            if desc:
                return desc
    return ""


def poll_all(cfg):
    items = []
    items += poll_youtube(cfg)
    items += poll_tiktok(cfg)
    items += poll_instagram(cfg)
    return items
