"""
browser.py — Captura de URLs do Chrome, Edge e Firefox.
Não requer extensão de browser.

Estratégia: usa Ctrl+L + Ctrl+C para copiar a URL da barra de endereço.
Método mais confiável que UI Automation direta.
"""

import logging
import re
import time

logger = logging.getLogger(__name__)

# Regex para validar que o texto capturado parece uma URL
_URL_RE = re.compile(
    r"^(https?://|ftp://|www\.|localhost|127\.0\.0\.1|[a-zA-Z0-9-]+\.[a-zA-Z]{2,})",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Captura via clipboard
# ---------------------------------------------------------------------------

def _get_url_via_clipboard(hwnd: int) -> str | None:
    """
    Captura URL da barra de endereço via Ctrl+L, Ctrl+A, Ctrl+C.
    Método mais confiável para todos os browsers modernos.
    """
    try:
        import win32gui
        import win32clipboard
        import win32con
        import ctypes

        # Salvar conteúdo atual da clipboard
        saved_data = None
        try:
            win32clipboard.OpenClipboard()
            saved_data = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
        except Exception:
            pass
        finally:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass

        # Garantir que a janela está em foco
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.1)

        VK_CONTROL = 0x11
        VK_L = 0x4C
        VK_A = 0x41
        VK_C = 0x43

        def key_down(key):
            ctypes.windll.user32.keybd_event(key, 0, 0, 0)

        def key_up(key):
            ctypes.windll.user32.keybd_event(key, 0, 2, 0)

        # Abrir barra de endereço (Ctrl+L)
        key_down(VK_CONTROL)
        key_down(VK_L)
        key_up(VK_L)
        key_up(VK_CONTROL)
        time.sleep(0.3)

        # Selecionar tudo (Ctrl+A)
        key_down(VK_CONTROL)
        key_down(VK_A)
        key_up(VK_A)
        key_up(VK_CONTROL)
        time.sleep(0.1)

        # Copiar (Ctrl+C)
        key_down(VK_CONTROL)
        key_down(VK_C)
        key_up(VK_C)
        key_up(VK_CONTROL)
        time.sleep(0.3)

        # Ler da clipboard
        url = None
        try:
            win32clipboard.OpenClipboard()
            url = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
        except Exception:
            pass
        finally:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass

        # Restaurar conteúdo anterior da clipboard
        if saved_data:
            try:
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, saved_data)
                win32clipboard.CloseClipboard()
            except Exception:
                pass

        if url and _URL_RE.match(url.strip()):
            return _normalize_url(url.strip())

    except Exception:
        logger.debug("Captura de URL via clipboard falhou para hwnd=%d", hwnd, exc_info=False)

    return None


# ---------------------------------------------------------------------------
# Captura via UI Automation (fallback)
# ---------------------------------------------------------------------------

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
    Retorna a URL ativa para um processo de browser, ou None se não conseguir.

    Args:
        process_name: nome do processo em minúsculas (ex: "chrome.exe")
        hwnd: handle da janela em foco
    """
    pn = process_name.lower()

    # Tenta método via clipboard primeiro (mais confiável)
    url = _get_url_via_clipboard(hwnd)
    if url:
        return url

    # Fallback para UI Automation
    if pn in ("chrome.exe", "msedge.exe", "brave.exe", "opera.exe"):
        return _get_url_pywinauto_chromium(hwnd)

    if pn == "firefox.exe":
        return _get_url_firefox(hwnd)

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
