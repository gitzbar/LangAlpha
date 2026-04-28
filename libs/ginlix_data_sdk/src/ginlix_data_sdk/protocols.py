from __future__ import annotations

from datetime import date
from typing import Protocol

import pandas as pd

from .schemas import CorporateAction


class PriceProvider(Protocol):
    """Fetch historical OHLCV data for US equities."""

    def get_daily(
        self,
        symbol: str,
        start: date | str,
        end: date | str,
    ) -> pd.DataFrame:
        """Return DataFrame indexed by UTC date with columns:
        open, high, low, close, volume, adj_close, split_adj_close.
        Index: DatetimeIndex (UTC, date-only resolution).
        Rows: NYSE trading days only.
        """
        ...


class CorporateActionProvider(Protocol):
    """Fetch corporate action history for US equities."""

    def get_actions(
        self,
        symbol: str,
        start: date | str,
        end: date | str,
    ) -> list[CorporateAction]:
        """Return corporate actions sorted ascending by ex_date."""
        ...
