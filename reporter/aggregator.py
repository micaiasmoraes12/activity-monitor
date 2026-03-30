"""
aggregator.py — Queries SQLite: top apps, categorias, timeline, picos.
"""

import logging
from collections import defaultdict
from datetime import date, timedelta

from monitor import db

logger = logging.getLogger(__name__)


def get_daily_stats(day: str | date) -> dict:
    """
    Retorna estatísticas completas de um dia.
    
    Args:
        day: data no formato 'YYYY-MM-DD' ou objeto date
    
    Returns:
        dict com:
            - total_active_sec: segundos ativos
            - total_idle_sec: segundos ocioso
            - top_apps: lista dos top 15 apps por tempo
            - category_breakdown: dict categoria -> segundos
            - timeline: lista de dicts {hour, app, category, duration}
            - peaks: momentos de maior atividade
            - idle_periods: períodos de ociosidade
    """
    if isinstance(day, date):
        day = day.strftime("%Y-%m-%d")

    sessions = db.fetch_sessions_for_day(day)
    
    total_active = sum(s["duration"] for s in sessions)
    
    events = db.fetch_events_for_day(day)
    total_idle = sum(e["duration"] for e in events if e["is_idle"])
    
    top_apps = _calc_top_apps(sessions, limit=15)
    top_domains = _calc_top_domains(sessions, limit=15)
    category_breakdown = _calc_category_breakdown(sessions)
    timeline = _build_timeline(sessions, day)
    peaks = _find_peaks(sessions)
    idle_periods = _find_idle_periods(events, day)
    
    return {
        "date": day,
        "total_active_sec": total_active,
        "total_idle_sec": total_idle,
        "top_apps": top_apps,
        "top_domains": top_domains,
        "category_breakdown": category_breakdown,
        "timeline": timeline,
        "peaks": peaks,
        "idle_periods": idle_periods,
    }


def get_weekly_comparison(day: str | date) -> dict:
    """
    Compara um dia com a média dos 7 dias anteriores.
    """
    if isinstance(day, date):
        day = day.strftime("%Y-%m-%d")
    
    current = get_daily_stats(day)
    
    prev_days = []
    d = date.fromisoformat(day) - timedelta(days=1)
    for _ in range(7):
        day_str = d.strftime("%Y-%m-%d")
        sessions = db.fetch_sessions_for_day(day_str)
        if sessions:
            total = sum(s["duration"] for s in sessions)
            cat_breakdown = _calc_category_breakdown(sessions)
            prev_days.append({
                "date": day_str,
                "total_sec": total,
                "category_breakdown": cat_breakdown,
            })
        d -= timedelta(days=1)
    
    avg_breakdown = defaultdict(int)
    for pd in prev_days:
        for cat, sec in pd["category_breakdown"].items():
            avg_breakdown[cat] += sec
    if prev_days:
        for cat in avg_breakdown:
            avg_breakdown[cat] = int(avg_breakdown[cat] / len(prev_days))
    
    avg_total = sum(pd["total_sec"] for pd in prev_days) / len(prev_days) if prev_days else 0
    
    return {
        "current": current,
        "previous_days": prev_days,
        "average_total_sec": avg_total,
        "average_category_breakdown": dict(avg_breakdown),
    }


def _calc_top_apps(sessions: list, limit: int = 15) -> list[dict]:
    """Agrega tempo por processo."""
    totals: dict[str, dict] = defaultdict(lambda: {"duration": 0, "category": "Outros"})
    
    for s in sessions:
        row = dict(s) if not isinstance(s, dict) else s
        key = row["process_name"]
        totals[key]["duration"] += row["duration"]
        totals[key]["category"] = row.get("category", "Outros")
        totals[key]["is_productive"] = bool(row.get("is_productive"))
    
    sorted_apps = sorted(totals.items(), key=lambda x: x[1]["duration"], reverse=True)
    
    return [
        {
            "process_name": name,
            "duration_sec": data["duration"],
            "duration_hm": _sec_to_hm(data["duration"]),
            "category": data["category"],
            "is_productive": data.get("is_productive", False),
        }
        for name, data in sorted_apps[:limit]
    ]


