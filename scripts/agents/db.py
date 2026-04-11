"""Aiven Postgres helper — single-connection, psycopg2-based query layer.

Replaces the former supabase-py client. Gives the pipeline scripts a thin,
consistent surface for SQL work:

    from scripts.agents.db import fetch_all, fetch_one, execute, execute_returning, vec_str

    row = fetch_one("SELECT * FROM episodes WHERE id=%s", (ep_id,))
    rows = fetch_all("SELECT id FROM episodes WHERE processed=%s", (False,))
    execute("UPDATE episodes SET processed=%s WHERE id=%s", (True, ep_id))
    new_id = execute_returning(
        "INSERT INTO people (name) VALUES (%s) RETURNING id", (name,)
    )["id"]

Design notes
------------
* One lazily-initialised connection with ``autocommit=True``. The pipeline is
  single-process / single-thread per script run, so pooling is unnecessary.
* ``dict`` and ``list`` are auto-adapted to JSONB so callers can pass native
  Python structures straight through to ``execute(...)``.
* pgvector is handled as text: the DB returns vectors as ``'[1.0,2.0,...]'``
  strings, callers use :func:`parse_vector` to re-hydrate, and
  :func:`vec_str` to format outgoing vectors for parameters followed by an
  explicit ``::vector`` cast in the SQL.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable, Sequence

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from psycopg2.extensions import connection as _Connection, register_adapter
from psycopg2.extras import Json, RealDictCursor

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env.local")

DATABASE_URL = os.environ["AIVEN_DATABASE_URL"]

# Adapt dict/list → JSONB automatically (write side).
register_adapter(dict, Json)
register_adapter(list, Json)

# Force JSONB → Python (read side). psycopg2 auto-registers on import in
# most environments, but some Aiven connections miss it — register
# explicitly so `row["words"]` is a list, not the raw JSON text.
psycopg2.extras.register_default_json(loads=json.loads, globally=True)
psycopg2.extras.register_default_jsonb(loads=json.loads, globally=True)

_conn: _Connection | None = None


def _connect() -> _Connection:
    conn = psycopg2.connect(
        DATABASE_URL,
        connect_timeout=15,
        client_encoding="utf8",
        # keepalives help Aiven's edge proxy notice dead clients
        # (and us notice dead servers) before an idle close kills us.
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=3,
    )
    conn.autocommit = True
    return conn


def get_db() -> _Connection:
    """Return the shared Aiven connection, creating it on first use."""
    global _conn
    if _conn is None or _conn.closed:
        _conn = _connect()
    return _conn


def _reset_conn() -> None:
    """Force-close the shared connection; next get_db() will reconnect."""
    global _conn
    if _conn is not None:
        try:
            _conn.close()
        except Exception:
            pass
    _conn = None


# Exceptions that indicate the connection is dead and we should reconnect
# and retry once. All other errors propagate immediately.
_TRANSIENT = (
    psycopg2.OperationalError,
    psycopg2.InterfaceError,
)


def _run_with_retry(fn):
    """Run *fn(conn)* once; on connection-dead errors reconnect and retry."""
    try:
        return fn(get_db())
    except _TRANSIENT as e:
        # Only retry on errors that clearly mean the socket is gone.
        msg = str(e).lower()
        dead = (
            "server closed the connection" in msg
            or "connection already closed" in msg
            or "terminating connection" in msg
            or "ssl connection has been closed" in msg
            or "eof detected" in msg
        )
        if not dead:
            raise
        print(f"[db] connection dropped ({e.__class__.__name__}); reconnecting…")
        _reset_conn()
        return fn(get_db())


def close_db() -> None:
    """Close the shared connection (optional — process exit will clean up)."""
    global _conn
    if _conn is not None and not _conn.closed:
        _conn.close()
    _conn = None


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def fetch_all(query: str, params: Sequence[Any] | None = None) -> list[dict]:
    """Run *query* and return every row as a plain ``dict``."""
    def _run(conn):
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params or ())
            return [dict(r) for r in cur.fetchall()]
    return _run_with_retry(_run)


def fetch_one(query: str, params: Sequence[Any] | None = None) -> dict | None:
    """Run *query* and return the first row as a ``dict``, or ``None``."""
    def _run(conn):
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params or ())
            row = cur.fetchone()
            return dict(row) if row else None
    return _run_with_retry(_run)


def fetch_value(query: str, params: Sequence[Any] | None = None) -> Any:
    """Return the first column of the first row (e.g. ``COUNT(*)``)."""
    def _run(conn):
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            row = cur.fetchone()
            return row[0] if row else None
    return _run_with_retry(_run)


def execute(query: str, params: Sequence[Any] | None = None) -> int:
    """Run a non-returning statement. Returns the affected row count."""
    def _run(conn):
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            return cur.rowcount
    return _run_with_retry(_run)


def execute_returning(
    query: str, params: Sequence[Any] | None = None
) -> dict | None:
    """Run an INSERT/UPDATE/DELETE ... RETURNING and return the first row."""
    def _run(conn):
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params or ())
            row = cur.fetchone()
            return dict(row) if row else None
    return _run_with_retry(_run)


def execute_many(query: str, rows: Iterable[Sequence[Any]], page_size: int = 500) -> None:
    """Batch insert/update — wraps ``execute_batch`` for speed."""
    materialized = list(rows)  # must be concrete so a retry re-runs the same data
    def _run(conn):
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, query, materialized, page_size=page_size)
    _run_with_retry(_run)


# ---------------------------------------------------------------------------
# LLM usage logging
# ---------------------------------------------------------------------------

def log_llm_usage(
    *,
    episode_id: str | None,
    stage: str,
    provider: str,
    model: str,
    status_code: int,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    reasoning_tokens: int = 0,
    cached_input_tokens: int = 0,
    total_tokens: int = 0,
    cost_usd: float = 0.0,
    request_id: str | None = None,
    finish_reason: str | None = None,
    duration_ms: int | None = None,
    error: str | None = None,
    raw_usage: dict | None = None,
) -> None:
    """Append one LLM call to the llm_usage table. Never raises — cost
    tracking failures must not kill the pipeline."""
    try:
        execute(
            """
            INSERT INTO llm_usage (
                episode_id, stage, provider, model, request_id,
                prompt_tokens, completion_tokens, reasoning_tokens,
                cached_input_tokens, total_tokens, cost_usd,
                status_code, finish_reason, duration_ms, error, raw_usage
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            """,
            (
                episode_id, stage, provider, model, request_id,
                prompt_tokens, completion_tokens, reasoning_tokens,
                cached_input_tokens, total_tokens, cost_usd,
                status_code, finish_reason, duration_ms, error, raw_usage,
            ),
        )
    except Exception as e:
        print(f"  WARN: failed to log llm_usage: {e}")


# ---------------------------------------------------------------------------
# pgvector helpers
# ---------------------------------------------------------------------------

def vec_str(vec: Sequence[float]) -> str:
    """Format a Python sequence as a pgvector literal.

    Usage in SQL::

        execute(
            "INSERT INTO speaker_embeddings (embedding) VALUES (%s::vector)",
            (vec_str(centroid),),
        )
    """
    return "[" + ",".join(f"{float(x):.8f}" for x in vec) + "]"


def parse_vector(raw: Any) -> list[float] | None:
    """Convert a pgvector value (returned as ``'[...]'`` text) to ``list[float]``."""
    if raw is None:
        return None
    if isinstance(raw, list):
        return [float(x) for x in raw]
    s = str(raw).strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
    if not s:
        return []
    return [float(x) for x in s.split(",")]


# ---------------------------------------------------------------------------
# JSON column helpers
# ---------------------------------------------------------------------------

def parse_json(raw: Any) -> Any:
    """JSONB columns usually come back already decoded; handle strings too."""
    if raw is None or not isinstance(raw, str):
        return raw
    return json.loads(raw)
