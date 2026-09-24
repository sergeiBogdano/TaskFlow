import { useEffect, useState, type FormEvent } from 'react';
import { AlertTriangle, BarChart3, Bot, CalendarClock, Send, Sparkles, Trash2, UsersRound, Wand2 } from 'lucide-react';
import { api, type AiAnalyticsResult, type Client } from '../api/client';
import { referenceCache } from '../api/cache';
import { useAuth } from '../hooks/useAuth';
import { cn } from '../lib/taskflow';

type AnalysisKind = 'overdue' | 'workload' | 'daily' | 'project' | 'bottlenecks';

const ANALYSIS_META: Record<AnalysisKind, { title: string; hint: string }> = {
  overdue: { title: 'Просрочки', hint: 'Кто и где срывает сроки' },
  workload: { title: 'Загрузка', hint: 'Перегруз сотрудников' },
  daily: { title: 'Сводка за сутки', hint: 'Создано, закрыто, клиенты' },
  project: { title: 'Проект', hint: 'Анализ одного клиента' },
  bottlenecks: { title: 'Проблемные места', hint: 'Узкие статусы потока' },
};

type ChatEntry = { role: 'user' | 'ai'; text: string };

type PositionRow = { key: string; was: string; now: string };

export function AiAnalytics() {
  const { hasRole } = useAuth();
  const isAdmin = hasRole('superadmin') || hasRole('admin');

  const [clients, setClients] = useState<Client[]>([]);
  const [projectId, setProjectId] = useState('');
  const [activeKind, setActiveKind] = useState<AnalysisKind | null>(null);
  const [result, setResult] = useState<AiAnalyticsResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');

  const [chat, setChat] = useState<ChatEntry[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);

  const [traffic, setTraffic] = useState('');
  const [pages, setPages] = useState('');
  const [seoNotes, setSeoNotes] = useState('');
  const [positions, setPositions] = useState<PositionRow[]>([{ key: '', was: '', now: '' }]);
  const [seoResult, setSeoResult] = useState('');
  const [seoLoading, setSeoLoading] = useState(false);
  const [seoError, setSeoError] = useState('');

  useEffect(() => {
    referenceCache.clients().then(setClients).catch(() => {});
  }, []);

  const runAnalysis = async (kind: AnalysisKind) => {
    setRunning(true);
    setError('');
    setResult(null);
    setActiveKind(kind);
    try {
      if (kind === 'overdue') setResult(await api.aiOverdue());
      else if (kind === 'workload') setResult(await api.aiWorkload());
      else if (kind === 'daily') setResult(await api.aiDaily());
      else if (kind === 'bottlenecks') setResult(await api.aiBottlenecks());
      else {
        if (!projectId) {
          setError('Выберите проект для анализа.');
          setRunning(false);
          return;
        }
        setResult(await api.aiProject(Number(projectId)));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI недоступен.');
    } finally {
      setRunning(false);
    }
  };

  const sendChat = async (event: FormEvent) => {
    event.preventDefault();
    const text = chatInput.trim();
    if (!text || chatLoading) return;
    setChatInput('');
    setChat(prev => [...prev, { role: 'user', text }]);
    setChatLoading(true);
    try {
      const res = await api.aiChat(text);
      setChat(prev => [...prev, { role: 'ai', text: res.answer }]);
    } catch (err) {
      setChat(prev => [...prev, { role: 'ai', text: err instanceof Error ? err.message : 'AI недоступен.' }]);
    } finally {
      setChatLoading(false);
    }
  };

  const runSeo = async () => {
    setSeoLoading(true);
    setSeoError('');
    setSeoResult('');
    try {
      const rows = positions
        .filter(row => row.key.trim())
        .map(row => ({
          key: row.key.trim(),
          was: row.was.trim() === '' ? null : Number(row.was.replace(',', '.')),
          now: row.now.trim() === '' ? null : Number(row.now.replace(',', '.')),
        }));
      const res = await api.seoReport({ traffic, positions: rows, pages, notes: seoNotes });
      setSeoResult(res.report);
    } catch (err) {
      setSeoError(err instanceof Error ? err.message : 'AI недоступен.');
    } finally {
      setSeoLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-[1200px] space-y-5">
      <div>
        <h2 className="tf-page-title">AI-аналитика</h2>
        <p className="tf-page-subtitle">TaskFlow готовит выборку из базы, локальная модель Ollama анализирует. Модель ничего не меняет — только текст.</p>
      </div>

      {isAdmin && (
        <section className="tf-panel-flat p-4 sm:p-5">
          <div className="mb-1 flex items-center gap-2 text-sm font-bold"><BarChart3 size={16} className="text-[var(--color-accent)]" />Анализ данных</div>
          <p className="mb-4 text-xs text-[var(--color-text-secondary)]">Кнопка собирает свежие данные и передаёт их модели.</p>
          <div className="flex flex-wrap gap-2">
            {(Object.keys(ANALYSIS_META) as AnalysisKind[]).filter(kind => kind !== 'project').map(kind => (
              <button
                key={kind}
                type="button"
                onClick={() => runAnalysis(kind)}
                disabled={running}
                className={cn('tf-button', activeKind === kind && result && 'tf-button-primary')}
              >
                <Sparkles size={15} />{ANALYSIS_META[kind].title}
              </button>
            ))}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <select
              className="tf-input min-w-[220px] flex-1 sm:max-w-xs"
              value={projectId}
              onChange={event => setProjectId(event.target.value)}
            >
              <option value="">Проект для анализа...</option>
              {clients.map(client => <option key={client.id} value={client.id}>{client.org_name}</option>)}
            </select>
            <button type="button" onClick={() => runAnalysis('project')} disabled={running || !projectId} className="tf-button tf-button-primary">
              <Sparkles size={15} />Анализ проекта
            </button>
          </div>

          <div className="mt-4">
            {running && <div className="grid h-32 place-items-center text-sm text-[var(--color-text-secondary)]">Модель думает... это может занять минуту.</div>}
            {error && <div className="rounded-lg border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 px-3 py-2 text-sm text-[var(--color-danger)]">{error}</div>}
            {result && !running && (
              <div className="anim-rise space-y-3">
                <FactsLine facts={result.facts} />
                <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4">
                  <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-[var(--color-muted)]">
                    <Bot size={14} /> Вывод модели · {result.model}
                  </div>
                  <div className="whitespace-pre-wrap text-[15px] leading-relaxed">{result.analysis}</div>
                </div>
              </div>
            )}
          </div>
        </section>
      )}

      {isAdmin && (
        <section className="tf-panel-flat p-4 sm:p-5">
          <div className="mb-1 flex items-center gap-2 text-sm font-bold"><CalendarClock size={16} className="text-[var(--color-accent)]" />SEO-отчёт</div>
          <p className="mb-4 text-xs text-[var(--color-text-secondary)]">Вставьте трафик, страницы и позиции «было → стало». Модель напишет что выросло, что упало и почему.</p>
          <div className="grid gap-3 lg:grid-cols-3">
            <label className="block">
              <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Трафик</span>
              <textarea className="tf-input min-h-24 resize-y" value={traffic} onChange={event => setTraffic(event.target.value)} placeholder="Например: органический трафик +10% за месяц..." />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Страницы</span>
              <textarea className="tf-input min-h-24 resize-y" value={pages} onChange={event => setPages(event.target.value)} placeholder="Какие страницы смотрели..." />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Заметки</span>
              <textarea className="tf-input min-h-24 resize-y" value={seoNotes} onChange={event => setSeoNotes(event.target.value)} placeholder="Изменения на сайте, контекст..." />
            </label>
          </div>
          <div className="mt-3 space-y-2">
            <div className="text-xs font-semibold text-[var(--color-text-secondary)]">Позиции: запрос, было, стало</div>
            {positions.map((row, index) => (
              <div key={index} className="grid grid-cols-[minmax(0,1fr)_110px_110px_auto] items-center gap-2">
                <input className="tf-input" value={row.key} onChange={event => setPositions(prev => prev.map((r, i) => i === index ? { ...r, key: event.target.value } : r))} placeholder="Ключевой запрос" />
                <input className="tf-input" value={row.was} onChange={event => setPositions(prev => prev.map((r, i) => i === index ? { ...r, was: event.target.value } : r))} placeholder="Было" inputMode="decimal" />
                <input className="tf-input" value={row.now} onChange={event => setPositions(prev => prev.map((r, i) => i === index ? { ...r, now: event.target.value } : r))} placeholder="Стало" inputMode="decimal" />
                <button
                  type="button"
                  onClick={() => setPositions(prev => prev.filter((_, i) => i !== index))}
                  disabled={positions.length <= 1}
                  className="tf-button w-9 px-0 text-[var(--color-danger)]"
                  aria-label="Убрать строку"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            ))}
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={() => setPositions(prev => [...prev, { key: '', was: '', now: '' }])} className="tf-button">+ Строка</button>
              <button type="button" onClick={runSeo} disabled={seoLoading} className="tf-button tf-button-primary"><Wand2 size={15} />{seoLoading ? 'Модель думает...' : 'Составить отчёт'}</button>
            </div>
          </div>
          {seoError && <div className="mt-3 rounded-lg border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 px-3 py-2 text-sm text-[var(--color-danger)]">{seoError}</div>}
          {seoResult && !seoLoading && (
            <div className="anim-rise mt-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4">
              <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-[var(--color-muted)]"><Bot size={14} /> Отчёт модели</div>
              <div className="whitespace-pre-wrap text-[15px] leading-relaxed">{seoResult}</div>
            </div>
          )}
        </section>
      )}

      <section className="tf-panel-flat p-4 sm:p-5">
        <div className="mb-1 flex items-center gap-2 text-sm font-bold"><UsersRound size={16} className="text-[var(--color-accent)]" />Чат с TaskFlow</div>
        <p className="mb-4 text-xs text-[var(--color-text-secondary)]">Спросите про свои просрочки, задачи клиента или загрузку. Отвечаю только по данным системы.</p>
        <div className="max-h-80 space-y-2 overflow-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3">
          {chat.length === 0 && <div className="p-4 text-center text-sm text-[var(--color-text-secondary)]">Например: «Сколько у меня просроченных задач?»</div>}
          {chat.map((entry, index) => (
            <div key={index} className={cn('max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed', entry.role === 'user' ? 'ml-auto bg-[var(--color-accent)] text-white' : 'bg-[var(--color-surface-3)]')}>
              <div className="whitespace-pre-wrap">{entry.text}</div>
            </div>
          ))}
          {chatLoading && <div className="text-sm text-[var(--color-text-secondary)]">Модель думает...</div>}
        </div>
        <form onSubmit={sendChat} className="mt-3 flex gap-2">
          <input
            className="tf-input flex-1"
            value={chatInput}
            onChange={event => setChatInput(event.target.value)}
            placeholder="Сколько у меня просроченных задач?"
          />
          <button type="submit" disabled={chatLoading || !chatInput.trim()} className="tf-button tf-button-primary shrink-0"><Send size={15} />Спросить</button>
        </form>
        {!isAdmin && (
          <p className="mt-3 flex items-center gap-2 text-xs text-[var(--color-text-secondary)]"><AlertTriangle size={13} />Кнопки анализа выше доступны администраторам.</p>
        )}
      </section>
    </div>
  );
}

function FactsLine({ facts }: { facts: Record<string, any> }) {
  const chips: { label: string; danger?: boolean }[] = [];
  if (typeof facts.total === 'number') chips.push({ label: `Всего: ${facts.total}` });
  if (typeof facts.total_active === 'number') chips.push({ label: `Активно: ${facts.total_active}` });
  if (typeof facts.overdue_total === 'number') chips.push({ label: `Просрочено: ${facts.overdue_total}`, danger: facts.overdue_total > 0 });
  if (typeof facts.overdue_count === 'number') chips.push({ label: `Просрочено: ${facts.overdue_count}`, danger: facts.overdue_count > 0 });
  if (typeof facts.created === 'number') chips.push({ label: `Создано: ${facts.created}` });
  if (typeof facts.closed === 'number') chips.push({ label: `Закрыто: ${facts.closed}` });
  if (typeof facts.waiting_share === 'number') chips.push({ label: `В ожидании: ${facts.waiting_share}%`, danger: facts.waiting_share > 20 });
  if (typeof facts.max_lag_days === 'number' && facts.max_lag_days > 0) chips.push({ label: `Отставание: ${facts.max_lag_days} дн.`, danger: true });
  if (typeof facts.client === 'string') chips.push({ label: facts.client });
  if (!chips.length) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {chips.map((chip, index) => (
        <span key={index} className={cn('tf-chip', chip.danger && 'border-[var(--color-danger)]/50 text-[var(--color-danger)]')}>{chip.label}</span>
      ))}
    </div>
  );
}
