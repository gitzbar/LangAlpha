"""Backtest MCP Server.

Lets the LangAlpha agent run quantitative backtests against local Parquet
snapshots by calling the backtest_service REST API (:8001).

Tools:
- run_backtest        : Run a strategy backtest and get performance metrics
- list_snapshots      : List available data snapshots (date ranges, symbols)
- list_symbols        : List symbols available in a given snapshot
- list_strategies     : List supported strategy types and their parameters
- run_parameter_sweep : Grid-search strategy parameters and get ranked results
- save_analysis       : Save backtest result + notes to persistent memory
- recall_analysis     : Recall all past backtest analyses for a symbol
- update_outcome      : Record actual realized return for a past analysis

Trading Journal:
- log_trade           : Record a buy or sell trade
- log_forex           : Record a currency exchange
- log_dividend        : Record dividend received
- log_note            : Record a free-form note or market observation
- show_journal        : Show recent journal entries
- journal_summary     : Portfolio summary from journal (positions, forex, dividends)

Setup (agent_config.yaml):
    - name: "backtest"
      transport: "stdio"
      command: "uv"
      args: ["run", "python", "mcp_servers/backtest_mcp_server.py"]
      env:
        BACKTEST_SERVICE_URL: "http://localhost:8001"
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

# repo root on path so backtest_service.memory is importable
sys.path.insert(0, str(Path(__file__).parents[1]))

import httpx
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_BASE_URL = os.environ.get("BACKTEST_SERVICE_URL", "http://localhost:8001").rstrip("/")
_TIMEOUT  = 120.0  # backtests can take a few seconds

mcp = FastMCP("BacktestMCP")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(path: str, **params) -> dict:
    with httpx.Client(timeout=_TIMEOUT) as client:
        r = client.get(f"{_BASE_URL}{path}", params=params)
        r.raise_for_status()
        return r.json()


def _post(path: str, body: dict) -> dict:
    with httpx.Client(timeout=_TIMEOUT) as client:
        r = client.post(f"{_BASE_URL}{path}", json=body)
        r.raise_for_status()
        return r.json()


def _fmt_pct(v: float) -> str:
    return f"{v:.1%}"


def _fmt_metrics(m: dict) -> str:
    lines = [
        f"  Sharpe ratio : {m['sharpe']:.2f}",
        f"  CAGR         : {_fmt_pct(m['cagr'])}",
        f"  Total return : {_fmt_pct(m['total_return'])}",
        f"  Max drawdown : {_fmt_pct(m['max_dd'])}",
        f"  Sortino      : {m['sortino']:.2f}",
        f"  Calmar       : {m['calmar']:.2f}",
        f"  Win rate     : {_fmt_pct(m['win_rate']) if m.get('win_rate') else 'n/a'}",
        f"  Num trades   : {m['n_trades']}",
    ]
    return "\n".join(lines)


def _fmt_bm(bm: dict | None) -> str:
    if not bm:
        return "  (no benchmark data)"
    return (
        f"  Benchmark return : {_fmt_pct(bm['benchmark_total_return'])}\n"
        f"  Excess return    : {_fmt_pct(bm['excess_return'])}\n"
        f"  Info ratio       : {bm['information_ratio']:.2f}\n"
        f"  Beta             : {bm['beta']:.2f}\n"
        f"  Correlation      : {bm['correlation']:.2f}"
    )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def run_backtest(
    symbol: str,
    strategy: str,
    params: Optional[str] = None,
    snapshot_id: str = "us-2026-04-24",
    start: Optional[str] = None,
    end: Optional[str] = None,
    benchmark: str = "SPY",
    initial_capital: float = 100_000.0,
) -> str:
    """Run a quantitative backtest for a given symbol and strategy.

    Returns performance metrics: Sharpe, CAGR, max drawdown, number of trades,
    win rate, and benchmark-relative metrics (excess return, beta, info ratio).

    Args:
        symbol:          Ticker symbol. Available: AAPL, MSFT, NVDA, GOOGL, AMZN, SPY, QQQ.
        strategy:        Strategy type. One of:
                           - weekday      : Buy on buy_day, sell on sell_day
                           - monthly      : Buy in buy_month, sell in sell_month (Sell in May etc.)
                           - streak       : Buy after N consecutive red/green candles
                           - ema_cross    : EMA golden/dead cross
                           - sma_cross    : SMA golden/dead cross (e.g. 50/200 Golden Cross)
                           - turn_of_month: Buy N days before month-end, sell N days after
        params:          JSON string of strategy parameters. Examples:
                           weekday      -> {"buy_day": "monday", "sell_day": "friday"}
                           monthly      -> {"buy_month": "november", "sell_month": "april"}
                           streak       -> {"n_red": 3, "hold_days": 3, "direction": "red"}
                           ema_cross    -> {"fast": 20, "slow": 60}
                           sma_cross    -> {"fast": 50, "slow": 200}
                           turn_of_month-> {"days_before_eom": 1, "days_after_som": 3}
        snapshot_id:     Data snapshot to use (default: us-2026-04-24).
        start:           Start date filter YYYY-MM-DD (optional).
        end:             End date filter YYYY-MM-DD (optional).
        benchmark:       Benchmark symbol for relative metrics (default: SPY).
        initial_capital: Starting capital in USD (default: 100000).

    Returns:
        Formatted performance report as text.
    """
    try:
        params_dict: dict[str, Any] = json.loads(params) if params else {}
    except json.JSONDecodeError as e:
        return f"Error: params must be a valid JSON string. Got: {params!r}\n{e}"

    body = {
        "symbol": symbol.upper(),
        "snapshot_id": snapshot_id,
        "strategy": strategy,
        "params": params_dict,
        "benchmark": benchmark,
        "initial_capital": initial_capital,
    }
    if start:
        body["start"] = start
    if end:
        body["end"] = end

    try:
        result = _post("/backtest/run", body)
    except httpx.HTTPStatusError as e:
        detail = e.response.json().get("detail", str(e))
        return f"Backtest failed: {detail}"
    except httpx.ConnectError:
        return (
            "Cannot connect to backtest service at "
            f"{_BASE_URL}. Make sure it is running:\n"
            "  uv run uvicorn backtest_service.main:app --port 8001"
        )

    lines = [
        f"=== Backtest Result: {result['symbol']} / {result['strategy']} ===",
        f"Period   : {result['start']} ~ {result['end']} ({result['n_bars']} bars)",
        f"Params   : {result['params']}",
        "",
        "--- Strategy Performance ---",
        _fmt_metrics(result["metrics"]),
        "",
        f"--- vs {benchmark} ---",
        _fmt_bm(result.get("benchmark_metrics")),
    ]
    return "\n".join(lines)


@mcp.tool()
def list_snapshots() -> str:
    """List all available data snapshots with date ranges and symbol counts.

    Use this before run_backtest to find valid snapshot_id values.
    """
    try:
        snapshots = _get("/snapshots")
    except httpx.ConnectError:
        return f"Cannot connect to backtest service at {_BASE_URL}."

    if not snapshots:
        return "No snapshots found. Run scripts/backfill_us_daily.py first."

    lines = ["Available data snapshots:", ""]
    for s in snapshots:
        lines.append(f"  ID          : {s['id']}")
        lines.append(f"  Date range  : {s['start_date']} ~ {s['end_date']}")
        lines.append(f"  Symbols     : {s['n_symbols']}")
        lines.append(f"  Storage     : {s['storage_root']}")
        lines.append("")
    return "\n".join(lines)


@mcp.tool()
def list_symbols(snapshot_id: str = "us-2026-04-24") -> str:
    """List symbols available in a given snapshot.

    Args:
        snapshot_id: Snapshot ID (get from list_snapshots).
    """
    try:
        from ginlix_data_sdk import parquet_store as store
        path = store.snapshot_path(snapshot_id) / "daily"
        if not path.exists():
            return f"Snapshot '{snapshot_id}' not found."
        symbols = sorted(p.stem for p in path.glob("*.parquet"))
        manifest = store.read_manifest(snapshot_id)
        start = manifest.get("start_date", "?")
        end   = manifest.get("end_date", "?")
        return (
            f"Snapshot: {snapshot_id}  ({start} ~ {end})\n"
            f"Symbols ({len(symbols)}): {', '.join(symbols)}"
        )
    except Exception as e:
        return f"Error reading snapshot: {e}"


@mcp.tool()
def list_strategies() -> str:
    """List all supported strategy types with parameter descriptions and defaults.

    Use this to understand what params to pass to run_backtest.
    """
    try:
        data = _get("/backtest/strategies")
    except httpx.ConnectError:
        return f"Cannot connect to backtest service at {_BASE_URL}."

    lines = ["Supported strategies:", ""]
    for name, info in data["strategies"].items():
        lines.append(f"  {name}")
        lines.append(f"    {info['description']}")
        lines.append(f"    Default params: {json.dumps(info['params'])}")
        lines.append("")
    return "\n".join(lines)


@mcp.tool()
def run_parameter_sweep(
    symbol: str,
    strategy: str,
    param_grid: str,
    snapshot_id: str = "us-2026-04-24",
    start: Optional[str] = None,
    end: Optional[str] = None,
    top_n: int = 5,
) -> str:
    """Grid-search strategy parameters and return ranked results by Sharpe ratio.

    Runs the strategy for every combination in param_grid and ranks them.
    Use this to find optimal parameters — but always check stability across
    multiple combinations (a strategy that only works at one exact parameter
    value is likely overfit).

    Args:
        symbol:     Ticker symbol.
        strategy:   Strategy type (same as run_backtest).
        param_grid: JSON string of {param: [value1, value2, ...]} for each param to sweep.
                    Example for streak: '{"n_red": [2,3,4,5], "hold_days": [1,3,5]}'
                    Example for ema_cross: '{"fast": [10,20], "slow": [50,100,200]}'
        snapshot_id: Data snapshot to use.
        start:      Start date filter YYYY-MM-DD (optional).
        end:        End date filter YYYY-MM-DD (optional).
        top_n:      How many top results to return (default: 5).

    Returns:
        Ranked parameter combinations with Sharpe, CAGR, max drawdown.
    """
    import itertools

    try:
        grid: dict[str, list] = json.loads(param_grid)
    except json.JSONDecodeError as e:
        return f"Error: param_grid must be valid JSON. {e}"

    param_names = list(grid.keys())
    combos = list(itertools.product(*grid.values()))
    total = len(combos)

    records = []
    for combo in combos:
        params_dict = dict(zip(param_names, combo))
        body: dict[str, Any] = {
            "symbol": symbol.upper(),
            "snapshot_id": snapshot_id,
            "strategy": strategy,
            "params": params_dict,
        }
        if start:
            body["start"] = start
        if end:
            body["end"] = end
        try:
            result = _post("/backtest/run", body)
            m = result["metrics"]
            records.append({
                "params": params_dict,
                "sharpe": m["sharpe"],
                "cagr": m["cagr"],
                "max_dd": m["max_dd"],
                "n_trades": m["n_trades"],
            })
        except Exception:
            records.append({"params": params_dict, "sharpe": float("nan"),
                            "cagr": float("nan"), "max_dd": float("nan"), "n_trades": 0})

    # Sort by Sharpe
    records.sort(key=lambda r: r["sharpe"] if r["sharpe"] == r["sharpe"] else -999, reverse=True)

    positive = sum(1 for r in records if r["sharpe"] > 0 and r["sharpe"] == r["sharpe"])
    stability = positive / total if total > 0 else 0

    lines = [
        f"=== Parameter Sweep: {symbol} / {strategy} ===",
        f"Total combinations: {total}  |  Stability: {stability:.0%} positive Sharpe",
        "",
        f"Top {min(top_n, len(records))} by Sharpe:",
        "",
    ]
    for i, r in enumerate(records[:top_n], 1):
        sharpe_str = f"{r['sharpe']:.2f}" if r["sharpe"] == r["sharpe"] else "n/a"
        lines.append(
            f"  #{i}  params={r['params']}"
            f"  sharpe={sharpe_str}"
            f"  cagr={_fmt_pct(r['cagr']) if r['cagr']==r['cagr'] else 'n/a'}"
            f"  max_dd={_fmt_pct(r['max_dd']) if r['max_dd']==r['max_dd'] else 'n/a'}"
            f"  trades={r['n_trades']}"
        )

    lines += [
        "",
        "Note: A strategy with high Sharpe at only ONE parameter combination is likely",
        "overfit. Look for strategies where many combinations show positive Sharpe.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Decision Memory tools
# ---------------------------------------------------------------------------

@mcp.tool()
def save_analysis(
    symbol: str,
    strategy: str,
    params: str,
    metrics: str,
    period_start: str,
    period_end: str,
    n_bars: int,
    notes: str = "",
    benchmark_metrics: Optional[str] = None,
) -> str:
    """Save a backtest result and your analysis notes to persistent memory.

    Call this after run_backtest to log the result so it can be recalled later.
    Memory persists across sessions — next time the same stock is analyzed,
    recall_analysis will surface this history automatically.

    Args:
        symbol:           Ticker symbol (e.g. AAPL).
        strategy:         Strategy type used (e.g. streak, ema_cross).
        params:           JSON string of strategy params used.
        metrics:          JSON string of metrics from run_backtest result.
        period_start:     Backtest start date (YYYY-MM-DD).
        period_end:       Backtest end date (YYYY-MM-DD).
        n_bars:           Number of bars in the backtest.
        notes:            Your analysis notes — key findings, caveats, regime context, etc.
        benchmark_metrics: JSON string of benchmark_metrics (optional).

    Returns:
        Confirmation with file path.
    """
    from backtest_service.memory import save_analysis as _save

    try:
        params_dict = json.loads(params) if params else {}
        metrics_dict = json.loads(metrics) if metrics else {}
        bm_dict = json.loads(benchmark_metrics) if benchmark_metrics else None
    except json.JSONDecodeError as e:
        return f"JSON 파싱 오류: {e}"

    path = _save(
        symbol=symbol,
        strategy=strategy,
        params=params_dict,
        metrics=metrics_dict,
        period_start=period_start,
        period_end=period_end,
        n_bars=n_bars,
        notes=notes,
        benchmark_metrics=bm_dict,
    )
    return f"저장 완료: {path}"


@mcp.tool()
def recall_analysis(symbol: str) -> str:
    """Recall all past backtest analyses and notes for a symbol.

    Call this at the START of any analysis session for a stock to surface
    what was previously found — strategies tested, outcomes, key insights.

    Args:
        symbol: Ticker symbol (e.g. AAPL).

    Returns:
        Full markdown history for the symbol, or a 'no history' message.
    """
    from backtest_service.memory import recall_analyses, list_analyzed_symbols

    symbols_with_memory = list_analyzed_symbols()
    result = recall_analyses(symbol)

    footer = ""
    if symbols_with_memory:
        footer = f"\n\n---\n메모리가 있는 종목: {', '.join(symbols_with_memory)}"

    return result + footer


@mcp.tool()
def update_outcome(
    symbol: str,
    entry_date: str,
    actual_return: float,
    note: str = "",
) -> str:
    """Record the actual realized return for a previously saved backtest analysis.

    Use this to close the loop — after a strategy was run and you observed
    what actually happened in the market, log the outcome here.
    This builds a track record that the agent can learn from over time.

    Args:
        symbol:        Ticker symbol.
        entry_date:    The period_start of the backtest to update (YYYY-MM-DD).
        actual_return: Actual realized return as a decimal (e.g. 0.08 = 8%).
        note:          What actually happened, why it worked or didn't.

    Returns:
        Confirmation message.
    """
    from backtest_service.memory import update_outcome as _update

    return _update(symbol=symbol, entry_date=entry_date,
                   actual_return=actual_return, note=note)


# ---------------------------------------------------------------------------
# Trading Journal tools
# ---------------------------------------------------------------------------

@mcp.tool()
def log_trade(
    action: str,
    symbol: str,
    quantity: float,
    price: float,
    currency: str = "USD",
    date: Optional[str] = None,
    broker: str = "",
    fees: float = 0.0,
    amount_krw: Optional[float] = None,
    rate: Optional[float] = None,
    notes: str = "",
) -> str:
    """매수 또는 매도 거래를 일지에 기록한다.

    Args:
        action:     'buy' (매수) 또는 'sell' (매도)
        symbol:     종목 코드 (예: AAPL, 005930.KS, BTC)
        quantity:   수량 (주 또는 단위)
        price:      1단위 가격
        currency:   통화 코드 (USD, KRW, JPY 등, 기본 USD)
        date:       거래일 YYYY-MM-DD (기본: 오늘)
        broker:     증권사/거래소 (예: 토스증권, 키움, 미래에셋, Fidelity)
        fees:       수수료 (해당 통화 기준)
        amount_krw: 원화 환산 총금액 (선택 — 달러 거래 시 원화 기록용)
        rate:       적용 환율 (선택)
        notes:      메모 (예: 이유, 전략, 시장 상황)
    """
    from backtest_service.journal import log_trade as _log
    if action not in ("buy", "sell"):
        return "오류: action 은 'buy' 또는 'sell' 이어야 합니다."
    return _log(
        action=action, symbol=symbol, quantity=quantity, price=price,
        currency=currency, date=date, broker=broker, fees=fees,
        amount_krw=amount_krw, rate=rate, notes=notes,
    )


@mcp.tool()
def log_forex(
    from_currency: str,
    to_currency: str,
    from_amount: float,
    rate: float,
    date: Optional[str] = None,
    broker: str = "",
    fees: float = 0.0,
    notes: str = "",
) -> str:
    """환전 내역을 일지에 기록한다.

    Args:
        from_currency: 환전 원본 통화 (예: KRW)
        to_currency:   환전 대상 통화 (예: USD)
        from_amount:   환전 원금 (from_currency 기준)
        rate:          적용 환율 — from 1단위당 to 금액
                       예) KRW->USD: 0.00074  /  USD->KRW: 1350.5
        date:          거래일 YYYY-MM-DD (기본: 오늘)
        broker:        은행 또는 증권사
        fees:          수수료 (from_currency 기준)
        notes:         메모
    """
    from backtest_service.journal import log_forex as _log
    return _log(
        from_currency=from_currency.upper(),
        to_currency=to_currency.upper(),
        from_amount=from_amount,
        rate=rate, date=date, broker=broker, fees=fees, notes=notes,
    )


@mcp.tool()
def log_dividend(
    symbol: str,
    amount: float,
    currency: str = "USD",
    date: Optional[str] = None,
    amount_krw: Optional[float] = None,
    tax_withheld: float = 0.0,
    notes: str = "",
) -> str:
    """배당금 수령을 일지에 기록한다.

    Args:
        symbol:       종목 코드
        amount:       수령 배당금 (세전)
        currency:     통화
        date:         수령일 YYYY-MM-DD
        amount_krw:   원화 환산 금액 (선택)
        tax_withheld: 원천징수 세금
        notes:        메모
    """
    from backtest_service.journal import log_dividend as _log
    return _log(
        symbol=symbol, amount=amount, currency=currency,
        date=date, amount_krw=amount_krw,
        tax_withheld=tax_withheld, notes=notes,
    )


@mcp.tool()
def log_note(
    content: str,
    date: Optional[str] = None,
    tags: Optional[str] = None,
) -> str:
    """자유 메모를 일지에 기록한다. 시장 관찰, 전략 아이디어, 뉴스 등.

    Args:
        content: 메모 내용 (자유 형식)
        date:    날짜 YYYY-MM-DD (기본: 오늘)
        tags:    쉼표로 구분된 태그 (예: 'AAPL,실적,어닝서프라이즈')
    """
    from backtest_service.journal import log_note as _log
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    return _log(content=content, date=date, tags=tag_list)


@mcp.tool()
def show_journal(last_n: int = 15) -> str:
    """최근 일지 항목을 조회한다.

    Args:
        last_n: 가져올 최근 항목 수 (기본 15)
    """
    from backtest_service.journal import show_journal as _show
    return _show(last_n=last_n)


@mcp.tool()
def journal_summary() -> str:
    """일지 전체 요약: 종목별 보유 포지션, 환전 내역, 배당 합계, 수수료 합계.

    CSV에서 자동으로 집계하므로 log_trade / log_forex / log_dividend 로
    기록한 항목만 반영된다.
    """
    from backtest_service.journal import journal_summary as _summary
    return _summary()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
