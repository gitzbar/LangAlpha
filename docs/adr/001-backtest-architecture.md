# ADR 001: 백테스팅 플랫폼 아키텍처

- **상태**: 승인됨 (Accepted)
- **날짜**: 2026-04-23
- **다음 단계**: Phase 0 착수

---

## 맥락 (Context)

LangAlpha는 LangGraph + PTC(Programmatic Tool Calling) 패턴 기반의 AI 금융 리서치 에이전트이다. 여기에 **백테스팅 역량**을 추가하여 퀀트 리서치 전용 플랫폼으로 확장하려 한다.

핵심 제약: **이 시스템은 공개 제품이 아니라 단일 사용자 리서치 도구**이다. 따라서 멀티유저, 샌드박싱, 악의적 코드 방어 등은 고려하지 않는다.

## 목표 (Goals)

1. 미국 주식 시장에 대해 임의의 Python 전략을 정의하고 과거 데이터로 검증
2. 다음 유스케이스를 v1부터 지원:
   - 개별 종목 백테스트
   - 다종목 포트폴리오 + 리밸런싱
   - 파라미터 스윕
   - 롤링 백테스트 (예: 5년 윈도우를 1개월 단위로 이동)
   - 레짐 분석 (VIX 구간, 강세/약세장, 금리 방향 등 버킷별 성과)
   - 캘린더 효과 검증 (요일/월/특정 주기)
3. 결과의 **신뢰도 보장**: look-ahead 방지, corporate action 올바른 처리, 재현 가능
4. Jupyter 노트북 기반 빠른 반복 연구
5. (Phase 3 이후) AI 에이전트가 채팅에서 호출 가능 (MCP 경유)
6. 과거 실험 결과를 Postgres에 영속 저장, 비교/재현

## 비목표 (Non-goals)

- 멀티유저, 공개 API, 권한 시스템
- 악의적 코드 샌드박싱
- 실시간 페이퍼 트레이딩 / 실거래 연동
- 미국 외 시장 (v1)
- v1부터 Monaco 기반 전용 웹 에디터

---

## 주요 결정 (Decisions)

### D1. 전략 정의는 Python 코드

구조화된 JSON/DSL은 복잡한 퀀트 전략(다인자 모델, 롤링 상관관계, 레짐 분기 등)을 표현하기에 한계가 있고, 빠르게 "작은 언어 만들기 지옥"으로 수렴한다. 전략의 1급 표현은 **Python 코드**.

### D2. 신뢰도 규칙은 프레임워크가 강제

사용자 코드가 아니라 프레임워크 레이어에서 다음을 자동으로 적용:

- 주문 체결 타이밍 (디폴트: 다음 바 시가)
- 수수료/슬리피지 (주문 처리 시)
- 가격 조정 (데이터 피드에서 이미 처리됨)
- 거래 달력 (바 자체가 휴장일을 제외)
- Look-ahead 방지 (API 수준에서 미래 데이터 접근 불가)

### D3. 엔진: vectorbt

리서치 유스케이스(다종목, 롤링, 파라미터 스윕, 캘린더/레짐 분석)가 벡터화 연산과 맞물린다. 이벤트 기반 엔진 대비 수십~수백 배 성능.

우리는 vectorbt 위에 **얇은 래퍼 레이어**를 만들어 신뢰도 규칙을 주입하고 연구 패턴을 짧게 쓸 수 있게 한다. 연구자는 vectorbt를 직접 만질 수도 있고 래퍼만 써도 됨.

### D4. 구조: 라이브러리 우선, 서비스는 나중

`libs/ginlix_backtest/` 파이썬 패키지가 **1급 인터페이스**. 주요 작업은 Jupyter 노트북에서 직접 수행. HTTP 서비스(`backtest_service/`)와 MCP 서버는 Phase 3에서 에이전트/웹 연동이 필요해진 시점에 추가.

### D5. 공용 데이터 SDK 분리

`libs/ginlix_data_sdk/` 공용 패키지로 데이터 접근을 일원화. `src/server/`와 `libs/ginlix_backtest/` 가 직접 import하지 않고 SDK를 경유. 모노레포 내에서 uv workspace member로 구성.

