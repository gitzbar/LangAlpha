"""yfinance-backed PriceProvider + CorporateActionProvider.

Fetches unadjusted OHLCV + corporate actions from Yahoo Finance and builds
both split-adjusted and fully-adjusted close series locally.
"""
from __future__ import annotations

import warnings
from datetime import date

import pandas as pd
import yfinance as yf

from ginlix_data_sdk.schemas import CorporateAction

# Suppress noisy yfinance deprecation warnings in notebook contexts
warnings.filterwarnings("ignore", category=FutureWarning, module="yfinance")


class YFinancePriceProvider:
    """Implements PriceProvider using yfinance.

    Returns a DataFrame with columns:
        open, high, low, close, volume, adj_close, split_adj_close
    indexed by UTC DatetimeIndex (date resolution).
    Only NYSE trading days are included (rows with zero volume on holidays
    are dropped by yfinance implicitly; any remaining non-trading rows are
    filtered by the caller via ginlix_data_sdk.calendar).
    """

    def get_daily(
        self,
        symbol: str,
        start: date | str,
        end: date | str,
    ) -> pd.DataFrame:
        ticker = yf.Ticker(symbol)

        # unadjusted prices (split-only adjustment applied by yfinance when auto_adjust=False)
        raw = ticker.history(
            start=str(start),
            end=str(end),
            auto_adjust=False,
            actions=False,
        )
        if raw.empty:
            return pd.DataFrame(
                columns=["open", "high", "low", "close", "volume", "adj_close", "split_adj_close"]
            )

        # fully adjusted (split + dividend) close from yfinance
        adj = ticker.history(
            start=str(start),
            end=str(end),
            auto_adjust=True,
            actions=False,
        )

        # In modern yfinance (>=0.2):
        #   auto_adjust=False → Close = split-adjusted only (dividend-unadjusted)
        #                        Adj Close = split + dividend adjusted
        #   auto_adjust=True  → Close = split + dividend adjusted (same as Adj Close above)
        # So:
        #   close / split_adj_close = raw["Close"]  (split-adjusted, div-unadjusted)
        #   adj_close              = adj["Close"]   (split + dividend adjusted)
        fully_adj = adj["Close"] if not adj.empty else raw["Close"]
        split_adj = raw["Close"]  # split-only adjusted (this is what charts show)

        df = pd.DataFrame(
            {
                "open": raw["Open"],
                "high": raw["High"],
                "low": raw["Low"],
                "close": raw["Close"],       # split-adjusted (chart price)
                "volume": raw["Volume"].astype("int64"),
                "adj_close": fully_adj,       # split + dividend adjusted (total return)
                "split_adj_close": split_adj, # same as close; explicit alias for consumers
            }
        )

        # Normalize index to UTC midnight
        df.index = pd.to_datetime(df.index).tz_localize("UTC") if df.index.tz is None else df.index.tz_convert("UTC")
        df.index.name = "timestamp"
        return df.sort_index()


class YFinanceCorporateActionProvider:
    """Fetches splits and dividends from Yahoo Finance."""

    def get_actions(
        self,
        symbol: str,
        start: date | str,
        end: date | str,
    ) -> list[CorporateAction]:
        ticker = yf.Ticker(symbol)
        actions: list[CorporateAction] = []

        try:
            divs = ticker.dividends
            if divs is not None and not divs.empty:
                divs.index = pd.to_datetime(divs.index).tz_localize("UTC") if divs.index.tz is None else divs.index.tz_convert("UTC")
                mask = (divs.index.date >= _as_date(start)) & (divs.index.date <= _as_date(end))
                for ts, amount in divs[mask].items():
                    actions.append(
                        CorporateAction(
                            ex_date=ts.date(),
                            event_type="dividend",
                            amount=float(amount),
                        )
                    )
        except Exception:
            pass

        try:
            splits = ticker.splits
            if splits is not None and not splits.empty:
                splits.index = pd.to_datetime(splits.index).tz_localize("UTC") if splits.index.tz is None else splits.index.tz_convert("UTC")
                mask = (splits.index.date >= _as_date(start)) & (splits.index.date <= _as_date(end))
                for ts, ratio in splits[mask].items():
                    actions.append(
                        CorporateAction(
                            ex_date=ts.date(),
                            event_type="split",
                            ratio=float(ratio),
                        )
                    )
        except Exception:
            pass

        return sorted(actions, key=lambda a: a.ex_date)


def _as_date(d: date | str) -> date:
    if isinstance(d, date):
        return d
    return pd.Timestamp(d).date()
