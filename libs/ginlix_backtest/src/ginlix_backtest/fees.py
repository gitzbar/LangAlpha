"""Fee and slippage models for US equity backtests.

All models operate on a per-trade basis and return a cost in dollars.

Usage:
    from ginlix_backtest.fees import US_DEFAULT
    cost = US_DEFAULT.total_cost(side="sell", qty=100, price=150.0)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class FeeModel:
    """Commission model.

    commission_per_share: flat per-share commission (USD). Default 0 (IBKR retail).
    sec_taf_rate: SEC/TAF fee rate applied to sell orders only. Default 0.0000278
                  (SEC fee: $0.0000278 per dollar of proceeds, ~2.78e-5).
    """

    commission_per_share: float = 0.0
    sec_taf_rate: float = 0.0000278

    def commission(self, side: Literal["buy", "sell"], qty: float, price: float) -> float:
        cost = self.commission_per_share * abs(qty)
        if side == "sell":
            cost += self.sec_taf_rate * abs(qty) * price
        return cost


@dataclass
class SlippageModel:
    """Fixed-bps slippage applied to the execution price.

    bps: basis points of slippage per trade (default 3 bps = 0.03%).
    """

    bps: float = 3.0

    def slippage_cost(self, qty: float, price: float) -> float:
        return abs(qty) * price * (self.bps / 10_000)

    def adjusted_price(self, side: Literal["buy", "sell"], price: float) -> float:
        """Return the price after slippage is applied."""
        factor = self.bps / 10_000
        return price * (1 + factor) if side == "buy" else price * (1 - factor)


@dataclass
class CostModel:
    """Combined fee + slippage model."""

    fee: FeeModel
    slippage: SlippageModel

    def total_cost(self, side: Literal["buy", "sell"], qty: float, price: float) -> float:
        return self.fee.commission(side, qty, price) + self.slippage.slippage_cost(qty, price)

    def fill_price(self, side: Literal["buy", "sell"], price: float) -> float:
        return self.slippage.adjusted_price(side, price)


# ── Preset cost models ────────────────────────────────────────────────────────

US_DEFAULT = CostModel(
    fee=FeeModel(commission_per_share=0.0, sec_taf_rate=0.0000278),
    slippage=SlippageModel(bps=3.0),
)

ZERO_COST = CostModel(
    fee=FeeModel(commission_per_share=0.0, sec_taf_rate=0.0),
    slippage=SlippageModel(bps=0.0),
)