### D6. 내부 실행은 항상 job 기반 (서비스 단계에서 적용)

Phase 3에서 서비스가 생기면, 단순/복잡 구분 없이 모든 백테스트는 내부 job 큐를 경유. 외부 API는 "짧으면 즉시 결과, 길면 task_id" UX를 제공하되 내부 코드 경로는 하나.

### D7. DB 스키마 분리

`backtest.*` 스키마에 모든 백테스트 관련 테이블을 격리. 기존 `public` 스키마와 섞지 않음.

### D8. 미국 시장 전용 v1

거래 달력, 수수료, 배당세, corporate action 규칙이 시장별로 다르다. 한 시장에 집중하여 신뢰도를 먼저 확보.

### D9. 데이터 공급자: 기존 `src/data_client/` 재사용 선호

원칙은 "가능하면 재사용, 불가하면 분리". Phase 0 초반에 기존 미국 주식 파이프라인의 성숙도를 평가:

- 조정/비조정 가격 양쪽 접근 가능한지
- Corporate actions (splits/dividends) 메타데이터 제공 여부
- 과거 데이터 백필 범위 및 데이터 품질
- 레이트 리밋 및 안정성

평가 결과 품질이 충분하면 **`ginlix_data_sdk` 가 기존 data_client를 감싸는 형태**로 구성. 부족하면 신규 fetcher 구현. 어느 쪽이든 SDK 인터페이스는 동일하게 유지되어 downstream 코드는 영향받지 않음.

### D10. 포트폴리오 초기 자본 디폴트: $100,000

전략 파라미터에서 오버라이드 가능. $100k는 미국 리테일 계좌의 중간값 수준이며 수수료 0 환경에서 포지션 사이징 부담이 크지 않음. Sharpe 같은 상대 지표는 초기 자본과 무관하므로 연구용으로 충분.

### D11. 벤치마크 디폴트: SPY

모든 백테스트 리포트에서 SPY 대비 초과수익, 정보비율(IR), 상관관계, Rolling beta를 자동 계산. 전략 파라미터에서 다른 벤치마크(`QQQ`, `IWM`, 사용자 정의 시리즈 등)로 오버라이드 가능.

### D12. 데이터 저장: Parquet + Postgres 메타데이터

대량 시계열(OHLCV)을 Postgres에 직접 넣지 않음. **Parquet 파일**로 저장하고 **메타데이터만 Postgres**에 기록.

**이유**:
- Parquet은 컬럼 기반 + 압축 → 동일 데이터가 10배 이상 작음
- pandas/vectorbt가 Parquet을 네이티브로 빠르게 읽음
- 대량 symbol 한번에 로드 시 Postgres 쿼리 대비 수십 배 빠름
- 버저닝이 자연스러움 (스냅샷 디렉토리 통째로 보존)
- Postgres는 메타/job/trades/artifacts 등 관계형 데이터만 담당 → 역할 분리 명확

**레이아웃**은 아래 "데이터 저장 레이아웃" 섹션 참조.

---

## 신뢰도 규칙 (Reliability Rules)

### R1. 가격 데이터

- **저장**: unadjusted OHLCV + 별도 `corporate_actions` 테이블
- **신호 계산용 시리즈**: split-adjusted, dividend-unadjusted (사용자가 본 차트와 동일한 모양)
- **수익률 계산**: 배당은 ex-date에 현금으로 계좌 적립 (price return + dividend cash = total return)
- **타임스탬프 규칙**: 바 **종료 시각**, UTC 저장, 로컬(ET) 표시

### R2. 수수료 / 슬리피지 (US 기본값)

| 항목 | 디폴트 | 비고 |
|---|---|---|
| Commission | 0 | IBKR retail 기준 |
| SEC/TAF fee | 매도 0.00278% | 옵션 |
| Slippage | 3 bps 고정 | 전략 메타에서 오버라이드 가능 |
| Slippage 모델 | fixed bps | v1; volume-dependent는 v2+ |

### R3. 거래 달력

