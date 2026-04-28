"""ginlix_data_sdk — unified financial data access for Ginlix quant platform.

Quick start:
    from ginlix_data_sdk import parquet_store as store
    prices = store.load_prices(["AAPL", "MSFT"], snapshot_id="us-2026-04-23")
"""
from . import parquet_store
from .providers import YFinanceCorporateActionProvider, YFinancePriceProvider
from .schemas import CorporateAction, OHLCVBar

__all__ = [
    "parquet_store",
    "YFinancePriceProvider",
    "YFinanceCorporateActionProvider",
    "OHLCVBar",
    "CorporateAction",
]
