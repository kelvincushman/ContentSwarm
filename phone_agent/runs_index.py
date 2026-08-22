"""SQLite summary index for flow-replay run reports.

Every replay writes a full JSON report via save_run_report(); this index
mirrors the summary fields into SQLite so health queries (verified-rate
trend per flow) don't require scanning every report file on disk.

Best-effort only: indexing failures must never fail a replay.
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_FILENAME = "index.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    flow TEXT NOT NULL,
    device_id TEXT,
    started_at TEXT NOT NULL,
    executed INTEGER NOT NULL,
    failed INTEGER NOT NULL,
    verified INTEGER NOT NULL,
    report_path TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_flow_started ON runs(flow, started_at);
"""


def db_path(flows_dir: str) -> Path:
    return Path(flows_dir) / "runs" / DB_FILENAME


def record(summary: Dict[str, Any], report_path: str, flows_dir: str) -> None:
    """Index one run report. Best-effort - never raises."""
    try:
        path = db_path(flows_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA)
            conn.execute(
                "INSERT INTO runs (flow, device_id, started_at, executed, failed, verified, report_path) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    summary.get("flow"),
                    summary.get("device_id"),
                    summary.get("started_at"),
                    summary.get("executed", 0),
                    summary.get("failed", 0),
                    summary.get("verified", 0),
                    report_path,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass  # indexing must never fail a replay


def health(
    flow_name: Optional[str] = None, days: int = 30, flows_dir: str = "flows"
) -> List[Dict[str, Any]]:
    """Per-flow run stats over the trailing `days` days."""
    path = db_path(flows_dir)
    if not path.exists():
        return []

    conn = sqlite3.connect(str(path))
    try:
        query = (
            "SELECT flow, COUNT(*), SUM(executed), SUM(failed), SUM(verified), MAX(started_at) "
            "FROM runs WHERE started_at >= datetime('now', 'localtime', ?)"
        )
        params: List[Any] = [f"-{int(days)} days"]
        if flow_name:
            query += " AND flow = ?"
            params.append(flow_name)
        query += " GROUP BY flow"
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    result = []
    for flow, runs, executed, failed, verified, last_run in rows:
        executed = executed or 0
        verified = verified or 0
        result.append({
            "flow": flow,
            "runs": runs,
            "executed": executed,
            "failed": failed or 0,
            "verified": verified,
            "verified_rate": round(verified / executed, 3) if executed else 0.0,
            "last_run": last_run,
        })
    return result