- 라이브러리: `exchange_calendars` (NYSE/NASDAQ)
- 휴장일에 발생한 시그널: **다음 개장일로 이월** 또는 **폐기** — 전략 설정에서 선택
- 바 자체는 프레임워크가 달력으로 필터링 (사용자 코드는 거래일 바만 받음)

### R4. Corporate Actions

| 이벤트 | 처리 |
|---|---|
| 주식분할 | 가격·수량 자동 조정 |
| 현금배당 | ex-date에 포지션 비율대로 현금 적립 |
| 주식배당 | 분할과 동일 처리 |
| 유상증자 | 해당 기간 해당 종목 백테스트 거부 + 경고 |
| 스핀오프 | 해당 기간 거부 또는 이벤트 직전 강제 청산 옵션 |
| 상장폐지 | 마지막 거래일 종가로 강제 청산, 결과에 명시 |

**원칙**: 애매한 경우는 보수적으로 거부. "결과가 나왔다 = 믿을 만하다"가 되도록.

### R5. Look-ahead 방지

API 수준에서 강제:
- `self.data.close[-1]` 은 오직 현재 바까지만 접근
- 미래 데이터를 조회할 수 있는 메서드를 **프레임워크가 제공하지 않음**
- 벡터화 경로에서도 `shift(1)` 을 프레임워크가 자동 삽입 (시그널 → 다음 바 체결)

### R6. 생존편향 (Survivorship Bias)

- v1: 사용자가 명시한 심볼 리스트만 사용
- v2+: 지수 시점별 구성 종목 스냅샷 추가 (S&P 500 historical constituents 등)

### R7. 재현성 (Reproducibility)

모든 job에 다음을 기록:

- `code_hash` — 전략 코드 SHA-256
- `framework_version` — `ginlix_backtest` 버전
- `data_snapshot_version` — 데이터 파이프라인 스냅샷 식별자 (예: `us-2026-04-23`)
- `seed` — 랜덤 사용 전략에 필수

동일 입력 + 동일 스냅샷 → 비트 단위 동일 결과.

---

## 컴포넌트 구조

```
quant all-in-one/
├── libs/
│   ├── ginlix_data_sdk/              # 공용 데이터 액세스 패키지
│   │   ├── pyproject.toml
│   │   └── src/ginlix_data_sdk/
│   │       ├── protocols.py          # 추상 인터페이스
│   │       ├── providers/            # yfinance, FMP, 내부 MCP HTTP
│   │       ├── schemas.py            # OHLCV, CorporateAction Pydantic
│   │       ├── calendar.py           # exchange_calendars 래퍼
│   │       └── adjust.py             # split/dividend 조정 유틸
│   │
│   └── ginlix_backtest/              # 백테스트 프레임워크
│       ├── pyproject.toml
│       └── src/ginlix_backtest/
│           ├── engine/
│           │   ├── portfolio.py      # vectorbt 기반 portfolio 팩토리
│           │   ├── signals.py        # 요일/월/주기 시그널 빌더
│           │   └── rolling.py        # 롤링 백테스트 유틸
│           ├── fees.py               # FeeModel, SlippageModel
│           ├── calendar.py           # NYSE 달력, 체결 타이밍
│           ├── data_feed.py          # adjusted/unadjusted, corp actions
│           ├── analysis/
│           │   ├── regime.py         # VIX/이동평균/금리 버킷팅
│           │   ├── stats.py          # bootstrap, Monte Carlo, t-test
│           │   └── tearsheet.py      # 표준 리포트
│           └── io/
│               └── persist.py        # DB 저장/조회
│
├── backtest_service/                 # (Phase 3) FastAPI :8001
│   ├── main.py
│   ├── worker.py                     # RQ 워커
│   └── Dockerfile
│
├── mcp_servers/
│   └── backtest_mcp_server.py        # (Phase 3) 에이전트용 MCP
│
├── src/server/app/
│   └── backtests.py                  # (Phase 3) REST 프록시
│
├── migrations/versions/
│   └── XXX_backtest_schema.py        # Phase 0
│
└── docs/adr/
    └── 001-backtest-architecture.md  # 이 문서
```

---

## 데이터 저장 레이아웃

### Parquet 데이터셋 (대량 시계열)

