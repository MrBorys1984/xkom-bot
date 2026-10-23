"""Wspólny pipeline: jeden nowy post -> kandydaci na kody.

Krok 1 (tani): opis wideo -> scan_text (kody bywają w tekstach)
Krok 2 (drogi): pobierz wideo -> OCR klatek -> scoring
"""
from .common import log
from . import sources, extract


def process_item(item, cfg):
    """Zwraca listę kandydatów na kody (z kontekstem źródła)."""
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
