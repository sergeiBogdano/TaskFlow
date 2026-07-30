import { useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, Eraser, FileText, RotateCcw, Trash2 } from 'lucide-react';
import { api, type Client, type GeneratedReport, type Task } from '../api/client';
import { formatDate, priorityMeta, statusMeta } from '../lib/taskflow';

export function Trash() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [reports, setReports] = useState<GeneratedReport[]>([]);
  const [openSections, setOpenSections] = useState({ tasks: true, clients: true, reports: true });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    setError('');
    const [taskItems, clientItems, reportItems] = await Promise.all([
      api.getTaskTrash(),
      api.getClientTrash().catch(() => []),
      api.getReportTrash().catch(() => []),
    ]);
    setTasks(taskItems);
    setClients(clientItems);
    setReports(reportItems);
  };

  useEffect(() => {
    load().catch(err => setError(err instanceof Error ? err.message : 'Не удалось загрузить корзину')).finally(() => setLoading(false));
  }, []);

  const restore = async (task: Task) => {
    await api.restoreTask(task.id);
    setTasks(prev => prev.filter(item => item.id !== task.id));
  };

  const restoreClient = async (client: Client) => {
    await api.restoreClient(client.id);
    setClients(prev => prev.filter(item => item.id !== client.id));
  };

  const restoreReport = async (report: GeneratedReport) => {
    await api.restoreGeneratedReport(report.id);
    setReports(prev => prev.filter(item => item.id !== report.id));
  };

  const toggleSection = (section: keyof typeof openSections) => {
    setOpenSections(prev => ({ ...prev, [section]: !prev[section] }));
  };

  const empty = async () => {
    if (!tasks.length && !reports.length) return;
    if (!confirm('Очистить корзину без возможности восстановления?')) return;
    await Promise.all([
      tasks.length ? api.emptyTaskTrash() : Promise.resolve(),
      reports.length ? api.emptyReportTrash() : Promise.resolve(),
    ]);
    setTasks([]);
    setReports([]);
  };

  if (loading) return <div className="grid h-64 place-items-center text-sm text-[var(--color-text-secondary)]">Загрузка корзины...</div>;

  return (
    <div className="mx-auto max-w-[1300px] space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h2 className="text-xl font-black">Корзина</h2>
          <p className="text-sm text-[var(--color-text-secondary)]">Удалённые задачи можно восстановить или окончательно очистить.</p>
        </div>
        <button onClick={empty} disabled={!tasks.length && !reports.length} className="tf-button tf-button-primary ml-auto">
          <Eraser size={16} />
          Очистить корзину
        </button>
      </div>

      {error && <div className="tf-panel-flat border-[var(--color-danger)]/45 p-4 text-sm text-[var(--color-danger)]">{error}</div>}

      <section className="tf-panel-flat overflow-x-auto">
        <button type="button" onClick={() => toggleSection('tasks')} className="flex w-full items-center gap-2 border-b border-[var(--color-border)] px-4 py-3 text-left text-sm font-bold">
          {openSections.tasks ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          <Trash2 size={15} className="text-[var(--color-muted)]" />
          <span className="min-w-0 flex-1">Удаленные задачи</span>
          <span className="tf-chip">{tasks.length}</span>
        </button>
        <div className={`${openSections.tasks ? 'grid' : 'hidden'} min-w-[940px] grid-cols-[minmax(260px,1fr)_150px_120px_130px_160px_120px] gap-3 border-b border-[var(--color-border)] px-4 py-3 text-xs font-bold uppercase text-[var(--color-muted)]`}>
          <span>Задача</span>
          <span>Клиент</span>
          <span>Статус</span>
          <span>Дедлайн</span>
          <span>Удалена</span>
          <span />
        </div>
        {tasks.map(task => {
          const status = statusMeta[task.status as keyof typeof statusMeta] || statusMeta.todo;
          const priority = priorityMeta[task.priority as keyof typeof priorityMeta] || priorityMeta.medium;
          return (
            <div key={task.id} className={`${openSections.tasks ? 'tf-table-row' : 'hidden'} min-w-[940px] grid-cols-[minmax(260px,1fr)_150px_120px_130px_160px_120px] gap-3 px-4 py-3`}>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <Trash2 size={15} className="text-[var(--color-muted)]" />
                  <span className="truncate text-sm font-semibold">{task.title}</span>
                </div>
                <div className="mt-1 text-xs text-[var(--color-text-secondary)]">#{task.id} · <span style={{ color: priority.color }}>{priority.label}</span></div>
              </div>
              <span className="truncate text-sm text-[var(--color-text-secondary)]">{task.client || 'Без клиента'}</span>
              <span className="text-sm font-semibold" style={{ color: status.color }}>{status.label}</span>
              <span className="text-sm text-[var(--color-text-secondary)]">{formatDate(task.deadline)}</span>
              <span className="text-sm text-[var(--color-text-secondary)]">{task.deleted_at ? new Date(task.deleted_at).toLocaleString('ru-RU') : '-'}</span>
              <button onClick={() => restore(task)} className="tf-button">
                <RotateCcw size={15} />
                Вернуть
              </button>
            </div>
          );
        })}
        {openSections.tasks && tasks.length === 0 && <div className="p-10 text-center text-sm text-[var(--color-text-secondary)]">Удалённых задач нет.</div>}
      </section>

      <section className="tf-panel-flat overflow-x-auto">
        <button type="button" onClick={() => toggleSection('clients')} className="flex w-full items-center gap-2 border-b border-[var(--color-border)] px-4 py-3 text-left text-sm font-bold">
          {openSections.clients ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          <Trash2 size={15} className="text-[var(--color-muted)]" />
          <span className="min-w-0 flex-1">Удаленные клиенты</span>
          <span className="tf-chip">{clients.length}</span>
        </button>
        <div className={`${openSections.clients ? 'grid' : 'hidden'} min-w-[760px] grid-cols-[minmax(260px,1fr)_180px_160px_160px_120px] gap-3 border-b border-[var(--color-border)] px-4 py-3 text-xs font-bold uppercase text-[var(--color-muted)]`}>
          <span>Организация</span>
          <span>Домен</span>
          <span>Статус</span>
          <span>Удалена</span>
          <span />
        </div>
        {clients.map(client => (
          <div key={client.id} className={`${openSections.clients ? 'tf-table-row' : 'hidden'} min-w-[760px] grid-cols-[minmax(260px,1fr)_180px_160px_160px_120px] gap-3 px-4 py-3`}>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <Trash2 size={15} className="text-[var(--color-muted)]" />
                <span className="truncate text-sm font-semibold">{client.org_name}</span>
              </div>
              <div className="mt-1 text-xs text-[var(--color-text-secondary)]">#{client.id}</div>
            </div>
            <span className="truncate text-sm text-[var(--color-text-secondary)]">{client.domain || 'Без домена'}</span>
            <span className="text-sm text-[var(--color-text-secondary)]">{client.status}</span>
            <span className="text-sm text-[var(--color-text-secondary)]">{client.deleted_at ? new Date(client.deleted_at).toLocaleString('ru-RU') : '-'}</span>
            <button onClick={() => restoreClient(client)} className="tf-button">
              <RotateCcw size={15} />
              Вернуть
            </button>
          </div>
        ))}
        {openSections.clients && clients.length === 0 && <div className="p-10 text-center text-sm text-[var(--color-text-secondary)]">Удалённых организаций нет.</div>}
      </section>

      <section className="tf-panel-flat overflow-x-auto">
        <button type="button" onClick={() => toggleSection('reports')} className="flex w-full items-center gap-2 border-b border-[var(--color-border)] px-4 py-3 text-left text-sm font-bold">
          {openSections.reports ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          <FileText size={15} className="text-[var(--color-muted)]" />
          <span className="min-w-0 flex-1">Удаленные отчеты</span>
          <span className="tf-chip">{reports.length}</span>
        </button>
        <div className={`${openSections.reports ? 'grid' : 'hidden'} min-w-[900px] grid-cols-[minmax(280px,1fr)_180px_180px_160px_120px] gap-3 border-b border-[var(--color-border)] px-4 py-3 text-xs font-bold uppercase text-[var(--color-muted)]`}>
          <span>Отчет</span>
          <span>Клиент</span>
          <span>Период</span>
          <span>Удален</span>
          <span />
        </div>
        {reports.map(report => (
          <div key={report.id} className={`${openSections.reports ? 'tf-table-row' : 'hidden'} min-w-[900px] grid-cols-[minmax(280px,1fr)_180px_180px_160px_120px] gap-3 px-4 py-3`}>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <FileText size={15} className="text-[var(--color-muted)]" />
                <span className="truncate text-sm font-semibold">{report.title}</span>
              </div>
              <div className="mt-1 text-xs text-[var(--color-text-secondary)]">#{report.id} · {report.status}</div>
            </div>
            <span className="truncate text-sm text-[var(--color-text-secondary)]">{report.client || 'Без клиента'}</span>
            <span className="text-sm text-[var(--color-text-secondary)]">{report.period_start ? new Date(report.period_start).toLocaleDateString('ru-RU') : '-'} - {report.period_end ? new Date(report.period_end).toLocaleDateString('ru-RU') : '-'}</span>
            <span className="text-sm text-[var(--color-text-secondary)]">{report.deleted_at ? new Date(report.deleted_at).toLocaleString('ru-RU') : '-'}</span>
            <button onClick={() => restoreReport(report)} className="tf-button">
              <RotateCcw size={15} />
              Вернуть
            </button>
          </div>
        ))}
        {openSections.reports && reports.length === 0 && <div className="p-10 text-center text-sm text-[var(--color-text-secondary)]">Удаленных отчетов нет.</div>}
      </section>
    </div>
  );
}