```
data/                              # 레포 루트의 .gitignore 에 포함
└── snapshots/
    └── us-2026-04-23/             # data_snapshot_version
        ├── daily/
        │   ├── AAPL.parquet       # 종목별 파일 (전체 기간)
        │   ├── MSFT.parquet
        │   └── ...
        ├── corporate_actions/
        │   ├── AAPL.parquet       # splits + dividends + 기타 이벤트
        │   └── ...
        ├── benchmarks/
        │   ├── SPY.parquet
        │   ├── QQQ.parquet
        │   └── IWM.parquet
        └── MANIFEST.json          # 스냅샷 메타 (날짜 범위, 심볼 수, 생성 시각 등)
```

**파일 스키마**:

- `daily/{symbol}.parquet`:
  ```
  columns: [timestamp (UTC), open, high, low, close, volume,
            adj_close, split_adj_close]
  index:   timestamp
  dtype:   float64 for prices, int64 for volume
  sort:    ascending by timestamp
  ```
- `corporate_actions/{symbol}.parquet`:
  ```
  columns: [ex_date, event_type (split|dividend|spinoff|merger|delisting),
            ratio (for splits), amount (for dividends),
            currency, notes]
  ```
- `benchmarks/{symbol}.parquet`: `daily/` 와 동일 스키마

**운영 원칙**:
- 각 `snapshot` 디렉토리는 **불변 (immutable)**. 데이터 업데이트는 새 스냅샷을 만들고 이전 스냅샷을 당분간 보존.
- 파일 단위 append 는 하지 않음. 대신 scheduled backfill 스크립트가 새 스냅샷 생성.
- 압축: snappy (빠름) 또는 zstd (작음). 기본 snappy.

### Postgres (메타 + 관계형 데이터)

모든 관계형 데이터와 스냅샷 메타데이터는 Postgres `backtest.*` 스키마에 저장.

## 데이터베이스 스키마 (초안 — Phase 0에서 확정)

```sql
CREATE SCHEMA backtest;

-- 데이터 스냅샷 메타 (Parquet 데이터셋을 가리킴)
CREATE TABLE backtest.data_snapshots (
    id            TEXT PRIMARY KEY,           -- "us-2026-04-23"
    market        TEXT NOT NULL,              -- "us"
    frequency     TEXT NOT NULL,              -- "1d" | "1h" | "5m"
    storage_root  TEXT NOT NULL,              -- 로컬 경로 또는 S3 URI
    start_date    DATE NOT NULL,
    end_date      DATE NOT NULL,
    n_symbols     INT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    description   TEXT
);

-- 재사용 가능한 전략 정의
CREATE TABLE backtest.strategies (
    id                UUID PRIMARY KEY,
    name              TEXT NOT NULL,
    description       TEXT,
    code              TEXT NOT NULL,
    code_hash         TEXT NOT NULL,
    framework_version TEXT NOT NULL,
    params_schema     JSONB,
    tags              TEXT[],
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    archived_at       TIMESTAMPTZ
);

-- 실행 요청 (한 번의 백테스트 실행 단위)
CREATE TABLE backtest.jobs (
    id                    UUID PRIMARY KEY,
    strategy_id           UUID REFERENCES backtest.strategies(id),
    params                JSONB NOT NULL,    -- dates, symbols, fees, slippage, seed, ...
    status                TEXT NOT NULL,     -- queued|running|succeeded|failed|canceled
    data_snapshot_id      TEXT NOT NULL REFERENCES backtest.data_snapshots(id),
    benchmark             TEXT DEFAULT 'SPY',
    initial_capital       NUMERIC DEFAULT 100000,
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    started_at            TIMESTAMPTZ,
    finished_at           TIMESTAMPTZ,
    error                 TEXT
);

-- 종목별 또는 포트폴리오 전체 실행 결과 요약
CREATE TABLE backtest.runs (
    id         UUID PRIMARY KEY,
    job_id     UUID REFERENCES backtest.jobs(id) ON DELETE CASCADE,
    symbol     TEXT,             -- NULL이면 포트폴리오 전체
    metrics    JSONB NOT NULL,   -- sharpe, cagr, max_dd, win_rate, sortino, ...
    n_trades   INT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 체결 내역 (감사/디버깅용)
CREATE TABLE backtest.trades (
    id            UUID PRIMARY KEY,
    run_id        UUID REFERENCES backtest.runs(id) ON DELETE CASCADE,
    symbol        TEXT NOT NULL,
    side          TEXT NOT NULL,  -- long_open | long_close | short_open | short_close
    entry_ts      TIMESTAMPTZ NOT NULL,
    entry_price   NUMERIC,
    exit_ts       TIMESTAMPTZ,
    exit_price    NUMERIC,
    qty           NUMERIC,
    pnl           NUMERIC,
    fees          NUMERIC,
    slippage_cost NUMERIC,
    reason        TEXT
);

-- 에쿼티 커브, 포지션 히스토리, 차트 등 대용량 아티팩트
CREATE TABLE backtest.artifacts (
    id           UUID PRIMARY KEY,
    job_id       UUID REFERENCES backtest.jobs(id) ON DELETE CASCADE,
    run_id       UUID REFERENCES backtest.runs(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL,  -- equity_curve | positions | chart_svg | logs
    storage_uri  TEXT NOT NULL,  -- local path or S3 URI
    content_type TEXT,
    size_bytes   BIGINT,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 사용 예시 (목표 API)

### 캘린더 효과 검증

```python
from ginlix_backtest import data, engine, analysis

