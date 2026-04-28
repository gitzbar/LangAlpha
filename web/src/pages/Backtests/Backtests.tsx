import { useState, useEffect } from 'react';
import { TrendingUp, AlertCircle, ServerOff } from 'lucide-react';
import { backtestApi, type RunResponse, type StrategyInfo, type RunRequest } from './utils/api';
import StrategyRunner from './components/StrategyRunner';
import MetricsGrid from './components/MetricsGrid';
import EquityChart from './components/EquityChart';
import './Backtests.css';

type ServiceState = 'loading' | 'ok' | 'offline';

export default function Backtests() {
  const [serviceState, setServiceState] = useState<ServiceState>('loading');
  const [strategies, setStrategies] = useState<Record<string, StrategyInfo>>({});
  const [snapshots, setSnapshots] = useState<string[]>([]);

  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RunResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // On mount: check service health + load metadata
  useEffect(() => {
    async function init() {
      try {
        const [healthData, stratData, snapData] = await Promise.all([
          backtestApi.health(),
          backtestApi.strategies(),
          backtestApi.snapshots(),
        ]);
        setSnapshots(healthData.snapshot_ids);
        setStrategies(stratData.strategies);
        setSnapshots(snapData.map((s) => s.id));
        setServiceState('ok');
      } catch {
        setServiceState('offline');
      }
    }
    init();
  }, []);

  async function handleRun(req: RunRequest) {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const res = await backtestApi.run(req);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : '알 수 없는 오류');
    } finally {
      setRunning(false);
    }
  }

  // --- Offline state ---
  if (serviceState === 'offline') {
    return (
      <div className="backtests-page">
        <div className="backtests-offline">
          <ServerOff size={40} style={{ color: 'var(--color-text-secondary)' }} />
          <h2 className="text-lg font-semibold" style={{ color: 'var(--color-text-primary)' }}>
            백테스트 서비스 오프라인
          </h2>
          <p className="text-sm text-center" style={{ color: 'var(--color-text-secondary)' }}>
            아래 명령어로 서비스를 시작하세요:
          </p>
          <code
            className="text-xs rounded-lg px-4 py-3 block"
            style={{
              backgroundColor: 'var(--color-bg-input)',
              color: 'var(--color-text-primary)',
              fontFamily: 'monospace',
            }}
          >
            uv run uvicorn backtest_service.main:app --port 8001 --reload
          </code>
        </div>
      </div>
    );
  }

  // --- Loading state ---
  if (serviceState === 'loading') {
    return (
      <div className="backtests-page">
        <div className="backtests-offline">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2" style={{ borderColor: 'var(--color-accent)' }} />
          <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>서비스 연결 중...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="backtests-page">
      {/* Header */}
      <div className="backtests-header">
        <div className="flex items-center gap-2">
          <TrendingUp size={20} style={{ color: 'var(--color-accent)' }} />
          <h1 className="text-xl font-bold" style={{ color: 'var(--color-text-primary)' }}>
            백테스트
          </h1>
        </div>
        <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
          전략을 선택하고 과거 데이터로 성과를 검증하세요
        </p>
      </div>

      {/* Layout: sidebar runner + main results */}
      <div className="backtests-layout">
        {/* Left panel: runner form */}
        <aside className="backtests-sidebar">
          <div
            className="rounded-xl p-5"
            style={{ backgroundColor: 'var(--color-bg-card)', border: '1px solid var(--color-border)' }}
          >
            <p className="text-sm font-semibold mb-4" style={{ color: 'var(--color-text-primary)' }}>
              전략 설정
            </p>
            {Object.keys(strategies).length > 0 ? (
              <StrategyRunner
                strategies={strategies}
                snapshots={snapshots}
                onRun={handleRun}
                loading={running}
              />
            ) : (
              <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                전략 목록 로드 중...
              </p>
            )}
          </div>
        </aside>

        {/* Right panel: results */}
        <main className="backtests-results">
          {/* Error */}
          {error && (
            <div
              className="rounded-xl p-4 flex items-start gap-3"
              style={{ backgroundColor: 'var(--color-bg-card)', border: '1px solid #f87171' }}
            >
              <AlertCircle size={18} className="text-red-400 mt-0.5 shrink-0" />
              <div>
                <p className="text-sm font-semibold text-red-400">백테스트 실패</p>
                <p className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>{error}</p>
              </div>
            </div>
          )}

          {/* Loading skeleton */}
          {running && (
            <div
              className="rounded-xl p-6 flex flex-col items-center gap-3"
              style={{ backgroundColor: 'var(--color-bg-card)', border: '1px solid var(--color-border)' }}
            >
              <div className="animate-spin rounded-full h-8 w-8 border-b-2" style={{ borderColor: 'var(--color-accent)' }} />
              <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                백테스트 실행 중...
              </p>
            </div>
          )}

          {/* Results */}
          {result && !running && (
            <div className="flex flex-col gap-5">
              <MetricsGrid
                metrics={result.metrics}
                benchmark={result.benchmark_metrics}
                symbol={result.symbol}
                strategy={result.strategy}
                start={result.start}
                end={result.end}
                nBars={result.n_bars}
              />
              {result.equity_curve.length > 0 && (
                <EquityChart data={result.equity_curve} benchmark="SPY" />
              )}
            </div>
          )}

          {/* Empty state */}
          {!result && !running && !error && (
            <div
              className="rounded-xl p-10 flex flex-col items-center gap-3 text-center"
              style={{ backgroundColor: 'var(--color-bg-card)', border: '1px solid var(--color-border)' }}
            >
              <TrendingUp size={36} style={{ color: 'var(--color-text-secondary)', opacity: 0.4 }} />
              <p className="text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                왼쪽에서 전략을 선택하고 실행해보세요
              </p>
              <p className="text-xs" style={{ color: 'var(--color-text-secondary)', opacity: 0.7 }}>
                Equity curve, Sharpe, CAGR, MDD, SPY 비교 결과가 표시됩니다
              </p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
