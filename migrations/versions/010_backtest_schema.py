"""Create backtest.* schema with all Phase 0 tables.

Revision ID: 010
"""

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE SCHEMA IF NOT EXISTS backtest;

-- Data snapshot metadata (points to Parquet dataset on disk)
CREATE TABLE backtest.data_snapshots (
    id            TEXT PRIMARY KEY,
    market        TEXT NOT NULL,
    frequency     TEXT NOT NULL DEFAULT '1d',
    storage_root  TEXT NOT NULL,
    start_date    DATE NOT NULL,
    end_date      DATE NOT NULL,
    n_symbols     INT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    description   TEXT
);

-- Reusable strategy definitions
CREATE TABLE backtest.strategies (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name              TEXT NOT NULL,
    description       TEXT,
    code              TEXT NOT NULL,
    code_hash         TEXT NOT NULL,
    framework_version TEXT NOT NULL,
    params_schema     JSONB,
    tags              TEXT[],
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived_at       TIMESTAMPTZ
);

-- One backtest execution request
CREATE TABLE backtest.jobs (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id        UUID REFERENCES backtest.strategies(id),
    params             JSONB NOT NULL DEFAULT '{}',
    status             TEXT NOT NULL DEFAULT 'queued'
                           CHECK (status IN ('queued','running','succeeded','failed','canceled')),
    data_snapshot_id   TEXT NOT NULL REFERENCES backtest.data_snapshots(id),
    benchmark          TEXT NOT NULL DEFAULT 'SPY',
    initial_capital    NUMERIC NOT NULL DEFAULT 100000,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at         TIMESTAMPTZ,
    finished_at        TIMESTAMPTZ,
    error              TEXT
);

-- Per-symbol or portfolio-level result summary
CREATE TABLE backtest.runs (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id     UUID NOT NULL REFERENCES backtest.jobs(id) ON DELETE CASCADE,
    symbol     TEXT,
    metrics    JSONB NOT NULL DEFAULT '{}',
    n_trades   INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Individual trade log (audit / debugging)
CREATE TABLE backtest.trades (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id        UUID NOT NULL REFERENCES backtest.runs(id) ON DELETE CASCADE,
    symbol        TEXT NOT NULL,
    side          TEXT NOT NULL
                      CHECK (side IN ('long_open','long_close','short_open','short_close')),
    entry_ts      TIMESTAMPTZ NOT NULL,
    entry_price   NUMERIC,
    exit_ts       TIMESTAMPTZ,
    exit_price    NUMERIC,
    qty           NUMERIC,
    pnl           NUMERIC,
    fees          NUMERIC,
    slippage_cost NUMERIC,
    reason        TEXT
);

-- Large artifacts: equity curves, charts, position history
CREATE TABLE backtest.artifacts (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id       UUID NOT NULL REFERENCES backtest.jobs(id) ON DELETE CASCADE,
    run_id       UUID REFERENCES backtest.runs(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL
                     CHECK (kind IN ('equity_curve','positions','chart_svg','logs','other')),
    storage_uri  TEXT NOT NULL,
    content_type TEXT,
    size_bytes   BIGINT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Useful query patterns
CREATE INDEX backtest_jobs_status_idx ON backtest.jobs(status);
CREATE INDEX backtest_jobs_snapshot_idx ON backtest.jobs(data_snapshot_id);
CREATE INDEX backtest_runs_job_idx ON backtest.runs(job_id);
CREATE INDEX backtest_trades_run_idx ON backtest.trades(run_id);
CREATE INDEX backtest_artifacts_job_idx ON backtest.artifacts(job_id);
""")


def downgrade() -> None:
    op.execute("""
DROP SCHEMA backtest CASCADE;
""")
