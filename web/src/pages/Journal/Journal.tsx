import { useState, useEffect, useCallback } from 'react';
import { BookOpen, Plus, TrendingUp, TrendingDown, DollarSign, StickyNote, RefreshCw, ArrowLeftRight } from 'lucide-react';
import { journalApi, type JournalEntry } from './utils/api';
import './Journal.css';

type TabType = 'entries' | 'summary' | 'add';
type AddType = 'trade' | 'forex' | 'dividend' | 'note';

function EntryRow({ entry }: { entry: JournalEntry }) {
  const typeColors: Record<string, string> = {
    trade: entry.action === 'buy' ? '#34d399' : '#f87171',
    forex: '#60a5fa',
    dividend: '#fbbf24',
    note: '#a78bfa',
    fee: '#94a3b8',
  };
  const typeLabels: Record<string, string> = {
    trade: entry.action === 'buy' ? '매수' : '매도',
    forex: '환전',
    dividend: '배당',
    note: '메모',
    fee: '수수료',
  };
  const color = typeColors[entry.type] ?? '#94a3b8';

  return (
    <div className="journal-entry-row">
      <span className="journal-entry-badge" style={{ background: color + '22', color }}>
        {typeLabels[entry.type] ?? entry.type}
      </span>
      <span className="journal-entry-date">{entry.date}</span>
      {entry.symbol && <span className="journal-entry-symbol">{entry.symbol}</span>}
      {entry.quantity && entry.price && (
        <span className="journal-entry-detail">
          {parseFloat(entry.quantity).toLocaleString()}주 @ {parseFloat(entry.price).toLocaleString()} {entry.currency}
        </span>
      )}
      {entry.type === 'note' && (
        <span className="journal-entry-notes">{entry.notes}</span>
      )}
      {entry.fees && parseFloat(entry.fees) > 0 && (
        <span className="journal-entry-fee">수수료 {entry.fees}</span>
      )}
    </div>
  );
}

function TradeForm({ onSuccess }: { onSuccess: () => void }) {
  const [form, setForm] = useState({
    action: 'buy' as 'buy' | 'sell',
    symbol: '', quantity: '', price: '',
    currency: 'USD', date: '', broker: '',
    fees: '', amount_krw: '', rate: '', notes: '',
  });
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState('');

  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true); setMsg('');
    try {
      const res = await journalApi.logTrade({
        action: form.action,
        symbol: form.symbol.toUpperCase(),
        quantity: parseFloat(form.quantity),
        price: parseFloat(form.price),
        currency: form.currency,
        date: form.date || undefined,
        broker: form.broker,
        fees: form.fees ? parseFloat(form.fees) : 0,
        amount_krw: form.amount_krw ? parseFloat(form.amount_krw) : null,
        rate: form.rate ? parseFloat(form.rate) : null,
        notes: form.notes,
      });
      setMsg(res.message);
      setForm(f => ({ ...f, symbol: '', quantity: '', price: '', fees: '', amount_krw: '', rate: '', notes: '' }));
      onSuccess();
    } catch (e) {
      setMsg('오류: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="journal-form" onSubmit={submit}>
      <div className="journal-form-row">
        <div className="journal-toggle-group">
          <button type="button" className={`journal-toggle ${form.action === 'buy' ? 'active-buy' : ''}`} onClick={() => set('action', 'buy')}>매수</button>
          <button type="button" className={`journal-toggle ${form.action === 'sell' ? 'active-sell' : ''}`} onClick={() => set('action', 'sell')}>매도</button>
        </div>
        <div className="journal-toggle-group">
          {['USD', 'KRW', 'JPY'].map(c => (
            <button key={c} type="button" className={`journal-toggle ${form.currency === c ? 'active-neutral' : ''}`} onClick={() => set('currency', c)}>{c}</button>
          ))}
        </div>
      </div>
      <div className="journal-form-grid">
        <label>종목 <input value={form.symbol} onChange={e => set('symbol', e.target.value)} placeholder="AAPL" required /></label>
        <label>수량 <input type="number" step="0.0001" value={form.quantity} onChange={e => set('quantity', e.target.value)} placeholder="10" required /></label>
        <label>단가 <input type="number" step="0.0001" value={form.price} onChange={e => set('price', e.target.value)} placeholder="150.00" required /></label>
        <label>수수료 <input type="number" step="0.01" value={form.fees} onChange={e => set('fees', e.target.value)} placeholder="0.00" /></label>
        <label>거래일 <input type="date" value={form.date} onChange={e => set('date', e.target.value)} /></label>
        <label>증권사 <input value={form.broker} onChange={e => set('broker', e.target.value)} placeholder="토스증권" /></label>
        <label>원화환산 <input type="number" value={form.amount_krw} onChange={e => set('amount_krw', e.target.value)} placeholder="2,000,000" /></label>
        <label>환율 <input type="number" step="0.01" value={form.rate} onChange={e => set('rate', e.target.value)} placeholder="1350.00" /></label>
      </div>
      <label className="journal-form-full">메모 <input value={form.notes} onChange={e => set('notes', e.target.value)} placeholder="투자 이유, 목표가 등" /></label>
      <button className="journal-submit-btn" disabled={loading}>{loading ? '기록 중...' : '기록 저장'}</button>
      {msg && <p className="journal-form-msg">{msg}</p>}
    </form>
  );
}

