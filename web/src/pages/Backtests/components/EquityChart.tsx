import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer,
} from 'recharts';
import type { EquityPoint } from '../utils/api';

interface Props {
  data: EquityPoint[];
  benchmark?: string;
}

function formatDate(dateStr: string) {
  const d = new Date(dateStr);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

interface TooltipPayload {
  name: string;
  value: number;
  color: string;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayload[];
  label?: string;
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs shadow-lg"
      style={{
        backgroundColor: 'var(--color-bg-card)',
        border: '1px solid var(--color-border)',
        color: 'var(--color-text-primary)',
      }}
    >
      <p className="font-semibold mb-1">{label}</p>
      {payload.map((p) => (
        <p key={p.name} style={{ color: p.color }}>
          {p.name}: {p.value.toFixed(1)}
        </p>
      ))}
    </div>
  );
}

export default function EquityChart({ data, benchmark = 'SPY' }: Props) {
  const hasBenchmark = data.some((d) => d.benchmark != null);

  // Determine if strategy outperforms at the end
  const last = data[data.length - 1];
  const stratColor = last && hasBenchmark && last.strategy >= (last.benchmark ?? 0)
    ? '#22c55e'  // green
    : '#f97316'; // orange

  return (
    <div
      className="rounded-xl p-4"
      style={{ backgroundColor: 'var(--color-bg-card)', border: '1px solid var(--color-border)' }}
    >
      <p className="text-sm font-semibold mb-3" style={{ color: 'var(--color-text-primary)' }}>
        Equity Curve (normalized to 100)
      </p>
      <ResponsiveContainer width="100%" height={280}>
        <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="stratGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={stratColor} stopOpacity={0.25} />
              <stop offset="95%" stopColor={stratColor} stopOpacity={0} />
            </linearGradient>
            <linearGradient id="bmGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#60a5fa" stopOpacity={0.15} />
              <stop offset="95%" stopColor="#60a5fa" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" strokeOpacity={0.5} />
          <XAxis
            dataKey="date"
            tickFormatter={formatDate}
            tick={{ fontSize: 11, fill: 'var(--color-text-secondary)' }}
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tickFormatter={(v: number) => v.toFixed(0)}
            tick={{ fontSize: 11, fill: 'var(--color-text-secondary)' }}
            tickLine={false}
            axisLine={false}
            width={48}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            wrapperStyle={{ fontSize: 12, color: 'var(--color-text-secondary)' }}
          />
          <Area
            type="monotone"
            dataKey="strategy"
            name="Strategy"
            stroke={stratColor}
            strokeWidth={2}
            fill="url(#stratGrad)"
            dot={false}
            activeDot={{ r: 4 }}
          />
          {hasBenchmark && (
            <Area
              type="monotone"
              dataKey="benchmark"
              name={benchmark}
              stroke="#60a5fa"
              strokeWidth={1.5}
              fill="url(#bmGrad)"
              dot={false}
              activeDot={{ r: 3 }}
              strokeDasharray="4 2"
            />
          )}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
