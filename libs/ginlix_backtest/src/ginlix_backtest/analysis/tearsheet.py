"""Tearsheet — pyfolio-style performance report.

Generates a multi-panel figure with:
- Cumulative returns vs benchmark
- Drawdown chart
- Monthly returns heatmap
- Return distribution histogram
- Key metrics table

Usage:
    from ginlix_backtest.analysis import tearsheet

    tearsheet.plot(result, benchmark_close=spy_close, title="Monday Effect — AAPL")
    df = tearsheet.metrics_table(result)
"""
from __future__ import annotations

import calendar as _cal

import numpy as np
import pandas as pd

from ginlix_backtest.engine.portfolio import BacktestResult


# ── Core stats ──────────────────────────────────────────────────────────────

def _monthly_returns(returns: pd.Series) -> pd.DataFrame:
    """Pivot daily returns into (year × month) table of monthly returns."""
    monthly = (1 + returns).resample("ME").prod() - 1
    df = monthly.to_frame("ret")
    df["year"] = df.index.year
    df["month"] = df.index.month
    pivot = df.pivot(index="year", columns="month", values="ret")
    pivot.columns = [_cal.month_abbr[m] for m in pivot.columns]
    return pivot


def _max_drawdown_series(cum_returns: pd.Series) -> pd.Series:
    rolling_max = cum_returns.cummax()
    dd = (cum_returns - rolling_max) / rolling_max
    return dd


def _ann_metrics(returns: pd.Series) -> dict:
    r = returns.dropna()
    n_years = len(r) / 252
    total = float((1 + r).prod() - 1)
    cagr = (1 + total) ** (1 / max(n_years, 1e-6)) - 1
    vol = float(r.std() * np.sqrt(252))
    sharpe = cagr / vol if vol > 0 else float("nan")
    sortino_denom = float(r[r < 0].std() * np.sqrt(252))
    sortino = cagr / sortino_denom if sortino_denom > 0 else float("nan")

    cum = (1 + r).cumprod()
    dd = _max_drawdown_series(cum)
    max_dd = float(dd.min())
    calmar = cagr / abs(max_dd) if max_dd != 0 else float("nan")

    win_rate = float((r > 0).mean())

    return {
        "Total Return": f"{total:.1%}",
        "CAGR": f"{cagr:.1%}",
        "Ann. Vol": f"{vol:.1%}",
        "Sharpe": f"{sharpe:.2f}",
        "Sortino": f"{sortino:.2f}",
        "Calmar": f"{calmar:.2f}",
        "Max Drawdown": f"{max_dd:.1%}",
        "Win Rate (daily)": f"{win_rate:.1%}",
        "Years": f"{n_years:.1f}",
    }


# ── Public API ───────────────────────────────────────────────────────────────

def metrics_table(result: BacktestResult) -> pd.DataFrame:
    """Return a DataFrame of key performance metrics.

    Args:
        result: BacktestResult from portfolio.from_signals or from_weights.
    """
    returns = result.returns
    metrics = _ann_metrics(returns)

    bm = result.benchmark_metrics
    if bm:
        metrics["Benchmark Return"] = f"{bm.get('benchmark_total_return', float('nan')):.1%}"
        metrics["Excess Return"] = f"{bm.get('excess_return', float('nan')):.1%}"
        metrics["Info Ratio"] = f"{bm.get('information_ratio', float('nan')):.2f}"
        metrics["Beta"] = f"{bm.get('beta', float('nan')):.2f}"

    return pd.DataFrame({"Metric": list(metrics.keys()), "Value": list(metrics.values())})


