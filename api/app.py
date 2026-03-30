"""
API para servir relatórios na Vercel.
"""

import json
import os

REPORTS_DIR = "/var/task/reports"

def get_report(date):
    path = f"{REPORTS_DIR}/report_{date}.html"
    if not os.path.exists(path):
        return {"statusCode": 404, "body": json.dumps({"error": "Not found"}), "headers": {"Content-Type": "application/json"}}
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return {"statusCode": 200, "body": content, "headers": {"Content-Type": "text/html"}}

def list_reports():
    reports = []
    if os.path.exists(REPORTS_DIR):
        for f in os.listdir(REPORTS_DIR):
            if f.startswith("report_") and f.endswith(".html"):
                date = f.replace("report_", "").replace(".html", "")
                reports.append({"date": date, "url": f"/report/{date}"})
    reports.sort(reverse=True)
    return {"statusCode": 200, "body": json.dumps({"reports": reports}), "headers": {"Content-Type": "application/json"}}

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
        if not os.path.exists(REPORTS_DIR):
            os.makedirs(REPORTS_DIR, exist_ok=True)
        path = f"{REPORTS_DIR}/report_{date}.html"
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return {"statusCode": 200, "body": json.dumps({"status": "ok", "date": date}), "headers": {"Content-Type": "application/json"}}
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
