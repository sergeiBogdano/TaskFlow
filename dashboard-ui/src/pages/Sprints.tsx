import { useEffect, useState, type FormEvent } from 'react';
import { CalendarDays, Flag, Plus, Target, Trash2, X } from 'lucide-react';
import { api, type Sprint, type SprintDetail, type Task } from '../api/client';
import { SearchSelect } from '../components/SearchSelect';
import { formatDate, cn } from '../lib/taskflow';

export function Sprints() {
  const [sprints, setSprints] = useState<Sprint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [detailId, setDetailId] = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      setSprints(await api.getSprints());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить спринты.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  return (
    <div className="mx-auto max-w-[1200px] space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h2 className="tf-page-title">Спринты</h2>
          <p className="tf-page-subtitle">Временные отрезки с набором задач и прогрессом. Как в Практикуме.</p>
        </div>
        <button type="button" onClick={() => setCreateOpen(true)} className="tf-button tf-button-primary ml-auto">
          <Plus size={16} />Новый спринт
        </button>
      </div>

      {error && <div className="rounded-lg border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 px-3 py-2 text-sm text-[var(--color-danger)]">{error}</div>}

      {loading ? (
        <div className="grid h-48 place-items-center text-sm text-[var(--color-text-secondary)]">Загрузка спринтов...</div>
      ) : sprints.length === 0 ? (
        <div className="tf-panel-flat p-10 text-center">
          <div className="mx-auto grid h-16 w-16 place-items-center rounded-[20px] bg-[var(--color-overlay)]">
            <Flag size={28} className="text-[var(--color-muted)]" strokeWidth={1.5} />
          </div>
          <p className="mt-4 text-lg font-semibold">Спринтов пока нет</p>
          <p className="mx-auto mt-1 max-w-sm text-sm text-[var(--color-text-secondary)]">Создайте первый — например «Неделя 1», добавьте задачи и следите за прогрессом.</p>
          <button type="button" onClick={() => setCreateOpen(true)} className="tf-button tf-button-primary mt-5">
            <Plus size={15} />Создать спринт
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {sprints.map(sprint => (
            <button
              key={sprint.id}
              type="button"
              onClick={() => setDetailId(sprint.id)}
              className="anim-rise tf-panel-flat p-5 text-left transition hover:-translate-y-0.5"
            >
              <div className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate text-base font-bold">{sprint.name}</span>
                <span className={cn('tf-chip shrink-0', sprint.status === 'done' && 'border-[var(--color-success)]/50 text-[var(--color-success)]')}>
                  {sprint.status === 'done' ? 'Завершён' : 'Активен'}
                </span>
              </div>
              {sprint.goal && <p className="mt-1 line-clamp-2 text-sm text-[var(--color-text-secondary)]">{sprint.goal}</p>}
              <div className="mt-2 flex items-center gap-1.5 text-xs text-[var(--color-muted)]">
                <CalendarDays size={13} />
                {[sprint.start_date, sprint.end_date].filter(Boolean).join(' — ') || 'Без дат'}
              </div>
              <div className="mt-4">
                <div className="h-2.5 overflow-hidden rounded-full bg-[var(--color-overlay)]">
                  <div
                    className="h-full rounded-full transition-[width] duration-500"
                    style={{ width: `${sprint.progress.percent}%`, background: 'var(--color-accent)' }}
                  />
                </div>
                <div className="mt-1.5 flex items-center justify-between text-xs text-[var(--color-text-secondary)]">
                  <span>{sprint.progress.done} из {sprint.progress.total} задач</span>
                  <span className="font-bold text-[var(--color-text)]">{sprint.progress.percent}%</span>
                </div>
              </div>
            </button>
          ))}
        </div>
      )}

      {createOpen && (
        <SprintCreateModal
          onClose={() => setCreateOpen(false)}
          onCreated={() => {
            setCreateOpen(false);
            void load();
          }}
        />
      )}
      {detailId !== null && (
        <SprintDetailModal
          sprintId={detailId}
          onClose={() => {
            setDetailId(null);
            void load();
          }}
        />
      )}
    </div>
  );
}

function SprintCreateModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState('');
  const [goal, setGoal] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) {
      setError('Нужно название.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await api.createSprint({
        name: name.trim(),
        goal: goal.trim() || null,
        start_date: start || null,
        end_date: end || null,
      });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось создать.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="anim-modal fixed inset-0 z-50 grid place-items-center bg-black/55 p-4" onClick={onClose}>
      <form onSubmit={submit} className="tf-modal-shell w-full max-w-md p-5" onClick={event => event.stopPropagation()}>
        <div className="mb-4 text-base font-bold">Новый спринт</div>
        <div className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Название</span>
            <input className="tf-input" value={name} onChange={event => setName(event.target.value)} placeholder="Например: Неделя 1" maxLength={200} required autoFocus />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Цель</span>
            <input className="tf-input" value={goal} onChange={event => setGoal(event.target.value)} placeholder="Что хотим закрыть" maxLength={2000} />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Начало</span>
              <input className="tf-input" type="date" value={start} onChange={event => setStart(event.target.value)} />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Конец</span>
              <input className="tf-input" type="date" value={end} min={start || undefined} onChange={event => setEnd(event.target.value)} />
            </label>
          </div>
          {error && <div className="text-sm font-semibold text-[var(--color-danger)]">{error}</div>}
          <div className="flex gap-2">
            <button type="button" onClick={onClose} className="tf-button flex-1">Отмена</button>
            <button type="submit" disabled={saving} className="tf-button tf-button-primary flex-1">{saving ? 'Создаём...' : 'Создать'}</button>
          </div>
        </div>
      </form>
    </div>
  );
}

