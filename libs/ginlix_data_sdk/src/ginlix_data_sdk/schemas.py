from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class OHLCVBar(BaseModel):
    """Single daily OHLCV bar. Timestamps stored as UTC datetime."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    adj_close: float = Field(description="Split + dividend adjusted close")
    split_adj_close: float = Field(description="Split-adjusted only (dividend-unadjusted)")


class CorporateAction(BaseModel):
    """A single corporate action event for a symbol."""

    ex_date: date
    event_type: Literal["split", "dividend", "spinoff", "merger", "delisting"]
    ratio: float | None = None    # split ratio (e.g. 2.0 for 2-for-1)
    amount: float | None = None   # cash dividend amount per share
    currency: str = "USD"
    notes: str | None = None
