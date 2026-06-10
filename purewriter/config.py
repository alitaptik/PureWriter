import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".purewriter"
CONFIG_FILE = CONFIG_DIR / "config.json"

API_KEY_ENV = "ELEVENLABS_API_KEY"
# Project root = parent of the purewriter/ package directory.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULTS = {
    "api_key": "",
    "last_voice_id": "",
    "last_model_id": "eleven_turbo_v2_5",
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


def _dotenv_values() -> dict:
    """Best-effort .env parsing (no dependency). Searches, in order, the project
    root, the current working dir, and ~/.purewriter/. First match per key wins."""
    values: dict = {}
    for path in (_PROJECT_ROOT / ".env", Path.cwd() / ".env", CONFIG_DIR / ".env"):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            values.setdefault(key.strip(),
                              val.strip().strip('"').strip("'"))
    return values


def resolve_api_key(config: dict) -> str:
    """Resolve the ElevenLabs key. Priority: real env var > .env file >
    config.json. The .env/env value is never written back to config.json."""
    env_key = os.environ.get(API_KEY_ENV) or _dotenv_values().get(API_KEY_ENV)
    if env_key and env_key.strip():
        return env_key.strip()
    return config.get("api_key", "")
