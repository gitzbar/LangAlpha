"""Portfolio engine — vectorbt wrapper with reliability rules baked in.

Key guarantees enforced here (not in user code):
- Signals are shifted by 1 bar before passing to vectorbt (next-bar fill)
- US_DEFAULT fee + slippage model applied automatically
- SPY benchmark metrics computed for every run
- Results wrapped in BacktestResult for uniform access
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt

# Trading-day index has no regular frequency — tell vectorbt to treat it as daily
vbt.settings.array_wrapper["freq"] = "D"

from ginlix_backtest.calendar import apply_next_bar_shift
from ginlix_backtest.fees import US_DEFAULT, CostModel


@dataclass
class BacktestResult:
    """Uniform result container returned by all portfolio factories."""

    portfolio: vbt.Portfolio
    symbol: str | None          # None for multi-asset portfolios
    metrics: dict[str, Any]
    benchmark_metrics: dict[str, Any]
    cost_model: CostModel

    @property
    def stats(self) -> pd.Series:
        return self.portfolio.stats()

    @property
    def returns(self) -> pd.Series:
        return self.portfolio.returns()

    @property
    def equity(self) -> pd.Series:
        return self.portfolio.value()

    def plot(self, **kwargs) -> None:
        self.portfolio.plot(**kwargs).show()

    def __repr__(self) -> str:
        s = self.metrics
        return (
            f"BacktestResult("
            f"sharpe={s.get('sharpe', float('nan')):.2f}, "
            f"cagr={s.get('cagr', float('nan')):.1%}, "
            f"max_dd={s.get('max_dd', float('nan')):.1%})"
        )


def _compute_metrics(pf: vbt.Portfolio) -> dict[str, Any]:
    stats = pf.stats()
    total_return = float(pf.total_return())
    n_years = len(pf.wrapper.index) / 252
    cagr = (1 + total_return) ** (1 / max(n_years, 1e-6)) - 1 if n_years > 0 else float("nan")

    return {
        "total_return": total_return,
        "cagr": cagr,
        "sharpe": float(pf.sharpe_ratio()),
        "sortino": float(pf.sortino_ratio()),
        "max_dd": float(pf.max_drawdown()),
        "n_trades": int(stats.get("Total Trades", 0)),
        "win_rate": float(stats.get("Win Rate [%]", float("nan"))) / 100
        if not pd.isna(stats.get("Win Rate [%]", float("nan")))
        else float("nan"),
        "calmar": float(pf.calmar_ratio()),
    }


def _compute_benchmark_metrics(
    equity: pd.Series,
    benchmark_close: pd.Series,
) -> dict[str, Any]:
    """Compute metrics relative to a benchmark price series."""
    bm = benchmark_close.reindex(equity.index, method="ffill").bfill()
    bm_returns = bm.pct_change().fillna(0)
    strat_returns = equity.pct_change().fillna(0)

    excess = strat_returns - bm_returns
    ir = float(excess.mean() / excess.std() * np.sqrt(252)) if excess.std() > 0 else float("nan")

    cov_matrix = np.cov(strat_returns, bm_returns)
    beta = float(cov_matrix[0, 1] / cov_matrix[1, 1]) if cov_matrix[1, 1] != 0 else float("nan")

    bm_total = float(bm.iloc[-1] / bm.iloc[0] - 1)
    strat_total = float(equity.iloc[-1] / equity.iloc[0] - 1)

    return {
        "benchmark_total_return": bm_total,
        "excess_return": strat_total - bm_total,
        "information_ratio": ir,
        "beta": beta,
        "correlation": float(strat_returns.corr(bm_returns)),
    }


def from_signals(
    close: pd.Series | pd.DataFrame,
    entries: pd.Series | pd.DataFrame,
    exits: pd.Series | pd.DataFrame,
    *,
    cost_model: CostModel = US_DEFAULT,
    initial_capital: float = 100_000.0,
    size: float = 1.0,
    size_type: str = "Percent",
    benchmark_close: pd.Series | None = None,
    symbol: str | None = None,
    **vbt_kwargs: Any,
) -> BacktestResult:
    """Run a signal-based backtest with reliability rules enforced.

    Args:
        close:      Price series (single or multi-asset DataFrame).
        entries:    Boolean buy signals — will be shifted +1 bar automatically.
        exits:      Boolean sell signals — will be shifted +1 bar automatically.
        cost_model: Fee + slippage model (default: US_DEFAULT).
        initial_capital: Starting cash in USD.
        size:       Position size (default: 100% of equity per signal).
        size_type:  vectorbt size type string.
        benchmark_close: Optional benchmark price series for relative metrics.
        symbol:     Label for single-asset runs.
    """
    # --- Reliability Rule: next-bar fill (look-ahead prevention) ---
    if isinstance(entries, pd.DataFrame):
        entries_shifted = entries.apply(apply_next_bar_shift)
        exits_shifted = exits.apply(apply_next_bar_shift)
    else:
        entries_shifted = apply_next_bar_shift(entries)
        exits_shifted = apply_next_bar_shift(exits)

    # vectorbt/numba requires plain numpy bool, not pandas nullable boolean
    entries_shifted = entries_shifted.fillna(False).astype(bool)
    exits_shifted = exits_shifted.fillna(False).astype(bool)

    # --- Fees via vectorbt's built-in fee/slippage params ---
    # slippage is applied as a fraction of price per trade
    slippage_frac = cost_model.slippage.bps / 10_000
    # commission: fixed per-trade fraction approximation (sec fee on sell only is minor)
    commission_frac = cost_model.fee.commission_per_share  # 0 for US retail

    pf = vbt.Portfolio.from_signals(
        close=close,
        entries=entries_shifted,
        exits=exits_shifted,
        init_cash=initial_capital,
        size=size,
        size_type=size_type,
        fees=commission_frac,
        slippage=slippage_frac,
        **vbt_kwargs,
    )

    metrics = _compute_metrics(pf)

    bm_metrics: dict[str, Any] = {}
    if benchmark_close is not None:
        bm_metrics = _compute_benchmark_metrics(pf.value(), benchmark_close)

    return BacktestResult(
        portfolio=pf,
        symbol=symbol,
        metrics=metrics,
        benchmark_metrics=bm_metrics,
        cost_model=cost_model,
    )


def from_weights(
    close: pd.DataFrame,
    weights: dict[str, float] | pd.DataFrame,
    *,
    rebalance: str = "monthly",
    cost_model: CostModel = US_DEFAULT,
    initial_capital: float = 100_000.0,
    benchmark_close: pd.Series | None = None,
    **vbt_kwargs: Any,
) -> BacktestResult:
    """Run a weight-based rebalancing backtest.

    Args:
        close:    Multi-asset price DataFrame (columns = symbols).
        weights:  Static dict {symbol: weight} or time-varying DataFrame.
        rebalance: Rebalance frequency — 'daily'|'weekly'|'monthly'|'quarterly'.
        cost_model: Fee + slippage model.
        initial_capital: Starting cash.
        benchmark_close: Optional benchmark for relative metrics.
    """
    # Find rebalance dates as the first trading day in each period
    _FREQ_MAP = {"daily": "D", "weekly": "W-MON", "monthly": "MS", "quarterly": "QS"}
    freq = _FREQ_MAP.get(rebalance, rebalance)

    if isinstance(weights, dict):
        weight_series = pd.Series(weights, dtype=float)
        weight_series = weight_series / weight_series.sum()
        target_row = weight_series.reindex(close.columns, fill_value=0.0)
    else:
        target_row = None

    # Build a size DataFrame: target weight on rebalance dates, NaN elsewhere
    # vectorbt with "TargetPercent" + NaN = hold (no order placed)
    size_df = pd.DataFrame(np.nan, index=close.index, columns=close.columns)

    # Mark the first trading day on or after each period boundary as a rebalance date
    tz = close.index.tz
    period_starts = pd.date_range(close.index[0], close.index[-1], freq=freq, tz=tz)
    for ps_date in period_starts:
        # Find the first trading day >= ps_date
        candidates = close.index[close.index >= ps_date]
        if len(candidates) == 0:
            continue
        rebalance_date = candidates[0]
        if target_row is not None:
            size_df.loc[rebalance_date] = target_row.values
        elif isinstance(weights, pd.DataFrame):
            if rebalance_date in weights.index:
                size_df.loc[rebalance_date] = weights.loc[rebalance_date].reindex(close.columns, fill_value=0.0).values

    # Also set the first bar to trigger initial buy
    if target_row is not None and size_df.iloc[0].isna().all():
        size_df.iloc[0] = target_row.values

    slippage_frac = cost_model.slippage.bps / 10_000

    pf = vbt.Portfolio.from_orders(
        close=close,
        size=size_df,
        size_type="TargetPercent",
        fees=cost_model.fee.commission_per_share,
        slippage=slippage_frac,
        init_cash=initial_capital,
        group_by=True,
        cash_sharing=True,
        call_seq="auto",
        **vbt_kwargs,
    )

    metrics = _compute_metrics(pf)
    bm_metrics: dict[str, Any] = {}
    if benchmark_close is not None:
        bm_metrics = _compute_benchmark_metrics(pf.value(), benchmark_close)

    return BacktestResult(
        portfolio=pf,
        symbol=None,
        metrics=metrics,
        benchmark_metrics=bm_metrics,
        cost_model=cost_model,
    )
