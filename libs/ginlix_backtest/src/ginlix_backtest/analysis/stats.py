"""Statistical significance tools for backtest results.

Three tests:
1. t-test: is mean daily return significantly > 0?
2. Bootstrap: empirical p-value by resampling daily returns
3. Monte Carlo: simulate random-entry strategies to establish a null distribution

Usage:
    from ginlix_backtest.analysis import stats

    result = stats.ttest(strategy_returns)
    result = stats.bootstrap_pvalue(strategy_returns, n_simulations=5000)
    mc = stats.monte_carlo(close, n_simulations=1000, holding_days=5)
    mc.plot()
    print(mc.percentile(strategy_sharpe))
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats as sp_stats


# ── t-test ─────────────────────────────────────────────────────────────────

@dataclass
class TTestResult:
    mean_daily_return: float
    t_statistic: float
    p_value: float          # one-sided: H1 = mean > 0
    ann_return: float
    ann_vol: float
    n_obs: int
    significant: bool       # p < 0.05

    def __repr__(self) -> str:
        sig = "YES" if self.significant else "NO"
        return (
            f"TTestResult(t={self.t_statistic:.2f}, p={self.p_value:.4f}, "
            f"ann={self.ann_return:.1%}, sig={sig})"
        )


def ttest(returns: pd.Series, alpha: float = 0.05) -> TTestResult:
    """One-sample t-test: H0 = mean daily return is zero.

    Args:
        returns: Daily strategy returns.
        alpha:   Significance level (default 0.05).

    Returns:
        TTestResult with t-statistic, one-sided p-value, and significance flag.
    """
    r = returns.dropna()
    t_stat, p_two = sp_stats.ttest_1samp(r, popmean=0)
    p_one = float(p_two) / 2 if t_stat > 0 else 1.0 - float(p_two) / 2

    mean_r = float(r.mean())
    ann_r = mean_r * 252
    ann_v = float(r.std() * np.sqrt(252))

    return TTestResult(
        mean_daily_return=mean_r,
        t_statistic=float(t_stat),
        p_value=p_one,
        ann_return=ann_r,
        ann_vol=ann_v,
        n_obs=len(r),
        significant=p_one < alpha,
    )


# ── Bootstrap ──────────────────────────────────────────────────────────────

@dataclass
class BootstrapResult:
    observed_sharpe: float
    p_value: float          # fraction of simulations with sharpe >= observed
    n_simulations: int
    ci_lower: float         # 5th percentile of bootstrap distribution
    ci_upper: float         # 95th percentile
    significant: bool

    def __repr__(self) -> str:
        sig = "YES" if self.significant else "NO"
        return (
            f"BootstrapResult(sharpe={self.observed_sharpe:.2f}, "
            f"p={self.p_value:.4f}, "
            f"CI=[{self.ci_lower:.2f}, {self.ci_upper:.2f}], sig={sig})"
        )


def bootstrap_pvalue(
    returns: pd.Series,
    n_simulations: int = 5000,
    alpha: float = 0.05,
    seed: int = 42,
) -> BootstrapResult:
    """Empirical p-value for Sharpe ratio via block bootstrap.

    Resamples daily returns with replacement (iid bootstrap).
    H0: returns come from a zero-mean distribution.
    H1: mean return > 0 (one-sided).

    Args:
        returns:       Daily strategy returns.
        n_simulations: Number of bootstrap resamples.
        alpha:         Significance level.
        seed:          Random seed for reproducibility.
    """
    rng = np.random.default_rng(seed)
    r = returns.dropna().to_numpy()
    n = len(r)

    # Demeaned returns for null distribution
    r_null = r - r.mean()

    def _sharpe(x: np.ndarray) -> float:
        std = x.std()
        return (x.mean() * np.sqrt(252)) / std if std > 0 else 0.0

    obs_sharpe = _sharpe(r)

    sim_sharpes = np.array([
        _sharpe(rng.choice(r_null, size=n, replace=True))
        for _ in range(n_simulations)
    ])

    p_val = float((sim_sharpes >= obs_sharpe).mean())
    ci_lo = float(np.percentile(sim_sharpes, 5))
    ci_hi = float(np.percentile(sim_sharpes, 95))

    return BootstrapResult(
        observed_sharpe=obs_sharpe,
        p_value=p_val,
        n_simulations=n_simulations,
        ci_lower=ci_lo,
        ci_upper=ci_hi,
        significant=p_val < alpha,
    )


# ── Monte Carlo (random entry null distribution) ───────────────────────────

@dataclass
class MonteCarloResult:
    """Distribution of Sharpe ratios under random-entry null hypothesis."""

    sharpe_distribution: np.ndarray
    observed_sharpe: float | None
    n_simulations: int
    holding_days: int

    def percentile(self, observed_sharpe: float | None = None) -> float:
        """Return the percentile of the observed Sharpe in the null distribution.

        Higher = better (e.g. 95 means strategy beats 95% of random entries).
        """
        s = observed_sharpe if observed_sharpe is not None else self.observed_sharpe
        if s is None:
            raise ValueError("observed_sharpe required")
        return float((self.sharpe_distribution < s).mean() * 100)

    def p_value(self, observed_sharpe: float | None = None) -> float:
        s = observed_sharpe if observed_sharpe is not None else self.observed_sharpe
        if s is None:
            raise ValueError("observed_sharpe required")
        return float((self.sharpe_distribution >= s).mean())

    def summary(self) -> dict:
        d = self.sharpe_distribution
        return {
            "mean": float(d.mean()),
            "std": float(d.std()),
            "p5": float(np.percentile(d, 5)),
            "p50": float(np.percentile(d, 50)),
            "p95": float(np.percentile(d, 95)),
            "observed": self.observed_sharpe,
            "percentile": self.percentile() if self.observed_sharpe is not None else None,
        }

    def plot(self, ax=None) -> None:
        import matplotlib.pyplot as plt

        fig, axis = (plt.subplots(figsize=(9, 4)) if ax is None else (None, ax))
        axis.hist(self.sharpe_distribution, bins=50, edgecolor="white", linewidth=0.4,
                  color="#3498db", alpha=0.8, label="Random strategies")
        axis.axvline(np.percentile(self.sharpe_distribution, 95), color="orange",
                     linestyle="--", linewidth=1.2, label="95th pct")
        if self.observed_sharpe is not None:
            axis.axvline(self.observed_sharpe, color="red", linewidth=1.5,
                         label=f"Strategy ({self.observed_sharpe:.2f})")
        axis.set_title(
            f"Monte Carlo null distribution — {self.n_simulations:,} random "
            f"entries, {self.holding_days}d hold"
        )
        axis.set_xlabel("Sharpe ratio")
        axis.legend()
        plt.tight_layout()
        if ax is None:
            plt.show()

    def __repr__(self) -> str:
        pct = f"{self.percentile():.0f}th" if self.observed_sharpe is not None else "n/a"
        return (
            f"MonteCarloResult(n={self.n_simulations}, "
            f"hold={self.holding_days}d, "
            f"observed_pct={pct})"
        )


def monte_carlo(
    prices: pd.Series,
    n_simulations: int = 1_000,
    holding_days: int = 5,
    observed_sharpe: float | None = None,
    seed: int = 42,
) -> MonteCarloResult:
    """Build a null Sharpe distribution via random-entry Monte Carlo.

    For each simulation, randomly pick entry dates, hold for `holding_days`,
    compute Sharpe of that "strategy".  Use this to establish what Sharpe
    a random strategy achieves on this price series, then compare your
    real strategy's Sharpe against this baseline.

    Args:
        prices:          Daily price series (close).
        n_simulations:   Number of random strategies to simulate.
        holding_days:    Fixed holding period in trading days.
        observed_sharpe: Your strategy's Sharpe (for percentile/p-value).
        seed:            RNG seed.
    """
    rng = np.random.default_rng(seed)
    log_r = np.log(prices / prices.shift(1)).dropna().to_numpy()
    n = len(log_r)

    sharpes: list[float] = []
    for _ in range(n_simulations):
        # Random entry on ~20% of bars
        entries = rng.random(n) < 0.2
        entry_idx = np.where(entries)[0]
        if len(entry_idx) == 0:
            continue

        daily_returns = np.zeros(n)
        for ei in entry_idx:
            ex = min(ei + holding_days, n)
            daily_returns[ei:ex] = log_r[ei:ex]

        # Avoid double-counting overlapping positions: clip to [-1, 1] per bar
        daily_returns = np.clip(daily_returns, -1, 1)

        std = daily_returns.std()
        sh = (daily_returns.mean() * np.sqrt(252)) / std if std > 0 else 0.0
        sharpes.append(sh)

    return MonteCarloResult(
        sharpe_distribution=np.array(sharpes),
        observed_sharpe=observed_sharpe,
        n_simulations=n_simulations,
        holding_days=holding_days,
    )