prices = data.load_universe("sp500", start="2005-01-01", end="2025-01-01")

signals = engine.signals.weekday_pattern(
    prices, buy="Mon open", sell="Fri close"
)

pf = engine.portfolio.from_signals(
    prices, signals,
    rebalance="weekly",
    fees=engine.fees.US_DEFAULT,
)

print(pf.stats())
analysis.regime.by_vix(pf)
analysis.stats.bootstrap_pval(pf)
pf.persist(name="Monday Effect SP500 2005-2025", tags=["calendar_effect"])
```

### 5년 롤링 백테스트

```python
from ginlix_backtest.engine import rolling

results = rolling.backtest(
    strategy_fn=my_golden_cross,
    prices=prices,
    window="5Y",
    step="1M",
    start="2000",
    end="2025",
)

results.plot_metric_distribution("sharpe")
results.worst_windows(n=10)
results.stability_score()
```

### 리밸런싱 포트폴리오

```python
pf = engine.portfolio.from_weights(
    prices=prices,
    weights={"SPY": 0.6, "TLT": 0.4},
    rebalance="quarterly",
    fees=engine.fees.US_DEFAULT,
)
```

### 전략 클래스 (경로 의존 로직이 필요할 때)

```python
from ginlix_backtest import Strategy
from ginlix_backtest.indicators import sma

class GoldenCross(Strategy):
    def setup(self):
        self.fast = sma(self.data.close, 50)
        self.slow = sma(self.data.close, 200)

    def on_bar(self, bar):
        if self.fast[-1] > self.slow[-1] and self.fast[-2] <= self.slow[-2]:
            if not self.position:
                self.buy(pct_equity=1.0)
        elif self.fast[-1] < self.slow[-1] and self.position:
            self.close()
