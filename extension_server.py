"""
extension_server.py — Servidor HTTP para receber dados da extensão Chrome.
Roda em localhost:8765
"""

import json
import logging
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
import ctypes

from monitor import db
from monitor.classifier import classify_url

logger = logging.getLogger(__name__)

EXTENSION_PORT = 8765

_tab_data = {}
_data_lock = threading.Lock()
_server = None


class ExtensionHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suprime logs do servidor

    def do_POST(self):
        if self.path == '/track':
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length)
                data = json.loads(body.decode('utf-8'))
                
                self._handle_track(data)
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode())
            except Exception as e:
                logger.exception("Erro ao processar dados da extensão")
                self.send_response(500)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == '/status':
            self._send_status()
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_track(self, data: dict):
        """Processa dados de tracking da extensão."""
        tabs = data.get('tabs', [])
        date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
        timestamp = data.get('timestamp', datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
        
        with _data_lock:
            if date not in _tab_data:
                _tab_data[date] = {}
            
            for tab in tabs:
                domain = tab.get('domain', 'unknown')
                url = tab.get('url', '')
                total_time = tab.get('totalTime', 0)
                active_time = tab.get('activeTime', 0)
                title = tab.get('title', '')
                
                if domain not in _tab_data[date]:
                    _tab_data[date][domain] = {
                        'totalTime': 0,
                        'activeTime': 0,
                        'url': url,
                        'title': title,
                        'count': 0
                    }
                
                _tab_data[date][domain]['totalTime'] += total_time
                _tab_data[date][domain]['activeTime'] += active_time
                _tab_data[date][domain]['count'] += 1
                _tab_data[date][domain]['url'] = url
                _tab_data[date][domain]['title'] = title
        
        # Salvar no banco de dados
        self._save_to_db(date, tabs)

    def _save_to_db(self, day: str, tabs: list):
        """Salva dados de tabs no banco."""
        for tab in tabs:
            url = tab.get('url', '')
            domain = tab.get('domain', 'unknown')
            duration = int(tab.get('activeTime', 0))
            
            if duration < 1:
                continue
            
            # Classificar URL
            cls = classify_url(url) if url else None
            category = cls['category'] if cls else 'Browser'
            is_productive = cls['is_productive'] if cls else False
            
            timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            
            try:
                db.insert_event(
                    timestamp=timestamp,
                    process_name=f"chrome:{domain}",
                    exe_path="chrome-extension",
                    window_title=tab.get('title', domain),
                    url=url,
                    duration=duration,
                    is_idle=False
                )
            except Exception as e:
                logger.debug("Erro ao salvar evento de extensão: %s", e)

    def _send_status(self):
        """Retorna status do servidor."""
        with _data_lock:
            today = datetime.now().strftime('%Y-%m-%d')
            open_tabs = len(_tab_data.get(today, {}))
        
        status = {
            'status': 'online',
            'openTabs': open_tabs,
            'monitorTime': datetime.now().strftime('%H:%M')
        }
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(status).encode())


def start_server():
    """Inicia o servidor HTTP."""
    global _server
    
    if _server is not None:
        logger.warning("Servidor da extensão já está rodando.")
        return
    
    try:
        _server = HTTPServer(('127.0.0.1', EXTENSION_PORT), ExtensionHandler)
        thread = threading.Thread(target=_server.serve_forever, daemon=True)
        thread.start()
        logger.info("Servidor da extensão iniciado em http://localhost:%d", EXTENSION_PORT)
    except OSError as e:
        if e.winerror == 10048:
            logger.info("Porta %d já em uso. Servidor já está rodando.", EXTENSION_PORT)
        else:
            logger.exception("Erro ao iniciar servidor da extensão")


def stop_server():
    """Para o servidor HTTP."""
    global _server
    if _server:
        _server.shutdown()
        _server = None
        logger.info("Servidor da extensão encerrado.")


def get_today_data() -> dict:
    """Retorna dados de hoje."""
    with _data_lock:
        today = datetime.now().strftime('%Y-%m-%d')
        return _tab_data.get(today, {})
