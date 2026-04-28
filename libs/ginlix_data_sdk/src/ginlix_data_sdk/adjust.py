from __future__ import annotations

from datetime import date

import pandas as pd

from .schemas import CorporateAction


def _as_date(d: date | pd.Timestamp | str) -> date:
    # pd.Timestamp is a subclass of datetime (which is a subclass of date),
    # so we must check for it first before the plain `date` branch.
    if isinstance(d, pd.Timestamp):
        if d is pd.NaT:
            raise ValueError("Cannot convert NaT to date")
        return d.date()
    if isinstance(d, date):
        return d
    return pd.Timestamp(d).date()


def apply_split_adjustment(
    prices: pd.DataFrame,
    actions: list[CorporateAction],
) -> pd.Series:
    """Return split-adjusted close series (dividend-unadjusted).

    Multiplies historical prices by the cumulative split ratio so that
    today's price is the reference point. Dividends are NOT folded in —
    use the raw close + dividend timeline for total-return accounting.
    """
    close = prices["close"].copy()
    for action in sorted(actions, key=lambda a: a.ex_date, reverse=True):
        if action.event_type == "split" and action.ratio and action.ratio != 1.0:
            mask = prices.index.date < action.ex_date
            close.loc[mask] = close.loc[mask] / action.ratio
    return close


def build_dividend_timeline(
    actions: list[CorporateAction],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.Series:
    """Return a Series of per-share cash dividends indexed by ex_date.

    Use this alongside split-adjusted prices for total-return accounting:
    on each ex_date, credit (shares_held × amount) to the cash account.
    """
    rows = [
        (pd.Timestamp(a.ex_date), a.amount)
        for a in actions
        if a.event_type == "dividend"
        and a.amount is not None
        and _as_date(start) <= a.ex_date <= _as_date(end)
    ]
    if not rows:
        return pd.Series(dtype=float)
    idx, vals = zip(*rows)
    return pd.Series(vals, index=pd.DatetimeIndex(idx), dtype=float).sort_index()
