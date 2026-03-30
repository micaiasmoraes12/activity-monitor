"""
notifications.py — Toast notifications nativo Windows 10/11.
"""

import logging
import subprocess
import sys
from datetime import datetime

logger = logging.getLogger(__name__)


def show_toast(title: str, message: str, duration: int = 5) -> bool:
    """
    Mostra toast notification nativo do Windows.
    
    Args:
        title: título da notificação
        message: corpo da mensagem
        duration: duração em segundos
    
    Returns:
        bool: True se bem-sucedido
    """
    try:
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        toaster.show_toast(
            title=title,
            msg=message,
            duration=duration,
            threaded=True,
        )
        return True
    except ImportError:
        logger.debug("win10toast não disponível, tentando plyer")
        return _show_toast_plyer(title, message)
    except Exception:
        logger.exception("Erro ao mostrar toast")
        return _show_toast_powershell(title, message)


def _show_toast_plyer(title: str, message: str) -> bool:
    """Fallback usando plyer."""
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="Activity Monitor",
            timeout=duration,
        )
        return True
    except Exception:
        return _show_toast_powershell(title, message)


def _show_toast_powershell(title: str, message: str) -> bool:
    """Fallback usando PowerShell direto."""
    try:
        script = f'''
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
        
        $template = @"
        <toast>
            <visual>
                <binding template="ToastText02">
                    <text id="1">{title}</text>
                    <text id="2">{message}</text>
                </binding>
            </visual>
        </toast>
"@
        
        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $xml.LoadXml($template)
        $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("ActivityMonitor").Show($toast)
        '''
        
        result = subprocess.run(
            ["powershell", "-Command", script],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        logger.debug("Toast via PowerShell falhou")
        return False


def show_report_ready(day: str, score: float) -> None:
    """Notifica que o relatório diário está pronto."""
    score_label = _get_score_label(score)
    show_toast(
        title="📊 Relatório de Produtividade Pronto",
        message=f"Relatório de {day} | Score: {score_label} ({score}%)",
        duration=8,
    )


def show_app_started() -> None:
    """Notifica que o monitoramento começou."""
    show_toast(
        title="🖥️ Activity Monitor",
        message="Monitoramento de produtividade iniciado.",
        duration=3,
    )


def show_app_stopped() -> None:
    """Notifica que o monitoramento foi interrompido."""
    show_toast(
        title="⏸️ Activity Monitor Pausado",
        message="O monitoramento foi pausado. Clique no ícone para retomar.",
        duration=5,
    )


def show_error(message: str) -> None:
    """Mostra notificação de erro."""
    show_toast(
        title="❌ Erro no Activity Monitor",
        message=message,
        duration=10,
    )


def _get_score_label(score: float) -> str:
    if score >= 80:
        return "Excelente"
    elif score >= 60:
        return "Bom"
    elif score >= 40:
        return "Regular"
    elif score >= 20:
        return "Baixo"
    else:
        return "Muito Baixo"