function ForexForm({ onSuccess }: { onSuccess: () => void }) {
  const [form, setForm] = useState({ from_currency: 'KRW', to_currency: 'USD', from_amount: '', rate: '', date: '', broker: '', fees: '', notes: '' });
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState('');
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true); setMsg('');
    try {
      const res = await journalApi.logForex({
        from_currency: form.from_currency, to_currency: form.to_currency,
        from_amount: parseFloat(form.from_amount), rate: parseFloat(form.rate),
        date: form.date || undefined, broker: form.broker,
        fees: form.fees ? parseFloat(form.fees) : 0, notes: form.notes,
      });
      setMsg(res.message);
      setForm(f => ({ ...f, from_amount: '', rate: '', fees: '', notes: '' }));
      onSuccess();
    } catch (e) {
      setMsg('오류: ' + (e instanceof Error ? e.message : String(e)));
    } finally { setLoading(false); }
  }

  return (
    <form className="journal-form" onSubmit={submit}>
      <div className="journal-form-grid">
        <label>원본 통화 <input value={form.from_currency} onChange={e => set('from_currency', e.target.value)} placeholder="KRW" required /></label>
        <label>대상 통화 <input value={form.to_currency} onChange={e => set('to_currency', e.target.value)} placeholder="USD" required /></label>
        <label>원금 <input type="number" step="0.01" value={form.from_amount} onChange={e => set('from_amount', e.target.value)} placeholder="1,000,000" required /></label>
        <label>환율 <input type="number" step="0.000001" value={form.rate} onChange={e => set('rate', e.target.value)} placeholder="0.00074" required /></label>
        <label>거래일 <input type="date" value={form.date} onChange={e => set('date', e.target.value)} /></label>
        <label>은행/증권사 <input value={form.broker} onChange={e => set('broker', e.target.value)} placeholder="신한은행" /></label>
        <label>수수료 <input type="number" step="0.01" value={form.fees} onChange={e => set('fees', e.target.value)} placeholder="0" /></label>
        <label>메모 <input value={form.notes} onChange={e => set('notes', e.target.value)} /></label>
      </div>
      <button className="journal-submit-btn" disabled={loading}>{loading ? '기록 중...' : '기록 저장'}</button>
      {msg && <p className="journal-form-msg">{msg}</p>}
    </form>
  );
}

function DividendForm({ onSuccess }: { onSuccess: () => void }) {
  const [form, setForm] = useState({ symbol: '', amount: '', currency: 'USD', date: '', amount_krw: '', tax_withheld: '', notes: '' });
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState('');
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true); setMsg('');
    try {
      const res = await journalApi.logDividend({
        symbol: form.symbol.toUpperCase(), amount: parseFloat(form.amount),
        currency: form.currency, date: form.date || undefined,
        amount_krw: form.amount_krw ? parseFloat(form.amount_krw) : null,
        tax_withheld: form.tax_withheld ? parseFloat(form.tax_withheld) : 0,
        notes: form.notes,
      });
      setMsg(res.message);
      setForm(f => ({ ...f, symbol: '', amount: '', amount_krw: '', tax_withheld: '', notes: '' }));
      onSuccess();
    } catch (e) {
      setMsg('오류: ' + (e instanceof Error ? e.message : String(e)));
    } finally { setLoading(false); }
  }

  return (
    <form className="journal-form" onSubmit={submit}>
      <div className="journal-form-grid">
        <label>종목 <input value={form.symbol} onChange={e => set('symbol', e.target.value)} placeholder="AAPL" required /></label>
        <label>수령 금액 <input type="number" step="0.0001" value={form.amount} onChange={e => set('amount', e.target.value)} placeholder="12.50" required /></label>
        <label>통화 <input value={form.currency} onChange={e => set('currency', e.target.value)} placeholder="USD" /></label>
        <label>지급일 <input type="date" value={form.date} onChange={e => set('date', e.target.value)} /></label>
        <label>원화 환산 <input type="number" value={form.amount_krw} onChange={e => set('amount_krw', e.target.value)} placeholder="16,875" /></label>
        <label>원천징수 <input type="number" step="0.0001" value={form.tax_withheld} onChange={e => set('tax_withheld', e.target.value)} placeholder="1.88" /></label>
      </div>
      <label className="journal-form-full">메모 <input value={form.notes} onChange={e => set('notes', e.target.value)} /></label>
      <button className="journal-submit-btn" disabled={loading}>{loading ? '기록 중...' : '기록 저장'}</button>
      {msg && <p className="journal-form-msg">{msg}</p>}
    </form>
  );
}

