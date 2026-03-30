"""
classifier.py — Categorização de apps e URLs via categories.json.

Suporta três tipos de match:
  - exact : igualdade direta (case-insensitive)
  - glob  : padrão glob (fnmatch)
  - regex : expressão regular
"""

import fnmatch
import logging
import re
from functools import lru_cache

from monitor.config import get_categories

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers de match
# ---------------------------------------------------------------------------

def _match(pattern: str, value: str, match_type: str) -> bool:
    v = value.lower()
    p = pattern.lower()

    if match_type == "exact":
        return v == p
    if match_type == "glob":
        return fnmatch.fnmatch(v, p)
    if match_type == "regex":
        try:
            return bool(re.search(p, v, re.IGNORECASE))
        except re.error:
            logger.warning("Regex inválido em categories.json: %s", pattern)
            return False

    # Fallback: glob
    return fnmatch.fnmatch(v, p)


# ---------------------------------------------------------------------------
# Classificação de processo
# ---------------------------------------------------------------------------

def classify_process(process_name: str) -> dict:
    """
    Classifica um processo pelo nome.

    Retorna:
        {"category": str, "is_productive": bool}
    """
    cfg = get_categories()
    rules = cfg.get("rules", [])

    for rule in rules:
        if _match(rule["pattern"], process_name, rule.get("match_type", "glob")):
            return {
                "category": rule["category"],
                "is_productive": bool(rule.get("is_productive", False)),
            }

    return {
        "category": cfg.get("default_category", "Outros"),
        "is_productive": bool(cfg.get("default_productive", False)),
    }


# ---------------------------------------------------------------------------
# Classificação de URL
# ---------------------------------------------------------------------------

def classify_url(url: str) -> dict | None:
    """
    Classifica uma URL pelas url_rules de categories.json.
    Retorna None se não houver regra específica para a URL
    (nesse caso o chamador deve usar a classificação do processo).
    """
    if not url:
        return None

    cfg = get_categories()
    url_rules = cfg.get("url_rules", [])

    url_lower = url.lower()
    for rule in url_rules:
        pattern = rule["pattern"].lower()
        # url_rules usam glob simples contra o domínio/URL
        if fnmatch.fnmatch(url_lower, f"*{pattern}*"):
            return {
                "category": rule["category"],
                "is_productive": bool(rule.get("is_productive", False)),
            }

    return None


# ---------------------------------------------------------------------------
# API principal
# ---------------------------------------------------------------------------

def classify(process_name: str, url: str | None = None) -> dict:
    """
    Retorna a classificação final de uma atividade.
    URLs têm prioridade sobre a regra do processo.

    Returns:
        {"category": str, "is_productive": bool}
    """
    if url:
        url_cls = classify_url(url)
        if url_cls:
            return url_cls

    return classify_process(process_name)
