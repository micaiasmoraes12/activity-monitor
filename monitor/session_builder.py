"""
session_builder.py — Agrupa eventos brutos em sessões contínuas por app.

Uma sessão é uma sequência de eventos consecutivos do mesmo processo
sem intervalo superior a GAP_THRESHOLD segundos.
"""

import json
import logging
from datetime import datetime, timezone

from monitor import db
from monitor.classifier import classify

logger = logging.getLogger(__name__)

GAP_THRESHOLD = 30   # segundos — lacuna que encerra uma sessão
MIN_DURATION  = 5    # segundos — sessões menores que isso são descartadas


# ---------------------------------------------------------------------------
# Estado de controle de processamento incremental
# ---------------------------------------------------------------------------

# ID do último evento já processado em sessões (persistido no daily_summaries
# não — guardamos em memória; no pior caso, na reinicialização reprocessamos
# o dia atual, o que é idempotente pois verificamos sobreposição de datas).
_last_processed_event_id: int = 0


def build_pending_sessions() -> int:
    """
    Lê eventos ainda não processados e constrói sessões no banco.
    Retorna o número de novas sessões inseridas.
    """
    global _last_processed_event_id

    with db.get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, timestamp, process_name, exe_path, window_title,
                   url, duration, is_idle
            FROM events
            WHERE id > ? AND is_idle = 0
            ORDER BY id
            """,
            (_last_processed_event_id,),
        ).fetchall()

    if not rows:
        return 0

    sessions = _group_into_sessions(rows)
    count = 0
    for s in sessions:
        _save_session(s)
        count += 1

    if rows:
        _last_processed_event_id = rows[-1]["id"]

    logger.debug("session_builder: %d novas sessões.", count)
    return count


def build_sessions_for_day(day: str) -> int:
    """
    (Re)constrói todas as sessões de um dia específico (YYYY-MM-DD).
    Apaga as sessões existentes do dia antes de recriar.
    """
    with db.get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE start_time LIKE ?", (f"{day}%",))

        rows = conn.execute(
            """
            SELECT id, timestamp, process_name, exe_path, window_title,
                   url, duration, is_idle
            FROM events
            WHERE timestamp LIKE ? AND is_idle = 0
            ORDER BY id
            """,
            (f"{day}%",),
        ).fetchall()

    if not rows:
        return 0

    sessions = _group_into_sessions(rows)
    for s in sessions:
        _save_session(s)

    return len(sessions)


# ---------------------------------------------------------------------------
# Lógica de agrupamento
# ---------------------------------------------------------------------------

def _group_into_sessions(rows) -> list[dict]:
    """
    Agrupa uma lista de eventos (Row) em sessões.
    Dois eventos pertencem à mesma sessão se:
      - Mesmo process_name
      - Gap temporal ≤ GAP_THRESHOLD
    """
    if not rows:
        return []

    sessions = []
    buf = [dict(rows[0])]

    for row in rows[1:]:
        prev = buf[-1]
        curr = dict(row)

        # Calcula gap entre fim do evento anterior e início do atual
        try:
            prev_end = _parse_ts(prev["timestamp"]) + prev["duration"]
            curr_start = _parse_ts(curr["timestamp"])
            gap = curr_start - prev_end
        except Exception:
            gap = GAP_THRESHOLD + 1  # força nova sessão em caso de erro

        same_app = prev["process_name"] == curr["process_name"]

        if same_app and gap <= GAP_THRESHOLD:
            buf.append(curr)
        else:
            session = _flush_buffer(buf)
            if session:
                sessions.append(session)
            buf = [curr]

    # Flush do buffer final
    session = _flush_buffer(buf)
    if session:
        sessions.append(session)

    return sessions


def _flush_buffer(buf: list[dict]) -> dict | None:
    """Converte um buffer de eventos em um dict de sessão."""
    if not buf:
        return None

    total_duration = sum(e["duration"] for e in buf)
    if total_duration < MIN_DURATION:
        return None

    first = buf[0]
    last = buf[-1]

    # URL mais frequente no buffer
    urls = [e["url"] for e in buf if e.get("url")]
    url = max(set(urls), key=urls.count) if urls else None

    cls = classify(first["process_name"], url)

    return {
        "start_time": first["timestamp"],
        "end_time": last["timestamp"],
        "duration": total_duration,
        "process_name": first["process_name"],
        "exe_path": first.get("exe_path", ""),
        "window_title": first["window_title"],
        "url": url,
        "category": cls["category"],
        "is_productive": cls["is_productive"],
    }


def _save_session(s: dict) -> None:
    db.insert_session(
        start_time=s["start_time"],
        end_time=s["end_time"],
        duration=s["duration"],
        process_name=s["process_name"],
        exe_path=s.get("exe_path", ""),
        window_title=s["window_title"],
        url=s.get("url"),
        category=s["category"],
        is_productive=s["is_productive"],
    )


def _parse_ts(ts: str) -> int:
    """Converte timestamp ISO-8601 para epoch seconds (int)."""
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except ValueError:
        # Tenta formato alternativo
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return int(dt.timestamp())
