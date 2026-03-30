"""
main.py — Entrypoint: inicia daemon + tray + scheduler.
"""

import logging
import sys
import signal
import atexit
from datetime import date, datetime, timedelta
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from monitor import db
from extension_server import start_server as start_extension_server, stop_server as stop_extension_server
from monitor.collector import get_collector
from monitor.config import get_settings
from monitor.session_builder import build_sessions_for_day
from reporter.aggregator import get_daily_stats, get_weekly_comparison
from reporter.scorer import calculate_detailed_score
from reporter.llm_client import get_llm_client
from reporter.renderer import render_report
from tray.notifications import show_report_ready, show_app_started, show_error
from tray import app as tray_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_collector = None
_generator = None


class ReportGenerator:
    """Gera relatórios de produtividade."""
    
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._generating = False
    
    def generate_today_report(self) -> None:
        """Gera relatório do dia atual."""
        self._generate_report(date.today().strftime("%Y-%m-%d"))
    
    def generate_report(self, day: str) -> None:
        """Gera relatório para dia específico."""
        self._generate_report(day)
    
    def _generate_report(self, day: str) -> None:
        """Lógica de geração de relatório."""
        with self._lock:
            if self._generating:
                logger.info("Geração de relatório já em andamento.")
                return
            self._generating = True
        
        try:
            logger.info(f"Iniciando geração de relatório para {day}")
            
            build_sessions_for_day(day)
            
            stats = get_daily_stats(day)
            
            score_data = calculate_detailed_score(db.fetch_sessions_for_day(day))
            stats["score"] = score_data["score"]
            
            db.upsert_daily_summary(
                day=day,
                total_active_sec=stats["total_active_sec"],
                total_idle_sec=stats["total_idle_sec"],
                top_apps=stats["top_apps"],
                category_breakdown=stats["category_breakdown"],
                score=stats["score"],
            )
            
            llm_client = get_llm_client()
            llm_content = None
            
            if llm_client.is_available():
                logger.info("Ollama disponível, gerando análise por IA...")
                payload = {
                    "date": day,
                    "score": stats["score"],
                    "top_apps": stats["top_apps"],
                    "category_breakdown": stats["category_breakdown"],
                    "total_active_sec": stats["total_active_sec"],
                    "peaks": stats["peaks"],
                }
                llm_content = llm_client.generate_report(payload)
                
                if llm_content:
                    logger.info("Análise IA gerada com sucesso.")
                else:
                    logger.warning("Falha ao gerar análise IA.")
            else:
                logger.info("Ollama não disponível. Pulando análise IA.")
            
            md_path, html_path = render_report(day, stats, llm_content)
            
            try:
                from tray.app import update_score
                update_score(stats["score"])
            except Exception:
                pass
            
            show_report_ready(day, stats["score"])
            
            logger.info(f"Relatório gerado: {html_path}")
            
        except Exception:
            logger.exception(f"Erro ao gerar relatório para {day}")
            show_error(f"Falha ao gerar relatório de {day}")
        finally:
            self._generating = False


def _setup_scheduler() -> None:
    """Configura APScheduler para geração automática de relatórios."""
    global _scheduler
    
    cfg = get_settings()
    report_hour = cfg.get("report_hour", 23)
    
    _scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")
    
    _scheduler.add_job(
        _scheduled_report,
        CronTrigger(hour=report_hour, minute=0),
        id="daily_report",
        name=f"Relatório diário às {report_hour}:00",
        replace_existing=True,
    )
    
    _scheduler.add_job(
        _update_score_job,
        "interval",
        minutes=cfg.get("score_update_interval_minutes", 60),
        id="score_update",
        name="Atualizar score no tray",
        replace_existing=True,
    )
    
    _scheduler.start()
    logger.info(f"Scheduler iniciado. Relatório agendado para {report_hour}:00.")


def _scheduled_report() -> None:
    """Job agendado para gerar relatório."""
    logger.info("Job agendado: gerando relatório diário.")
    if _generator:
        _generator.generate_today_report()


def _update_score_job() -> None:
    """Job para atualizar score no tray."""
    today = date.today().strftime("%Y-%m-%d")
    
    sessions = db.fetch_sessions_for_day(today)
    score_data = calculate_detailed_score(sessions)
    
    try:
        from tray.app import update_score
        update_score(score_data["score"])
    except Exception:
        pass


def _signal_handler(signum, frame) -> None:
    """Trata sinais de encerramento."""
    logger.info("Sinal de encerramento recebido.")
    shutdown()


def shutdown() -> None:
    """Encerra todos os componentes."""
    logger.info("Encerrando aplicação...")
    
    if _scheduler:
        _scheduler.shutdown(wait=False)
    
    if _collector:
        _collector.stop()
    
    try:
        stop_extension_server()
    except Exception:
        pass
    
    try:
        tray_app.stop_tray()
    except Exception:
        pass
    
    logger.info("Aplicação encerrada.")


def main() -> None:
    """Função principal."""
    global _collector, _generator
    
    logger.info("=" * 50)
    logger.info("Activity Monitor v2.0")
    logger.info("=" * 50)
    
    db.init_db()
    
    _generator = ReportGenerator()
    
    _collector = get_collector()
    _collector.start()
    
    start_extension_server()
    
    try:
        tray_app.create_tray_icon(collector=_collector, generator=_generator)
    except Exception:
        logger.warning("System Tray não disponível.")
    
    _setup_scheduler()
    
    show_app_started()
    
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    atexit.register(shutdown)
    
    logger.info("Application rodando. Pressione Ctrl+C para encerrar.")
    
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
