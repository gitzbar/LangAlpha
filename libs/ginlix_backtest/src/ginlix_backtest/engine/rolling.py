"""Rolling (walk-forward) backtest engine.

Slices a price series into overlapping windows and runs a strategy on each.
Use this to:
- Measure strategy stability across different market regimes
- Avoid overfitting to a single historical period
- Get a distribution of Sharpe ratios rather than one point estimate

Example:
    results = rolling.backtest(
        strategy_fn=my_strategy,
        prices=close,
        window="5Y",
        step="1M",
    )
    results.plot_metric("sharpe")
    results.worst_windows(n=5)
    print(results.stability_score())
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd

from ginlix_backtest.engine.portfolio import BacktestResult


@dataclass
class WindowResult:
    start: pd.Timestamp
    end: pd.Timestamp
    metrics: dict[str, Any]
    benchmark_metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def sharpe(self) -> float:
        return self.metrics.get("sharpe", float("nan"))

    @property
    def cagr(self) -> float:
        return self.metrics.get("cagr", float("nan"))

    @property
    def max_dd(self) -> float:
        return self.metrics.get("max_dd", float("nan"))


@dataclass
class RollingResult:
    """Aggregate of all rolling window backtest results."""

    windows: list[WindowResult]
    window_size: str
    step_size: str

    # ── Accessors ────────────────────────────────────────────────────────────

    def metric_series(self, metric: str = "sharpe") -> pd.Series:
        """Return a Series of a metric across windows, indexed by window start."""
        return pd.Series(
            {w.start: w.metrics.get(metric, float("nan")) for w in self.windows}
        )

    def summary(self) -> pd.DataFrame:
        """Return a DataFrame with key metrics for each window."""
        rows = []
        for w in self.windows:
            rows.append({
                "start": w.start.date(),
                "end": w.end.date(),
                "sharpe": round(w.sharpe, 2),
                "cagr": f"{w.cagr:.1%}",
                "max_dd": f"{w.max_dd:.1%}",
                "n_trades": w.metrics.get("n_trades", 0),
            })
        return pd.DataFrame(rows)

    def worst_windows(self, n: int = 5, by: str = "sharpe") -> pd.DataFrame:
        """Return the N worst-performing windows by a given metric."""
        df = self.summary().copy()
        # Re-attach numeric sharpe for sorting
        df["_sort"] = [w.metrics.get(by, float("nan")) for w in self.windows]
        return df.drop("_sort", axis=1).iloc[
            df["_sort"].argsort().values[:n]
        ].reset_index(drop=True)

    def best_windows(self, n: int = 5, by: str = "sharpe") -> pd.DataFrame:
        df = self.summary().copy()
        df["_sort"] = [w.metrics.get(by, float("nan")) for w in self.windows]
        return df.drop("_sort", axis=1).iloc[
            df["_sort"].argsort().values[::-1][:n]
        ].reset_index(drop=True)

    def stability_score(self) -> float:
        """Fraction of windows with positive Sharpe. Range: 0–1."""
        sharpes = [w.sharpe for w in self.windows if not np.isnan(w.sharpe)]
        if not sharpes:
            return float("nan")
        return sum(1 for s in sharpes if s > 0) / len(sharpes)

    def plot_metric(self, metric: str = "sharpe", ax=None) -> None:
        """Plot the distribution and time series of a metric across windows."""
        import matplotlib.pyplot as plt

        series = self.metric_series(metric)
        fig, axes = plt.subplots(1, 2, figsize=(14, 4))

        axes[0].plot(series.index, series.values, marker="o", markersize=4, linewidth=1.2)
        axes[0].axhline(0, color="red", linestyle="--", linewidth=0.8)
        axes[0].set_title(f"Rolling {metric} — {self.window_size} window, {self.step_size} step")
        axes[0].set_xlabel("Window start")
        axes[0].set_ylabel(metric)

        axes[1].hist(series.dropna().values, bins=20, edgecolor="white", linewidth=0.5)
        axes[1].axvline(series.mean(), color="red", linestyle="--", label=f"mean={series.mean():.2f}")
        axes[1].axvline(0, color="black", linestyle="-", linewidth=0.5)
        axes[1].set_title(f"Distribution of {metric}")
        axes[1].set_xlabel(metric)
        axes[1].legend()

        plt.tight_layout()
        plt.show()


def _parse_offset(s: str) -> pd.DateOffset:
    """Parse strings like '5Y', '1M', '3M', '6M', '1Y'."""
    s = s.strip().upper()
    n = int(s[:-1])
    unit = s[-1]
    if unit == "Y":
        return pd.DateOffset(years=n)
    elif unit == "M":
        return pd.DateOffset(months=n)
    elif unit == "W":
        return pd.DateOffset(weeks=n)
    elif unit == "D":
        return pd.DateOffset(days=n)
    raise ValueError(f"Unknown offset: {s!r}. Use e.g. '5Y', '3M', '20D'.")


def backtest(
    strategy_fn: Callable[[pd.Series], BacktestResult],
    prices: pd.Series,
    window: str = "5Y",
    step: str = "1M",
    min_bars: int = 60,
) -> RollingResult:
    """Run a rolling walk-forward backtest.

    Args:
        strategy_fn: Callable that takes a price slice (pd.Series) and returns
                     a BacktestResult. Build it using engine.portfolio.from_signals.
        prices:      Full price series (split_adj_close).
        window:      Window size string — e.g. '5Y', '18M', '252D'.
        step:        Step between windows — e.g. '1M', '3M', '1Y'.
        min_bars:    Skip windows with fewer bars than this.

    Returns:
        RollingResult with per-window metrics.
    """
    window_offset = _parse_offset(window)
    step_offset   = _parse_offset(step)

    start = prices.index[0]
    end   = prices.index[-1]

    windows: list[WindowResult] = []
    cursor = start

    while True:
        win_end = cursor + window_offset
        if win_end > end:
            break

        slice_ = prices.loc[cursor:win_end]
        if len(slice_) < min_bars:
            cursor += step_offset
            continue

        try:
            result = strategy_fn(slice_)
            windows.append(WindowResult(
                start=cursor,
                end=win_end,
                metrics=result.metrics,
                benchmark_metrics=result.benchmark_metrics,
            ))
        except Exception as e:
            # Log but don't crash — some windows may have insufficient data for indicators
            windows.append(WindowResult(
                start=cursor,
                end=win_end,
                metrics={"error": str(e)},
            ))

        cursor += step_offset

    return RollingResult(windows=windows, window_size=window, step_size=step)
