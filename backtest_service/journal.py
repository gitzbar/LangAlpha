"""Trading Journal — 실거래 일지 엔진.

파일 구조:
    data/journal/
        trades.md       -- 전체 일지 (사람이 직접 읽고 편집 가능)
        trades.csv      -- 분석용 CSV (자동 동기화)

항목 종류:
    trade   -- 매수/매도 (주식, ETF, 코인 등)
    forex   -- 환전 (USD/KRW 등)
    dividend-- 배당 수령
    fee     -- 수수료/세금 별도 기록
    note    -- 자유 메모 (시장 관찰, 전략 아이디어 등)
"""
from __future__ import annotations

import csv
import re
from datetime import datetime, timezone, date as date_type
import os
from pathlib import Path
from typing import Literal

_REPO_ROOT = Path(__file__).parents[1]
# DATA_ROOT env var → /app/data in Docker (volume-mounted to host Desktop/data)
# Fallback → repo_root/data (local dev)
_DATA_BASE    = Path(os.environ["DATA_ROOT"]) if "DATA_ROOT" in os.environ else _REPO_ROOT / "data"
_JOURNAL_ROOT = _DATA_BASE / "journal"
_JOURNAL_ROOT.mkdir(parents=True, exist_ok=True)

_MD_FILE  = _JOURNAL_ROOT / "trades.md"
_CSV_FILE = _JOURNAL_ROOT / "trades.csv"

EntryType = Literal["trade", "forex", "dividend", "fee", "note"]

# CSV 헤더
_CSV_HEADERS = [
    "date", "type", "symbol", "action", "quantity", "price",
    "currency", "amount_krw", "rate", "broker", "fees", "notes"
]


# ---------------------------------------------------------------------------
# 내부 유틸
# ---------------------------------------------------------------------------

def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")


def _ensure_md_header():
    if not _MD_FILE.exists():
        _MD_FILE.write_text(
            "# 매매 일지\n\n"
            "> 자동 생성 파일입니다. 직접 편집해도 됩니다.\n"
            "> MCP 도구로 항목을 추가하거나 파일을 직접 수정하세요.\n\n",
            encoding="utf-8",
        )


def _ensure_csv_header():
    if not _CSV_FILE.exists():
        with _CSV_FILE.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_HEADERS)
            writer.writeheader()


def _append_csv(row: dict):
    _ensure_csv_header()
    with _CSV_FILE.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_HEADERS)
        writer.writerow({h: row.get(h, "") for h in _CSV_HEADERS})


def _append_md(block: str):
    _ensure_md_header()
    with _MD_FILE.open("a", encoding="utf-8") as f:
        f.write(block + "\n")


# ---------------------------------------------------------------------------
# 매수 / 매도
# ---------------------------------------------------------------------------

def log_trade(
    action: Literal["buy", "sell"],
    symbol: str,
    quantity: float,
    price: float,
    currency: str = "USD",
    date: str | None = None,
    broker: str = "",
    fees: float = 0.0,
    amount_krw: float | None = None,
    rate: float | None = None,
    notes: str = "",
) -> str:
    """매수 또는 매도 기록.

    Args:
        action:     'buy' 또는 'sell'
        symbol:     종목 코드 (예: AAPL, 005930.KS)
        quantity:   수량 (주)
        price:      1주당 가격
        currency:   통화 (USD, KRW, JPY 등)
        date:       거래일 YYYY-MM-DD (기본: 오늘)
        broker:     증권사 (예: 토스증권, 키움, 미래에셋)
        fees:       수수료 (해당 통화 기준)
        amount_krw: 원화 환산 총금액 (선택)
        rate:       적용 환율 (선택, 예: 1350.5)
        notes:      메모
    """
    date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total = quantity * price
    action_kr = "매수" if action == "buy" else "매도"
    emoji = "🟢" if action == "buy" else "🔴"

    krw_line = ""
    if amount_krw:
        krw_line = f"\n  - 원화 환산 : {amount_krw:,.0f} KRW"
        if rate:
            krw_line += f"  (환율 {rate:,.2f})"

    fee_line = f"\n  - 수수료     : {fees:.2f} {currency}" if fees else ""

    block = (
        f"\n---\n"
        f"### {emoji} {action_kr} | {date} | {symbol}\n"
        f"  - 수량       : {quantity:,.4g}주\n"
        f"  - 단가       : {price:,.4f} {currency}\n"
        f"  - 총금액     : {total:,.4f} {currency}"
        f"{krw_line}"
        f"{fee_line}\n"
        f"  - 증권사     : {broker if broker else '미입력'}\n"
        f"  - 메모       : {notes if notes else '없음'}\n"
        f"  - 기록시각   : {_now_str()} UTC\n"
    )
    _append_md(block)
    _append_csv({
        "date": date, "type": "trade", "symbol": symbol.upper(),
        "action": action, "quantity": quantity, "price": price,
        "currency": currency, "amount_krw": amount_krw or "",
        "rate": rate or "", "broker": broker, "fees": fees, "notes": notes,
    })
    return f"{action_kr} 기록 완료: {symbol} {quantity}주 @ {price} {currency}"