function SprintDetailModal({ sprintId, onClose }: { sprintId: number; onClose: () => void }) {
  const [detail, setDetail] = useState<SprintDetail | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [error, setError] = useState('');
  const [name, setName] = useState('');
  const [goal, setGoal] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [status, setStatus] = useState('active');
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setError('');
    try {
      const [loaded, taskList] = await Promise.all([api.getSprint(sprintId), api.getTasks().catch(() => [] as Task[])]);
      setDetail(loaded);
      setName(loaded.name);
      setGoal(loaded.goal || '');
      setStart(loaded.start_date || '');
      setEnd(loaded.end_date || '');
      setStatus(loaded.status);
      setTasks(Array.isArray(taskList) ? taskList : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить спринт.');
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sprintId]);

  const save = async () => {
    if (!name.trim()) {
      setError('Название не может быть пустым.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await api.updateSprint(sprintId, {
        name: name.trim(),
        goal: goal.trim() || null,
        start_date: start || null,
        end_date: end || null,
        status,
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить.');
    } finally {
      setSaving(false);
    }
  };

  const addTask = async (value: string) => {
    if (!value) return;
    try {
      await api.addSprintTasks(sprintId, [Number(value)]);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось добавить задачу.');
    }
  };

  const removeTask = async (taskId: number) => {
    try {
      await api.removeSprintTask(sprintId, taskId);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось убрать задачу.');
    }
  };

  const removeSprint = async () => {
    if (!confirm(`Удалить спринт «${detail?.name}»? Задачи останутся.`)) return;
    try {
      await api.deleteSprint(sprintId);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось удалить.');
    }
  };

  const inSprint = new Set((detail?.tasks || []).map(t => t.id));
  const options = tasks.filter(t => !inSprint.has(t.id)).map(t => ({
    value: String(t.id),
    label: t.title,
    description: t.client || 'Без клиента',
  }));

  return (
    <div className="anim-modal fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-black/55 p-3 sm:p-6" onClick={onClose}>
      <div className="tf-modal-shell flex max-h-[92dvh] w-full max-w-3xl flex-col overflow-hidden" onClick={event => event.stopPropagation()}>
        <div className="flex shrink-0 items-center gap-3 px-5 pb-4 pt-5">
          <Target size={18} className="shrink-0 text-[var(--color-accent)]" />
          <input
            value={name}
            onChange={event => setName(event.target.value)}
            placeholder="Название спринта"
            maxLength={200}
            className="min-w-0 flex-1 bg-transparent text-xl font-bold tracking-tight outline-none placeholder:text-[var(--color-muted)]"
          />
          <button type="button" onClick={onClose} aria-label="Закрыть" className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[var(--color-overlay)] text-[var(--color-text-secondary)] transition hover:bg-[var(--color-overlay-strong)]">
            <X size={16} />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 pb-2">
          {error && <div className="text-sm font-semibold text-[var(--color-danger)]">{error}</div>}
          {!detail ? (
            <div className="grid h-32 place-items-center text-sm text-[var(--color-text-secondary)]">Загрузка...</div>
          ) : (
            <>
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4">
                <div className="h-2.5 overflow-hidden rounded-full bg-[var(--color-overlay)]">
                  <div className="h-full rounded-full transition-[width] duration-500" style={{ width: `${detail.progress.percent}%`, background: 'var(--color-accent)' }} />
                </div>
                <div className="mt-2 flex items-center justify-between text-sm">
                  <span className="text-[var(--color-text-secondary)]">{detail.progress.done} из {detail.progress.total} задач</span>
                  <span className="text-lg font-bold">{detail.progress.percent}%</span>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <label className="block sm:col-span-2">
                  <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Цель спринта</span>
                  <input className="tf-input" value={goal} onChange={event => setGoal(event.target.value)} placeholder="Что хотим закрыть" maxLength={2000} />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Начало</span>
                  <input className="tf-input" type="date" value={start} onChange={event => setStart(event.target.value)} />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Конец</span>
                  <input className="tf-input" type="date" value={end} min={start || undefined} onChange={event => setEnd(event.target.value)} />
                </label>
              </div>
              <div className="text-xs text-[var(--color-text-secondary)]">
                {detail.start_date || detail.end_date
                  ? <>Сроки: {detail.start_date ? formatDate(detail.start_date) : '—'} — {detail.end_date ? formatDate(detail.end_date) : '—'}</>
                  : 'Сроки не заданы'}
              </div>

              <div>
                <div className="mb-2 text-sm font-bold">Задачи спринта · {(detail.tasks || []).length}</div>
                <div className="mb-3">
                  <SearchSelect value="" options={options} onChange={addTask} placeholder="Добавить задачу..." searchPlaceholder="Найти задачу..." />
                </div>
                <div className="space-y-1.5">
                  {(detail.tasks || []).map(t => (
                    <div key={t.id} className="flex items-center gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2">
                      <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: t.status === 'done' ? 'var(--color-success)' : 'var(--color-accent)' }} />
                      <span className="min-w-0 flex-1 truncate text-sm font-medium">{t.title}</span>
                      <button type="button" onClick={() => removeTask(t.id)} className="grid h-7 w-7 shrink-0 place-items-center rounded-md text-[var(--color-muted)] transition hover:bg-[var(--color-surface-3)] hover:text-[var(--color-danger)]" aria-label={`Убрать ${t.title}`}>
                        <X size={14} />
                      </button>
                    </div>
                  ))}
                  {(detail.tasks || []).length === 0 && (
                    <div className="text-sm text-[var(--color-text-secondary)]">Пока пусто — добавьте задачи поиском выше.</div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2 px-5 py-4">
          <button type="button" onClick={removeSprint} className="tf-button text-[var(--color-danger)]"><Trash2 size={15} />Удалить</button>
          <div className="ml-auto flex gap-2">
            <button
              type="button"
              onClick={() => { setStatus(status === 'done' ? 'active' : 'done'); }}
              className="tf-button"
            >
              {status === 'done' ? 'Вернуть в работу' : 'Завершить'}
            </button>
            <button type="button" onClick={save} disabled={saving} className="tf-button tf-button-primary">
              {saving ? 'Сохранение...' : 'Сохранить'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
