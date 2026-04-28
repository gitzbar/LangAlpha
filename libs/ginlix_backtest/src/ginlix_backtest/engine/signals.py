"""Calendar-effect and pattern signal builders.

All functions return boolean entry/exit Series aligned to the price index.
Signals are NOT pre-shifted — portfolio.from_signals() applies next-bar shift.
"""
from __future__ import annotations

import pandas as pd

# Day-of-week map (Monday=0 … Friday=4)
_DOW = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4,
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4}

# Month map
_MON = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        "january": 1, "february": 2, "march": 3, "april": 4,
        "june": 6, "july": 7, "august": 8, "september": 9,
        "october": 10, "november": 11, "december": 12,
        **{str(i): i for i in range(1, 13)}}


def _dow(name: str | int) -> int:
    if isinstance(name, int):
        return name
    return _DOW[name.lower()]


def _month(name: str | int) -> int:
    if isinstance(name, int):
        return name
    return _MON[name.lower()]


def weekday_pattern(
    prices: pd.Series | pd.DataFrame,
    buy_day: str | int = "monday",
    sell_day: str | int = "friday",
) -> tuple[pd.Series, pd.Series]:
    """Generate entry/exit signals for a day-of-week pattern.

    Returns (entries, exits) boolean Series.

    Example — "buy Monday open, sell Friday close":
        entries, exits = weekday_pattern(close, buy_day="monday", sell_day="friday")
        result = portfolio.from_signals(close, entries, exits)
    """
    idx = prices.index if isinstance(prices, pd.Series) else prices.index
    buy_dow = _dow(buy_day)
    sell_dow = _dow(sell_day)

    entries = pd.Series(idx.dayofweek == buy_dow, index=idx)
    exits   = pd.Series(idx.dayofweek == sell_dow, index=idx)
    return entries, exits


def monthly_pattern(
    prices: pd.Series | pd.DataFrame,
    buy_month: str | int = "november",
    sell_month: str | int = "april",
) -> tuple[pd.Series, pd.Series]:
    """Generate entry/exit signals for a month-of-year pattern.

    Default: "Sell in May" — buy November, sell April.
    Returns (entries, exits) firing on the first trading day of each month.
    """
    idx = prices.index if isinstance(prices, pd.Series) else prices.index
    buy_m  = _month(buy_month)
    sell_m = _month(sell_month)

    # Fire on first trading day of the target month
    month_starts = idx.to_series().groupby(idx.to_period("M")).first()

    entries = pd.Series(False, index=idx)
    exits   = pd.Series(False, index=idx)

    for ts in month_starts:
        if ts.month == buy_m:
            entries.loc[ts] = True
        elif ts.month == sell_m:
            exits.loc[ts] = True

    return entries, exits


def turn_of_month(
    prices: pd.Series | pd.DataFrame,
    days_before_eom: int = 1,
    days_after_som: int = 3,
) -> tuple[pd.Series, pd.Series]:
    """Turn-of-month effect: buy N days before month-end, sell N days after month-start.

    Based on research showing excess returns in the first/last few days of each month.
    """
    idx = prices.index if isinstance(prices, pd.Series) else prices.index
    # Use year-month string as groupby key to avoid Period tz-aware issues
    s = idx.to_series().reset_index(drop=True)
    ym_keys = idx.strftime("%Y-%m")

    eom_set: set = set()
    som_set: set = set()
    for ym in pd.unique(ym_keys):
        mask = ym_keys == ym
        group = idx[mask]
        if len(group) >= days_before_eom:
            eom_set.add(group[-days_before_eom])
        if len(group) >= days_after_som:
            som_set.add(group[days_after_som - 1])

    entries = pd.Series(idx.isin(eom_set), index=idx)
    exits   = pd.Series(idx.isin(som_set), index=idx)
    return entries, exits


def cross_signal(
    fast: pd.Series,
    slow: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    """Generic crossover signal: entry when fast crosses above slow, exit when below.

    Works for any two series (SMA, EMA, price vs MA, etc.).
    """
    entries = (fast > slow) & (fast.shift(1) <= slow.shift(1))
    exits   = (fast < slow) & (fast.shift(1) >= slow.shift(1))
    return entries.fillna(False), exits.fillna(False)


def streak_signal(
    prices: pd.Series,
    n_red: int = 3,
    hold_days: int = 1,
    direction: str = "red",
) -> tuple[pd.Series, pd.Series]:
    """Buy after N consecutive red (or green) candles.

    Args:
        prices:    Close price series.
        n_red:     Number of consecutive candles required before entry.
        hold_days: How many bars to hold after entry.
        direction: 'red'  -> enter after N consecutive down closes
                   'green'-> enter after N consecutive up closes

    Returns:
        (entries, exits) boolean Series.

    Example - "buy after 3 consecutive red candles, sell 1 day later":
        entries, exits = streak_signal(close, n_red=3, hold_days=1)
        result = portfolio.from_signals(close, entries, exits)
    """
    import numpy as np

    ret = prices.pct_change()
    if direction == "red":
        is_candle = (ret < 0).astype(int)
    else:
        is_candle = (ret > 0).astype(int)

    # Count consecutive candles using a rolling window
    # rolling(n).sum() == n means all n bars are in the required direction
    streak = is_candle.rolling(n_red).sum()
    entries = (streak == n_red)

    # Exit after hold_days bars
    exits = entries.shift(hold_days).fillna(False).astype(bool)

    return entries.fillna(False).astype(bool), exits


def candle_streak(prices: pd.Series) -> pd.Series:
    """Return a Series of consecutive candle streak counts.

    Positive = consecutive green candles, Negative = consecutive red candles.
    Useful for analysis before building a strategy.

    Example:
        streak = candle_streak(close)
        streak.describe()  # distribution of streak lengths
    """
    ret = prices.pct_change()
    direction = ret.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))

    streak = pd.Series(0, index=prices.index, dtype=int)
    count = 0
    prev_dir = 0

    for i, d in enumerate(direction):
        if d == 0:
            count = 0
        elif d == prev_dir:
            count += d  # +1 or -1 each step
        else:
            count = d
        streak.iloc[i] = count
        prev_dir = d if d != 0 else prev_dir

    return streak
