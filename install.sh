#!/bin/bash
# Instalacja xkom-bot
set -e
cd "$(dirname "$0")"

echo "==> Wymagania systemowe"
command -v python3 >/dev/null || { echo "Brak python3"; exit 1; }
command -v ffmpeg >/dev/null || { echo "Brak ffmpeg: brew install ffmpeg"; exit 1; }
command -v tesseract >/dev/null || { echo "Brak tesseract: brew install tesseract"; exit 1; }
tesseract --list-langs 2>/dev/null | grep -qi '^pol' || {
  echo "Instaluję polski model OCR (tesseract-lang)..."
  brew install tesseract-lang
}

echo "==> yt-dlp"
command -v yt-dlp >/dev/null || brew install yt-dlp

echo "==> Python packages"
python3 -m pip install -r requirements.txt

echo "==> Playwright (Chromium)"
python3 -m playwright install chromium

echo ""
echo "Gotowe. Kolejne kroki:"
echo "  1) (opcjonalnie) dodaj Telegram: token i chat_id w config.yaml"
echo "  2) python3 -m xkom.bot          # start monitorowania"
echo "  3) python3 -m xkom.status       # kandydaci na kody"
echo "  4) python3 -m xkom.go KOD       # SYGNAŁ GO — aplikuje kod w koszyku"
echo "     (pierwszym razem: zaloguj się na x-kom w otwartym oknie przeglądarki)"
