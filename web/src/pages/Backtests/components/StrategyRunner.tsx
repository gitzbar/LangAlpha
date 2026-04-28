import { useState } from 'react';
import type { RunRequest, StrategyInfo } from '../utils/api';

interface Props {
  strategies: Record<string, StrategyInfo>;
  snapshots: string[];
  onRun: (req: RunRequest) => void;
  loading: boolean;
}

const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'];
const MONTHS = [
  'january', 'february', 'march', 'april', 'may', 'june',
  'july', 'august', 'september', 'october', 'november', 'december',
];

export default function StrategyRunner({ strategies, snapshots, onRun, loading }: Props) {
  const [symbol, setSymbol] = useState('AAPL');
  const [strategy, setStrategy] = useState(Object.keys(strategies)[0] ?? 'streak');
  const [snapshotId, setSnapshotId] = useState(snapshots[0] ?? 'us-2026-04-24');
  const [params, setParams] = useState<Record<string, string | number>>({});

  const stratInfo = strategies[strategy];
  const defaultParams = stratInfo?.params ?? {};

  function getParam(key: string): string | number {
    return params[key] !== undefined ? params[key] : (defaultParams[key] as string | number);
  }

  function setParam(key: string, value: string | number) {
    setParams((p) => ({ ...p, [key]: value }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const finalParams: Record<string, unknown> = {};
    for (const key of Object.keys(defaultParams)) {
      const v = getParam(key);
      // coerce numbers
      finalParams[key] = typeof defaultParams[key] === 'number' ? Number(v) : v;
    }
    onRun({ symbol: symbol.toUpperCase(), snapshot_id: snapshotId, strategy, params: finalParams });
  }

  function renderParamField(key: string, defaultVal: unknown) {
    const val = getParam(key);

    // Day select
    if (key.includes('day') && typeof defaultVal === 'string' && DAYS.includes(defaultVal)) {
      return (
        <div key={key} className="flex flex-col gap-1">
          <label className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
            {key.replace(/_/g, ' ')}
          </label>
          <select
            className="rounded-lg px-3 py-2 text-sm"
            style={{
              backgroundColor: 'var(--color-bg-input)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text-primary)',
            }}
            value={String(val)}
            onChange={(e) => setParam(key, e.target.value)}
          >
            {DAYS.map((d) => <option key={d} value={d}>{d.charAt(0).toUpperCase() + d.slice(1)}</option>)}
          </select>
        </div>
      );
    }

    // Month select
    if (key.includes('month') && typeof defaultVal === 'string') {
      return (
        <div key={key} className="flex flex-col gap-1">
          <label className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
            {key.replace(/_/g, ' ')}
          </label>
          <select
            className="rounded-lg px-3 py-2 text-sm"
            style={{
              backgroundColor: 'var(--color-bg-input)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text-primary)',
            }}
            value={String(val)}
            onChange={(e) => setParam(key, e.target.value)}
          >
            {MONTHS.map((m) => <option key={m} value={m}>{m.charAt(0).toUpperCase() + m.slice(1)}</option>)}
          </select>
        </div>
      );
    }

    // Direction select
    if (key === 'direction') {
      return (
        <div key={key} className="flex flex-col gap-1">
          <label className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
            direction
          </label>
          <select
            className="rounded-lg px-3 py-2 text-sm"
            style={{
              backgroundColor: 'var(--color-bg-input)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text-primary)',
            }}
            value={String(val)}
            onChange={(e) => setParam(key, e.target.value)}
          >
            <option value="red">Red (매수 반등)</option>
            <option value="green">Green (추세 추종)</option>
          </select>
        </div>
      );
    }

    // Number input
    if (typeof defaultVal === 'number') {
      return (
        <div key={key} className="flex flex-col gap-1">
          <label className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
            {key.replace(/_/g, ' ')}
          </label>
          <input
            type="number"
            className="rounded-lg px-3 py-2 text-sm"
            style={{
              backgroundColor: 'var(--color-bg-input)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text-primary)',
            }}
            value={String(val)}
            onChange={(e) => setParam(key, e.target.value)}
          />
        </div>
      );
    }

    return null;
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {/* Symbol */}
      <div className="flex flex-col gap-1">
        <label className="text-xs font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
          종목 (Symbol)
        </label>
        <input
          className="rounded-lg px-3 py-2 text-sm font-mono uppercase"
          style={{
            backgroundColor: 'var(--color-bg-input)',
            border: '1px solid var(--color-border)',
            color: 'var(--color-text-primary)',
          }}
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          placeholder="AAPL"
        />
      </div>

      {/* Snapshot */}
      {snapshots.length > 0 && (
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
            데이터 스냅샷
          </label>
          <select
            className="rounded-lg px-3 py-2 text-sm"
            style={{
              backgroundColor: 'var(--color-bg-input)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text-primary)',
            }}
            value={snapshotId}
            onChange={(e) => setSnapshotId(e.target.value)}
          >
            {snapshots.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      )}

      {/* Strategy */}
      <div className="flex flex-col gap-1">
        <label className="text-xs font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
          전략
        </label>
        <select
          className="rounded-lg px-3 py-2 text-sm"
          style={{
            backgroundColor: 'var(--color-bg-input)',
            border: '1px solid var(--color-border)',
            color: 'var(--color-text-primary)',
          }}
          value={strategy}
          onChange={(e) => { setStrategy(e.target.value); setParams({}); }}
        >
          {Object.entries(strategies).map(([k, v]) => (
            <option key={k} value={k}>{k} — {v.description}</option>
          ))}
        </select>
        {stratInfo && (
          <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>
            {stratInfo.description}
          </p>
        )}
      </div>

      {/* Dynamic params */}
      {Object.keys(defaultParams).length > 0 && (
        <div className="flex flex-col gap-3">
          <p className="text-xs font-semibold" style={{ color: 'var(--color-text-secondary)' }}>파라미터</p>
          <div className="grid grid-cols-2 gap-3">
            {Object.entries(defaultParams).map(([k, v]) => renderParamField(k, v))}
          </div>
        </div>
      )}

      {/* Submit */}
      <button
        type="submit"
        disabled={loading}
        className="rounded-lg py-2.5 text-sm font-semibold transition-opacity"
        style={{
          backgroundColor: 'var(--color-accent)',
          color: '#fff',
          opacity: loading ? 0.6 : 1,
          cursor: loading ? 'not-allowed' : 'pointer',
        }}
      >
        {loading ? '실행 중...' : '백테스트 실행'}
      </button>
    </form>
  );
}
