"""ginlix_backtest — reliability-first backtesting framework.

Quick start (Phase 1):
    from ginlix_backtest import indicators as ind
    from ginlix_backtest.engine import portfolio
    from ginlix_backtest.data_feed import DataFeed
    from ginlix_data_sdk import parquet_store as store

    close = store.load_prices(["AAPL"], snapshot_id="us-2026-04-23")["AAPL"]
    fast = ind.sma(close, 50)
    slow = ind.sma(close, 200)
    entries = (fast > slow) & (fast.shift(1) <= slow.shift(1))
    exits   = (fast < slow) & (fast.shift(1) >= slow.shift(1))
    result  = portfolio.from_signals(close, entries, exits)
    print(result)
"""
from . import calendar, data_feed, engine, fees, indicators, io
from .fees import US_DEFAULT, ZERO_COST, CostModel, FeeModel, SlippageModel
from .strategy import Strategy, StrategyResult

__all__ = [
    "calendar",
    "data_feed",
    "engine",
    "fees",
    "indicators",
    "io",
    "FeeModel",
    "SlippageModel",
    "CostModel",
    "US_DEFAULT",
    "ZERO_COST",
    "Strategy",
    "StrategyResult",
]
