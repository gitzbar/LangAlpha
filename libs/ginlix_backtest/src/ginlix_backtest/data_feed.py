"""DataFeed — the framework's view of price data for a backtest run.

Wraps a snapshot from ginlix_data_sdk and exposes:
- split-adjusted close (for signal calculation)
- unadjusted OHLCV (for realistic fill prices)
- dividend timeline (for total-return accounting)

Look-ahead prevention: DataFeed.as_of(ts) returns a slice up to and
including ts. Any access beyond the current bar is blocked by construction
in the vectorized path (shift-1 applied by calendar.apply_next_bar_shift).
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from ginlix_data_sdk import parquet_store as store
from ginlix_data_sdk.adjust import build_dividend_timeline
from ginlix_data_sdk.schemas import CorporateAction

from .calendar import filter_to_trading_days


class DataFeed:
    """Encapsulates all price/action data for one backtest run.

    Attributes:
        close:       split-adjusted close (dividend-unadjusted) — use for signals
        adj_close:   fully adjusted close (total-return) — use for perf comparison
        open/high/low/volume: unadjusted OHLCV — use for realistic fill prices
        dividends:   per-share cash dividends keyed by ex_date
    """

    def __init__(
        self,
        symbol: str,
        snapshot_id: str,
        actions: list[CorporateAction] | None = None,
    ) -> None:
        df = store.read_daily(symbol, snapshot_id)
        df = filter_to_trading_days(df)
        if df.empty:
            raise ValueError(
                f"DataFeed: no trading-day rows found for {symbol!r} in snapshot {snapshot_id!r}. "
                "Check that the snapshot was created with filter_to_trading_days."
            )

        self.symbol = symbol
        self.open: pd.Series = df["open"]
        self.high: pd.Series = df["high"]
        self.low: pd.Series = df["low"]
        self.close: pd.Series = df["split_adj_close"]
        self.adj_close: pd.Series = df["adj_close"]
        self.volume: pd.Series = df["volume"]

        start = df.index.min()
        end = df.index.max()
        self.dividends: pd.Series = (
            build_dividend_timeline(actions, start, end) if actions else pd.Series(dtype=float)
        )

    def as_of(self, ts: pd.Timestamp) -> "DataFeed":
        """Return a view of this DataFeed up to and including ts.

        Used in event-driven strategies to enforce look-ahead prevention.
        """
        view = object.__new__(DataFeed)
        view.symbol = self.symbol
        view.open = self.open.loc[:ts]
        view.high = self.high.loc[:ts]
        view.low = self.low.loc[:ts]
        view.close = self.close.loc[:ts]
        view.adj_close = self.adj_close.loc[:ts]
        view.volume = self.volume.loc[:ts]
        view.dividends = self.dividends.loc[:ts] if not self.dividends.empty else self.dividends
        return view

    @classmethod
    def from_snapshot(
        cls,
        symbols: list[str],
        snapshot_id: str,
    ) -> dict[str, "DataFeed"]:
        """Load DataFeeds for multiple symbols from a snapshot."""
        return {sym: cls(sym, snapshot_id) for sym in symbols}

    def __repr__(self) -> str:
        return (
            f"DataFeed({self.symbol!r}, "
            f"{self.close.index[0].date()} to {self.close.index[-1].date()}, "
            f"{len(self.close)} bars)"
        )
