"""
renderer.py — Salva relatório em .md e .html em %APPDATA%\ActivityMonitor\reports\
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from monitor import db
from monitor.config import get_settings

logger = logging.getLogger(__name__)


def get_reports_dir() -> Path:
    cfg = get_settings()
    if cfg.get("reports_dir"):
        p = Path(cfg["reports_dir"])
    else:
        p = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "ActivityMonitor" / "reports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def render_report(day: str, stats: dict, llm_content: str | None = None) -> tuple[Path, Path]:
    """
    Gera arquivos .md e .html do relatório.
    
    Args:
        day: data no formato 'YYYY-MM-DD'
        stats: dict com dados do agregador
        llm_content: conteúdo gerado pelo LLM (opcional)
    
    Returns:
        tuple: (caminho_md, caminho_html)
    """
    reports_dir = get_reports_dir()
    
    md_path = reports_dir / f"report_{day}.md"
    html_path = reports_dir / f"report_{day}.html"
    
    md_content = _build_markdown(day, stats, llm_content)
    html_content = _build_html(day, stats, llm_content)
    
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    logger.info("Relatório salvo: %s e %s", md_path, html_path)
    
    db.upsert_report(
        day=day,
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        md_path=str(md_path),
        html_path=str(html_path),
        score=stats.get("score", 0),
    )
    
    return md_path, html_path


def _build_markdown(day: str, stats: dict, llm_content: str | None) -> str:
    """Constrói conteúdo Markdown do relatório."""
    score = stats.get("score", 0)
    total_active = stats.get("total_active_sec", 0)
    top_apps = stats.get("top_apps", [])
    top_domains = stats.get("top_domains", [])
    categories = stats.get("category_breakdown", {})
    peaks = stats.get("peaks", [])
    
    md = f"""# Relatório de Produtividade — {day}

## Sumário

| Métrica | Valor |
|---------|-------|
| Score de Produtividade | **{score}%** |
| Tempo Total Ativo | {_sec_to_hm(total_active)} |

"""
    
    if llm_content:
        md += f"""## Análise por IA

{llm_content}

---

"""
    
    md += """## 🖥️ Top Apps

| # | App | Tempo | Categoria |
|---|-----|-------|-----------|
"""
    
    for i, app in enumerate(top_apps[:10], 1):
        md += f"| {i} | `{app['process_name']}` | {app.get('duration_hm', '0m')} | {app.get('category', 'Outro')} |\n"
    
    if top_domains:
        md += """
## 🌐 Tempo por Site/URL

| # | Site | Tempo | Categoria |
|---|------|-------|-----------|
"""
        for i, domain in enumerate(top_domains[:10], 1):
            display = domain['domain'] if domain['domain'] else 'Sem URL'
            md += f"| {i} | `{display}` | {domain.get('duration_hm', '0m')} | {domain.get('category', 'Outro')} |\n"
    
    md += """
## 📁 Tempo por Categoria

"""
    
    for cat, sec in sorted(categories.items(), key=lambda x: x[1], reverse=True):
        pct = sec / total_active * 100 if total_active > 0 else 0
        bar = "█" * int(pct / 5)
        md += f"- **{cat}**: {bar} {pct:.1f}% ({_sec_to_hm(sec)})\n"
    
    if peaks:
        md += """
## ⏱️ Principais Períodos de Foco

"""
        for peak in peaks[:5]:
            md += f"- `{peak['app']}`: {peak.get('duration_hm', '0m')} (início: {peak.get('start_time', '')[:16]})\n"
    
    md += f"""

