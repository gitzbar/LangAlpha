"""Strategy base class for path-dependent strategies.

Use this when vectorized signals are insufficient — e.g. strategies that
need position sizing based on account state, trailing stops, or multi-step
logic that doesn't express cleanly as a boolean signal array.

For purely vectorized strategies (most cases), use engine.portfolio.from_signals
directly — it's faster and simpler.

Example:
    class GoldenCross(Strategy):
        fast: int = 50
        slow: int = 200

        def setup(self):
            self.fast_ma = sma(self.data.close, self.fast)
            self.slow_ma = sma(self.data.close, self.slow)

        def on_bar(self, i: int):
            if self.fast_ma.iloc[i] > self.slow_ma.iloc[i] and \\
               self.fast_ma.iloc[i - 1] <= self.slow_ma.iloc[i - 1]:
                if not self.position:
                    self.buy(pct_equity=1.0)
            elif self.fast_ma.iloc[i] < self.slow_ma.iloc[i] and self.position:
                self.close()
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ginlix_backtest.calendar import apply_next_bar_shift
from ginlix_backtest.data_feed import DataFeed
from ginlix_backtest.fees import US_DEFAULT, CostModel


@dataclass
class _Trade:
    entry_bar: int
    entry_price: float
    qty: float
    side: str = "long"
    exit_bar: int | None = None
    exit_price: float | None = None

    @property
    def is_open(self) -> bool:
        return self.exit_bar is None

    @property
    def pnl(self) -> float:
        if self.exit_price is None:
            return 0.0
        if self.side == "long":
            return (self.exit_price - self.entry_price) * self.qty
        return (self.entry_price - self.exit_price) * self.qty


class Strategy:
    """Event-driven strategy base class.

    Subclass and override `setup()` and `on_bar(i)`.
    Call `self.buy()`, `self.sell()`, `self.close()` to place orders.
    All orders fill at the NEXT bar's open (next-bar fill, enforced here).
    """

    def __init__(
        self,
        data: DataFeed,
        cost_model: CostModel = US_DEFAULT,
        initial_capital: float = 100_000.0,
    ) -> None:
        self.data = data
        self.cost_model = cost_model
        self.initial_capital = initial_capital

        self._cash = initial_capital
        self._position: float = 0.0        # shares held (+ = long, - = short)
        self._trades: list[_Trade] = []
        self._equity_curve: list[float] = []
        self._pending_orders: list[dict[str, Any]] = []  # filled next bar

    # ── Overridable hooks ────────────────────────────────────────────────────

    def setup(self) -> None:
        """Called once before the bar loop. Precompute indicators here."""

    def on_bar(self, i: int) -> None:
        """Called on each bar. Index i is the CURRENT bar (not future)."""

    # ── Order API ────────────────────────────────────────────────────────────

    @property
    def position(self) -> float:
        return self._position

    @property
    def cash(self) -> float:
        return self._cash

    def buy(self, pct_equity: float = 1.0, qty: float | None = None) -> None:
        """Queue a market buy for next bar's open."""
        self._pending_orders.append({"side": "buy", "pct_equity": pct_equity, "qty": qty})

    def sell(self, pct_equity: float = 1.0, qty: float | None = None) -> None:
        """Queue a market sell (short) for next bar's open."""
        self._pending_orders.append({"side": "sell", "pct_equity": pct_equity, "qty": qty})

    def close(self) -> None:
        """Queue a close of the current position at next bar's open."""
        self._pending_orders.append({"side": "close"})

    # ── Internal execution ───────────────────────────────────────────────────

    def _fill_orders(self, i: int) -> None:
        open_price = float(self.data.open.iloc[i])
        for order in self._pending_orders:
            side = order["side"]
            fill_price = self.cost_model.fill_price(
                "buy" if side != "sell" else "sell", open_price
            )

            if side == "close" and self._position != 0:
                close_side = "sell" if self._position > 0 else "buy"
                qty = abs(self._position)
                fee = self.cost_model.fee.commission(close_side, qty, fill_price)
                slip = self.cost_model.slippage.slippage_cost(qty, fill_price)
                proceeds = qty * fill_price - fee - slip
                self._cash += proceeds if self._position > 0 else -proceeds
                # Mark open trade as closed
                for t in reversed(self._trades):
                    if t.is_open:
                        t.exit_bar = i
                        t.exit_price = fill_price
                        break
                self._position = 0.0

            elif side in ("buy", "sell"):
                qty = order.get("qty")
                if qty is None:
                    pct = order.get("pct_equity", 1.0)
                    equity = self._cash + self._position * float(self.data.close.iloc[i - 1])
                    qty = max(0, (equity * pct) // fill_price)
                if qty <= 0:
                    continue
                fee = self.cost_model.fee.commission(side, qty, fill_price)
                slip = self.cost_model.slippage.slippage_cost(qty, fill_price)
                cost = qty * fill_price + fee + slip
                if side == "buy" and cost <= self._cash:
                    self._cash -= cost
                    self._position += qty
                    self._trades.append(_Trade(i, fill_price, qty, "long"))
                elif side == "sell":
                    self._cash += qty * fill_price - fee - slip
                    self._position -= qty
                    self._trades.append(_Trade(i, fill_price, qty, "short"))

        self._pending_orders.clear()

    def run(self) -> "StrategyResult":
        """Execute the strategy across all bars and return results."""
        self.setup()
        n = len(self.data.close)

        # Start from bar 1 so on_bar(i) can safely look back to i-1
        for i in range(1, n):
            self._fill_orders(i)  # fill previous bar's pending orders
            self.on_bar(i)
            price = float(self.data.close.iloc[i])
            equity = self._cash + self._position * price
            self._equity_curve.append(equity)

        # Close any open position at last bar
        if self._position != 0 and len(self._equity_curve) > 0:
            pass  # leave open; user can check strategy.position

        equity_series = pd.Series(
            [self.initial_capital] + self._equity_curve,
            index=self.data.close.index[:n],
        )
        return StrategyResult(equity=equity_series, trades=list(self._trades))


@dataclass
class StrategyResult:
    """Lightweight result from a Strategy.run() call."""

    equity: pd.Series
    trades: list[_Trade]

    @property
    def total_return(self) -> float:
        return float(self.equity.iloc[-1] / self.equity.iloc[0] - 1)

    @property
    def n_trades(self) -> int:
        return len(self.trades)

    @property
    def closed_trades(self) -> list[_Trade]:
        return [t for t in self.trades if not t.is_open]

    @property
    def win_rate(self) -> float:
        closed = self.closed_trades
        if not closed:
            return float("nan")
        return sum(1 for t in closed if t.pnl > 0) / len(closed)

    def to_metrics(self) -> dict[str, Any]:
        returns = self.equity.pct_change().dropna()
        sharpe = float(returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else float("nan")
        drawdown = (self.equity / self.equity.cummax() - 1).min()
        n_years = len(self.equity) / 252
        cagr = (1 + self.total_return) ** (1 / max(n_years, 1e-6)) - 1

        return {
            "total_return": self.total_return,
            "cagr": cagr,
            "sharpe": sharpe,
            "max_dd": float(drawdown),
            "n_trades": self.n_trades,
            "win_rate": self.win_rate,
        }
