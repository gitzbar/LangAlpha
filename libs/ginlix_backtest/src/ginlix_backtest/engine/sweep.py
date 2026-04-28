"""Parameter sweep (grid search) for strategy optimization.

Usage:
    from ginlix_backtest.engine import sweep

    results = sweep.grid_search(
        strategy_fn=lambda prices, fast, slow: portfolio.from_signals(
            prices,
            *signals.cross_signal(indicators.ema(prices, fast), indicators.ema(prices, slow)),
        ),
        prices=close,
        param_grid={"fast": [5, 10, 20], "slow": [50, 100, 200]},
        metric="sharpe",
    )
    results.heatmap("fast", "slow", metric="sharpe")
    print(results.best(n=5))
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd

from ginlix_backtest.engine.portfolio import BacktestResult


@dataclass
class SweepResult:
    """Results of a parameter sweep."""

    records: list[dict[str, Any]]   # each record: {param: value, ..., metric: value, ...}
    param_names: list[str]
    metric: str

    # ── Accessors ────────────────────────────────────────────────────────────

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(self.records)

    def best(self, n: int = 10, ascending: bool = False) -> pd.DataFrame:
        """Return the top-N parameter combinations sorted by metric."""
        df = self.to_dataframe()
        return df.sort_values(self.metric, ascending=ascending).head(n).reset_index(drop=True)

    def worst(self, n: int = 10) -> pd.DataFrame:
        return self.best(n=n, ascending=True)

    def heatmap(
        self,
        param_x: str,
        param_y: str,
        metric: str | None = None,
        ax=None,
    ) -> None:
        """Plot a heatmap of metric values across two parameters.

        Args:
            param_x: Parameter name for x-axis.
            param_y: Parameter name for y-axis.
            metric:  Metric column to plot (default: self.metric).
        """
        import matplotlib.pyplot as plt

        m = metric or self.metric
        df = self.to_dataframe()
        pivot = df.pivot_table(index=param_y, columns=param_x, values=m, aggfunc="mean")

        fig, axis = (plt.subplots(figsize=(10, 6)) if ax is None else (None, ax))
        im = axis.imshow(pivot.values, aspect="auto", cmap="RdYlGn")
        plt.colorbar(im, ax=axis, label=m)

        axis.set_xticks(range(len(pivot.columns)))
        axis.set_xticklabels([str(c) for c in pivot.columns])
        axis.set_yticks(range(len(pivot.index)))
        axis.set_yticklabels([str(i) for i in pivot.index])
        axis.set_xlabel(param_x)
        axis.set_ylabel(param_y)
        axis.set_title(f"{m} heatmap: {param_x} vs {param_y}")

        # Annotate cells
        for i in range(len(pivot.index)):
            for j in range(len(pivot.columns)):
                val = pivot.values[i, j]
                if not np.isnan(val):
                    axis.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=8)

        plt.tight_layout()
        if ax is None:
            plt.show()

    def stability_map(self, param_x: str, param_y: str) -> float:
        """Fraction of parameter combinations with positive metric value.

        A high stability map score means the strategy works across many
        parameter values (robust), not just one optimized point.
        """
        df = self.to_dataframe()
        vals = df[self.metric].dropna()
        if len(vals) == 0:
            return float("nan")
        return float((vals > 0).mean())

    def __repr__(self) -> str:
        df = self.to_dataframe()
        best_row = df.loc[df[self.metric].idxmax()] if len(df) > 0 else None
        if best_row is not None:
            params = {k: best_row[k] for k in self.param_names}
            return (
                f"SweepResult({len(df)} combos, "
                f"best {self.metric}={best_row[self.metric]:.2f} at {params})"
            )
        return f"SweepResult(0 combos)"


def grid_search(
    strategy_fn: Callable[..., BacktestResult],
    prices: pd.Series | pd.DataFrame,
    param_grid: dict[str, list[Any]],
    metric: str = "sharpe",
    extra_metrics: list[str] | None = None,
) -> SweepResult:
    """Run a strategy over all combinations in param_grid.

    Args:
        strategy_fn:   Callable(prices, **params) -> BacktestResult.
                       Must accept `prices` as its first positional argument,
                       then keyword arguments matching param_grid keys.
        prices:        Price series or DataFrame passed as first arg.
        param_grid:    Dict of {param_name: [value1, value2, ...]}.
        metric:        Primary metric to record (default: "sharpe").
        extra_metrics: Additional metrics to record (e.g. ["cagr", "max_dd"]).

    Returns:
        SweepResult with all parameter combinations and their metrics.

    Example:
        results = grid_search(
            strategy_fn=lambda prices, fast, slow: portfolio.from_signals(
                prices, *signals.cross_signal(
                    indicators.ema(prices, fast), indicators.ema(prices, slow)
                ),
            ),
            prices=close,
            param_grid={"fast": [5, 10, 20], "slow": [50, 100, 200]},
            metric="sharpe",
            extra_metrics=["cagr", "max_dd"],
        )
    """
    extra = extra_metrics or []
    all_metrics = list({metric} | set(extra))

    param_names = list(param_grid.keys())
    combos = list(itertools.product(*param_grid.values()))

    records: list[dict[str, Any]] = []
    for combo in combos:
        params = dict(zip(param_names, combo))
        record: dict[str, Any] = dict(params)
        try:
            result = strategy_fn(prices, **params)
            for m in all_metrics:
                record[m] = result.metrics.get(m, float("nan"))
        except Exception as e:
            for m in all_metrics:
                record[m] = float("nan")
            record["_error"] = str(e)
        records.append(record)

    return SweepResult(records=records, param_names=param_names, metric=metric)