function NoteForm({ onSuccess }: { onSuccess: () => void }) {
  const [content, setContent] = useState('');
  const [tags, setTags] = useState('');
  const [date, setDate] = useState('');
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState('');

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true); setMsg('');
    try {
      const res = await journalApi.logNote({
        content,
        date: date || undefined,
        tags: tags ? tags.split(',').map(t => t.trim()).filter(Boolean) : undefined,
      });
      setMsg(res.message);
      setContent(''); setTags(''); setDate('');
      onSuccess();
    } catch (e) {
      setMsg('오류: ' + (e instanceof Error ? e.message : String(e)));
    } finally { setLoading(false); }
  }

  return (
    <form className="journal-form" onSubmit={submit}>
      <label className="journal-form-full">
        내용
        <textarea value={content} onChange={e => setContent(e.target.value)} placeholder="시장 관찰, 전략 아이디어, 뉴스 메모 등..." rows={4} required style={{ resize: 'vertical' }} />
      </label>
      <div className="journal-form-grid">
        <label>태그 (쉼표 구분) <input value={tags} onChange={e => setTags(e.target.value)} placeholder="AAPL, 실적, 전략" /></label>
        <label>날짜 <input type="date" value={date} onChange={e => setDate(e.target.value)} /></label>
      </div>
      <button className="journal-submit-btn" disabled={loading}>{loading ? '기록 중...' : '메모 저장'}</button>
      {msg && <p className="journal-form-msg">{msg}</p>}
    </form>
  );
}

