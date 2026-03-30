"""
API para servir relatórios na Vercel.
Endpoints:
  GET /             - Lista relatórios disponíveis
  GET /report/{date} - Retorna relatório HTML de uma data
  POST /api/upload  - Upload de relatório (requer token)
"""

import os
import json
from pathlib import Path
from datetime import datetime
import hashlib

REPORTS_DIR = Path(os.environ.get("REPORTS_DIR", "/tmp/ActivityMonitor/reports"))
UPLOAD_TOKEN = os.environ.get("UPLOAD_TOKEN", "")

REPORTS_DIR.mkdir(parents=True, exist_ok=True)

def get_report(date: str):
    """Retorna relatório HTML para uma data específica."""
    html_path = REPORTS_DIR / f"report_{date}.html"
    
    if not html_path.exists():
        return {
            "statusCode": 404,
            "body": json.dumps({"error": f"Relatório não encontrado para {date}"}),
            "headers": {"Content-Type": "application/json"}
        }
    
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    return {
        "statusCode": 200,
        "body": content,
        "headers": {"Content-Type": "text/html"}
    }


def list_reports():
    """Lista relatórios disponíveis."""
    if not REPORTS_DIR.exists():
        return {
            "statusCode": 200,
            "body": json.dumps({"reports": []}),
            "headers": {"Content-Type": "application/json"}
        }
    
    reports = []
    for f in REPORTS_DIR.glob("report_*.html"):
        date = f.stem.replace("report_", "")
        reports.append({
            "date": date,
            "url": f"/report/{date}"
        })
    
    reports.sort(key=lambda x: x["date"], reverse=True)
    
    return {
        "statusCode": 200,
        "body": json.dumps({"reports": reports}),
        "headers": {"Content-Type": "application/json"}
    }


def upload_report(request):
    """Endpoint para upload de relatórios."""
    auth = request.get("headers", {}).get("Authorization", "")
    
    if not auth.startswith("Bearer "):
        return {
            "statusCode": 401,
            "body": json.dumps({"error": "Token required"}),
            "headers": {"Content-Type": "application/json"}
        }
    
    token = auth.replace("Bearer ", "")
    
    try:
        body = json.loads(request.get("body", "{}"))
        date = body.get("date")
        html = body.get("html")
        
        if not date or not html:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "date and html required"}),
                "headers": {"Content-Type": "application/json"}
            }
        
        html_path = REPORTS_DIR / f"report_{date}.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        
        return {
            "statusCode": 200,
            "body": json.dumps({"status": "ok", "date": date}),
            "headers": {"Content-Type": "application/json"}
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
            "headers": {"Content-Type": "application/json"}
        }


def handler(request):
    """Router principal."""
    path = request.get("path", "/")
    method = request.get("method", "GET")
    
    if path == "/" or path == "":
        return list_reports()
    
    if path == "/api/upload" and method == "POST":
        return upload_report(request)
    
    if path.startswith("/report/"):
        date = path.replace("/report/", "").replace(".html", "")
        return get_report(date)
    
    return {
        "statusCode": 404,
        "body": json.dumps({"error": "Not found"}),
        "headers": {"Content-Type": "application/json"}
    }
