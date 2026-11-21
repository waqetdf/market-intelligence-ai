"""Credentials retained locally outside SQLite and omitted from settings responses."""

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock

INTEGRATION_KEYS = {
    "ai": ("MARKET_AI_PROVIDER", "MARKET_AI_URL", "MARKET_AI_MODEL", "MARKET_AI_TOKEN"),
    "discord": ("DISCORD_WEBHOOK_URL",),
    "telegram": ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"),
}
ALLOWED_KEYS = set().union(*INTEGRATION_KEYS.values())
write_lock = Lock()


def read_local_integrations(directory: Path):
    path = directory / "integrations.json"
    if not path.is_file():
        return {}
    values = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(values, dict):
        raise ValueError("Configuración local inválida")
    return {key: value for key, value in values.items() if key in ALLOWED_KEYS and isinstance(value, str)}


def apply_local_integrations(values):
    os.environ.update(values)


def save_local_integrations(directory, key, values, clear):
    with write_lock:
        _save_local_integrations(directory, key, values, clear)


def _save_local_integrations(directory, key, values, clear):
    settings = read_local_integrations(directory)
    for name, value in zip(INTEGRATION_KEYS[key], values, strict=True):
        if clear or value:
            settings[name] = "" if clear else value
    if key == "ai" and not clear and values[1] and values[1] != os.getenv("MARKET_AI_URL") and not values[3]:
        settings["MARKET_AI_TOKEN"] = ""
    path = directory / "integrations.json"
    with NamedTemporaryFile(mode="w", dir=directory, encoding="utf-8", delete=False) as handle:
        temporary = Path(handle.name)
        try:
            json.dump(settings, handle, ensure_ascii=False)
        except BaseException:
            handle.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    apply_local_integrations(settings)
