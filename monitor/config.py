"""
config.py — Leitura centralizada de settings.json, categories.json e blocklist.json.
"""

import json
import logging
from pathlib import Path
from functools import lru_cache

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load_json(filename: str) -> dict:
    path = CONFIG_DIR / filename
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("Arquivo de config não encontrado: %s", path)
        return {}
    except json.JSONDecodeError as e:
        logger.error("JSON inválido em %s: %s", path, e)
        return {}


@lru_cache(maxsize=1)
def get_settings() -> dict:
    return _load_json("settings.json")


@lru_cache(maxsize=1)
def get_categories() -> dict:
    return _load_json("categories.json")


@lru_cache(maxsize=1)
def get_blocklist() -> dict:
    return _load_json("blocklist.json")


def reload_all() -> None:
    """Invalida o cache de configurações (útil após edição pelo usuário)."""
    get_settings.cache_clear()
    get_categories.cache_clear()
    get_blocklist.cache_clear()
