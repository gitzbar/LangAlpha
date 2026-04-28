"""Backtest execution logic — translates RunRequest into BacktestResult."""
from __future__ import annotations

import pandas as pd

from ginlix_backtest.data_feed import DataFeed
from ginlix_backtest.engine import portfolio, signals
from ginlix_backtest.engine.portfolio import BacktestResult
from ginlix_backtest import indicators
from ginlix_data_sdk import parquet_store as store

from .schemas import (
    RunRequest, RunResponse, MetricsOut, BenchmarkMetricsOut, EquityPoint,
    StrategyType, WeekdayParams, MonthlyParams, StreakParams,
    EmaCrossParams, SmaCrossParams, TurnOfMonthParams,
)


def _build_entries_exits(
    close: pd.Series,
    strategy: StrategyType,
    params: dict,
) -> tuple[pd.Series, pd.Series]:
    """Dispatch to the correct signal builder."""
    if strategy == StrategyType.weekday:
        p = WeekdayParams(**params)
        return signals.weekday_pattern(close, p.buy_day, p.sell_day)

    if strategy == StrategyType.monthly:
        p = MonthlyParams(**params)
        return signals.monthly_pattern(close, p.buy_month, p.sell_month)

    if strategy == StrategyType.streak:
        p = StreakParams(**params)
        return signals.streak_signal(close, p.n_red, p.hold_days, p.direction)

    if strategy == StrategyType.ema_cross:
        p = EmaCrossParams(**params)
        if p.fast >= p.slow:
            raise ValueError(f"ema_cross: fast ({p.fast}) must be < slow ({p.slow})")
        return signals.cross_signal(
            indicators.ema(close, p.fast),
            indicators.ema(close, p.slow),
        )

    if strategy == StrategyType.sma_cross:
        p = SmaCrossParams(**params)
        if p.fast >= p.slow:
            raise ValueError(f"sma_cross: fast ({p.fast}) must be < slow ({p.slow})")
        return signals.cross_signal(
            indicators.sma(close, p.fast),
            indicators.sma(close, p.slow),
        )

    if strategy == StrategyType.turn_of_month:
        p = TurnOfMonthParams(**params)
        return signals.turn_of_month(close, p.days_before_eom, p.days_after_som)

    raise ValueError(f"Unknown strategy: {strategy}")


def run_backtest(req: RunRequest) -> RunResponse:
    """Execute a backtest and return structured results."""
    # Load data
    feed = DataFeed(req.symbol, req.snapshot_id)
    close = feed.close

    # Date slice
    if req.start:
        close = close.loc[req.start:]
    if req.end:
        close = close.loc[:req.end]

    if len(close) < 30:
        raise ValueError(
            f"Too few bars ({len(close)}) after date filter. "
            "Check start/end or expand the range."
        )

    # Load benchmark close for relative metrics
    benchmark_close: pd.Series | None = None
    try:
        bm_path = store.snapshot_path(req.snapshot_id) / "benchmarks" / f"{req.benchmark}.parquet"
        if bm_path.exists():
            bm_df = pd.read_parquet(bm_path)
            bm_col = "split_adj_close" if "split_adj_close" in bm_df.columns else "close"
            benchmark_close = bm_df[bm_col]
            benchmark_close.index = pd.to_datetime(benchmark_close.index)
            if req.start:
                benchmark_close = benchmark_close.loc[req.start:]
            if req.end:
                benchmark_close = benchmark_close.loc[:req.end]
    except Exception:
        pass  # benchmark is optional

    # Build signals
    entries, exits = _build_entries_exits(close, req.strategy, req.params)

    # Run backtest
    result: BacktestResult = portfolio.from_signals(
        close=close,
        entries=entries,
        exits=exits,
        initial_capital=req.initial_capital,
        benchmark_close=benchmark_close,
        symbol=req.symbol,
    )

    m = result.metrics
    bm = result.benchmark_metrics

    # --- Equity curve (normalize to 100 at start, sample to ≤500 points) ---
    equity = result.equity
    equity_norm = equity / equity.iloc[0] * 100

    # Benchmark buy-and-hold curve (normalized to 100)
    bm_norm: pd.Series | None = None
    if benchmark_close is not None:
        bm_aligned = benchmark_close.reindex(equity.index).ffill()
        bm_norm = bm_aligned / bm_aligned.iloc[0] * 100

    # Downsample if too many points (keep first, last, and evenly spaced)
    MAX_POINTS = 500
    if len(equity_norm) > MAX_POINTS:
        idx = list(range(0, len(equity_norm), len(equity_norm) // MAX_POINTS))
        if idx[-1] != len(equity_norm) - 1:
            idx.append(len(equity_norm) - 1)
        equity_norm = equity_norm.iloc[idx]
        if bm_norm is not None:
            bm_norm = bm_norm.iloc[idx]

    equity_curve = [
        EquityPoint(
            date=str(ts.date()),
            strategy=round(float(sv), 4),
            benchmark=round(float(bm_norm.iloc[i]), 4) if bm_norm is not None else None,
        )
        for i, (ts, sv) in enumerate(equity_norm.items())
    ]

    return RunResponse(
        symbol=req.symbol,
        strategy=req.strategy.value,
        params=req.params,
        snapshot_id=req.snapshot_id,
        start=str(close.index[0].date()),
        end=str(close.index[-1].date()),
        n_bars=len(close),
        metrics=MetricsOut(
            total_return=round(m["total_return"], 6),
            cagr=round(m["cagr"], 6),
            sharpe=round(m["sharpe"], 4),
            sortino=round(m["sortino"], 4),
            max_dd=round(m["max_dd"], 6),
            n_trades=m["n_trades"],
            win_rate=round(m["win_rate"], 4) if m["win_rate"] == m["win_rate"] else None,
            calmar=round(m["calmar"], 4),
        ),
        benchmark_metrics=BenchmarkMetricsOut(
            benchmark_total_return=round(bm["benchmark_total_return"], 6),
            excess_return=round(bm["excess_return"], 6),
            information_ratio=round(bm["information_ratio"], 4),
            beta=round(bm["beta"], 4),
            correlation=round(bm["correlation"], 4),
        ) if bm else None,
        equity_curve=equity_curve,
    )
