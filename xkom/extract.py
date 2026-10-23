"""Pobiera wideo, wyłapuje klatki z kodem (OCR) i zapisuje kandydaty.

Optymalizacje:
- deduplikacja klatek (hash) — statyczne ujęcia nie idą 2x do OCR
- OCR tylko unikalnych klatek, reszta dziedziczy wynik sąsiada
"""
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from .common import LOGS, ROOT, STATE, log, load_state, save_state

VIDEO_DIR = STATE / "videos"
SHOTS_DIR = STATE / "shots"
VIDEO_DIR.mkdir(parents=True, exist_ok=True)
SHOTS_DIR.mkdir(parents=True, exist_ok=True)

# Oficjalny format kodów akcji x-kom (strona Black Weeks):
# 6-8 znaków, wielkie litery i cyfry, np. ABCDEF, 12345678, A2C3E4L.
# Każda litera/cyfra może być wyświetlana osobno lub cały ciąg.
STRICT = re.compile(r"^[A-Z0-9]{6,8}$")
# luźniejszy wariant na błędy OCR (5-9 znaków) — kandydat "loose"
LOOSE = re.compile(r"^[A-Z0-9]{5,9}$")


def looks_like_code(token, stopwords, hint=False):
    """
    Zwraca 'strict', 'loose' albo None.
    hint=True gdy w klatce jest słowo 'kod' — pozwala na same cyfry
    (bez hintu same cyfry to częściej cena).
    """
    t = token.strip().upper()
    # kod to czysty ASCII — token z polskimi znakami nie może być kodem
    if not t.isascii():
        return None
    if t in stopwords:
        return None
    if STRICT.match(t):
        if t.isdigit() and not hint:
            return None          # 6-8 cyfr bez kontekstu = prawdopodobna cena
        return "strict"
    if LOOSE.match(t) and not t.isdigit():
        return "loose"
    return None


def scan_text(text, stopwords):
    """Skanuje TEKST (opis, komentarz) pod kątem kodów — szybszy niż OCR.

    Celowane wzorce: kod pisany tuż obok słowa 'kod/kodu/kody',
    zwykle 'kod: XXXX', 'kod XXXX', 'kod rabatowy XXXX'.
    URL-e są wycinane (nie chcemy HTTPS/TWITTER/XGRUPA).
    Zwraca listę kandydatów {code, level}.
    """
    out = []
    if not text:
        return out
    # wycinamy URL-e i linki skrócone
    clean = re.sub(r"https?://\S+", " ", text)
    clean = re.sub(r"\b(?:www|xkom)\.\w+\S*", " ", clean)
    seen = set()

    def add(tok):
        tok = tok.strip().upper()
        lvl = looks_like_code(tok, stopwords, hint=True)
        if lvl and lvl == "strict" and tok not in seen:
            seen.add(tok)
            out.append({"code": tok, "level": lvl})

    # wzorzec 1: 'kod' + separator + token 6-8 (najczęstszy format)
    for m in re.finditer(
            r"\bkod(?:u|y|em|zie)?\b\s*(?:rabatow(?:y|e|a)|promocyj(?:y|ne|a))?"
            r"\s*[:\-–=]?\s*([A-Za-z0-9]{6,8})\b",
            clean, flags=re.I):
        add(m.group(1))
    # wzorzec 2: 'kod' + token 6-8 w odległości do 3 znaków (np. "kodX")
    for m in re.finditer(r"\bkod\w{0,3}\s?([A-Z][A-Z0-9]{5,7})\b", clean):
        add(m.group(1))
    return out


def download_video(item, cfg):
    """Pobiera wideo (max 720p) przez yt-dlp. Zwraca ścieżkę.

    Próbuje kolejno klientów z _yt_clients() — domyślny bywa blokowany
    na IP datacenter ('Sign in to confirm you're not a bot'), a 'tv'
    lub 'web_embedded' przechodzą.
    """
    from .sources import _yt_cookies_args, _yt_clients
    vid = item["id"]
    out = VIDEO_DIR / f"{vid}.mp4"
    if out.exists():
        return out
    maxh = (cfg.get("download") or {}).get("max_height", 720)
    base = ["yt-dlp", "-f", f"bv*[height<={maxh}]+ba/b[height<={maxh}]/b",
            "--merge-output-format", "mp4", "-o", str(out), "--no-warnings",
            *_yt_cookies_args()]
    last_err = ""
    for extra in _yt_clients():
        t0 = time.time()
        r = subprocess.run(base + extra + [item["url"]],
                           capture_output=True, text=True, timeout=600)
        if r.returncode == 0 and out.exists():
            tag = extra[-1] if extra else "default"
            log(f"pobrane: {vid} w {time.time()-t0:.0f}s (klient: {tag})")
            return out
        last_err = r.stderr[-300:]
        log(f"[download] klient {extra[-1] if extra else 'default'} nie zadziałał: {last_err[:120]}")
        for p in [out, *(VIDEO_DIR.glob(f"{vid}.*"))]:
            try:
                p.unlink()
            except OSError:
                pass
    raise RuntimeError(f"download failed (wszyscy klienci): {last_err}")


