"""
idle_detector.py — Detecção de ociosidade e tela bloqueada no Windows.

Duas fontes de detecção:
  1. win32api.GetLastInputInfo  → inatividade de teclado/mouse
  2. OpenInputDesktop           → tela bloqueada (Winlogon/LockApp)
"""

import ctypes
import logging
from ctypes import wintypes

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Estruturas Win32
# ---------------------------------------------------------------------------

class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwTime", wintypes.DWORD),
    ]


# ---------------------------------------------------------------------------
# Idle por inatividade de input
# ---------------------------------------------------------------------------

def get_idle_seconds() -> float:
    """
    Retorna quantos segundos se passaram desde o último evento de teclado/mouse.
    Usa GetLastInputInfo (user32) — não depende de pywin32.
    """
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)

    if not user32.GetLastInputInfo(ctypes.byref(lii)):
        return 0.0

    tick_now = kernel32.GetTickCount()
    idle_ms = tick_now - lii.dwTime
    # GetTickCount() tem wrap-around em ~49 dias; garantir positivo
    if idle_ms < 0:
        idle_ms += 2**32
    return idle_ms / 1000.0


def is_idle(threshold_seconds: int | None = None) -> bool:
    """
    Retorna True se o usuário estiver ocioso por mais de `threshold_seconds`.
    Se threshold_seconds for None, lê de settings.json (padrão 60s).
    """
    if threshold_seconds is None:
        try:
            from monitor.config import get_settings
            threshold_seconds = get_settings().get("idle_threshold_seconds", 60)
        except Exception:
            threshold_seconds = 60

    return get_idle_seconds() >= threshold_seconds if threshold_seconds else False


# ---------------------------------------------------------------------------
# Detecção de tela bloqueada
# ---------------------------------------------------------------------------

def is_screen_locked() -> bool:
    """
    Retorna True se a estação de trabalho estiver bloqueada.

    Estratégia: tenta abrir o desktop de input atual.
    Quando a tela está bloqueada, o desktop ativo é "Winlogon" ou
    "Default" mas inacessível — OpenInputDesktop retorna NULL.
    """
    user32 = ctypes.windll.user32

    # DESKTOP_SWITCHDESKTOP = 0x0100
    h_desktop = user32.OpenInputDesktop(0, False, 0x0100)
    if not h_desktop:
        return True

    # Verifica se o nome é "Default" (desbloqueado) ou outro (bloqueado/winlogon)
    name_buf = ctypes.create_unicode_buffer(256)
    length = wintypes.DWORD(0)
    # GetUserObjectInformationW — UOI_NAME = 2
    ok = user32.GetUserObjectInformationW(
        h_desktop, 2, name_buf, ctypes.sizeof(name_buf), ctypes.byref(length)
    )
    user32.CloseDesktop(h_desktop)

    if not ok:
        # Não conseguiu ler o nome: assume bloqueado por precaução
        return True

    desktop_name = name_buf.value.lower()
    # Quando desbloqueado o nome é "Default"; bloqueado é "Winlogon" ou vazio
    return desktop_name != "default"


# ---------------------------------------------------------------------------
# Status combinado
# ---------------------------------------------------------------------------

def get_activity_status(threshold_seconds: int | None = None) -> dict:
    """
    Retorna um dict com o estado de atividade atual:
      - locked   : tela bloqueada
      - idle     : usuário ocioso (sem input há N segundos)
      - idle_sec : segundos desde último input
      - active   : True somente quando nem bloqueado nem ocioso
    """
    locked = is_screen_locked()
    idle_sec = get_idle_seconds()

    if threshold_seconds is None:
        try:
            from monitor.config import get_settings
            threshold_seconds = get_settings().get("idle_threshold_seconds", 60)
        except Exception:
            threshold_seconds = 60

    idle = idle_sec >= threshold_seconds

    return {
        "locked": locked,
        "idle": idle,
        "idle_sec": idle_sec,
        "active": not locked and not idle,
    }
