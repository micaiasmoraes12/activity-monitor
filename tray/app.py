"""
app.py — System Tray com pystray: ícone, menu e badge de score.
"""

import logging
import os
import threading
import webbrowser
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from monitor.config import get_settings
from monitor import db
from tray.notifications import show_report_ready, show_app_started, show_app_stopped

logger = logging.getLogger(__name__)

_current_score: float = 0.0
_tray_icon = None
_collector_ref = None
_generator_ref = None


def create_tray_icon(collector=None, generator=None) -> None:
    """
    Cria e inicia o ícone do System Tray.
    
    Args:
        collector: referência ao Collector para pause/resume
        generator: referência ao ReportGenerator para forçar geração
    """
    global _tray_icon, _collector_ref, _generator_ref
    _collector_ref = collector
    _generator_ref = generator
    
    icon_image = _generate_icon_image(_current_score)
    
    menu = pystray.Menu(
        pystray.MenuItem(
            "Score de Hoje: --",
            _do_nothing,
            enabled=False,
        ),
        pystray.MenuItem(
            "Ver Relatório de Hoje",
            _show_today_report,
        ),
        pystray.MenuItem(
            "Histórico de Relatórios",
            _show_history,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Pausar Monitoramento",
            _toggle_pause,
        ),
        pystray.MenuItem(
            "Forçar Relatório Agora",
            _force_report,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Configurações",
            _open_settings,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Sair",
            _quit,
        ),
    )
    
    _tray_icon = pystray.Icon(
        "ActivityMonitor",
        icon_image,
        "Activity Monitor",
        menu,
    )
    
    _tray_icon.run_detached()
    logger.info("System Tray iniciado.")


def update_score(score: float) -> None:
    """Atualiza o score exibido no tray."""
    global _current_score
    _current_score = score
    
    if _tray_icon:
        try:
            new_image = _generate_icon_image(score)
            _tray_icon.icon = new_image
            
            menu = _tray_icon.menu
            _tray_icon.menu = pystray.Menu(
                pystray.MenuItem(
                    f"Score de Hoje: {_get_score_emoji(score)} {score}%",
                    _do_nothing,
                    enabled=False,
                ),
                pystray.MenuItem(
                    "Ver Relatório de Hoje",
                    _show_today_report,
                ),
                pystray.MenuItem(
                    "Histórico de Relatórios",
                    _show_history,
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "Pausar Monitoramento" if not (_collector_ref and _collector_ref.is_paused) else "Retomar Monitoramento",
                    _toggle_pause,
                ),
                pystray.MenuItem(
                    "Forçar Relatório Agora",
                    _force_report,
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "Configurações",
                    _open_settings,
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "Sair",
                    _quit,
                ),
            )
        except Exception:
            logger.debug("Erro ao atualizar tray icon")


def _generate_icon_image(score: float) -> Image.Image:
    """Gera imagem do ícone com base no score."""
    img = Image.new("RGB", (64, 64), color=(45, 45, 48))
    draw = ImageDraw.Draw(img)
    
    if score >= 60:
        color = (76, 175, 80)
    elif score >= 40:
        color = (255, 152, 0)
    else:
        color = (244, 67, 54)
    
    draw.ellipse([8, 8, 56, 56], fill=color, outline=(255, 255, 255), width=2)
    
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font = ImageFont.load_default()
    
    text = str(int(score))
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    x = (64 - text_width) // 2
    y = (64 - text_height) // 2 - 2
    
    draw.text((x, y), text, fill=(255, 255, 255), font=font)
    
    return img


def _get_score_emoji(score: float) -> str:
    if score >= 80:
        return "🚀"
    elif score >= 60:
        return "📈"
    elif score >= 40:
        return "⚖️"
    elif score >= 20:
        return "📉"
    else:
        return "😴"


def _do_nothing(icon, item) -> None:
    """Placeholder para itens desabilitados."""
    pass


def _show_today_report(icon, item) -> None:
    """Abre o relatório de hoje no browser."""
    today = date.today().strftime("%Y-%m-%d")
    
    report = db.fetch_report_for_day(today)
    if report and report.get("html_path"):
        path = report["html_path"]
        try:
            webbrowser.open(f"file://{path}")
        except Exception:
            logger.error("Erro ao abrir relatório: %s", path)
    else:
        logger.info("Nenhum relatório disponível para hoje.")


def _show_history(icon, item) -> None:
    """Abre o último relatório disponível."""
    report = db.fetch_latest_report()
    if report and report.get("html_path"):
        path = report["html_path"]
        try:
            webbrowser.open(f"file://{path}")
        except Exception:
            logger.error("Erro ao abrir relatório: %s", path)
    else:
        logger.info("Nenhum relatório disponível.")


def _toggle_pause(icon, item) -> None:
    """Alterna pause/resume do collector."""
    if _collector_ref:
        if _collector_ref.is_paused:
            _collector_ref.resume()
            show_app_started()
            logger.info("Monitoramento retomado via tray.")
        else:
            _collector_ref.pause()
            show_app_stopped()
            logger.info("Monitoramento pausado via tray.")


def _force_report(icon, item) -> None:
    """Força geração imediata do relatório."""
    if _generator_ref:
        try:
            threading.Thread(target=_generator_ref.generate_today_report, daemon=True).start()
        except Exception:
            logger.exception("Erro ao forçar relatório")


def _open_settings(icon, item) -> None:
    """Abre o diretório de configurações."""
    cfg_path = Path(__file__).resolve().parent.parent / "config"
    try:
        os.startfile(str(cfg_path))
    except Exception:
        logger.error("Erro ao abrir configurações")


def _quit(icon, item) -> None:
    """Encerra a aplicação."""
    logger.info("Encerrando aplicação via tray.")
    if _collector_ref:
        _collector_ref.stop()
    if _tray_icon:
        _tray_icon.stop()


def stop_tray() -> None:
    """Para o tray icon."""
    global _tray_icon
    if _tray_icon:
        _tray_icon.stop()
        _tray_icon = None


import pystray
