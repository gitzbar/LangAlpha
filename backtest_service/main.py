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
from . import journal as _journal
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Journal schemas
# ---------------------------------------------------------------------------

class TradeIn(BaseModel):
    action: str          # "buy" | "sell"
    symbol: str
    quantity: float
    price: float
    currency: str = "USD"
    date: str | None = None
    broker: str = ""
    fees: float = 0.0
    amount_krw: float | None = None
    rate: float | None = None
    notes: str = ""

class ForexIn(BaseModel):
    from_currency: str
    to_currency: str
    from_amount: float
    rate: float
    date: str | None = None
    broker: str = ""
    fees: float = 0.0
    notes: str = ""

class DividendIn(BaseModel):
    symbol: str
    amount: float
    currency: str = "USD"
    date: str | None = None
    amount_krw: float | None = None
    tax_withheld: float = 0.0
    notes: str = ""

class NoteIn(BaseModel):
    content: str
    date: str | None = None
    tags: list[str] | None = None

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


# ---------------------------------------------------------------------------
# Journal routes
# ---------------------------------------------------------------------------

@app.get("/journal/entries", tags=["Journal"])
def journal_entries(limit: int = 50) -> dict:
    """Return recent journal entries as markdown."""
    return {"markdown": _journal.show_journal(limit)}


@app.get("/journal/summary", tags=["Journal"])
def journal_summary() -> dict:
    """Return portfolio summary from journal (positions, forex, dividends)."""
    return {"markdown": _journal.journal_summary()}


@app.get("/journal/csv", tags=["Journal"])
def journal_csv() -> list[dict]:
    """Return all journal entries as structured list (from CSV)."""
    import csv
    path = _journal._CSV_FILE
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            rows.append(dict(row))
    return rows


@app.post("/journal/trade", tags=["Journal"])
def log_trade(body: TradeIn) -> dict:
    msg = _journal.log_trade(
        action=body.action, symbol=body.symbol,
        quantity=body.quantity, price=body.price,
        currency=body.currency, date=body.date,
        broker=body.broker, fees=body.fees,
        amount_krw=body.amount_krw, rate=body.rate,
        notes=body.notes,
    )
    return {"ok": True, "message": msg}


@app.post("/journal/forex", tags=["Journal"])
def log_forex(body: ForexIn) -> dict:
    msg = _journal.log_forex(
        from_currency=body.from_currency, to_currency=body.to_currency,
        from_amount=body.from_amount, rate=body.rate,
        date=body.date, broker=body.broker,
        fees=body.fees, notes=body.notes,
    )
    return {"ok": True, "message": msg}


@app.post("/journal/dividend", tags=["Journal"])
def log_dividend(body: DividendIn) -> dict:
    msg = _journal.log_dividend(
        symbol=body.symbol, amount=body.amount,
        currency=body.currency, date=body.date,
        amount_krw=body.amount_krw,
        tax_withheld=body.tax_withheld, notes=body.notes,
    )
    return {"ok": True, "message": msg}


@app.post("/journal/note", tags=["Journal"])
def log_note(body: NoteIn) -> dict:
    msg = _journal.log_note(
        content=body.content, date=body.date, tags=body.tags,
    )
    return {"ok": True, "message": msg}