def probe_duration(video_path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "default=nk=1:nw=1", str(video_path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def ocr_image(path, lang="pol"):
    """OCR pliku przez tesseract. Zwraca listę (token, height_px, conf).

    TSV daje per-word confidence i wysokość — kluczowe do scoringu:
    kod jest wyświetlany DUŻO większą czcionką niż body-text.
    """
    r = subprocess.run(["tesseract", str(path), "stdout", "-l", lang,
                        "--psm", "11", "tsv"],
                       capture_output=True, text=True, timeout=90)
    if r.returncode != 0:
        return []
    out = []
    all_words = []
    for ln in r.stdout.splitlines()[1:]:
        parts = ln.split("\t")
        if len(parts) < 12:
            continue
        text = parts[11].strip()
        if not text:
            continue
        try:
            conf = float(parts[10])
        except ValueError:
            conf = 0.0
        try:
            height = int(parts[9])
        except ValueError:
            height = 0
        all_words.append(text.lower())
    ctx_frame = " ".join(all_words)
    for ln in r.stdout.splitlines()[1:]:
        parts = ln.split("\t")
        if len(parts) < 12:
            continue
        text = parts[11].strip()
        if not text:
            continue
        try:
            conf = float(parts[10])
        except ValueError:
            conf = 0.0
        try:
            height = int(parts[9])
        except ValueError:
            height = 0
        out.append((text, height, conf, "kod" in ctx_frame))
    return out


def extract_codes(item, video_path, cfg):
    """
    Przeszukuje klatki wideo pod kątem kodów.
    Zwraca listę {code, at_sec, shot} — pierwsze wystąpienie wygrywa.
    """
    ex = cfg.get("extract") or {}
    stopwords = set(s.upper() for s in (ex.get("stopwords") or []))
    lang = ex.get("ocr_lang", "pol")
    dur = probe_duration(video_path)
    fps = ex.get("fps_short", 10) if dur <= ex.get("long_threshold_sec", 120) else ex.get("fps_long", 2)
    log(f"OCR {item['id']}: {dur:.0f}s @ {fps} fps")

    t0 = time.time()
    max_frames = ex.get("max_frames", 300)
    frames = []
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error",
                        "-i", str(video_path), "-vf", f"fps={fps}",
                        "-frames:v", str(max_frames), "-q:v", "2",
                        str(SHOTS_DIR / f"{item['id']}_%03d.jpg")],
                       capture_output=True, text=True, timeout=600)
    if r.returncode == 0:
        frames = sorted(SHOTS_DIR.glob(f"{item['id']}_*.jpg"))

    # deduplikacja: klatki z identycznym obrazem nie idą ponownie do OCR
    unique = []
    seen_hashes = set()
    hashes = []
    for i, f in enumerate(frames):
        h = hash_file(f)
        if h is None:          # błąd odczytu — traktuj jako unikalną
            h = f"__unhashable_{i}"
        hashes.append(h)
        if h not in seen_hashes:
            seen_hashes.add(h)
            unique.append((h, f))
    log(f"  klatek: {len(frames)}, unikalnych: {len(unique)}")

    # OCR unikalnych klatek (wątki; tesseract to osobny proces)
    def _work(hf):
        h, f = hf
        return h, ocr_image(str(f), lang)
    with ThreadPoolExecutor(max_workers=4) as ex:
        results = dict(ex.map(_work, unique))

    # scoring kandydatów — kod ma 3 cechy odróżniające go od napisów:
    #  1) WIELKOŚĆ: czcionka ~2x+ większa niż mediana słów w klatce
    #  2) STABILNOŚĆ: ten sam token (±1 litera OCR) w wielu klatkach
    #  3) KONT EKST: słowo 'kod' gdziekolwiek na klatce
    from collections import defaultdict
    from statistics import median
    clusters = defaultdict(lambda: {"frames": 0, "first_frame": None,
                                    "first_at": None, "kod_ctx": 0,
                                    "prominent": 0, "conf": []})
    frame_idx = {h: i for i, h in enumerate(hashes)}

    for h, words in results.items():
        if isinstance(h, str) and h.startswith("__unhashable"):
            continue
        fi = frame_idx.get(h)
        if fi is None or not words:
            continue
        at = fi / fps
        heights = [w[1] for w in words if w[1] > 0]
        med_h = median(heights) if heights else 0
        for tok, height, conf, has_kod in words:
            # hint=True: cyfry też są kandydatami — scoring je odfiltruje
            if not looks_like_code(tok, stopwords, hint=True):
                continue
            ck = tok.upper()
            cl = clusters[ck]
            cl["frames"] += 1
            cl["kod_ctx"] += 1 if has_kod else 0
            if med_h > 0 and height >= 4.0 * med_h:
                cl["prominent"] += 1
            cl["conf"].append(conf)
            if cl["first_frame"] is None:
                cl["first_frame"] = h
                cl["first_at"] = at

    # scal klucze różniące się 1 literą (błędy OCR tego samego kodu) — union-find
    keys = list(clusters.keys())
    parent = {k: k for k in keys}
    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            # korzeń z większą liczbą powtórzeń wygrywa
            parent[rb if clusters[rb]["frames"] >= clusters[ra]["frames"] else ra] = \
                ra if clusters[rb]["frames"] >= clusters[ra]["frames"] else rb

    for i, k in enumerate(keys):
        for k2 in keys[i + 1:]:
            if len(k) == len(k2) and sum(c1 != c2 for c1, c2 in zip(k, k2)) == 1:
                union(k, k2)

    found = []
    for root in {find(k) for k in keys}:
        cl = clusters[root]
        rep = cl["frames"]
        prom = cl["prominent"]
        has_kod = cl["kod_ctx"] > 0
        is_digits = root.isdigit()
        # STRICT WYMAGA: kontekst 'kod' na klatce + DUŻA czcionka (prom>=1).
        # Bez tego fałszywe alerty to nazwy marek (STEAM, MOTOROLA, UGREEN...)
        # albo zwykłe słowa z klatki, na której przypadkiem jest napis 'kod'.
        #  bez kontekstu: max 'loose' (logi + status, NIE alarmuje w Telegramie)
        #  cyfry z kontekstem: cena też bywa duża — wymagamy stabilności (>=3 klatki)
        #  litery z kontekstem: strict tylko gdy DUŻE (prom>=1);
        #    małe/stabilne bez prominentu to max 'loose'
        if not has_kod:
            level = "loose" if (rep >= 6 and prom >= 1) else None
        elif is_digits:
            level = "strict" if (prom >= 1 and rep >= 3) else "loose"
        else:
            if prom >= 1:
                level = "strict"
            elif rep >= 2:
                level = "loose"
            else:
                level = None
        if not level:
            continue
        avg_conf = sum(cl["conf"]) / len(cl["conf"]) if cl["conf"] else 0
        fh = cl["first_frame"]
        fpath = next((f for hh, f in unique if hh == fh), None)
        found.append({
            "code": root, "level": level,
            "at_sec": round(cl["first_at"], 1),
            "repeats": rep, "prominent": prom,
            "kod_context": cl["kod_ctx"],
            "avg_conf": round(avg_conf, 1),
            "shot": f"{fpath.name} (t≈{cl['first_at']:.1f}s)" if fpath else "",
            "frame": str(fpath) if fpath else "",
        })
    found.sort(key=lambda c: (-(c["prominent"] * 3 + c["repeats"])))
    log(f"OCR {item['id']} zakończone w {time.time()-t0:.0f}s, kandydatów: {len(found)}")
    for c in found:
        log(f"  KANDYDAT [{c['level']}]: {c['code']} (powtórzenia: {c['repeats']}, "
            f"kontekst kod: {c['kod_context']}, conf: {c['avg_conf']}) @ t≈{c['at_sec']}s")
    return found


def hash_file(path):
    """Szybki fingerprint klatki (miniatura 32px) — do deduplikacji statycznych ujęć."""
    try:
        img = Image.open(path).convert("L").resize((32, 32))
        return tuple(img.getdata())
    except Exception:
        return None