# ---------------------------------------------------------------------------
# 환전
# ---------------------------------------------------------------------------

def log_forex(
    from_currency: str,
    to_currency: str,
    from_amount: float,
    rate: float,
    date: str | None = None,
    broker: str = "",
    fees: float = 0.0,
    notes: str = "",
) -> str:
    """환전 기록.

    Args:
        from_currency: 원본 통화 (예: KRW)
        to_currency:   대상 통화 (예: USD)
        from_amount:   환전 원금 (from_currency 기준)
        rate:          적용 환율 (from -> to 기준, 예: KRW->USD = 0.00074)
        date:          거래일 YYYY-MM-DD
        broker:        은행/증권사
        fees:          수수료 (from_currency 기준)
        notes:         메모
    """
    date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    to_amount = from_amount * rate

    block = (
        f"\n---\n"
        f"### 💱 환전 | {date} | {from_currency} → {to_currency}\n"
        f"  - 원금       : {from_amount:,.2f} {from_currency}\n"
        f"  - 환율       : {rate:,.6f} ({from_currency}/{to_currency})\n"
        f"  - 환전 후    : {to_amount:,.2f} {to_currency}\n"
        f"  - 수수료     : {fees:,.2f} {from_currency}\n" if fees else
        f"  - 수수료     : 없음\n"
        f"  - 은행/증권사: {broker if broker else '미입력'}\n"
        f"  - 메모       : {notes if notes else '없음'}\n"
        f"  - 기록시각   : {_now_str()} UTC\n"
    )
    _append_md(block)
    _append_csv({
        "date": date, "type": "forex",
        "symbol": f"{from_currency}/{to_currency}",
        "action": "exchange",
        "quantity": from_amount, "price": rate,
        "currency": from_currency,
        "amount_krw": to_amount if to_currency == "KRW" else "",
        "rate": rate, "broker": broker, "fees": fees, "notes": notes,
    })
    return (
        f"환전 기록 완료: {from_amount:,.0f} {from_currency} "
        f"→ {to_amount:,.2f} {to_currency} (환율 {rate})"
    )


# ---------------------------------------------------------------------------
# 배당
# ---------------------------------------------------------------------------

def log_dividend(
    symbol: str,
    amount: float,
    currency: str = "USD",
    date: str | None = None,
    amount_krw: float | None = None,
    tax_withheld: float = 0.0,
    notes: str = "",
) -> str:
    """배당 수령 기록."""
    date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    krw_line = f"\n  - 원화 환산 : {amount_krw:,.0f} KRW" if amount_krw else ""
    tax_line  = f"\n  - 원천징수  : {tax_withheld:.2f} {currency}" if tax_withheld else ""

    block = (
        f"\n---\n"
        f"### 💰 배당 | {date} | {symbol}\n"
        f"  - 수령금액   : {amount:.4f} {currency}"
        f"{krw_line}"
        f"{tax_line}\n"
        f"  - 메모       : {notes if notes else '없음'}\n"
        f"  - 기록시각   : {_now_str()} UTC\n"
    )
    _append_md(block)
    _append_csv({
        "date": date, "type": "dividend", "symbol": symbol.upper(),
        "action": "dividend", "quantity": "", "price": "",
        "currency": currency, "amount_krw": amount_krw or "",
        "rate": "", "broker": "", "fees": tax_withheld, "notes": notes,
    })
    return f"배당 기록 완료: {symbol} {amount:.4f} {currency}"


# ---------------------------------------------------------------------------
# 자유 메모
# ---------------------------------------------------------------------------

