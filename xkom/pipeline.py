"""Wspólny pipeline: jeden nowy post -> kandydaci na kody.

Krok 1 (tani): opis wideo -> scan_text (kody bywają w tekstach)
Krok 2 (drogi): pobierz wideo -> OCR klatek -> scoring
Po przetworzeniu wideo i klatki są KASOWANE z dysku (zostaje tylko
podgląd kandydata do alertu) — stan nie rośnie w nieskończoność.
"""
from pathlib import Path

from .common import log
from . import sources, extract


def _cleanup(item, found):
    """Usuwa wideo i klatki po przetworzeniu; zostawia podglądy kandydatów."""
    vid = item["id"]
    keep = set()
    for c in found:
        f = c.get("frame")
        if f:
            p = Path(f)
            if p.exists():
                keep.add(p)
    vdir = extract.VIDEO_DIR
    for p in [vdir / f"{vid}.mp4", *(vdir.glob(f"{vid}.*"))]:
        try:
            p.unlink()
        except OSError:
            pass
    n = 0
    for p in extract.SHOTS_DIR.glob(f"{vid}_*.jpg"):
        if p in keep:
            continue
        try:
            p.unlink()
            n += 1
        except OSError:
            pass
    log(f"  [cleanup] usunięto wideo + {n} klatek ({vid})")


def process_item(item, cfg):
    """Zwraca listę kandydatów na kody (z kontekstem źródła)."""
    found = []
    try:
        found = _process_item(item, cfg)
        return found
    finally:
        _cleanup(item, found)


def _process_item(item, cfg):
    stopwords = set(s.upper() for s in ((cfg.get("extract") or {}).get("stopwords") or []))

    desc = sources.get_description(item["url"])
    text_hits = extract.scan_text(desc, stopwords)
    if text_hits:
        log(f"  HIT W OPISIE: {[h['code'] for h in text_hits]}")
        found = [dict(h, at_sec=None, shot="opis wideo", frame="") for h in text_hits]
    else:
        found = []
        try:
            path = extract.download_video(item, cfg)
        except Exception as e:
            log(f"pobieranie {item['id']} nie powiodło się: {e}")
            path = None
        if path:
            try:
                found = extract.extract_codes(item, path, cfg)
            except Exception as e:
                log(f"OCR {item['id']} nie powiodło się: {e}")

    for f in found:
        f.update({"source": item["source"], "title": item["title"],
                  "url": item["url"], "video_id": item["id"]})
    return found
