"""Regime analysis - bucket strategy returns by market environment.

Three regime dimensions:
- Volatility: VIX percentile buckets (low / medium / high)
- Trend: price vs 200-day MA (bull / bear)
- Rates: direction of 10Y yield (rising / falling)

Usage:
    from ginlix_backtest.analysis import regime

    ra = regime.RegimeAnalysis(strategy_returns, prices)
    ra.by_vix(vix_series).summary()
    ra.by_trend().summary()
    ra.full_report()
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd


@dataclass
class BucketStats:
    label: str
    n_days: int
    mean_daily_return: float
    ann_return: float
    ann_vol: float
    sharpe: float
    pct_time: float  # fraction of total days in this bucket

    def __repr__(self) -> str:
        return (
            f"BucketStats({self.label!r}: "
            f"sharpe={self.sharpe:.2f}, "
            f"ann={self.ann_return:.1%}, "
            f"time={self.pct_time:.0%})"
        )


def _bucket_stats(returns: pd.Series, mask: pd.Series, label: str, total_days: int) -> BucketStats:
    r = returns[mask]
    n = len(r)
    if n == 0:
        return BucketStats(label=label, n_days=0, mean_daily_return=float("nan"),
                           ann_return=float("nan"), ann_vol=float("nan"),
                           sharpe=float("nan"), pct_time=0.0)
    mean_r = float(r.mean())
    ann_r = mean_r * 252
    ann_v = float(r.std() * np.sqrt(252))
    sh = ann_r / ann_v if ann_v > 0 else float("nan")
    return BucketStats(
        label=label,
        n_days=n,
        mean_daily_return=mean_r,
        ann_return=ann_r,
        ann_vol=ann_v,
        sharpe=sh,
        pct_time=n / total_days,
    )


def _stats_df(buckets: list[BucketStats]) -> pd.DataFrame:
    rows = []
    for b in buckets:
        rows.append({
            "regime": b.label,
            "days": b.n_days,
            "ann_return": f"{b.ann_return:.1%}" if not np.isnan(b.ann_return) else "n/a",
            "ann_vol": f"{b.ann_vol:.1%}" if not np.isnan(b.ann_vol) else "n/a",
            "sharpe": round(b.sharpe, 2) if not np.isnan(b.sharpe) else float("nan"),
            "pct_time": f"{b.pct_time:.0%}",
        })
    return pd.DataFrame(rows)


class RegimeAnalysis:
    """Slice strategy returns by market regime.

    Args:
        returns:  Daily strategy returns (pd.Series, DatetimeIndex).
        prices:   Underlying price series (pd.Series) used for MA200 trend regime.
                  Pass adj_close (total-return series) for best results.
    """

    def __init__(self, returns: pd.Series, prices: pd.Series | None = None) -> None:
        self.returns = returns.copy()
        self.prices = prices
        self._total_days = len(returns)

    # ── VIX regime ───────────────────────────────────────────────────────────

    def by_vix(
        self,
        vix: pd.Series,
        low_pct: float = 33,
        high_pct: float = 67,
    ) -> "RegimeReport":
        """Bucket returns by VIX percentile.

        Args:
            vix:      VIX closing price series (daily).  Fetch via yfinance: '^VIX'.
            low_pct:  VIX percentile threshold for 'low vol' bucket (default 33rd).
            high_pct: VIX percentile threshold for 'high vol' bucket (default 67th).
        """
        vix_aligned = vix.reindex(self.returns.index, method="ffill")
        lo = float(np.nanpercentile(vix_aligned, low_pct))
        hi = float(np.nanpercentile(vix_aligned, high_pct))

        buckets = [
            _bucket_stats(self.returns, vix_aligned <= lo,       f"Low VIX (<={lo:.0f})",       self._total_days),
            _bucket_stats(self.returns, (vix_aligned > lo) & (vix_aligned <= hi), f"Mid VIX ({lo:.0f}-{hi:.0f})", self._total_days),
            _bucket_stats(self.returns, vix_aligned > hi,        f"High VIX (>{hi:.0f})",       self._total_days),
        ]
        return RegimeReport(buckets=buckets, dimension="VIX")

    # ── Trend regime (MA200) ─────────────────────────────────────────────────

    def by_trend(
        self,
        ma_window: int = 200,
        prices: pd.Series | None = None,
    ) -> "RegimeReport":
        """Bucket returns by whether price is above or below its MA.

        Args:
            ma_window: Moving average window in trading days (default 200).
            prices:    Override the price series set at construction.
        """
        px = prices if prices is not None else self.prices
        if px is None:
            raise ValueError("prices must be provided either at construction or here")

        px_aligned = px.reindex(self.returns.index, method="ffill")
        ma = px_aligned.rolling(ma_window, min_periods=ma_window // 2).mean()

        bull = px_aligned > ma
        bear = px_aligned <= ma

        buckets = [
            _bucket_stats(self.returns, bull, f"Bull (price > MA{ma_window})", self._total_days),
            _bucket_stats(self.returns, bear, f"Bear (price <= MA{ma_window})", self._total_days),
        ]
        return RegimeReport(buckets=buckets, dimension=f"MA{ma_window} Trend")

    # ── Rate direction regime ─────────────────────────────────────────────────

    def by_rates(
        self,
        yields: pd.Series,
        lookback: int = 63,
    ) -> "RegimeReport":
        """Bucket returns by interest rate direction (rising / falling).

        Args:
            yields:   10Y treasury yield series (e.g. from yfinance: '^TNX').
            lookback: Days over which to measure yield change (default 63 = ~1 quarter).
        """
        y_aligned = yields.reindex(self.returns.index, method="ffill")
        y_change = y_aligned - y_aligned.shift(lookback)

        rising  = y_change > 0
        falling = y_change <= 0

        buckets = [
            _bucket_stats(self.returns, rising,  f"Rising Rates ({lookback}d)",  self._total_days),
            _bucket_stats(self.returns, falling, f"Falling Rates ({lookback}d)", self._total_days),
        ]
        return RegimeReport(buckets=buckets, dimension="Rate Direction")

    # ── Combined ──────────────────────────────────────────────────────────────

    def full_report(
        self,
        vix: pd.Series | None = None,
        yields: pd.Series | None = None,
    ) -> dict[str, "RegimeReport"]:
        """Run all available regime analyses and return a dict of reports.

        Skips VIX/rates if their series are not provided.
        """
        reports: dict[str, RegimeReport] = {}
        if self.prices is not None:
            reports["trend"] = self.by_trend()
        if vix is not None:
            reports["vix"] = self.by_vix(vix)
        if yields is not None:
            reports["rates"] = self.by_rates(yields)
        return reports


@dataclass
class RegimeReport:
    """Result of a single regime dimension analysis."""

    buckets: list[BucketStats]
    dimension: str

    def summary(self) -> pd.DataFrame:
        return _stats_df(self.buckets)

    def plot(self, ax=None) -> None:
        import matplotlib.pyplot as plt

        df = pd.DataFrame({
            "regime": [b.label for b in self.buckets],
            "sharpe": [b.sharpe for b in self.buckets],
            "ann_return": [b.ann_return * 100 for b in self.buckets],
        }).set_index("regime")

        fig, axes = plt.subplots(1, 2, figsize=(12, 4))
        df["sharpe"].plot.bar(ax=axes[0], color=["#2ecc71" if v > 0 else "#e74c3c" for v in df["sharpe"]])
        axes[0].axhline(0, color="black", linewidth=0.8)
        axes[0].set_title(f"Sharpe by {self.dimension}")
        axes[0].set_ylabel("Sharpe")
        axes[0].tick_params(axis="x", rotation=15)

        df["ann_return"].plot.bar(ax=axes[1], color=["#2ecc71" if v > 0 else "#e74c3c" for v in df["ann_return"]])
        axes[1].axhline(0, color="black", linewidth=0.8)
        axes[1].set_title(f"Ann. Return (%) by {self.dimension}")
        axes[1].set_ylabel("Ann. Return (%)")
        axes[1].tick_params(axis="x", rotation=15)

        plt.tight_layout()
        plt.show()

    def __repr__(self) -> str:
        return f"RegimeReport({self.dimension!r}, {len(self.buckets)} buckets)"
