/** Backtest Service API — calls localhost:8001 directly (CORS open) */

const BASE = import.meta.env.VITE_BACKTEST_URL ?? 'http://localhost:8001';

export interface MetricsOut {
  total_return: number;
  cagr: number;
  sharpe: number;
  sortino: number;
  max_dd: number;
  n_trades: number;
  win_rate: number | null;
  calmar: number;
}

export interface BenchmarkMetricsOut {
  benchmark_total_return: number;
  excess_return: number;
  information_ratio: number;
  beta: number;
  correlation: number;
}

export interface EquityPoint {
  date: string;
  strategy: number;
  benchmark: number | null;
}

export interface RunResponse {
  symbol: string;
  strategy: string;
  params: Record<string, unknown>;
  snapshot_id: string;
  start: string;
  end: string;
  n_bars: number;
  metrics: MetricsOut;
  benchmark_metrics: BenchmarkMetricsOut | null;
  equity_curve: EquityPoint[];
}

export interface SnapshotOut {
  id: string;
  start_date: string;
  end_date: string;
  n_symbols: number;
  storage_root: string;
}

export interface StrategyInfo {
  description: string;
  params: Record<string, unknown>;
}

export interface RunRequest {
  symbol: string;
  snapshot_id: string;
  strategy: string;
  params: Record<string, unknown>;
  start?: string;
  end?: string;
  benchmark?: string;
  initial_capital?: number;
}

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

export const backtestApi = {
  health: () => fetchJSON<{ status: string; snapshot_ids: string[] }>('/health'),

  snapshots: () => fetchJSON<SnapshotOut[]>('/snapshots'),

  strategies: () =>
    fetchJSON<{ strategies: Record<string, StrategyInfo> }>('/backtest/strategies'),

  run: (req: RunRequest) =>
    fetchJSON<RunResponse>('/backtest/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }),
};
