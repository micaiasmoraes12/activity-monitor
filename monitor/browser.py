"""
browser.py — Captura de URLs do Chrome, Edge e Firefox.
Usa Chrome DevTools Protocol para capturar URLs de forma silenciosa.
"""

import logging
import re
import json
import subprocess
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Regex para validar URL
_URL_RE = re.compile(
    r"^(https?://|ftp://|www\.|localhost|127\.0\.0\.1|[a-zA-Z0-9-]+\.[a-zA-Z]{2,})",
    re.IGNORECASE,
)

# Cache de conexões CDP por processo
_cdp_connections = {}


def _get_chrome_debugging_port(pid: int) -> int | None:
    """Obtém a porta de debug do Chrome para um PID específico."""
    try:
        import win32api
        import win32con
        
        # Tenta conectar na porta padrão de debug
        # O Chrome precisa ser iniciado com --remote-debugging-port=9222
        # Por agora, retornamos None (extensão é a solução recomendada)
        return None
    except Exception:
        return None


def _get_url_via_wmic(process_name: str, hwnd: int) -> str | None:
    """
    Tenta obter URL via linha de comando - método não intrusivo.
    """
    return None


def _get_url_pywinauto_chromium(hwnd: int) -> str | None:
    """
    Lê a barra de endereço do Chrome/Edge usando pywinauto + UI Automation.
    """
    try:
        from pywinauto import Application
        from pywinauto.findwindows import ElementNotFoundError

        app = Application(backend="uia").connect(handle=hwnd)
        win = app.window(handle=hwnd)

        try:
            addr = win.child_window(auto_id="addressEditBox", control_type="Edit")
            url = addr.get_value()
            if url and _URL_RE.match(url):
                return _normalize_url(url)
        except (ElementNotFoundError, Exception):
            pass

        try:
            addr = win.child_window(class_name="Chrome_OmniboxView")
            url = addr.get_value()
            if url and _URL_RE.match(url):
                return _normalize_url(url)
        except (ElementNotFoundError, Exception):
            pass

    except Exception:
        logger.debug("pywinauto falhou para hwnd=%d", hwnd, exc_info=False)

    return None


def _get_url_firefox(hwnd: int) -> str | None:
    """Lê a barra de endereço do Firefox via UI Automation."""
    try:
        from pywinauto import Application
        from pywinauto.findwindows import ElementNotFoundError

        app = Application(backend="uia").connect(handle=hwnd)
        win = app.window(handle=hwnd)

        for kwargs in [
            {"auto_id": "urlbar-input"},
            {"auto_id": "urlbar"},
            {"title_re": ".*address.*", "control_type": "Edit"},
        ]:
            try:
                elem = win.child_window(**kwargs)
                url = elem.get_value()
                if not url:
                    url = elem.window_text()
                if url and _URL_RE.match(url):
                    return _normalize_url(url)
            except (ElementNotFoundError, Exception):
                continue

    except Exception:
        logger.debug("Firefox UI Automation falhou para hwnd=%d", hwnd, exc_info=False)

    return None


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def get_active_url(process_name: str, hwnd: int) -> str | None:
    """
    Retorna a URL ativa para um processo de browser.
    
    Para captura confiável sem interferência, use a extensão do Chrome
    em chrome-extension/ e instale em chrome://extensions/
    
    Args:
        process_name: nome do processo em minúsculas (ex: "chrome.exe")
        hwnd: handle da janela em foco
    
    Returns:
        URL ou None (sem captura via UI para evitar interferência)
    """
    # Captura de URL desabilitada para não interferir na experiência do usuário.
    # Use a extensão do Chrome para captura confiável de URLs.
    return None


def _normalize_url(url: str) -> str:
    """Garante que a URL tem esquema e remove trailing whitespace."""
    url = url.strip()
    if url and not url.startswith(("http://", "https://", "ftp://")):
        if url.startswith("localhost") or url.startswith("127."):
            url = "http://" + url
        else:
            url = "https://" + url
    return url
