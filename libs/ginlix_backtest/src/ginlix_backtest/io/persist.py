"""Persist backtest results to Postgres (backtest.* schema).

Usage:
    from ginlix_backtest.io.persist import save_result
    job_id = save_result(
        result=bt_result,
        strategy_name="Golden Cross AAPL",
        strategy_code=open("strategy.py").read(),
        snapshot_id="us-2026-04-23",
        params={"symbol": "AAPL", "fast": 50, "slow": 200},
    )
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import os
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ginlix_backtest.engine.portfolio import BacktestResult
    from ginlix_backtest.strategy import StrategyResult


def _get_framework_version() -> str:
    try:
        return importlib.metadata.version("ginlix-backtest")
    except Exception:
        return "0.0.0-dev"


def _code_hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _get_conn():
    """Return a psycopg3 sync connection using DATABASE_URL env var."""
    import psycopg

    dsn = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    if not dsn:
        raise RuntimeError(
            "DATABASE_URL environment variable not set. "
            "Cannot persist to Postgres."
        )
    return psycopg.connect(dsn)


def save_strategy(
    conn,
    name: str,
    code: str,
    description: str = "",
    params_schema: dict | None = None,
    tags: list[str] | None = None,
) -> str:
    """Upsert a strategy definition. Returns strategy UUID."""
    strategy_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO backtest.strategies
                (id, name, description, code, code_hash, framework_version, params_schema, tags)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                strategy_id,
                name,
                description,
                code,
                _code_hash(code),
                _get_framework_version(),
                params_schema,
                tags or [],
            ),
        )
    conn.commit()
    return strategy_id


def save_job(
    conn,
    strategy_id: str,
    snapshot_id: str,
    params: dict,
    benchmark: str = "SPY",
    initial_capital: float = 100_000.0,
) -> str:
    """Insert a job record and return job UUID."""
    job_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO backtest.jobs
                (id, strategy_id, params, status, data_snapshot_id,
                 benchmark, initial_capital, started_at, finished_at)
            VALUES (%s, %s, %s, 'succeeded', %s, %s, %s, NOW(), NOW())
            """,
            (
                job_id,
                strategy_id,
                params,
                snapshot_id,
                benchmark,
                initial_capital,
            ),
        )
    conn.commit()
    return job_id


def save_run(
    conn,
    job_id: str,
    metrics: dict,
    symbol: str | None = None,
    n_trades: int | None = None,
) -> str:
    """Insert a run record and return run UUID."""
    run_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO backtest.runs (id, job_id, symbol, metrics, n_trades)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (run_id, job_id, symbol, metrics, n_trades),
        )
    conn.commit()
    return run_id


def save_result(
    result: "BacktestResult | StrategyResult",
    strategy_name: str,
    strategy_code: str,
    snapshot_id: str,
    params: dict[str, Any] | None = None,
    description: str = "",
    tags: list[str] | None = None,
    benchmark: str = "SPY",
    initial_capital: float = 100_000.0,
) -> str:
    """Save a complete backtest result to Postgres. Returns job_id.

    Works with both BacktestResult (vectorbt) and StrategyResult (event-driven).
    """
    from ginlix_backtest.engine.portfolio import BacktestResult

    if isinstance(result, BacktestResult):
        metrics = result.metrics
        bm_metrics = result.benchmark_metrics
        symbol = result.symbol
        n_trades = metrics.get("n_trades")
        combined_metrics = {**metrics, **bm_metrics}
    else:
        metrics = result.to_metrics()
        symbol = None
        n_trades = result.n_trades
        combined_metrics = metrics

    conn = _get_conn()
    try:
        strategy_id = save_strategy(
            conn,
            name=strategy_name,
            code=strategy_code,
            description=description,
            tags=tags,
        )
        job_id = save_job(
            conn,
            strategy_id=strategy_id,
            snapshot_id=snapshot_id,
            params=params or {},
            benchmark=benchmark,
            initial_capital=initial_capital,
        )
        save_run(
            conn,
            job_id=job_id,
            metrics=combined_metrics,
            symbol=symbol,
            n_trades=n_trades,
        )
    finally:
        conn.close()

    return job_id


def load_run(job_id: str) -> dict[str, Any]:
    """Load a saved run's metrics by job_id."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.symbol, r.metrics, r.n_trades, j.params, j.created_at
                FROM backtest.runs r
                JOIN backtest.jobs j ON r.job_id = j.id
                WHERE j.id = %s
                """,
                (job_id,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return [
        {"symbol": row[0], "metrics": row[1], "n_trades": row[2], "params": row[3], "created_at": row[4]}
        for row in rows
    ]


def list_jobs(limit: int = 20) -> list[dict[str, Any]]:
    """List recent backtest jobs."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT j.id, s.name, j.params, j.status, j.created_at,
                       r.metrics->>'sharpe' AS sharpe,
                       r.metrics->>'cagr' AS cagr,
                       r.metrics->>'max_dd' AS max_dd
                FROM backtest.jobs j
                LEFT JOIN backtest.strategies s ON j.strategy_id = s.id
                LEFT JOIN backtest.runs r ON r.job_id = j.id AND r.symbol IS NULL
                ORDER BY j.created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            cols = [d.name for d in cur.description]
            rows = cur.fetchall()
    finally:
        conn.close()

    return [dict(zip(cols, row)) for row in rows]
