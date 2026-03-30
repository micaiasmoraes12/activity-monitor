"""
API para servir relatórios na Vercel.
"""

import os
import json
import tempfile

REPORTS_DIR = os.environ.get("REPORTS_DIR") or tempfile.gettempdir()

def get_report(date):
    path = os.path.join(REPORTS_DIR, f"report_{date}.html")
    if not os.path.exists(path):
        return {"statusCode": 404, "body": json.dumps({"error": "Not found"}), "headers": {"Content-Type": "application/json"}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"statusCode": 200, "body": content, "headers": {"Content-Type": "text/html"}}
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)}), "headers": {"Content-Type": "application/json"}}

def list_reports():
    reports = []
    try:
        if os.path.exists(REPORTS_DIR):
            for f in os.listdir(REPORTS_DIR):
                if f.startswith("report_") and f.endswith(".html"):
                    date = f.replace("report_", "").replace(".html", "")
                    reports.append({"date": date, "url": f"/report/{date}"})
        reports.sort(reverse=True)
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)}), "headers": {"Content-Type": "application/json"}}
    return {"statusCode": 200, "body": json.dumps({"reports": reports, "dir": REPORTS_DIR}), "headers": {"Content-Type": "application/json"}}

def upload_report(request):
    auth = request.get("headers", {}).get("Authorization", "")
    if not auth.startswith("Bearer "):
        return {"statusCode": 401, "body": json.dumps({"error": "Token required"}), "headers": {"Content-Type": "application/json"}}
    try:
        body = json.loads(request.get("body", "{}"))
        date = body.get("date")
        html = body.get("html")
        if not date or not html:
            return {"statusCode": 400, "body": json.dumps({"error": "date and html required"}), "headers": {"Content-Type": "application/json"}}
        os.makedirs(REPORTS_DIR, exist_ok=True)
        path = os.path.join(REPORTS_DIR, f"report_{date}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return {"statusCode": 200, "body": json.dumps({"status": "ok", "date": date, "path": path}), "headers": {"Content-Type": "application/json"}}
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)}), "headers": {"Content-Type": "application/json"}}

def handler(request):
    path = request.get("path", "/")
    method = request.get("method", "GET")
    if path == "/" or path == "":
        return list_reports()
    if path == "/api/upload" and method == "POST":
        return upload_report(request)
    if path.startswith("/report/"):
        date = path.replace("/report/", "").replace(".html", "")
        return get_report(date)
    return {"statusCode": 404, "body": json.dumps({"error": "Not found"}), "headers": {"Content-Type": "application/json"}}

app = handler
