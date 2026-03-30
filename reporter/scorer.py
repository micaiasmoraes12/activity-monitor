"""
scorer.py — Calcula score de produtividade diário.
Score = % tempo em apps produtivos vs. distrações.
"""

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


def calculate_score(sessions: list[dict]) -> float:
    """
    Calcula score de produtividade (0-100).
    
    Score alto = mais tempo em apps produtivos.
    Score baixo = mais tempo em distrações.
    
    Args:
        sessions: lista de sessões do dia (com campos duration, is_productive)
    
    Returns:
        float: score de 0 a 100
    """
    if not sessions:
        return 0.0
    
    productive_time = 0
    total_time = 0
    
    for s in sessions:
        row = dict(s) if not isinstance(s, dict) else s
        duration = row.get("duration", 0)
        total_time += duration
        
        if row.get("is_productive"):
            productive_time += duration
    
    if total_time == 0:
        return 0.0
    
    score = (productive_time / total_time) * 100
    return round(score, 1)


def calculate_detailed_score(sessions: list[dict]) -> dict:
    """
    Retorna score detalhado com breakdown por categoria.
    """
    if not sessions:
        return {
            "score": 0.0,
            "productive_time_sec": 0,
            "distraction_time_sec": 0,
            "total_time_sec": 0,
            "category_scores": {},
        }
    
    productive_time = 0
    distraction_time = 0
    total_time = 0
    category_times: dict[str, int] = defaultdict(int)
    category_productive: dict[str, int] = defaultdict(int)
    
    for s in sessions:
        row = dict(s) if not isinstance(s, dict) else s
        duration = row.get("duration", 0)
        total_time += duration
        
        cat = row.get("category", "Outros")
        category_times[cat] += duration
        
        if row.get("is_productive"):
            productive_time += duration
            category_productive[cat] += duration
        else:
            distraction_time += duration
    
    score = calculate_score(sessions)
    
    category_scores = {}
    for cat, cat_time in category_times.items():
        cat_prod = category_productive.get(cat, 0)
        cat_score = (cat_prod / cat_time * 100) if cat_time > 0 else 0
        category_scores[cat] = {
            "score": round(cat_score, 1),
            "time_sec": cat_time,
            "productive_time_sec": cat_prod,
            "distraction_time_sec": cat_time - cat_prod,
        }
    
    return {
        "score": score,
        "productive_time_sec": productive_time,
        "distraction_time_sec": distraction_time,
        "total_time_sec": total_time,
        "category_scores": category_scores,
        "productive_pct": round(productive_time / total_time * 100, 1) if total_time > 0 else 0,
        "distraction_pct": round(distraction_time / total_time * 100, 1) if total_time > 0 else 0,
    }


def get_score_emoji(score: float) -> str:
    """Retorna emoji baseado no score."""
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


def get_score_label(score: float) -> str:
    """Retorna label textual baseado no score."""
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


def compare_with_average(day_score: float, avg_score: float) -> dict:
    """
    Compara score do dia com média histórica.
    """
    diff = day_score - avg_score
    
    if abs(diff) < 5:
        trend = "stable"
        message = "similar à média"
    elif diff > 0:
        trend = "up"
        message = f"{diff:.1f}% acima da média"
    else:
        trend = "down"
        message = f"{abs(diff):.1f}% abaixo da média"
    
    return {
        "trend": trend,
        "message": message,
        "diff": round(diff, 1),
    }
