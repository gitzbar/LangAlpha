"""Decision Memory — persist and recall backtest analyses per symbol.

Each symbol gets its own markdown file:
    data/memory/{SYMBOL}.md

Format:
    ## 2026-04-25T14:32 | streak | n_red=3, hold_days=3
    - Period   : 2015-01-02 ~ 2026-04-23 (2843 bars)
    - Sharpe   : 0.52  CAGR: 5.3%  MaxDD: -22.2%  Trades: 161
    - Notes    : 3연속 음봉 후 반등 확률 60%로 통계적 유의. 강세장에서만 작동.
    - Outcome  : [미기록] ← 나중에 실제 결과 업데이트
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

# 프로젝트 루트의 data/memory/
_REPO_ROOT   = Path(__file__).parents[1]
_MEMORY_ROOT = _REPO_ROOT / "data" / "memory"
_MEMORY_ROOT.mkdir(parents=True, exist_ok=True)


def _symbol_path(symbol: str) -> Path:
    return _MEMORY_ROOT / f"{symbol.upper()}.md"


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def save_analysis(
    symbol: str,
    strategy: str,
    params: dict,
    metrics: dict,
    period_start: str,
    period_end: str,
    n_bars: int,
    notes: str = "",
    benchmark_metrics: dict | None = None,
) -> str:
    """Append a backtest result to the symbol's memory file.

    Returns the path of the memory file written.
    """
    path = _symbol_path(symbol)
    now  = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")

    params_str = ", ".join(f"{k}={v}" for k, v in params.items())
    header = f"## {now} | {strategy} | {params_str}"

    m = metrics
    bm_line = ""
    if benchmark_metrics:
        bm_line = (
            f"\n- vs SPY    : excess={benchmark_metrics.get('excess_return', 0):.1%}"
            f"  IR={benchmark_metrics.get('information_ratio', 0):.2f}"
            f"  beta={benchmark_metrics.get('beta', 0):.2f}"
        )

    block = (
        f"\n{header}\n"
        f"- Period   : {period_start} ~ {period_end} ({n_bars} bars)\n"
        f"- Sharpe   : {m.get('sharpe', 0):.2f}"
        f"  CAGR: {m.get('cagr', 0):.1%}"
        f"  MaxDD: {m.get('max_dd', 0):.1%}"
        f"  Trades: {m.get('n_trades', 0)}"
        f"{bm_line}\n"
        f"- Notes    : {notes if notes else '(없음)'}\n"
        f"- Outcome  : [미기록]\n"
    )

    # 파일이 없으면 헤더 추가
    if not path.exists():
        path.write_text(
            f"# {symbol.upper()} Backtest Memory\n\n"
            f"이 파일은 자동으로 기록됩니다. 직접 편집해도 됩니다.\n",
            encoding="utf-8",
        )

    with path.open("a", encoding="utf-8") as f:
        f.write(block)

    return str(path)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def recall_analyses(symbol: str) -> str:
    """Return the full memory file for a symbol, or a 'no history' message."""
    path = _symbol_path(symbol)
    if not path.exists():
        return f"{symbol.upper()}에 대한 이전 분석 기록이 없습니다."
    content = path.read_text(encoding="utf-8")
    if not content.strip():
        return f"{symbol.upper()} 메모리 파일이 비어 있습니다."
    return content


def list_analyzed_symbols() -> list[str]:
    """Return symbols that have memory files."""
    return sorted(p.stem for p in _MEMORY_ROOT.glob("*.md"))


# ---------------------------------------------------------------------------
# Update outcome
# ---------------------------------------------------------------------------

def update_outcome(symbol: str, entry_date: str, actual_return: float, note: str = "") -> str:
    """Update the Outcome field for a specific entry_date in symbol's memory.

    Finds the block whose Period starts with entry_date and replaces
    its Outcome line.

    Args:
        symbol:        Ticker symbol.
        entry_date:    Start date of the backtest period (YYYY-MM-DD).
        actual_return: Actual realized return (e.g. 0.08 = 8%).
        note:          Optional note about the outcome.
    """
    path = _symbol_path(symbol)
    if not path.exists():
        return f"메모리 없음: {symbol}"

    content = path.read_text(encoding="utf-8")
    outcome_str = (
        f"{actual_return:.2%}"
        + (f" / {note}" if note else "")
    )

    # 해당 entry_date가 포함된 블록의 Outcome 교체
    pattern = rf"(- Period\s+:\s+{re.escape(entry_date)}.*?\n(?:.*\n)*?- Outcome\s+:\s*)\[미기록\]"
    new_content, count = re.subn(pattern, rf"\g<1>{outcome_str}", content, count=1)

    if count == 0:
        return f"'{entry_date}' 시작하는 기록을 찾지 못했습니다. 날짜를 확인해주세요."

    path.write_text(new_content, encoding="utf-8")
    return f"업데이트 완료: {symbol} / {entry_date} → {outcome_str}"
