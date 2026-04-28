const BASE = 'http://localhost:8001';

export interface JournalEntry {
  date: string;
  type: string;
  symbol: string;
  action: string;
  quantity: string;
  price: string;
  currency: string;
  amount_krw: string;
  rate: string;
  broker: string;
  fees: string;
  notes: string;
}

export interface TradePayload {
  action: 'buy' | 'sell';
  symbol: string;
  quantity: number;
  price: number;
  currency?: string;
  date?: string;
  broker?: string;
  fees?: number;
  amount_krw?: number | null;
  rate?: number | null;
  notes?: string;
}

export interface ForexPayload {
  from_currency: string;
  to_currency: string;
  from_amount: number;
  rate: number;
  date?: string;
  broker?: string;
  fees?: number;
  notes?: string;
}

export interface DividendPayload {
  symbol: string;
  amount: number;
  currency?: string;
  date?: string;
  amount_krw?: number | null;
  tax_withheld?: number;
  notes?: string;
}

export interface NotePayload {
  content: string;
  date?: string;
  tags?: string[];
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `${res.status}`);
  }
  return res.json();
}

export const journalApi = {
  health: () => get<{ status: string }>('/health'),
  entries: (limit = 100) => get<{ markdown: string }>(`/journal/entries?limit=${limit}`),
  summary: () => get<{ markdown: string }>('/journal/summary'),
  csv: () => get<JournalEntry[]>('/journal/csv'),

  logTrade: (p: TradePayload) => post<{ ok: boolean; message: string }>('/journal/trade', p),
  logForex: (p: ForexPayload) => post<{ ok: boolean; message: string }>('/journal/forex', p),
  logDividend: (p: DividendPayload) => post<{ ok: boolean; message: string }>('/journal/dividend', p),
  logNote: (p: NotePayload) => post<{ ok: boolean; message: string }>('/journal/note', p),
};