```

---

## Phase 계획

### Phase 0 — 기반 (Foundation)

1. **기존 `src/data_client/` 미국 주식 파이프라인 평가** — D9 참조. 재사용 여부 결정.
2. **uv workspace 구성** — `libs/ginlix_data_sdk/`, `libs/ginlix_backtest/` 를 workspace member 로 등록.
3. **`libs/ginlix_data_sdk/` 스켈레톤**:
   - `protocols.py` — `PriceProvider`, `CorporateActionProvider` 추상 인터페이스
   - `providers/` — 선택된 공급자 구현
   - `parquet_store.py` — 스냅샷 읽기/쓰기
4. **`libs/ginlix_backtest/` 신뢰도 규칙 구현**:
   - `calendar.py` — `exchange_calendars` NYSE 래퍼, 체결 타이밍 유틸
   - `fees.py` — `US_DEFAULT` FeeModel, SlippageModel
   - `data_feed.py` — split-adjusted 시리즈 생성, 배당 이벤트 타임라인
5. **Alembic 마이그레이션** — `backtest.*` 스키마 + 모든 테이블 (data_snapshots 포함)
6. **미국 주식 데이터 백필 스크립트** — 스냅샷 디렉토리 생성, Parquet 파일 작성, Postgres 메타 등록
7. **`pyproject.toml` 의존성**: `vectorbt`, `exchange_calendars`, `pyarrow`, `pandas>=2.0`
8. **`.gitignore` 에 `data/` 추가**

**완료 기준**:
- 스냅샷 `us-YYYY-MM-DD` 가 로컬 파일시스템과 Postgres 양쪽에 존재
- `from ginlix_backtest import data; prices = data.load_prices(["AAPL", "MSFT"], snapshot="us-2026-04-23")` 가 정상 동작
- 로드된 시리즈가 NYSE 거래일만 포함하며 split/dividend 메타가 동반됨

### Phase 1 — 기본 백테스트

- `engine.portfolio.from_signals` — vectorbt 래퍼
- `Strategy` 베이스 클래스 (경로 의존 전략용)
- 단일 종목 + 다종목 포트폴리오
- 기본 지표 (`sma`, `ema`, `rsi`, `atr`, `bollinger`)
- 노트북 예제: golden cross, 모멘텀
- 결과 영속화 (`io.persist`)

**완료 기준**: 예제 노트북이 끝까지 실행되고, DB에 결과가 저장되며, 동일 job을 다시 실행하면 동일 결과가 나옴.

### Phase 2 — 연구 도구 (Research Toolkit)

- `engine.rolling` 롤링 백테스트
- `analysis.regime` 레짐 분석 (VIX, MA200 상하, 금리 방향)
- `analysis.stats` 통계적 유의성 (bootstrap, Monte Carlo, t-test)
- `engine.signals.weekday_pattern`, `monthly_pattern` 캘린더 효과 헬퍼
- 파라미터 스윕
- `analysis.tearsheet` 표준 리포트 (pyfolio-style)

**완료 기준**: "월요일 효과" 같은 전형적 리서치 질문을 한 노트북으로 수행 가능.

### Phase 3 — 서비스 레이어 (선택적)

- `backtest_service/` FastAPI :8001, RQ 워커
- `src/server/app/backtests.py` REST 프록시
- `mcp_servers/backtest_mcp_server.py` 에이전트 연동
- 에이전트 자연어 → 전략 코드 생성 → MCP 호출 flow

### Phase 4 — 웹 UI (선택적)

- 과거 실험 히스토리 브라우징
- 결과 비교 대시보드 (equity curve 오버레이, metric 표)
- (노트북으로 충분하다면 생략)

---

## 열린 결정 (Open Decisions)

주요 결정(D1~D12)은 모두 확정됨. Phase 0 진행 중 확인이 필요한 **검증 항목**만 남아 있음:

1. **기존 `src/data_client/` 재사용 가능성 평가** (D9 참조). Phase 0 최초 작업. 결과에 따라:
   - 재사용: `ginlix_data_sdk` 가 기존 클라이언트를 provider 구현 하나로 래핑
   - 분리: `ginlix_data_sdk` 내부에 신규 fetcher 구현
2. **Parquet 압축 방식**: snappy(기본) vs zstd(파일 크기 우선). Phase 0 백필 시 크기/속도 측정 후 확정.
3. **데이터 스냅샷 주기**: 월 1회 vs 분기 1회 vs 수동. 초기엔 수동, 사용 패턴 보고 자동화 판단.

구현 중 새로 발견되는 설계 사안은 **ADR 개정** 또는 **새 ADR 추가**로 기록.

---

## 참고

- 이 ADR은 합의된 설계를 기록한 것으로, Phase 0 착수 이전이다.
- 구현 중 발견되는 사안은 **ADR 개정** 또는 **새 ADR 추가**로 문서화한다 (예: `002-data-storage-decision.md`).
- 기본 CLAUDE.md에 이 문서로의 포인터를 추가하여 향후 Claude Code 세션이 자연스럽게 로드하도록 한다.
