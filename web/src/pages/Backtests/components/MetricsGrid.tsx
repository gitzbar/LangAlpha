import type { MetricsOut, BenchmarkMetricsOut } from '../utils/api';

interface Props {
  metrics: MetricsOut;
  benchmark?: BenchmarkMetricsOut | null;
  symbol: string;
  strategy: string;
  start: string;
  end: string;
  nBars: number;
}

function pct(v: number) {
  return `${(v * 100).toFixed(2)}%`;
}
function num(v: number, d = 2) {
  return v.toFixed(d);
}
function colorClass(v: number) {
  return v >= 0 ? 'text-green-500' : 'text-red-400';
}

interface CardProps {
  label: string;
  value: string;
  sub?: string;
  color?: string;
}

function StatCard({ label, value, sub, color }: CardProps) {
  return (
    <div
      className="rounded-xl p-4 flex flex-col gap-1"
      style={{ backgroundColor: 'var(--color-bg-card)', border: '1px solid var(--color-border)' }}
    >
      <span className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
        {label}
      </span>
      <span className={`text-xl font-bold ${color ?? ''}`}>{value}</span>
      {sub && (
        <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
          {sub}
        </span>
      )}
    </div>
  );
}

export default function MetricsGrid({ metrics: m, benchmark: bm, symbol, strategy, start, end, nBars }: Props) {
  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-lg font-bold" style={{ color: 'var(--color-text-primary)' }}>
            {symbol} · {strategy}
          </h2>
          <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
            {start} ~ {end} ({nBars.toLocaleString()} bars)
          </p>
        </div>
      </div>

      {/* Strategy metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard
          label="Total Return"
          value={pct(m.total_return)}
          color={colorClass(m.total_return)}
        />
        <StatCard
          label="CAGR"
          value={pct(m.cagr)}
          color={colorClass(m.cagr)}
        />
        <StatCard
          label="Sharpe"
          value={num(m.sharpe)}
          sub="risk-adjusted return"
          color={m.sharpe >= 1 ? 'text-green-500' : m.sharpe >= 0.5 ? 'text-yellow-400' : 'text-red-400'}
        />
        <StatCard
          label="Max Drawdown"
          value={pct(m.max_dd)}
          color="text-red-400"
        />
        <StatCard
          label="Sortino"
          value={num(m.sortino)}
          sub="downside risk-adj"
        />
        <StatCard
          label="Win Rate"
          value={m.win_rate != null ? pct(m.win_rate) : 'N/A'}
          sub={`${m.n_trades} trades`}
          color={m.win_rate != null && m.win_rate >= 0.5 ? 'text-green-500' : 'text-red-400'}
        />
        <StatCard
          label="Calmar"
          value={num(m.calmar)}
          sub="return / max DD"
        />
        <StatCard
          label="Trades"
          value={String(m.n_trades)}
          sub={`avg ${(nBars / Math.max(m.n_trades, 1)).toFixed(0)} bars/trade`}
        />
      </div>

      {/* Benchmark comparison */}
      {bm && (
        <>
          <p className="text-xs font-semibold mt-1" style={{ color: 'var(--color-text-secondary)' }}>
            vs SPY
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard
              label="SPY Return"
              value={pct(bm.benchmark_total_return)}
              color={colorClass(bm.benchmark_total_return)}
            />
            <StatCard
              label="Excess Return"
              value={pct(bm.excess_return)}
              color={colorClass(bm.excess_return)}
            />
            <StatCard
              label="Info Ratio"
              value={num(bm.information_ratio)}
              sub="excess / tracking err"
              color={colorClass(bm.information_ratio)}
            />
            <StatCard
              label="Beta"
              value={num(bm.beta)}
              sub={`corr ${num(bm.correlation)}`}
            />
          </div>
        </>
      )}
    </div>
  );
}