def plot(
    result: BacktestResult,
    benchmark_close: pd.Series | None = None,
    title: str = "Strategy Tearsheet",
    figsize: tuple[int, int] = (16, 18),
) -> None:
    """Plot a comprehensive tearsheet.

    Args:
        result:          BacktestResult to visualize.
        benchmark_close: Optional benchmark price series (e.g. SPY close).
        title:           Figure title.
        figsize:         Figure size in inches.
    """
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec

    returns = result.returns
    cum_ret = (1 + returns).cumprod()
    dd = _max_drawdown_series(cum_ret)
    monthly_ret = _monthly_returns(returns)
    metrics = _ann_metrics(returns)

    has_bm = benchmark_close is not None
    if has_bm:
        bm_aligned = benchmark_close.reindex(returns.index, method="ffill").bfill()
        bm_returns = bm_aligned.pct_change().fillna(0)
        cum_bm = (1 + bm_returns).cumprod()

    fig = plt.figure(figsize=figsize)
    fig.suptitle(title, fontsize=14, fontweight="bold", y=0.98)
    gs = gridspec.GridSpec(4, 2, figure=fig, hspace=0.45, wspace=0.35)

    # 1. Cumulative returns
    ax1 = fig.add_subplot(gs[0, :])
    ax1.plot(cum_ret.index, cum_ret.values, linewidth=1.5, label="Strategy")
    if has_bm:
        ax1.plot(cum_bm.index, cum_bm.values, linewidth=1.0, alpha=0.7,
                 linestyle="--", label="Benchmark", color="grey")
    ax1.set_title("Cumulative Returns")
    ax1.set_ylabel("Growth of $1")
    ax1.legend(loc="upper left")
    ax1.axhline(1, color="black", linewidth=0.5)

    # 2. Drawdown
    ax2 = fig.add_subplot(gs[1, :])
    ax2.fill_between(dd.index, dd.values, 0, color="#e74c3c", alpha=0.5)
    ax2.set_title("Drawdown")
    ax2.set_ylabel("Drawdown")
    ax2.axhline(0, color="black", linewidth=0.5)

    # 3. Monthly returns heatmap
    ax3 = fig.add_subplot(gs[2, :])
    data = monthly_ret.values
    vmax = max(abs(np.nanmin(data)), abs(np.nanmax(data)))
    im = ax3.imshow(data, aspect="auto", cmap="RdYlGn", vmin=-vmax, vmax=vmax)
    plt.colorbar(im, ax=ax3, label="Monthly Return")
    ax3.set_xticks(range(len(monthly_ret.columns)))
    ax3.set_xticklabels(monthly_ret.columns, fontsize=8)
    ax3.set_yticks(range(len(monthly_ret.index)))
    ax3.set_yticklabels(monthly_ret.index, fontsize=8)
    ax3.set_title("Monthly Returns Heatmap")
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            v = data[i, j]
            if not np.isnan(v):
                ax3.text(j, i, f"{v:.1%}", ha="center", va="center", fontsize=6)

    # 4. Return distribution
    ax4 = fig.add_subplot(gs[3, 0])
    ax4.hist(returns.dropna().values * 100, bins=60, edgecolor="white", linewidth=0.4,
             color="#3498db", alpha=0.8)
    ax4.axvline(0, color="black", linewidth=0.8)
    ax4.axvline(float(returns.mean() * 100), color="red", linestyle="--",
                label=f"mean={float(returns.mean())*100:.2f}%")
    ax4.set_title("Daily Return Distribution")
    ax4.set_xlabel("Daily Return (%)")
    ax4.legend(fontsize=8)

    # 5. Metrics table
    ax5 = fig.add_subplot(gs[3, 1])
    ax5.axis("off")
    bm = result.benchmark_metrics
    if bm:
        metrics["Excess Return"] = f"{bm.get('excess_return', float('nan')):.1%}"
        metrics["Info Ratio"] = f"{bm.get('information_ratio', float('nan')):.2f}"
        metrics["Beta"] = f"{bm.get('beta', float('nan')):.2f}"
    rows = list(metrics.items())
    tbl = ax5.table(
        cellText=rows,
        colLabels=["Metric", "Value"],
        cellLoc="left",
        loc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    tbl.scale(1, 1.4)
    ax5.set_title("Key Metrics", pad=10)

    plt.show()
