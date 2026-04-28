#!/usr/bin/env python
"""Backfill US daily OHLCV data into a Parquet snapshot.

Creates:
    data/snapshots/{snapshot_id}/daily/{symbol}.parquet
    data/snapshots/{snapshot_id}/corporate_actions/{symbol}.parquet
    data/snapshots/{snapshot_id}/benchmarks/{symbol}.parquet
    data/snapshots/{snapshot_id}/MANIFEST.json

Then registers the snapshot in Postgres (backtest.data_snapshots).

Usage:
    uv run python scripts/backfill_us_daily.py \\
        --symbols AAPL MSFT NVDA GOOGL AMZN META TSLA BRK-B JPM UNH \\
        --start 2015-01-01 --end 2026-04-23

    # Dry-run (skip DB registration):
    uv run python scripts/backfill_us_daily.py --symbols AAPL --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# Repo root on sys.path so we can import src/
sys.path.insert(0, str(Path(__file__).parents[1]))

import pandas as pd

from ginlix_data_sdk import parquet_store as store
from ginlix_data_sdk.calendar import filter_to_trading_days
from ginlix_data_sdk.providers import YFinanceCorporateActionProvider, YFinancePriceProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

BENCHMARKS = ["SPY", "QQQ", "IWM"]

price_provider = YFinancePriceProvider()
action_provider = YFinanceCorporateActionProvider()


def _actions_to_df(actions) -> pd.DataFrame:
    if not actions:
        return pd.DataFrame(
            columns=["ex_date", "event_type", "ratio", "amount", "currency", "notes"]
        )
    rows = [
        {
            "ex_date": a.ex_date,
            "event_type": a.event_type,
            "ratio": a.ratio,
            "amount": a.amount,
            "currency": a.currency,
            "notes": a.notes,
        }
        for a in actions
    ]
    df = pd.DataFrame(rows)
    df["ex_date"] = pd.to_datetime(df["ex_date"])
    return df.set_index("ex_date").sort_index()


def backfill_symbol(
    symbol: str,
    start: str,
    end: str,
    snapshot_id: str,
    is_benchmark: bool = False,
) -> bool:
    """Fetch and persist one symbol. Returns True on success."""
    try:
        log.info("fetching %s (benchmark=%s)", symbol, is_benchmark)
        df = price_provider.get_daily(symbol, start, end)
        if df.empty:
            log.warning("no data for %s — skipping", symbol)
            return False

        df = filter_to_trading_days(df)

        if is_benchmark:
            store.write_benchmark(symbol, df, snapshot_id)
        else:
            store.write_daily(symbol, df, snapshot_id)
            actions = action_provider.get_actions(symbol, start, end)
            actions_df = _actions_to_df(actions)
            store.write_corporate_actions(symbol, actions_df, snapshot_id)

        log.info("  saved %d bars for %s", len(df), symbol)
        return True
    except Exception as exc:
        log.error("failed to backfill %s: %s", symbol, exc)
        return False


async def register_snapshot_in_db(
    snapshot_id: str,
    start: str,
    end: str,
    symbols: list[str],
    storage_root: str,
) -> None:
    """Insert a row into backtest.data_snapshots."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
        import psycopg

        dsn = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
        if not dsn:
            log.warning("DATABASE_URL not set — skipping Postgres registration")
            return

        async with await psycopg.AsyncConnection.connect(dsn) as conn:
            await conn.execute(
                """
                INSERT INTO backtest.data_snapshots
                    (id, market, frequency, storage_root, start_date, end_date, n_symbols, description)
                VALUES (%s, 'us', '1d', %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    storage_root = EXCLUDED.storage_root,
                    end_date     = EXCLUDED.end_date,
                    n_symbols    = EXCLUDED.n_symbols
                """,
                (
                    snapshot_id,
                    storage_root,
                    start,
                    end,
                    len(symbols),
                    f"US daily snapshot backfilled {datetime.now(timezone.utc).isoformat()}",
                ),
            )
        log.info("registered snapshot %s in Postgres", snapshot_id)
    except Exception as exc:
        log.error("DB registration failed (non-fatal): %s", exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill US daily OHLCV Parquet snapshot")
    parser.add_argument("--symbols", nargs="+", required=True, help="Ticker symbols to backfill")
    parser.add_argument("--start", default="2010-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=date.today().isoformat(), help="End date YYYY-MM-DD")
    parser.add_argument("--snapshot-id", default=None, help="Override snapshot ID (default: us-{end})")
    parser.add_argument("--no-benchmarks", action="store_true", help="Skip SPY/QQQ/IWM benchmarks")
    parser.add_argument("--dry-run", action="store_true", help="Skip Postgres registration")
    args = parser.parse_args()

    snapshot_id = args.snapshot_id or f"us-{args.end}"
    storage_root = str(store.snapshot_path(snapshot_id).resolve())

    log.info("snapshot: %s  [%s → %s]", snapshot_id, args.start, args.end)
    log.info("symbols: %s", args.symbols)

    succeeded = []
    failed = []
    for sym in args.symbols:
        ok = backfill_symbol(sym, args.start, args.end, snapshot_id)
        (succeeded if ok else failed).append(sym)

    if not args.no_benchmarks:
        for bm in BENCHMARKS:
            ok = backfill_symbol(bm, args.start, args.end, snapshot_id, is_benchmark=True)
            if not ok:
                log.warning("benchmark %s failed", bm)

    store.write_manifest(
        snapshot_id=snapshot_id,
        symbols=succeeded,
        start_date=args.start,
        end_date=args.end,
        description=f"Backfilled via yfinance on {date.today()}",
    )
    log.info("manifest written to %s/MANIFEST.json", storage_root)

    if failed:
        log.warning("failed symbols (%d): %s", len(failed), failed)

    if not args.dry_run:
        # Windows ProactorEventLoop is incompatible with psycopg async
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(
            register_snapshot_in_db(snapshot_id, args.start, args.end, succeeded, storage_root)
        )

    log.info(
        "done — %d/%d symbols succeeded. Run: from ginlix_data_sdk import parquet_store as store; "
        "store.load_prices(%r, %r)",
        len(succeeded),
        len(args.symbols),
        succeeded[:3],
        snapshot_id,
    )


if __name__ == "__main__":
    main()
