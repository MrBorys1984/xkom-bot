"""Ręczny test pipeline: pobranie -> OCR -> kandydaci (uruchom: python3 test_pipeline.py)"""
import time

from xkom import extract
from xkom.common import load_config

cfg = load_config()
item = {"id": "NFGHQDi9Cdk", "title": "test promo short",
        "url": "https://www.youtube.com/watch?v=NFGHQDi9Cdk"}
p = extract.download_video(item, cfg)
print("Pobrano:", p, p.stat().st_size, "bajtów", flush=True)
t0 = time.time()
found = extract.extract_codes(item, p, cfg)
print("KANDYDACI:", found, flush=True)
print("CZAS:", round(time.time() - t0), "s", flush=True)
