import { useEffect, useMemo, useState } from 'react';
import { Clock3, Download, Eye, FileText, Loader2, RefreshCw, Trash2, Wand2 } from 'lucide-react';
import { api } from '../api/client';
import { referenceCache } from '../api/cache';
import { SearchSelect } from '../components/SearchSelect';
import type { Client, GeneratedReport } from '../api/client';
import { formatDate } from '../lib/taskflow';

const reportBlocks = [
  { key: 'work', label: 'Проделанная работа' },
  { key: 'stats', label: 'Показатели периода' },
  { key: 'recommendations', label: 'Выводы и рекомендации' },
  { key: 'plan', label: 'План и открытые задачи' },
];

const statusText: Record<GeneratedReport['status'], string> = {
  queued: 'В очереди',
  running: 'Генерируется',
  done: 'Готов',
  error: 'Ошибка',
};

function isoDate(date: Date) {
  return date.toISOString().slice(0, 10);
}

function oneMonthAgo() {
  const date = new Date();
  date.setMonth(date.getMonth() - 1);
  return isoDate(date);
}

function downloadHtml(report: GeneratedReport) {
  if (!report.html) return;
  const blob = new Blob([report.html], { type: 'text/html;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `taskflow-report-${report.id}.html`;
  link.click();
  URL.revokeObjectURL(url);
}

export function Reports() {
  const [activeTab, setActiveTab] = useState<'new' | 'history'>('new');
  const [clients, setClients] = useState<Client[]>([]);
  const [reports, setReports] = useState<GeneratedReport[]>([]);
  const [models, setModels] = useState<string[]>([]);
  const [selectedReport, setSelectedReport] = useState<GeneratedReport | null>(null);
  const [clientId, setClientId] = useState('');
  const [dateFrom, setDateFrom] = useState(oneMonthAgo);
  const [dateTo, setDateTo] = useState(() => isoDate(new Date()));
  const [blocks, setBlocks] = useState(() => reportBlocks.map(block => block.key));
  const [useAi, setUseAi] = useState(true);
  const [aiModel, setAiModel] = useState('');
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');

  const refreshReports = () => api.getGeneratedReports().then(setReports);

  useEffect(() => {
    Promise.all([
      referenceCache.clients().catch(() => []),
      api.getGeneratedReports().catch(() => []),
      api.getOllamaModels().catch(() => ({ models: [] })),
    ])
      .then(([clientList, reportList, modelList]) => {
        setClients(clientList);
        setReports(reportList);
        setModels(modelList.models);
        setClientId(clientList[0]?.id ? String(clientList[0].id) : '');
        setAiModel(modelList.models[0] || '');
        setSelectedReport(reportList[0] || null);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedReport || !['queued', 'running'].includes(selectedReport.status)) return;
    const timer = window.setInterval(async () => {
      const fresh = await api.getGeneratedReport(selectedReport.id);
      setSelectedReport(fresh);
      setReports(prev => prev.map(report => (report.id === fresh.id ? fresh : report)));
      if (fresh.status === 'done' || fresh.status === 'error') {
        window.clearInterval(timer);
        refreshReports().catch(() => undefined);
      }
    }, 2500);
    return () => window.clearInterval(timer);
  }, [selectedReport?.id, selectedReport?.status]);

  const currentClient = useMemo(() => clients.find(client => String(client.id) === clientId), [clientId, clients]);

  const createReport = async () => {
    if (!clientId) {
      setError('Выберите клиента для отчёта.');
      return;
    }
    if (dateFrom > dateTo) {
      setError('Дата начала не может быть позже даты окончания.');
      return;
    }
    setError('');
    setGenerating(true);
    try {
      const report = await api.generateReport({
        client_id: Number(clientId),
        period_start: dateFrom,
        period_end: dateTo,
        blocks,
        use_ai: useAi,
        ai_model: aiModel || undefined,
      });
      setSelectedReport(report);
      setReports(prev => [report, ...prev]);
      setActiveTab('history');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось запустить генерацию отчёта.');
    } finally {
      setGenerating(false);
    }
  };

  const deleteReport = async (report: GeneratedReport) => {
    if (!window.confirm(`Удалить отчёт "${report.title}"?`)) return;
    await api.deleteGeneratedReport(report.id);
    setReports(prev => prev.filter(item => item.id !== report.id));
    if (selectedReport?.id === report.id) {
      setSelectedReport(null);
    }
  };

  if (loading) {
    return <div className="grid h-64 place-items-center text-sm text-[var(--color-text-secondary)]">Загрузка отчётов...</div>;
  }

  return (
    <div className="mx-auto grid max-w-[1600px] gap-5 xl:grid-cols-[420px_1fr]">
      <section className="space-y-4">
        <div>
          <h2 className="text-xl font-black">Отчёты</h2>
          <p className="text-sm text-[var(--color-text-secondary)]">
            Собирайте HTML-отчёт по клиенту. Генерация идёт на сервере, поэтому можно перейти в другую вкладку и вернуться позже.
          </p>
        </div>

        <div className="tf-panel-flat p-2">
          <div className="grid grid-cols-2 gap-2">
            <button className={`tf-button ${activeTab === 'new' ? 'tf-button-primary' : ''}`} onClick={() => setActiveTab('new')}>
              <Wand2 size={16} /> Новый
            </button>
            <button className={`tf-button ${activeTab === 'history' ? 'tf-button-primary' : ''}`} onClick={() => setActiveTab('history')}>
              <Clock3 size={16} /> Прошлые
            </button>
          </div>
        </div>

        {activeTab === 'new' ? (
          <div className="tf-panel-flat space-y-4 p-4">
            <div>
              <label className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Клиент</label>
              <SearchSelect
                value={clientId}
                options={clients.map(client => ({ value: String(client.id), label: client.org_name, description: client.domain || 'Без домена', searchText: client.domain || '' }))}
                onChange={setClientId}
                placeholder="Выберите клиента"
                searchPlaceholder="Найти клиента или домен"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <label>
                <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Дата с</span>
                <input className="tf-input" type="date" value={dateFrom} onChange={event => setDateFrom(event.target.value)} />
              </label>
              <label>
                <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Дата по</span>
                <input className="tf-input" type="date" value={dateTo} onChange={event => setDateTo(event.target.value)} />
              </label>
            </div>

            <div>
              <div className="mb-2 text-xs font-semibold text-[var(--color-text-secondary)]">Блоки отчёта</div>
              <div className="space-y-2">
                {reportBlocks.map(block => (
                  <label key={block.key} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={blocks.includes(block.key)}
                      onChange={event => {
                        setBlocks(prev => event.target.checked ? [...prev, block.key] : prev.filter(item => item !== block.key));
                      }}
                    />
                    {block.label}
                  </label>
                ))}
              </div>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] p-3">
              <label className="flex items-center gap-2 text-sm font-semibold">
                <input type="checkbox" checked={useAi} onChange={event => setUseAi(event.target.checked)} />
                Помочь текстом через Ollama
              </label>
              <p className="mt-1 text-xs text-[var(--color-text-secondary)]">
                В модель отправляется только короткая сводка по задачам, без доступов и больших текстов.
              </p>
              {useAi && (
                <select className="tf-input mt-3" value={aiModel} onChange={event => setAiModel(event.target.value)}>
                  {models.length === 0 && <option value="">Модели не найдены</option>}
                  {models.map(model => <option key={model} value={model}>{model}</option>)}
                </select>
              )}
            </div>

            {error && <div className="rounded-lg border border-red-400/40 bg-red-500/10 p-3 text-sm text-red-300">{error}</div>}

            <button className="tf-button tf-button-primary w-full justify-center" onClick={createReport} disabled={generating || !clientId || blocks.length === 0}>
              {generating ? <Loader2 size={16} className="animate-spin" /> : <Wand2 size={16} />}
              Сгенерировать отчёт
            </button>

            <div className="text-xs text-[var(--color-text-secondary)]">
              {currentClient ? `Будет создан отчёт для ${currentClient.org_name}.` : 'Сначала добавьте клиента.'}
            </div>
          </div>
        ) : (
          <div className="tf-panel-flat overflow-hidden">
            <div className="flex items-center gap-2 border-b border-[var(--color-border)] p-3">
              <FileText size={16} />
              <span className="text-sm font-bold">Прошлые отчёты</span>
              <button className="tf-button ml-auto" onClick={() => refreshReports()} title="Обновить">
                <RefreshCw size={15} />
              </button>
            </div>
            <div className="max-h-[640px] divide-y divide-[var(--color-border)] overflow-auto">
              {reports.map(report => (
                <button
                  key={report.id}
                  className={`w-full px-4 py-3 text-left hover:bg-[var(--color-surface-2)] ${selectedReport?.id === report.id ? 'bg-[var(--color-surface-2)]' : ''}`}
                  onClick={() => setSelectedReport(report)}
                >
                  <div className="flex items-start gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-bold">{report.title}</div>
                      <div className="mt-1 text-xs text-[var(--color-text-secondary)]">
                        {report.client || 'Клиент'} • {formatDate(report.period_start)} - {formatDate(report.period_end)}
                      </div>
                    </div>
                    <span className={`tf-chip ${report.status === 'error' ? 'text-red-300' : report.status === 'done' ? 'text-emerald-300' : 'text-amber-300'}`}>
                      {statusText[report.status]}
                    </span>
                  </div>
                </button>
              ))}
              {reports.length === 0 && <div className="p-6 text-sm text-[var(--color-text-secondary)]">Пока нет сохранённых отчётов.</div>}
            </div>
          </div>
        )}
      </section>

      <section className="tf-panel-flat min-h-[760px] overflow-hidden">
        {selectedReport ? (
          <div className="flex h-full flex-col">
            <div className="flex flex-wrap items-center gap-2 border-b border-[var(--color-border)] p-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-bold">{selectedReport.title}</div>
                <div className="text-xs text-[var(--color-text-secondary)]">
                  {statusText[selectedReport.status]} • создан {formatDate(selectedReport.created_at)}
                </div>
              </div>
              <div className="ml-auto flex flex-wrap gap-2">
                <button className="tf-button" onClick={() => api.getGeneratedReport(selectedReport.id).then(setSelectedReport)}>
                  <RefreshCw size={15} /> Обновить
                </button>
                <button className="tf-button" onClick={() => downloadHtml(selectedReport)} disabled={!selectedReport.html}>
                  <Download size={15} /> HTML
                </button>
                <button className="tf-button text-red-300" onClick={() => deleteReport(selectedReport)}>
                  <Trash2 size={15} /> Удалить
                </button>
              </div>
            </div>

            {['queued', 'running'].includes(selectedReport.status) && (
              <div className="grid flex-1 place-items-center p-10 text-center">
                <div>
                  <Loader2 className="mx-auto mb-3 animate-spin text-[var(--color-accent)]" size={34} />
                  <div className="font-bold">Отчёт генерируется в фоне</div>
                  <p className="mt-1 max-w-md text-sm text-[var(--color-text-secondary)]">
                    Можно перейти в задачи, календарь или клиентов. Готовый отчёт останется в истории.
                  </p>
                </div>
              </div>
            )}

            {selectedReport.status === 'error' && (
              <div className="m-4 rounded-lg border border-red-400/40 bg-red-500/10 p-4 text-sm text-red-200">
                {selectedReport.error || 'Не удалось сформировать отчёт.'}
              </div>
            )}

            {selectedReport.status === 'done' && selectedReport.html && (
              <iframe title="Предпросмотр отчёта" className="h-[calc(100vh-210px)] min-h-[680px] w-full bg-white" srcDoc={selectedReport.html} />
            )}
          </div>
        ) : (
          <div className="grid h-full min-h-[640px] place-items-center p-8 text-center text-sm text-[var(--color-text-secondary)]">
            <div>
              <Eye className="mx-auto mb-3 opacity-60" size={32} />
              Создайте новый отчёт или выберите сохранённый из истории.
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