def _calc_top_domains(sessions: list, limit: int = 15) -> list[dict]:
    """Agrega tempo por domínio/URL."""
    totals: dict[str, dict] = defaultdict(lambda: {"duration": 0, "url": "", "category": "Outros"})
    
    for s in sessions:
        row = dict(s) if not isinstance(s, dict) else s
        url = row.get("url")
        
        if url:
            domain = _extract_domain(url)
            key = domain
            totals[key]["url"] = url
        else:
            key = f"[{row.get('process_name', 'Unknown')}]"
            totals[key]["url"] = None
        
        totals[key]["duration"] += row["duration"]
        totals[key]["category"] = row.get("category", "Outros")
    
    sorted_domains = sorted(totals.items(), key=lambda x: x[1]["duration"], reverse=True)
    
    return [
        {
            "domain": name,
            "duration_sec": data["duration"],
            "duration_hm": _sec_to_hm(data["duration"]),
            "category": data["category"],
            "url": data.get("url"),
        }
        for name, data in sorted_domains[:limit]
    ]


def _extract_domain(url: str) -> str:
    """Extrai domínio de uma URL."""
    import re
    match = re.search(r'https?://([^/]+)', url)
    if match:
        domain = match.group(1)
        domain = domain.replace('www.', '')
        return domain
    return url[:50]


def _calc_category_breakdown(sessions: list) -> dict[str, int]:
    """Agrega tempo por categoria."""
    breakdown: dict[str, int] = defaultdict(int)
    for s in sessions:
        row = dict(s) if not isinstance(s, dict) else s
        cat = row.get("category") or "Outros"
        breakdown[cat] += row["duration"]
    return dict(breakdown)


def _build_timeline(sessions: list, day: str) -> list[dict]:
    """Constrói linha do tempo horária."""
    from datetime import datetime
    
    timeline = []
    
    for s in sessions:
        row = dict(s) if not isinstance(s, dict) else s
        try:
            dt = datetime.strptime(row["start_time"], "%Y-%m-%dT%H:%M:%SZ")
            hour = dt.hour
        except (ValueError, TypeError):
            hour = 0
        
        timeline.append({
            "hour": hour,
            "app": row["process_name"],
            "category": row.get("category", "Outros"),
            "duration": row["duration"],
            "url": row.get("url"),
        })
    
    return timeline


def _find_peaks(sessions: list, min_duration: int = 300) -> list[dict]:
    """Encontra períodos de maior concentração de uso (>5 min contínuo)."""
    peaks = []
    
    sorted_sessions = sorted(sessions, key=lambda s: dict(s)["start_time"] if not isinstance(s, dict) else s["start_time"])
    
    for s in sorted_sessions:
        row = dict(s) if not isinstance(s, dict) else s
        if row["duration"] >= min_duration:
            peaks.append({
                "app": row["process_name"],
                "start_time": row["start_time"],
                "duration": row["duration"],
                "category": row.get("category", "Outros"),
            })
    
    peaks.sort(key=lambda x: x["duration"], reverse=True)
    return peaks[:5]


def _find_idle_periods(events: list, day: str) -> list[dict]:
    """Encontra períodos de ociosidade prolongados (>2 min)."""
    idle_periods = []
    idle_buffer = []
    
    for e in events:
        if e["is_idle"]:
            idle_buffer.append(e)
        else:
            if len(idle_buffer) >= 12:
                total_idle = sum(ev["duration"] for ev in idle_buffer)
                if total_idle >= 120:
                    idle_periods.append({
                        "start": idle_buffer[0]["timestamp"],
                        "end": idle_buffer[-1]["timestamp"],
                        "duration_sec": total_idle,
                        "duration_hm": _sec_to_hm(total_idle),
                    })
            idle_buffer = []
    
    return idle_periods


def _sec_to_hm(sec: int) -> str:
    """Converte segundos para string 'Xh Ym'."""
    h = sec // 3600
    m = (sec % 3600) // 60
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"