def log_note(
    content: str,
    date: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """자유 메모 기록 — 시장 관찰, 전략 아이디어, 뉴스 등.

    Args:
        content: 메모 내용
        date:    날짜 YYYY-MM-DD (기본: 오늘)
        tags:    태그 목록 (예: ['AAPL', '실적', '전략'])
    """
    date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tag_line = f"  - 태그 : {', '.join(f'#{t}' for t in tags)}\n" if tags else ""

    block = (
        f"\n---\n"
        f"### 📝 메모 | {date}\n"
        f"{tag_line}"
        f"  {content}\n"
        f"  - 기록시각 : {_now_str()} UTC\n"
    )
    _append_md(block)
    _append_csv({
        "date": date, "type": "note", "symbol": "",
        "action": "", "quantity": "", "price": "", "currency": "",
        "amount_krw": "", "rate": "", "broker": "", "fees": "",
        "notes": content,
    })
    return f"메모 기록 완료 ({date})"


# ---------------------------------------------------------------------------
# 조회
# ---------------------------------------------------------------------------

def show_journal(last_n: int = 20) -> str:
    """최근 N개 항목을 마크다운 원문으로 반환."""
    if not _MD_FILE.exists():
        return "일지가 비어 있습니다. log_trade / log_forex / log_note 로 기록을 시작하세요."
    content = _MD_FILE.read_text(encoding="utf-8")
    # --- 구분자로 블록 분리
    blocks = [b.strip() for b in content.split("---") if b.strip()]
    if not blocks:
        return "기록 없음"
    header = blocks[0]  # 파일 헤더 (# 매매 일지)
    entries = blocks[1:]
    recent = entries[-last_n:]
    return header + "\n\n---\n" + "\n\n---\n".join(recent)


def journal_summary() -> str:
    """CSV에서 집계: 종목별 매수/매도 수량, 환전 내역, 배당 합계."""
    if not _CSV_FILE.exists():
        return "기록 없음"

    trades: dict[str, dict] = {}   # symbol -> {bought, sold, avg_buy}
    forex_records: list[dict] = []
    dividends: dict[str, float] = {}
    total_fees: dict[str, float] = {}

    with _CSV_FILE.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            t = row["type"]
            sym = row["symbol"]

            if t == "trade":
                if sym not in trades:
                    trades[sym] = {"bought": 0, "sold": 0,
                                   "buy_cost": 0.0, "sell_proceeds": 0.0}
                qty   = float(row["quantity"] or 0)
                price = float(row["price"] or 0)
                if row["action"] == "buy":
                    trades[sym]["bought"] += qty
                    trades[sym]["buy_cost"] += qty * price
                else:
                    trades[sym]["sold"] += qty
                    trades[sym]["sell_proceeds"] += qty * price
                fee = float(row["fees"] or 0)
                total_fees[row["currency"]] = total_fees.get(row["currency"], 0) + fee

            elif t == "forex":
                forex_records.append({
                    "date": row["date"],
                    "pair": sym,
                    "from_amt": float(row["quantity"] or 0),
                    "rate": float(row["rate"] or 0),
                })

            elif t == "dividend":
                dividends[sym] = dividends.get(sym, 0) + float(row["quantity"] or 0)

    lines = ["## 일지 요약\n"]

    # 매매 포지션
    if trades:
        lines.append("### 종목별 포지션")
        for sym, d in sorted(trades.items()):
            net = d["bought"] - d["sold"]
            avg_buy = d["buy_cost"] / d["bought"] if d["bought"] > 0 else 0
            lines.append(
                f"  {sym}: 매수 {d['bought']:.4g}주 / 매도 {d['sold']:.4g}주 "
                f"/ 보유 {net:.4g}주 / 평균매수가 {avg_buy:.4f}"
            )

    # 환전
    if forex_records:
        lines.append("\n### 환전 내역")
        for r in forex_records:
            to_amt = r["from_amt"] * r["rate"]
            lines.append(f"  {r['date']} | {r['pair']} | {r['from_amt']:,.0f} → {to_amt:,.2f} (환율 {r['rate']})")

    # 배당
    if dividends:
        lines.append("\n### 배당 합계")
        for sym, total in sorted(dividends.items()):
            lines.append(f"  {sym}: {total:.4f}")

    # 수수료
    if total_fees:
        lines.append("\n### 수수료 합계")
        for cur, fee in sorted(total_fees.items()):
            lines.append(f"  {cur}: {fee:.4f}")

    if len(lines) == 1:
        return "아직 기록된 거래가 없습니다."

    return "\n".join(lines)