export default function Journal() {
  const [tab, setTab] = useState<TabType>('entries');
  const [addType, setAddType] = useState<AddType>('trade');
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [summaryMd, setSummaryMd] = useState('');
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);

  const loadEntries = useCallback(async () => {
    try {
      const data = await journalApi.csv();
      setEntries([...data].reverse());
    } catch { /* ignore */ }
  }, []);

  const loadSummary = useCallback(async () => {
    try {
      const data = await journalApi.summary();
      setSummaryMd(data.markdown);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    journalApi.health()
      .then(() => {
        setOffline(false);
        setLoading(false);
        loadEntries();
        loadSummary();
      })
      .catch(() => {
        setOffline(true);
        setLoading(false);
      });
  }, [loadEntries, loadSummary]);

  function onSuccess() {
    loadEntries();
    loadSummary();
  }

  // Stats
  const buys = entries.filter(e => e.type === 'trade' && e.action === 'buy').length;
  const sells = entries.filter(e => e.type === 'trade' && e.action === 'sell').length;
  const dividendCount = entries.filter(e => e.type === 'dividend').length;
  const noteCount = entries.filter(e => e.type === 'note').length;
  const totalEntries = entries.length;

  const positions = new Map<string, number>();
  entries.filter(e => e.type === 'trade').forEach(e => {
    const qty = parseFloat(e.quantity) || 0;
    const cur = positions.get(e.symbol) ?? 0;
    positions.set(e.symbol, e.action === 'buy' ? cur + qty : cur - qty);
  });
  const heldPositions = [...positions.entries()].filter(([, q]) => q > 0);

  if (offline || loading) {
    return (
      <div className="journal-page">
        <div className="journal-center">
          {loading ? (
            <div className="animate-spin rounded-full h-8 w-8 border-b-2" style={{ borderColor: 'var(--color-accent)' }} />
          ) : (
            <>
              <BookOpen size={36} style={{ color: 'var(--color-text-secondary)', opacity: 0.4 }} />
              <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>백테스트 서비스(:8001)에 연결할 수 없습니다</p>
              <code className="text-xs px-3 py-2 rounded" style={{ background: 'var(--color-bg-input)', color: 'var(--color-text-primary)' }}>
                docker compose up -d backtest
              </code>
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="journal-page">
      {/* Header */}
      <div className="journal-header">
        <div className="flex items-center gap-2">
          <BookOpen size={20} style={{ color: 'var(--color-accent)' }} />
          <h1 className="text-xl font-bold" style={{ color: 'var(--color-text-primary)' }}>매매 기록장</h1>
        </div>
        <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>거래, 환전, 배당, 메모를 기록하세요</p>
      </div>

      {/* Stat cards */}
      <div className="journal-stats">
        {[
          { label: '전체 기록', value: totalEntries, icon: <BookOpen size={14} />, color: '#94a3b8' },
          { label: '매수', value: buys, icon: <TrendingUp size={14} />, color: '#34d399' },
          { label: '매도', value: sells, icon: <TrendingDown size={14} />, color: '#f87171' },
          { label: '보유 종목', value: heldPositions.length, icon: <DollarSign size={14} />, color: '#fbbf24' },
          { label: '배당 기록', value: dividendCount, icon: <DollarSign size={14} />, color: '#60a5fa' },
          { label: '메모', value: noteCount, icon: <StickyNote size={14} />, color: '#a78bfa' },
        ].map(s => (
          <div key={s.label} className="journal-stat-card">
            <span style={{ color: s.color }}>{s.icon}</span>
            <span className="journal-stat-value" style={{ color: s.color }}>{s.value}</span>
            <span className="journal-stat-label">{s.label}</span>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="journal-tabs">
        {(['entries', 'summary', 'add'] as TabType[]).map(t => (
          <button
            key={t}
            className={`journal-tab ${tab === t ? 'active' : ''}`}
            onClick={() => setTab(t)}
          >
            {t === 'entries' ? '기록 목록' : t === 'summary' ? '포지션 요약' : '+ 기록 추가'}
          </button>
        ))}
        <button className="journal-refresh-btn" onClick={() => { loadEntries(); loadSummary(); }}>
          <RefreshCw size={13} />
        </button>
      </div>

      {/* Content */}
      {tab === 'entries' && (
        <div className="journal-card">
          {entries.length === 0 ? (
            <div className="journal-center" style={{ padding: '40px 0' }}>
              <BookOpen size={32} style={{ color: 'var(--color-text-secondary)', opacity: 0.3 }} />
              <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>아직 기록이 없습니다. + 기록 추가를 눌러 시작하세요.</p>
            </div>
          ) : (
            <div className="journal-entries-list">
              {entries.map((e, i) => <EntryRow key={i} entry={e} />)}
            </div>
          )}
        </div>
      )}

      {tab === 'summary' && (
        <div className="journal-card">
          {summaryMd ? (
            <div>
              {/* Positions */}
              {heldPositions.length > 0 && (
                <div className="journal-section">
                  <p className="journal-section-title">보유 포지션</p>
                  <div className="journal-position-grid">
                    {heldPositions.map(([sym, qty]) => {
                      const trades = entries.filter(e => e.type === 'trade' && e.symbol === sym && e.action === 'buy');
                      const totalCost = trades.reduce((acc, e) => acc + (parseFloat(e.quantity) * parseFloat(e.price) || 0), 0);
                      const totalQty = trades.reduce((acc, e) => acc + (parseFloat(e.quantity) || 0), 0);
                      const avgBuy = totalQty > 0 ? totalCost / totalQty : 0;
                      return (
                        <div key={sym} className="journal-position-card">
                          <span className="journal-position-sym">{sym}</span>
                          <span className="journal-position-qty">{qty.toLocaleString(undefined, { maximumFractionDigits: 4 })}주</span>
                          {avgBuy > 0 && <span className="journal-position-avg">평균 {avgBuy.toFixed(2)}</span>}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Pre-formatted summary */}
              <div className="journal-section">
                <p className="journal-section-title">전체 요약</p>
                <pre className="journal-summary-pre">{summaryMd}</pre>
              </div>
            </div>
          ) : (
            <div className="journal-center" style={{ padding: '40px 0' }}>
              <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>거래 기록이 없습니다</p>
            </div>
          )}
        </div>
      )}

      {tab === 'add' && (
        <div className="journal-card">
          <div className="journal-add-tabs">
            {([
              { key: 'trade', icon: <TrendingUp size={13} />, label: '매매' },
              { key: 'forex', icon: <ArrowLeftRight size={13} />, label: '환전' },
              { key: 'dividend', icon: <DollarSign size={13} />, label: '배당' },
              { key: 'note', icon: <StickyNote size={13} />, label: '메모' },
            ] as { key: AddType; icon: React.ReactNode; label: string }[]).map(t => (
              <button
                key={t.key}
                className={`journal-add-tab ${addType === t.key ? 'active' : ''}`}
                onClick={() => setAddType(t.key)}
              >
                {t.icon}{t.label}
              </button>
            ))}
          </div>
          {addType === 'trade' && <TradeForm onSuccess={onSuccess} />}
          {addType === 'forex' && <ForexForm onSuccess={onSuccess} />}
          {addType === 'dividend' && <DividendForm onSuccess={onSuccess} />}
          {addType === 'note' && <NoteForm onSuccess={onSuccess} />}
        </div>
      )}
    </div>
  );
}
