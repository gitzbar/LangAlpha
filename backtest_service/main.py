"""Backtest Service — FastAPI :8001

Endpoints:
    GET  /health                  Health check + available snapshots
    GET  /snapshots               List data snapshots on disk
    POST /backtest/run            Run a backtest synchronously
    GET  /backtest/strategies     List supported strategy types + params

Run locally:
    uv run uvicorn backtest_service.main:app --port 8001 --reload
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from ginlix_data_sdk import parquet_store as store

from .runner import run_backtest
from .schemas import (
    HealthOut, RunRequest, RunResponse, SnapshotOut, StrategyType,
)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Ginlix Backtest Service",
    version="0.1.0",
    description="REST API for running quantitative backtests over local Parquet snapshots.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _list_snapshots() -> list[str]:
    return store.list_snapshots()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthOut, tags=["Meta"])
def health() -> HealthOut:
    """Service health check. Returns available snapshot IDs."""
    return HealthOut(status="ok", snapshot_ids=_list_snapshots())


@app.get("/snapshots", response_model=list[SnapshotOut], tags=["Meta"])
def list_snapshots() -> list[SnapshotOut]:
    """List all available Parquet data snapshots."""
    out = []
    for sid in _list_snapshots():
        manifest = store.read_manifest(sid)
        if manifest:
            out.append(SnapshotOut(
                id=sid,
                start_date=manifest.get("start_date", ""),
                end_date=manifest.get("end_date", ""),
                n_symbols=manifest.get("n_symbols", 0),
                storage_root=str(store.snapshot_path(sid)),
            ))
    return out


@app.get("/backtest/strategies", tags=["Backtest"])
def list_strategies() -> dict:
    """List supported strategy types and their parameter schemas."""
    return {
        "strategies": {
            StrategyType.weekday: {
                "description": "Buy on a specific weekday, sell on another",
                "params": {"buy_day": "monday", "sell_day": "friday"},
            },
            StrategyType.monthly: {
                "description": "Buy at start of buy_month, sell at start of sell_month (Sell in May)",
                "params": {"buy_month": "november", "sell_month": "april"},
            },
            StrategyType.streak: {
                "description": "Buy after N consecutive red/green candles, hold for M days",
                "params": {"n_red": 3, "hold_days": 3, "direction": "red"},
            },
            StrategyType.ema_cross: {
                "description": "EMA golden/dead cross signal",
                "params": {"fast": 20, "slow": 60},
            },
            StrategyType.sma_cross: {
                "description": "SMA golden/dead cross signal",
                "params": {"fast": 50, "slow": 200},
            },
            StrategyType.turn_of_month: {
                "description": "Buy N days before month-end, sell N days after month-start",
                "params": {"days_before_eom": 1, "days_after_som": 3},
            },
        }
    }


@app.post("/backtest/run", response_model=RunResponse, tags=["Backtest"])
def run(req: RunRequest) -> RunResponse:
    """Run a backtest synchronously and return results.

    Strategy types: weekday | monthly | streak | ema_cross | sma_cross | turn_of_month
    """
    try:
        return run_backtest(req)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e}")
