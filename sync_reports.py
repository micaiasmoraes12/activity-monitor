"""
Script para sincronizar relatórios locais para a Vercel.
Uso: python sync_reports.py

Configure a variável VERCEL_DEPLOY_TOKEN no ambiente ou passe como argumento.
"""

import os
import sys
import json
import requests
from pathlib import Path

REPORTS_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "ActivityMonitor" / "reports"
API_URL = os.environ.get("API_URL", "https://activity-monitor-ochre.vercel.app")

def get_vercel_token():
    """Obtém token de deploy da Vercel."""
    if len(sys.argv) > 1:
        return sys.argv[1]
    token = os.environ.get("VERCEL_DEPLOY_TOKEN")
    if not token:
        # Retorna token temporário para desenvolvimento
        return "dev-token"
    return token

def upload_report(date: str, html_path: Path, token: str) -> bool:
    """Faz upload de um relatório para a Vercel."""
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    try:
        response = requests.post(
            f"{API_URL}/api/upload",
            json={"date": date, "html": content},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        print(f"  Response: {response.status_code} - {response.text[:200]}")
        return response.status_code == 200
    except Exception as e:
        print(f"  Error: {e}")
        return False

def main():
    token = get_vercel_token()
    if not token:
        print("Erro: Defina VERCEL_DEPLOY_TOKEN ou passe como argumento")
        print("Uso: python sync_reports.py <token>")
        sys.exit(1)
    
    if not REPORTS_DIR.exists():
        print(f"Diretório de relatórios não encontrado: {REPORTS_DIR}")
        sys.exit(1)
    
    print(f"Sincronizando relatórios de {REPORTS_DIR}...")
    
    count = 0
    for html_file in REPORTS_DIR.glob("report_*.html"):
        date = html_file.stem.replace("report_", "")
        print(f"Enviando {date}...")
        if upload_report(date, html_file, token):
            count += 1
            print(f"  ✓ {date}")
        else:
            print(f"  ✗ {date} - falhou")
    
    print(f"\nSincronizados {count} relatórios.")

if __name__ == "__main__":
    main()
