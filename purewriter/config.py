import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".purewriter"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS = {
    "api_key": "",
    "last_voice_id": "",
    "window_width": 900,
    "window_height": 700,
    "theme": "dark",
    "preview_visible": False,
}


def load() -> dict:
    if not CONFIG_FILE.exists():
        return dict(DEFAULTS)
    with open(CONFIG_FILE) as f:
        data = json.load(f)
    return {**DEFAULTS, **data}


def save(config: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
