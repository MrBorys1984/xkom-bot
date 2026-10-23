import json
import os
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
# STATE_DIR da się nadpisać (XKOM_STATE_DIR) — GitHub Actions trzyma stan
# w katalogu, który potem ląduje w artyfakcie.
STATE = Path(os.environ.get("XKOM_STATE_DIR") or (ROOT / "state"))
LOGS = STATE / "logs"
for _d in (STATE, LOGS):
    _d.mkdir(parents=True, exist_ok=True)


def load_config():
    cfg_path = Path(os.environ.get("XKOM_CONFIG") or (ROOT / "config.yaml"))
    if not cfg_path.exists():
        # chmura: repo ma config.example.yaml (bez sekretów)
        cfg_path = ROOT / "config.example.yaml"
    with open(cfg_path) as f:
        return yaml.safe_load(f)


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOGS / "bot.log", "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_state(name, default):
    p = STATE / f"{name}.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return default


def save_state(name, data):
    (STATE / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
