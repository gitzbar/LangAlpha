"""Snapshot-based Parquet store for OHLCV and corporate action data.

Layout:
    data/snapshots/{snapshot_id}/
        daily/{symbol}.parquet
        corporate_actions/{symbol}.parquet
        benchmarks/{symbol}.parquet
        MANIFEST.json
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# DATA_ROOT env var overrides default (used in Docker to mount host data dir)
# Default: repo_root/data/snapshots  (works for local dev)
_REPO_ROOT = Path(__file__).parents[5]  # libs/ginlix_data_sdk/src/ginlix_data_sdk -> repo root
_DATA_ROOT = (
    Path(os.environ["DATA_ROOT"]) / "snapshots"
    if "DATA_ROOT" in os.environ
    else _REPO_ROOT / "data" / "snapshots"
)


def snapshot_path(snapshot_id: str) -> Path:
    return _DATA_ROOT / snapshot_id


def write_daily(symbol: str, df: pd.DataFrame, snapshot_id: str) -> Path:
    """Persist a daily OHLCV DataFrame as Parquet. Returns the file path."""
    dest = snapshot_path(snapshot_id) / "daily"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{symbol}.parquet"
    df.to_parquet(path, compression="snappy", index=True)
    return path


def write_corporate_actions(symbol: str, df: pd.DataFrame, snapshot_id: str) -> Path:
    dest = snapshot_path(snapshot_id) / "corporate_actions"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{symbol}.parquet"
    df.to_parquet(path, compression="snappy", index=True)
    return path


def write_benchmark(symbol: str, df: pd.DataFrame, snapshot_id: str) -> Path:
    dest = snapshot_path(snapshot_id) / "benchmarks"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{symbol}.parquet"
    df.to_parquet(path, compression="snappy", index=True)
    return path


def read_daily(symbol: str, snapshot_id: str) -> pd.DataFrame:
    path = snapshot_path(snapshot_id) / "daily" / f"{symbol}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"No data for {symbol} in snapshot {snapshot_id}")
    return pd.read_parquet(path)


def read_corporate_actions(symbol: str, snapshot_id: str) -> pd.DataFrame:
    path = snapshot_path(snapshot_id) / "corporate_actions" / f"{symbol}.parquet"
    if not path.exists():
        return pd.DataFrame(columns=["ex_date", "event_type", "ratio", "amount", "currency", "notes"])
    return pd.read_parquet(path)


def read_benchmark(symbol: str, snapshot_id: str) -> pd.DataFrame:
    path = snapshot_path(snapshot_id) / "benchmarks" / f"{symbol}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"No benchmark data for {symbol} in snapshot {snapshot_id}")
    return pd.read_parquet(path)


def load_prices(
    symbols: list[str],
    snapshot_id: str,
    column: str = "split_adj_close",
) -> pd.DataFrame:
    """Load a single price column for multiple symbols into a wide DataFrame.

    Returns a DataFrame with symbols as columns and DatetimeIndex as rows.
    Missing symbols raise FileNotFoundError.
    """
    series = {}
    for sym in symbols:
        df = read_daily(sym, snapshot_id)
        series[sym] = df[column]
    return pd.DataFrame(series)


def write_manifest(
    snapshot_id: str,
    symbols: list[str],
    start_date: str,
    end_date: str,
    description: str = "",
) -> Path:
    manifest = {
        "snapshot_id": snapshot_id,
        "market": "us",
        "frequency": "1d",
        "start_date": start_date,
        "end_date": end_date,
        "n_symbols": len(symbols),
        "symbols": sorted(symbols),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "description": description,
    }
    path = snapshot_path(snapshot_id) / "MANIFEST.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2))
    return path


def read_manifest(snapshot_id: str) -> dict:
    path = snapshot_path(snapshot_id) / "MANIFEST.json"
    return json.loads(path.read_text())


def list_snapshots() -> list[str]:
    if not _DATA_ROOT.exists():
        return []
    return sorted(p.name for p in _DATA_ROOT.iterdir() if p.is_dir())
