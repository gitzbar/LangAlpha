"""Pydantic request/response schemas for the backtest service."""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Strategy definitions
# ---------------------------------------------------------------------------

class StrategyType(str, Enum):
    weekday    = "weekday"       # buy Mon / sell Fri
    monthly    = "monthly"       # sell-in-May style
    streak     = "streak"        # N consecutive red/green candles
    ema_cross  = "ema_cross"     # EMA golden/dead cross
    sma_cross  = "sma_cross"     # SMA golden/dead cross
    turn_of_month = "turn_of_month"


class WeekdayParams(BaseModel):
    buy_day:  str = "monday"
    sell_day: str = "friday"


class MonthlyParams(BaseModel):
    buy_month:  str = "november"
    sell_month: str = "april"


class StreakParams(BaseModel):
    n_red:     int = Field(3, ge=1, le=20)
    hold_days: int = Field(3, ge=1, le=60)
    direction: Literal["red", "green"] = "red"


class EmaCrossParams(BaseModel):
    fast: int = Field(20,  ge=2,  le=500)
    slow: int = Field(60,  ge=5,  le=500)


class SmaCrossParams(BaseModel):
    fast: int = Field(50,  ge=2,  le=500)
    slow: int = Field(200, ge=5,  le=500)


class TurnOfMonthParams(BaseModel):
    days_before_eom: int = Field(1, ge=1, le=10)
    days_after_som:  int = Field(3, ge=1, le=10)


# ---------------------------------------------------------------------------
# Main run request
# ---------------------------------------------------------------------------

class RunRequest(BaseModel):
    symbol:      str             = Field(..., description="e.g. AAPL")
    snapshot_id: str             = Field("us-2026-04-24", description="Data snapshot to use")
    strategy:    StrategyType
    params:      dict[str, Any]  = Field(default_factory=dict, description="Strategy params")
    start:       str | None      = Field(None, description="Slice start date YYYY-MM-DD")
    end:         str | None      = Field(None, description="Slice end date YYYY-MM-DD")
    benchmark:   str             = Field("SPY", description="Benchmark symbol")
    initial_capital: float       = Field(100_000.0, ge=1_000)

    model_config = {"json_schema_extra": {"examples": [
        {
            "symbol": "AAPL",
            "snapshot_id": "us-2026-04-24",
            "strategy": "streak",
            "params": {"n_red": 3, "hold_days": 3, "direction": "red"},
            "benchmark": "SPY",
        }
    ]}}


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class MetricsOut(BaseModel):
    total_return: float
    cagr:         float
    sharpe:       float
    sortino:      float
    max_dd:       float
    n_trades:     int
    win_rate:     float | None
    calmar:       float


class BenchmarkMetricsOut(BaseModel):
    benchmark_total_return: float
    excess_return:          float
    information_ratio:      float
    beta:                   float
    correlation:            float


class RunResponse(BaseModel):
    symbol:           str
    strategy:         str
    params:           dict[str, Any]
    snapshot_id:      str
    start:            str
    end:              str
    n_bars:           int
    metrics:          MetricsOut
    benchmark_metrics: BenchmarkMetricsOut | None


class SnapshotOut(BaseModel):
    id:           str
    start_date:   str
    end_date:     str
    n_symbols:    int
    storage_root: str


class HealthOut(BaseModel):
    status: Literal["ok"]
    snapshot_ids: list[str]
