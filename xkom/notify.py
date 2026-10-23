"""Powiadomienia: Telegram + dźwięk + powiadomienie macOS."""
import subprocess
import urllib.parse
import urllib.request

from .common import log


def _macos_notify(title, msg):
    script = (f"display notification {msg!r} with title {title!r} "
              f"sound name 'Glass'")
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=15)
    except Exception:
        pass


def notify(cfg, title, msg, sound=True):
    log(f"POWIADOMIENIE: {title} | {msg}")
    _macos_notify(title, msg)
    if sound:
        try:
            subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"],
                           capture_output=True, timeout=15)
        except Exception:
            pass
    tg = cfg.get("telegram") or {}
    if tg.get("token") and tg.get("chat_id"):
        _telegram(tg["token"], tg["chat_id"], f"*{title}*\n{msg}")


def _telegram(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except Exception as e:
        log(f"[telegram] nie udało się wysłać: {e}")
