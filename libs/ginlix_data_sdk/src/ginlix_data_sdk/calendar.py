from __future__ import annotations

from datetime import date

import exchange_calendars as xcals
import pandas as pd

_nyse = xcals.get_calendar("XNYS")


def get_trading_days(start: date | str, end: date | str) -> pd.DatetimeIndex:
    """Return NYSE trading days between start and end (inclusive)."""
    sessions = _nyse.sessions_in_range(str(start), str(end))
    return sessions


def is_trading_day(d: date | str) -> bool:
    return _nyse.is_session(str(d))


def next_trading_day(d: date | str) -> pd.Timestamp:
    """Return the next NYSE session on or after d."""
    ts = pd.Timestamp(str(d))
    if _nyse.is_session(ts):
        return ts
    return _nyse.date_to_session(ts, direction="next")


def filter_to_trading_days(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only rows whose index falls on a NYSE trading day."""
    trading = _nyse.sessions_in_range(
        df.index.min().strftime("%Y-%m-%d"),
        df.index.max().strftime("%Y-%m-%d"),
    )
    # trading is tz-naive; normalize df.index to date strings for comparison
    trading_dates = set(trading.strftime("%Y-%m-%d"))
    index_dates = df.index.normalize().strftime("%Y-%m-%d")
    return df[pd.Index(index_dates).isin(trading_dates)]
