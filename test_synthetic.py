"""Test syntezy: generuje fałszywe wideo "promo" z dużym kodem na środku
i polskimi napisami, potem odpiera pipeline extract_codes.
Kod do znalezienia: A2C3E4L (6-8 znaków, litery+cyfry, duży, ~5s na ekranie).
Drugi kod cyfrowy: 7391205 (pojawia się z napisem "Twój kod:").
"""
import os
import subprocess
import textwrap
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="xkom_test_"))
FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Geneva.ttf",
]

CODE1 = "A2C3E4L"
CODE2 = "7391205"

frames_dir = TMP / "frames"
frames_dir.mkdir()


def font_path():
    for f in FONT_CANDIDATES:
        if Path(f).exists():
            return f
    return None


def make_frame(idx, path):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (1080, 1920), "white")
    d = ImageDraw.Draw(img)
    f = font_path()
    big = ImageFont.truetype(f, 140) if f else ImageFont.load_default()
    med = ImageFont.truetype(f, 60) if f else ImageFont.load_default()
    small = ImageFont.truetype(f, 28) if f else ImageFont.load_default()

    # body-text (mały) przez całe wideo
    d.text((60, 200), "Znajdz kody i zgarnij produkty", font=med, fill="black")
    d.text((60, 280), "za 1 zl w x-kom!", font=small, fill="black")
    d.text((60, 340), "Subskrybuj kanal aby nic nie przegapic", font=small, fill="black")
    d.text((60, 1750), "xkom.pl - promocja - akcja - kody rabatowe - codziennie", font=small, fill="gray")
    d.text((60, 1800), "laptopy sluchawki ram smartwatche - puli 50 produktow", font=small, fill="gray")

    if 20 <= idx < 70:          # kod 1: duzy, 5 s na ekranie
        d.text((190, 800), CODE1, font=big, fill="black")
    elif 70 <= idx < 120:       # kod 2: cyfrowy + kontekst 'kod'
        d.text((120, 750), "Twoj kod:", font=med, fill="black")
        d.text((180, 900), CODE2, font=big, fill="black")

    img.save(path)


N = 150
for i in range(N):
    make_frame(i, frames_dir / f"f_{i:03d}.jpg")

out = TMP / "testpromo.mp4"
subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-framerate", "10", "-i", str(frames_dir / "f_%03d.jpg"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)], check=True)

from xkom import extract
from xkom.common import load_config

cfg = load_config()
item = {"id": "SYNTH", "title": "syntetyczny test", "url": "synth"}
p = extract.download_video.__wrapped__(item, cfg) if hasattr(extract.download_video, "__wrapped__") else None
# download_video pobiera z URL-a — dla testu kopiujemy plik
import shutil
target = extract.VIDEO_DIR / "SYNTH.mp4"
if target.exists():
    target.unlink()
shutil.copy(out, target)

found = extract.extract_codes(item, target, cfg)
print("=== WYNIK ===")
print(f"kandydatów: {len(found)}")
for c in found:
    print(f"  {c['code']} [{c['level']}] prom={c['prominent']} rep={c['repeats']} kodctx={c['kod_context']} @ t={c['at_sec']}s")

ok1 = any(c["code"] == CODE1 and c["level"] == "strict" for c in found)
ok2 = any(c["code"] == CODE2 and c["level"] == "strict" for c in found)
print(f"KOD1 ({CODE1}) strict: {'TAK' if ok1 else 'NIE'}")
print(f"KOD2 ({CODE2}) strict: {'TAK' if ok2 else 'NIE'}")
print("PASS" if (ok1 and ok2) else "FAIL")
