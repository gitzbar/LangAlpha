#!/usr/bin/env python
"""Backfill US daily OHLCV data into a Parquet snapshot.

Creates:
    data/snapshots/{snapshot_id}/daily/{symbol}.parquet
    data/snapshots/{snapshot_id}/corporate_actions/{symbol}.parquet
    data/snapshots/{snapshot_id}/benchmarks/{symbol}.parquet
    data/snapshots/{snapshot_id}/MANIFEST.json

Then registers the snapshot in Postgres (backtest.data_snapshots).

Usage:
    # S&P 500 전체 (권장)
    uv run python scripts/backfill_us_daily.py --sp500 --start 2015-01-01

    # 직접 종목 지정
    uv run python scripts/backfill_us_daily.py \\
        --symbols AAPL MSFT NVDA GOOGL AMZN META TSLA BRK-B JPM UNH \\
        --start 2015-01-01 --end 2026-04-23

    # Dry-run (DB 등록 스킵)
    uv run python scripts/backfill_us_daily.py --sp500 --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# Repo root on sys.path so we can import src/
sys.path.insert(0, str(Path(__file__).parents[1]))

import pandas as pd

from ginlix_data_sdk import parquet_store as store


# ---------------------------------------------------------------------------
# S&P 500 종목 리스트 자동 수집
# ---------------------------------------------------------------------------

def fetch_sp500_symbols() -> list[str]:
    """S&P 500 구성종목을 가져옴.

    Wikipedia (User-Agent 헤더로 403 우회) 시도 후,
    실패 시 하드코딩된 주요 500종목 fallback.
    """
    try:
        import io
        import requests
        headers = {"User-Agent": "Mozilla/5.0 (compatible; backfill-script/1.0)"}
        resp = requests.get(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            headers=headers, timeout=15,
        )
        resp.raise_for_status()
        tables = pd.read_html(io.StringIO(resp.text))
        df = tables[0]
        symbols = df["Symbol"].str.replace(".", "-", regex=False).tolist()
        log.info("Wikipedia에서 S&P 500 종목 %d개 수집 완료", len(symbols))
        return symbols
    except Exception as exc:
        log.warning("Wikipedia 수집 실패 (%s) — fallback 목록 사용", exc)
        return _SP500_FALLBACK


# Wikipedia 접근 실패 시 fallback — S&P 500 주요 종목 (2025년 기준)
_SP500_FALLBACK = [
    # 정보기술
    "AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "AMD", "ADBE", "CRM", "QCOM", "TXN",
    "INTU", "IBM", "AMAT", "NOW", "LRCX", "ADI", "MU", "KLAC", "PANW", "SNPS",
    "CDNS", "FTNT", "MRVL", "ROP", "ANSS", "MSI", "KEYS", "TRMB", "TDY", "EPAM",
    "IT", "GEN", "HPQ", "STX", "WDC", "NTAP", "SWKS", "AKAM", "CTSH", "GDDY",
    # 통신/미디어
    "GOOGL", "GOOG", "META", "NFLX", "DIS", "CMCSA", "T", "VZ", "CHTR", "TMUS",
    "ATVI", "EA", "TTWO", "WBD", "OMC", "IPG", "NWSA", "NWS", "FOX", "FOXA",
    # 임의소비재
    "AMZN", "TSLA", "HD", "MCD", "NKE", "LOW", "SBUX", "TJX", "BKNG", "MAR",
    "GM", "F", "ROST", "ORLY", "AZO", "ULTA", "DHI", "LEN", "PHM", "NVR",
    "MGM", "LVS", "WYNN", "HLT", "H", "CCL", "RCL", "NCLH", "EXPE", "TRIP",
    # 필수소비재
    "WMT", "COST", "PG", "KO", "PEP", "PM", "MO", "MDLZ", "CL", "KMB",
    "GIS", "K", "CPB", "HRL", "SJM", "MKC", "CAG", "HSY", "MNST", "KHC",
    # 헬스케어
    "UNH", "LLY", "JNJ", "MRK", "ABBV", "TMO", "ABT", "DHR", "BMY", "AMGN",
    "GILD", "ISRG", "VRTX", "REGN", "ZTS", "BSX", "SYK", "ELV", "CI", "HCA",
    "MCK", "CVS", "IDXX", "BDX", "IQV", "DGX", "LH", "HOLX", "ALGN", "PODD",
    # 금융
    "BRK-B", "JPM", "V", "MA", "BAC", "GS", "MS", "WFC", "C", "AXP",
    "BLK", "SPGI", "MCO", "CME", "ICE", "CB", "PGR", "TRV", "ALL", "AFL",
    "MET", "PRU", "USB", "PNC", "TFC", "SCHW", "COF", "DFS", "SYF", "AMP",
    # 에너지
    "XOM", "CVX", "EOG", "SLB", "MPC", "VLO", "PSX", "PXD", "OXY", "COP",
    "HAL", "BKR", "DVN", "HES", "APA", "FANG", "MRO", "OKE", "WMB", "KMI",
    # 산업재
    "GE", "CAT", "RTX", "HON", "UPS", "LMT", "BA", "DE", "NOC", "GD",
    "FDX", "EMR", "ETN", "ITW", "PH", "ROK", "AME", "CARR", "OTIS", "TDG",
    "CTAS", "RSG", "WM", "VRSK", "EFX", "INFO", "CPRT", "FAST", "GWW", "MSC",
    # 소재
    "LIN", "APD", "SHW", "ECL", "DD", "DOW", "PPG", "NEM", "FCX", "NUE",
    "VMC", "MLM", "ALB", "CE", "EMN", "FMC", "IFF", "MOS", "CF", "LYB",
    # 부동산
    "PLD", "AMT", "CCI", "EQIX", "PSA", "WELL", "AVB", "EQR", "SPG", "O",
    "DLR", "ARE", "VTR", "NNN", "KIM", "REG", "BXP", "VNO", "SLG", "MAA",
    # 유틸리티
    "NEE", "DUK", "SO", "D", "SRE", "AEP", "EXC", "PCG", "XEL", "WEC",
    "ES", "ETR", "PPL", "AEE", "CMS", "LNT", "EVRG", "ATO", "NI", "PNW",
    # ETF/벤치마크
    "SPY", "QQQ", "IWM", "DIA", "VTI", "GLD", "TLT", "HYG", "EFA", "EEM",
]
from ginlix_data_sdk.calendar import filter_to_trading_days
from ginlix_data_sdk.providers import YFinanceCorporateActionProvider, YFinancePriceProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

BENCHMARKS = ["SPY", "QQQ", "IWM"]

price_provider = YFinancePriceProvider()
action_provider = YFinanceCorporateActionProvider()


def _actions_to_df(actions) -> pd.DataFrame:
    if not actions:
        return pd.DataFrame(
            columns=["ex_date", "event_type", "ratio", "amount", "currency", "notes"]
        )
    rows = [
        {
            "ex_date": a.ex_date,
            "event_type": a.event_type,
            "ratio": a.ratio,
            "amount": a.amount,
            "currency": a.currency,
            "notes": a.notes,
        }
        for a in actions
    ]
    df = pd.DataFrame(rows)
    df["ex_date"] = pd.to_datetime(df["ex_date"])
    return df.set_index("ex_date").sort_index()


def backfill_symbol(
    symbol: str,
    start: str,
    end: str,
    snapshot_id: str,
    is_benchmark: bool = False,
) -> bool:
    """Fetch and persist one symbol. Returns True on success."""
    try:
        log.info("fetching %s (benchmark=%s)", symbol, is_benchmark)
        df = price_provider.get_daily(symbol, start, end)
        if df.empty:
            log.warning("no data for %s — skipping", symbol)
            return False

        df = filter_to_trading_days(df)

        if is_benchmark:
            store.write_benchmark(symbol, df, snapshot_id)
        else:
            store.write_daily(symbol, df, snapshot_id)
            actions = action_provider.get_actions(symbol, start, end)
            actions_df = _actions_to_df(actions)
            store.write_corporate_actions(symbol, actions_df, snapshot_id)

        log.info("  saved %d bars for %s", len(df), symbol)
        return True
    except Exception as exc:
        log.error("failed to backfill %s: %s", symbol, exc)
        return False


async def register_snapshot_in_db(
    snapshot_id: str,
    start: str,
    end: str,
    symbols: list[str],
    storage_root: str,
) -> None:
    """Insert a row into backtest.data_snapshots."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
        import psycopg

        dsn = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
        if not dsn:
            log.warning("DATABASE_URL not set — skipping Postgres registration")
            return

        async with await psycopg.AsyncConnection.connect(dsn) as conn:
            await conn.execute(
                """
                INSERT INTO backtest.data_snapshots
                    (id, market, frequency, storage_root, start_date, end_date, n_symbols, description)
                VALUES (%s, 'us', '1d', %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    storage_root = EXCLUDED.storage_root,
                    end_date     = EXCLUDED.end_date,
                    n_symbols    = EXCLUDED.n_symbols
                """,
                (
                    snapshot_id,
                    storage_root,
                    start,
                    end,
                    len(symbols),
                    f"US daily snapshot backfilled {datetime.now(timezone.utc).isoformat()}",
                ),
            )
        log.info("registered snapshot %s in Postgres", snapshot_id)
    except Exception as exc:
        log.error("DB registration failed (non-fatal): %s", exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill US daily OHLCV Parquet snapshot")

    sym_group = parser.add_mutually_exclusive_group(required=True)
    sym_group.add_argument("--symbols", nargs="+", help="직접 종목 지정 (예: AAPL MSFT NVDA)")
    sym_group.add_argument("--sp500", action="store_true", help="S&P 500 전체 자동 수집 (Wikipedia)")

    parser.add_argument("--start", default="2015-01-01", help="시작일 YYYY-MM-DD")
    parser.add_argument("--end", default=date.today().isoformat(), help="종료일 YYYY-MM-DD")
    parser.add_argument("--snapshot-id", default=None, help="스냅샷 ID 직접 지정 (기본: us-{end})")
    parser.add_argument("--no-benchmarks", action="store_true", help="SPY/QQQ/IWM 벤치마크 스킵")
    parser.add_argument("--dry-run", action="store_true", help="DB 등록 스킵 (테스트용)")
    parser.add_argument("--workers", type=int, default=1, help="병렬 다운로드 스레드 수 (기본: 1)")
    args = parser.parse_args()

    # 종목 리스트 결정
    if args.sp500:
        symbols = fetch_sp500_symbols()
    else:
        symbols = args.symbols

    snapshot_id = args.snapshot_id or f"us-{args.end}"
    storage_root = str(store.snapshot_path(snapshot_id).resolve())

    log.info("snapshot: %s  [%s ~ %s]", snapshot_id, args.start, args.end)
    log.info("총 종목 수: %d개  (workers=%d)", len(symbols), args.workers)

    if args.dry_run:
        log.info("[DRY-RUN] 실제 다운로드 없이 종목 목록만 확인:")
        for i, s in enumerate(symbols[:20], 1):
            log.info("  %3d. %s", i, s)
        if len(symbols) > 20:
            log.info("  ... 외 %d개", len(symbols) - 20)
        log.info("[DRY-RUN] 실제 실행하려면 --dry-run 없이 다시 실행하세요.")
        return

    succeeded = []
    failed = []

    if args.workers > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(backfill_symbol, sym, args.start, args.end, snapshot_id): sym
                for sym in symbols
            }
            done = 0
            for future in as_completed(futures):
                sym = futures[future]
                ok = future.result()
                (succeeded if ok else failed).append(sym)
                done += 1
                if done % 50 == 0:
                    log.info("진행: %d/%d (성공 %d, 실패 %d)", done, len(symbols), len(succeeded), len(failed))
    else:
        for i, sym in enumerate(symbols, 1):
            ok = backfill_symbol(sym, args.start, args.end, snapshot_id)
            (succeeded if ok else failed).append(sym)
            if i % 50 == 0:
                log.info("진행: %d/%d (성공 %d, 실패 %d)", i, len(symbols), len(succeeded), len(failed))

    if not args.no_benchmarks:
        for bm in BENCHMARKS:
            ok = backfill_symbol(bm, args.start, args.end, snapshot_id, is_benchmark=True)
            if not ok:
                log.warning("benchmark %s failed", bm)

    store.write_manifest(
        snapshot_id=snapshot_id,
        symbols=succeeded,
        start_date=args.start,
        end_date=args.end,
        description=f"Backfilled via yfinance on {date.today()}",
    )
    log.info("manifest written to %s/MANIFEST.json", storage_root)

    if failed:
        log.warning("failed symbols (%d): %s", len(failed), failed)

    # Windows ProactorEventLoop is incompatible with psycopg async
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(
        register_snapshot_in_db(snapshot_id, args.start, args.end, succeeded, storage_root)
    )

    log.info(
        "done — %d/%d symbols succeeded. Run: from ginlix_data_sdk import parquet_store as store; "
        "store.load_prices(%r, %r)",
        len(succeeded),
        len(args.symbols),
        succeeded[:3],
        snapshot_id,
    )


if __name__ == "__main__":
    main()
