"""NYSE calendar utilities and execution timing helpers.

All barsets produced by ginlix_backtest use NYSE trading days only.
Signal-to-fill timing: signals generated on bar T are filled at bar T+1 open
(next-bar open), enforced by the framework — not by user code.
"""
from __future__ import annotations

from datetime import date
from typing import Literal

import exchange_calendars as xcals
import pandas as pd

_nyse = xcals.get_calendar("XNYS")

OnHolidayPolicy = Literal["next", "discard"]


def trading_sessions(start: date | str, end: date | str) -> pd.DatetimeIndex:
    """NYSE sessions between start and end (both inclusive)."""
    return _nyse.sessions_in_range(str(start), str(end))


def is_session(d: date | str) -> bool:
    return _nyse.is_session(str(d))


def resolve_signal_date(
    signal_date: date | str,
    policy: OnHolidayPolicy = "next",
) -> pd.Timestamp | None:
    """Map a signal date to the execution session.

    - If signal_date is a trading day, returns it unchanged.
    - If it is a holiday/weekend:
        - 'next'   → next open session (order carried forward)
        - 'discard' → None (order cancelled)
    """
    ts = pd.Timestamp(str(signal_date))
    if _nyse.is_session(ts):
        return ts
    if policy == "discard":
        return None
    return _nyse.date_to_session(ts, direction="next")


def apply_next_bar_shift(signals: pd.Series) -> pd.Series:
    """Shift a boolean/float signal series by 1 bar (next-bar fill convention).

    This is the core look-ahead prevention step for vectorized strategies.
    The framework calls this automatically before passing signals to the
    portfolio engine so user code never needs to remember to shift.
    """
    return signals.shift(1)


def filter_to_trading_days(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows not on a NYSE session. Index must be DatetimeIndex."""
    start = df.index.min().strftime("%Y-%m-%d")
    end = df.index.max().strftime("%Y-%m-%d")
    sessions = _nyse.sessions_in_range(start, end)
    # Compare as date strings to avoid tz-aware vs tz-naive mismatch
    trading_dates = set(sessions.strftime("%Y-%m-%d"))
    index_dates = df.index.normalize().strftime("%Y-%m-%d")
    return df[pd.Index(index_dates).isin(trading_dates)]