---
*Relatório gerado automaticamente pelo Activity Monitor em {datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""
    
    return md


def _build_html(day: str, stats: dict, llm_content: str | None) -> str:
    """Constrói conteúdo HTML do relatório."""
    score = stats.get("score", 0)
    total_active = stats.get("total_active_sec", 0)
    top_apps = stats.get("top_apps", [])
    top_domains = stats.get("top_domains", [])
    categories = stats.get("category_breakdown", {})
    peaks = stats.get("peaks", [])
    
    score_color = _get_score_color(score)
    score_emoji = _get_score_emoji(score)
    
    apps_rows = ""
    for i, app in enumerate(top_apps[:10], 1):
        prod_class = "productive" if app.get("is_productive") else "distraction"
        apps_rows += f"""
            <tr class="{prod_class}">
                <td>{i}</td>
                <td><code>{app['process_name']}</code></td>
                <td>{app.get('duration_hm', '0m')}</td>
                <td>{app.get('category', 'Outro')}</td>
            </tr>"""
    
    domains_rows = ""
    for i, domain in enumerate(top_domains[:10], 1):
        display = domain['domain'] if domain['domain'] else 'Sem URL'
        domains_rows += f"""
            <tr>
                <td>{i}</td>
                <td><code>{display}</code></td>
                <td>{domain.get('duration_hm', '0m')}</td>
                <td>{domain.get('category', 'Outro')}</td>
            </tr>"""
    
    cats_rows = ""
    for cat, sec in sorted(categories.items(), key=lambda x: x[1], reverse=True):
        pct = sec / total_active * 100 if total_active > 0 else 0
        cats_rows += f"""
            <tr>
                <td>{cat}</td>
                <td>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: {pct}%"></div>
                    </div>
                </td>
                <td>{pct:.1f}%</td>
                <td>{_sec_to_hm(sec)}</td>
            </tr>"""
    
    peaks_html = ""
    if peaks:
        for peak in peaks[:5]:
            peaks_html += f"""
            <div class="peak-item">
                <strong><code>{peak['app']}</code></strong> — {peak.get('duration_hm', '0m')}
                <small>({peak.get('start_time', '')[:16]})</small>
            </div>"""
    else:
        peaks_html = "<p>Nenhum pico registrado.</p>"
    
    llm_html = ""
    if llm_content:
        llm_html = f'<div class="llm-section">{llm_content}</div>'
    
    domains_html = ""
    if top_domains:
        domains_html = f'''
        <div class="card">
            <h2>🌐 Tempo por Site/URL</h2>
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Site</th>
                        <th>Tempo</th>
                        <th>Categoria</th>
                    </tr>
                </thead>
                <tbody>
                    {domains_rows}
                </tbody>
            </table>
        </div>
        '''
    
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Relatório de Produtividade — {day}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: #f5f5f5;
            color: #333;
            line-height: 1.6;
            padding: 20px;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
        }}
        h1 {{
            color: #2c3e50;
            margin-bottom: 20px;
        }}
        .card {{
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            padding: 20px;
            margin-bottom: 20px;
        }}
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
        }}
        .metric {{
            text-align: center;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
        }}
        .metric-value {{
            font-size: 2em;
            font-weight: bold;
            color: {score_color};
        }}
        .metric-label {{
            color: #666;
            font-size: 0.9em;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}
        th, td {{
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}
        th {{
            background: #f8f9fa;
            font-weight: 600;
        }}
        .productive td {{
            background: #e8f5e9;
        }}
        .distraction td {{
            background: #ffebee;
        }}
        .progress-bar {{
            height: 8px;
            background: #e0e0e0;
            border-radius: 4px;
            overflow: hidden;
        }}
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #4caf50, #8bc34a);
            border-radius: 4px;
        }}
        .peak-item {{
            padding: 10px;
            background: #f8f9fa;
            border-left: 3px solid #2196f3;
            margin-bottom: 10px;
            border-radius: 0 4px 4px 0;
        }}
        .llm-section {{
            background: #fff8e1;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #ffc107;
        }}
        .emoji {{ font-size: 1.5em; }}
        .footer {{
            text-align: center;
            color: #999;
            font-size: 0.85em;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Relatório de Produtividade — {day}</h1>
        
        <div class="card">
            <div class="summary-grid">
                <div class="metric">
                    <div class="metric-value">{score_emoji} {score}%</div>
                    <div class="metric-label">Score de Produtividade</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{_sec_to_hm(total_active)}</div>
                    <div class="metric-label">Tempo Total Ativo</div>
                </div>
            </div>
        </div>
        
        {llm_html}
        
        <div class="card">
            <h2>🖥️ Top Apps</h2>
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>App</th>
                        <th>Tempo</th>
                        <th>Categoria</th>
                    </tr>
                </thead>
                <tbody>
                    {apps_rows}
                </tbody>
            </table>
        </div>
        
        {domains_html}
        
        <div class="card">
            <h2>📁 Tempo por Categoria</h2>
            <table>
                <thead>
                    <tr>
                        <th>Categoria</th>
                        <th>Distribuição</th>
                        <th>Percentual</th>
                        <th>Tempo</th>
                    </tr>
                </thead>
                <tbody>
                    {cats_rows}
                </tbody>
            </table>
        </div>
        
        <div class="card">
            <h2>⏱️ Principais Períodos de Foco</h2>
            {peaks_html}
        </div>
        
        <div class="footer">
            Relatório gerado automaticamente pelo Activity Monitor em {datetime.now().strftime('%Y-%m-%d %H:%M')}
        </div>
    </div>
</body>
</html>"""
    
    return html


def _sec_to_hm(sec: int) -> str:
    h = sec // 3600
    m = (sec % 3600) // 60
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


def _get_score_color(score: float) -> str:
    if score >= 80:
        return "#4caf50"
    elif score >= 60:
        return "#8bc34a"
    elif score >= 40:
        return "#ff9800"
    elif score >= 20:
        return "#ff5722"
    else:
        return "#f44336"


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
