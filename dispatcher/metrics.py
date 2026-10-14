"""One row per task. SQLite locally; `to_snowflake.sql` is the mirror's DDL."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

COLUMNS = ("task_id", "repo", "task_type", "created_at", "closed_tier", "local_attempts", "escalations",
           "tokens_t0", "tokens_t1", "tokens_t2", "calls_canon", "calls_graph", "calls_lsp", "calls_search",
           "calls_file_read", "tests_passed", "gate_confidence", "review_verdict", "human_review_minutes", "wall_seconds")

DDL = """CREATE TABLE IF NOT EXISTS tasks (
  task_id TEXT PRIMARY KEY, repo TEXT, task_type TEXT, created_at TEXT, closed_tier TEXT,
  local_attempts INTEGER, escalations INTEGER, tokens_t0 INTEGER, tokens_t1 INTEGER, tokens_t2 INTEGER,
  calls_canon INTEGER, calls_graph INTEGER, calls_lsp INTEGER, calls_search INTEGER, calls_file_read INTEGER,
  tests_passed INTEGER, gate_confidence REAL, review_verdict TEXT, human_review_minutes REAL, wall_seconds REAL
)"""

SNOWFLAKE_DDL = """-- Mirror of the dispatcher's metrics table. Load from the SQLite export nightly.
CREATE TABLE IF NOT EXISTS DS_OPS.AGENT.TASKS (
  TASK_ID STRING PRIMARY KEY, REPO STRING, TASK_TYPE STRING, CREATED_AT TIMESTAMP_NTZ, CLOSED_TIER STRING,
  LOCAL_ATTEMPTS NUMBER, ESCALATIONS NUMBER, TOKENS_T0 NUMBER, TOKENS_T1 NUMBER, TOKENS_T2 NUMBER,
  CALLS_CANON NUMBER, CALLS_GRAPH NUMBER, CALLS_LSP NUMBER, CALLS_SEARCH NUMBER, CALLS_FILE_READ NUMBER,
  TESTS_PASSED BOOLEAN, GATE_CONFIDENCE FLOAT, REVIEW_VERDICT STRING, HUMAN_REVIEW_MINUTES FLOAT, WALL_SECONDS FLOAT
);
"""


class Metrics:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute(DDL)
        (self.path.parent / "to_snowflake.sql").write_text(SNOWFLAKE_DDL)

    def record(self, **row) -> None:
        row.setdefault("created_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        values = [row.get(c) for c in COLUMNS]
        placeholders = ", ".join("?" for _ in COLUMNS)
        self.conn.execute(f"INSERT OR REPLACE INTO tasks ({', '.join(COLUMNS)}) VALUES ({placeholders})", values)
        self.conn.commit()

    def rows(self) -> list[dict]:
        cur = self.conn.execute(f"SELECT {', '.join(COLUMNS)} FROM tasks ORDER BY created_at")
        return [dict(zip(COLUMNS, r)) for r in cur.fetchall()]
