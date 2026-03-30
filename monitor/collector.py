"""
collector.py — Daemon de coleta: polling win32gui a cada 10s + persistência SQLite.

Fluxo principal:
  1. Poll GetForegroundWindow() a cada POLL_INTERVAL segundos
  2. Resolve nome do processo (psutil) e URL (browser.py, se browser)
  3. Verifica ociosidade e tela bloqueada (idle_detector.py)
  4. Aplica blocklist (config/blocklist.json)
  5. Persiste evento no SQLite (db.py)
  6. A cada SESSION_FLUSH_INTERVAL chama session_builder para agrupar sessões
"""

import ctypes
import logging
import threading
import time
from datetime import datetime, timezone

import psutil
import win32gui
import win32process

from monitor import db, idle_detector
from monitor.config import get_settings, get_blocklist

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

BROWSER_PROCESSES = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"}
SESSION_FLUSH_INTERVAL = 60  # segundos entre flushes do session_builder


# ---------------------------------------------------------------------------
# Helpers Win32
# ---------------------------------------------------------------------------

def _get_foreground_window_info() -> dict | None:
    """
    Retorna informações da janela em foco:
      process_name, exe_path, window_title, pid
    Retorna None se não houver janela ativa.
    """
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None

    title = win32gui.GetWindowText(hwnd)

    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc = psutil.Process(pid)
        process_name = proc.name().lower()
        exe_path = ""
        try:
            exe_path = proc.exe()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        process_name = "unknown"
        exe_path = ""
        pid = 0

    return {
        "hwnd": hwnd,
        "pid": pid,
        "process_name": process_name,
        "exe_path": exe_path,
        "window_title": title,
    }


def _is_blocked(process_name: str, window_title: str) -> bool:
    """Verifica se o app/título está na blocklist."""
    bl = get_blocklist()
    blocked_procs = {p.lower() for p in bl.get("processes", [])}
    if process_name in blocked_procs:
        return True

    title_lower = window_title.lower()
    for kw in bl.get("window_title_keywords", []):
        if kw.lower() in title_lower:
            return True

    return False


# ---------------------------------------------------------------------------
# Classe principal
# ---------------------------------------------------------------------------

class Collector:
    """
    Daemon de coleta de atividade.
    Executa em thread dedicada; controlado via start() / stop() / pause() / resume().
    """

    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()   # set = pausado
        self._thread: threading.Thread | None = None
        self._last_flush = time.monotonic()

        cfg = get_settings()
        self.poll_interval: int = cfg.get("poll_interval_seconds", 10)

    # ------------------------------------------------------------------
    # Controle do daemon
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            logger.warning("Collector já está rodando.")
            return

        db.init_db()

        self._stop_event.clear()
        self._pause_event.clear()
        self._thread = threading.Thread(target=self._run, name="collector", daemon=True)
        self._thread.start()
        logger.info("Collector iniciado (poll=%ds).", self.poll_interval)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=15)
        logger.info("Collector encerrado.")

    def pause(self) -> None:
        self._pause_event.set()
        logger.info("Collector pausado.")

    def resume(self) -> None:
        self._pause_event.clear()
        logger.info("Collector retomado.")

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def is_paused(self) -> bool:
        return self._pause_event.is_set()

    # ------------------------------------------------------------------
    # Loop principal
    # ------------------------------------------------------------------

    def _run(self) -> None:
        logger.debug("Thread do collector iniciada.")
        while not self._stop_event.is_set():
            try:
                if not self._pause_event.is_set():
                    self._tick()
            except Exception:
                logger.exception("Erro inesperado no tick do collector.")

            # Dorme em fatias para reagir rapidamente ao stop/pause
            for _ in range(self.poll_interval * 10):
                if self._stop_event.is_set():
                    return
                time.sleep(0.1)

    def _tick(self) -> None:
        """Uma iteração do ciclo de coleta."""
        status = idle_detector.get_activity_status()

        # Não coleta quando a tela está bloqueada
        if status["locked"]:
            logger.debug("Tela bloqueada — pulando tick.")
            return

        win_info = _get_foreground_window_info()
        if not win_info:
            return

        process_name = win_info["process_name"]
        window_title = win_info["window_title"]

        # Aplica blocklist
        if _is_blocked(process_name, window_title):
            logger.debug("App bloqueado: %s", process_name)
            return

        # Captura URL se for browser
        url: str | None = None
        if process_name in BROWSER_PROCESSES:
            try:
                from monitor.browser import get_active_url
                url = get_active_url(process_name, win_info["hwnd"])
            except Exception:
                logger.debug("Falha ao capturar URL de %s.", process_name, exc_info=True)
            # Checa blocklist de URLs
            if url and _is_url_blocked(url):
                logger.debug("URL bloqueada: %s", url)
                return

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        is_idle = status["idle"]

        db.insert_event(
            timestamp=timestamp,
            process_name=process_name,
            exe_path=win_info["exe_path"],
            window_title=window_title,
            url=url,
            duration=self.poll_interval,
            is_idle=is_idle,
        )

        logger.debug(
            "[%s] %s | idle=%s | url=%s",
            timestamp, process_name, is_idle, url or "-",
        )

        # Flush de sessões periodicamente
        now = time.monotonic()
        if now - self._last_flush >= SESSION_FLUSH_INTERVAL:
            self._flush_sessions()
            self._last_flush = now

    def _flush_sessions(self) -> None:
        """Delega ao session_builder para agrupar eventos em sessões."""
        try:
            from monitor.session_builder import build_pending_sessions
            build_pending_sessions()
        except Exception:
            logger.exception("Erro ao fazer flush de sessões.")


# ---------------------------------------------------------------------------
# Blocklist de URL
# ---------------------------------------------------------------------------

def _is_url_blocked(url: str) -> bool:
    bl = get_blocklist()
    url_lower = url.lower()
    for domain in bl.get("url_domains", []):
        if domain.lower() in url_lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Singleton global
# ---------------------------------------------------------------------------

_collector: Collector | None = None


def get_collector() -> Collector:
    global _collector
    if _collector is None:
        _collector = Collector()
    return _collector
