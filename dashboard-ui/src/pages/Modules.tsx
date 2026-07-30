import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { Building2, CalendarClock, Clock3, Edit3, FileText, Plus, Trash2, UsersRound, X } from 'lucide-react';
import { api } from '../api/client';
import { referenceCache } from '../api/cache';
import { RichTextEditor } from '../components/RichTextEditor';
import { SearchSelect } from '../components/SearchSelect';
import type { Client, User } from '../api/client';
import { taskTypeMeta } from '../lib/taskflow';
import { useAuth } from '../hooks/useAuth';

type ModuleRule = {
  id: number;
  name: string;
  description: string;
  client_id: number | null;
  client_ids?: number[];
  client?: string;
  assignee_id: number | null;
  assignee?: string;
  recurring_interval: 'daily' | 'weekly' | 'monthly' | null;
  recurring_day: number | null;
  recurring_count: number | null;
  task_title_template: string | null;
  task_title_templates?: string[];
  completion_offset_days?: number;
  deadline_offset_days?: number | null;
  task_type: string;
  task_priority?: string;
  task_notes_template?: string;
  is_active: boolean;
  last_generated_at?: string;
};

const weekdays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

function plainText(value: string) {
  return value.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
}

export function Modules() {
  const { hasRole } = useAuth();
  const canManage = hasRole('superadmin') || hasRole('admin');
  const [modules, setModules] = useState<ModuleRule[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<ModuleRule | null>(null);
  const [showModal, setShowModal] = useState(false);

  const load = async () => {
    const [moduleList, clientList, userList] = await Promise.all([
      api.getModules(),
      referenceCache.clients().catch(() => []),
      referenceCache.users().catch(() => []),
    ]);
    setModules(moduleList);
    setClients(clientList);
    setUsers(userList);
  };

  useEffect(() => {
    load().finally(() => setLoading(false));
  }, []);

  const handleDelete = async (id: number) => {
    if (!confirm('Удалить правило модуля?')) return;
    await api.deleteModule(id);
    setModules(prev => prev.filter(module => module.id !== id));
  };

  const saveRule = async (data: Partial<ModuleRule>) => {
    if (editing) await api.updateModule(editing.id, data);
    else await api.createModule(data);
    setShowModal(false);
    setEditing(null);
    await load();
  };

  if (loading) return <div className="grid h-64 place-items-center text-sm text-[var(--color-text-secondary)]">Загрузка модулей...</div>;

  return (
    <div className="mx-auto max-w-[1400px] space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h2 className="text-xl font-black">Модули</h2>
          <p className="text-sm text-[var(--color-text-secondary)]">Автоматические правила, которые сами создают задачи по клиентам, датам и типам работ.</p>
        </div>
        {canManage && <button onClick={() => { setEditing(null); setShowModal(true); }} className="tf-button tf-button-primary ml-auto"><Plus size={16} />Новое правило</button>}
      </div>

      <section className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        {modules.map(rule => (
          <article key={rule.id} className="tf-panel-flat p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="truncate text-base font-bold">{rule.name}</h3>
                  <span className={rule.is_active ? 'tf-chip text-[var(--color-success)]' : 'tf-chip text-[var(--color-muted)]'}>
                    {rule.is_active ? 'Активно' : 'Пауза'}
                  </span>
                </div>
                {rule.description && <p className="mt-1 text-sm text-[var(--color-text-secondary)]">{plainText(rule.description)}</p>}
              </div>
              {canManage && <div className="flex shrink-0 gap-1">
                <button onClick={() => { setEditing(rule); setShowModal(true); }} className="tf-button" title="Редактировать"><Edit3 size={15} /></button>
                <button onClick={() => handleDelete(rule.id)} className="tf-button text-[var(--color-danger)]" title="Удалить"><Trash2 size={15} /></button>
              </div>}
            </div>

            <div className="mt-4 grid grid-cols-1 gap-2 text-sm md:grid-cols-2">
              <Info label="Клиент" value={rule.client || 'Не выбран'} />
              <Info label="Исполнитель" value={rule.assignee || 'Не назначен'} />
              <Info label="Тип задачи" value={taskTypeMeta[rule.task_type] || rule.task_type || 'Обычная'} />
              <Info label="Приоритет" value={rule.task_priority || 'Средний'} />
              <Info label="Расписание" value={scheduleText(rule)} />
              <Info label="Дата выполнения" value={offsetText(rule.completion_offset_days ?? 0)} />
              <Info label="Крайний срок" value={rule.deadline_offset_days === null || rule.deadline_offset_days === undefined ? 'Не задавать' : offsetText(rule.deadline_offset_days)} />
              <Info label="Основной шаблон" value={rule.task_title_template || rule.name} wide />
              <Info label="Дополнительных шаблонов" value={String(rule.task_title_templates?.length || 0)} />
              <Info label="Последний запуск" value={rule.last_generated_at || 'Ещё не запускалось'} />
            </div>
          </article>
        ))}
      </section>

      {modules.length === 0 && (
        <div className="tf-panel-flat p-10 text-center text-sm text-[var(--color-text-secondary)]">Пока нет правил. Создайте модуль для регулярного отчёта, аудита, контент-плана или звонка клиенту.</div>
      )}

      {showModal && (
        <ModuleModal
          rule={editing}
          clients={clients}
          users={users}
          onClose={() => setShowModal(false)}
          onSave={saveRule}
        />
      )}
    </div>
  );
}

function Info({ label, value, wide }: { label: string; value: string; wide?: boolean }) {
  return (
    <div className={wide ? 'md:col-span-2' : ''}>
      <div className="text-xs text-[var(--color-text-secondary)]">{label}</div>
      <div className="mt-0.5 truncate font-semibold">{value}</div>
    </div>
  );
}

function offsetText(days: number) {
  if (days === 0) return 'В день генерации';
  if (days === 1) return 'На следующий день';
  return `Через ${days} дн.`;
}

function scheduleText(rule: ModuleRule) {
  if (rule.recurring_interval === 'daily') return 'Каждый день';
  if (rule.recurring_interval === 'weekly') return `Каждую неделю, ${weekdays[(rule.recurring_day || 1) - 1] || 'день не выбран'}`;
  if (rule.recurring_interval === 'monthly') return `Каждый месяц, ${rule.recurring_day || 1} число`;
  return 'Не настроено';
}

function ModuleModal({
  rule,
  clients,
  users,
  onClose,
  onSave,
}: {
  rule: ModuleRule | null;
  clients: Client[];
  users: User[];
  onClose: () => void;
  onSave: (data: Partial<ModuleRule>) => Promise<void>;
}) {
  const [name, setName] = useState(rule?.name || '');
  const [description, setDescription] = useState(rule?.description || '');
  const [clientIds, setClientIds] = useState<number[]>(rule?.client_ids?.length ? rule.client_ids : (rule?.client_id ? [rule.client_id] : []));
  const [clientSearch, setClientSearch] = useState('');
  const [assigneeId, setAssigneeId] = useState(rule?.assignee_id ? String(rule.assignee_id) : '');
  const [taskType, setTaskType] = useState(rule?.task_type || 'custom');
  const [taskPriority, setTaskPriority] = useState(rule?.task_priority || 'medium');
  const [taskNotesTemplate, setTaskNotesTemplate] = useState(rule?.task_notes_template || '');
  const [template, setTemplate] = useState(rule?.task_title_template || rule?.name || '');
  const [templates, setTemplates] = useState((rule?.task_title_templates || []).join('\n'));
  const [completionOffset, setCompletionOffset] = useState(rule?.completion_offset_days ?? 0);
  const [deadlineOffset, setDeadlineOffset] = useState<string | number>(rule?.deadline_offset_days ?? '');
  const [interval, setInterval] = useState<ModuleRule['recurring_interval']>(rule?.recurring_interval || 'monthly');
  const [day, setDay] = useState(rule?.recurring_day || 1);
  const [count, setCount] = useState(rule?.recurring_count || 1);
  const [active, setActive] = useState(rule?.is_active ?? true);
  const [saving, setSaving] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (deadlineOffset !== '' && Number(completionOffset) > Number(deadlineOffset)) return;
    setSaving(true);
    await onSave({
      name,
      description,
      client_id: clientIds[0] || null,
      client_ids: clientIds,
      assignee_id: assigneeId ? Number(assigneeId) : null,
      task_type: taskType,
      task_priority: taskPriority,
      task_notes_template: taskNotesTemplate,
      task_title_template: template || name,
      task_title_templates: templates.split('\n').map(item => item.trim()).filter(Boolean),
      completion_offset_days: Number(completionOffset) || 0,
      deadline_offset_days: deadlineOffset === '' ? null : Number(deadlineOffset),
      recurring_interval: interval,
      recurring_day: interval === 'daily' ? null : Number(day),
      recurring_count: Math.max(1, Number(count) || 1),
      is_active: active,
    });
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4" onClick={onClose}>
      <form onSubmit={submit} className="tf-panel max-h-[92vh] w-full max-w-4xl overflow-y-auto p-5" onClick={event => event.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-black">{rule ? 'Редактировать правило' : 'Новое правило модуля'}</h2>
            <p className="text-sm text-[var(--color-text-secondary)]">Настройте, когда и кому приложение будет автоматически ставить задачи.</p>
          </div>
          <button type="button" onClick={onClose} className="tf-button"><X size={16} /></button>
        </div>

        <div className="grid gap-4">
          <ModuleSection icon={<FileText size={16} />} title="Что создавать">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <Field label="Название правила"><input className="tf-input" value={name} onChange={event => setName(event.target.value)} required placeholder="Ежемесячный отчёт" /></Field>
              <Field label="Тип задачи">
                <select className="tf-input" value={taskType} onChange={event => setTaskType(event.target.value)}>
                  {Object.entries(taskTypeMeta).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                </select>
              </Field>
              <Field label="Приоритет">
                <select className="tf-input" value={taskPriority} onChange={event => setTaskPriority(event.target.value)}>
                  <option value="low">Низкий</option><option value="medium">Средний</option><option value="high">Высокий</option><option value="urgent">Срочный</option>
                </select>
              </Field>
              <Field label="Статус правила">
                <label className="flex h-10 items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 text-sm">
                  <input type="checkbox" checked={active} onChange={event => setActive(event.target.checked)} />
                  Активно
                </label>
              </Field>
            </div>
          </ModuleSection>

          <ModuleSection icon={<Building2 size={16} />} title="Для каких организаций">
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2">
              <input className="tf-input mb-2" value={clientSearch} onChange={event => setClientSearch(event.target.value)} placeholder="Найти организацию или домен" />
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <button type="button" className="tf-button px-2.5 py-1.5 text-xs" onClick={() => setClientIds(clients.map(client => client.id))}>Выбрать все</button>
                <button type="button" className="tf-button px-2.5 py-1.5 text-xs" onClick={() => setClientIds([])}>Снять все</button>
                <span className="text-xs text-[var(--color-muted)]">Выбрано: {clientIds.length}</span>
              </div>
              <div className="grid max-h-52 grid-cols-1 gap-1 overflow-auto md:grid-cols-2">
                {clients.filter(client => {
                  const query = clientSearch.trim().toLocaleLowerCase('ru-RU');
                  return !query || `${client.org_name} ${client.domain || ''}`.toLocaleLowerCase('ru-RU').includes(query);
                }).map(client => (
                  <label key={client.id} className="flex min-w-0 cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm hover:bg-[var(--color-surface-3)]">
                    <input type="checkbox" checked={clientIds.includes(client.id)} onChange={() => setClientIds(prev => prev.includes(client.id) ? prev.filter(id => id !== client.id) : [...prev, client.id])} />
                    <span className="min-w-0"><span className="block truncate font-semibold">{client.org_name}</span>{client.domain && <span className="block truncate text-xs text-[var(--color-muted)]">{client.domain}</span>}</span>
                  </label>
                ))}
              </div>
            </div>
          </ModuleSection>

          <ModuleSection icon={<UsersRound size={16} />} title="Кому и когда ставить">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <Field label="Кому поставить задачу">
                <SearchSelect value={assigneeId} options={users.map(user => ({ value: String(user.id), label: user.username }))} onChange={setAssigneeId} emptyLabel="Не назначать" searchPlaceholder="Найти сотрудника" />
              </Field>
              <Field label="Периодичность">
                <select className="tf-input" value={interval || 'monthly'} onChange={event => setInterval(event.target.value as ModuleRule['recurring_interval'])}>
                  <option value="daily">Каждый день</option>
                  <option value="weekly">Каждую неделю</option>
                  <option value="monthly">Каждый месяц</option>
                </select>
              </Field>
              <Field label={interval === 'weekly' ? 'День недели' : 'Число месяца'}>
                {interval === 'weekly' ? (
                  <select className="tf-input" value={day} onChange={event => setDay(Number(event.target.value))}>
                    {weekdays.map((label, index) => <option key={label} value={index + 1}>{label}</option>)}
                  </select>
                ) : (
                  <input className="tf-input" type="number" min={1} max={31} value={day} onChange={event => setDay(Number(event.target.value))} disabled={interval === 'daily'} />
                )}
              </Field>
              <Field label="Сколько задач создать">
                <input className="tf-input" type="number" min={1} max={20} value={count} onChange={event => setCount(Number(event.target.value))} />
              </Field>
              <Field label="Дата выполнения через, дней">
                <input className="tf-input" type="number" min={0} max={365} value={completionOffset} onChange={event => setCompletionOffset(Number(event.target.value))} />
              </Field>
              <Field label="Крайний срок через, дней">
                <input className="tf-input" type="number" min={completionOffset || 0} max={365} value={deadlineOffset} onChange={event => setDeadlineOffset(event.target.value)} placeholder="Не задавать" />
              </Field>
            </div>
          </ModuleSection>

          <ModuleSection icon={<Clock3 size={16} />} title="Шаблоны задачи">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <Field label="Основной шаблон названия" wide>
                <input className="tf-input" value={template} onChange={event => setTemplate(event.target.value)} placeholder="Подготовить отчёт для клиента" />
              </Field>
              <Field label="Шаблон описания создаваемой задачи" wide>
                <RichTextEditor value={taskNotesTemplate} onChange={setTaskNotesTemplate} minHeightClassName="min-h-24" placeholder="Что нужно сделать, какой результат получить, ссылки и критерии готовности..." />
              </Field>
              <Field label="Дополнительные шаблоны, каждый с новой строки" wide>
                <textarea className="tf-input min-h-24" value={templates} onChange={event => setTemplates(event.target.value)} placeholder={'Собрать данные\nПроверить доступы\nОтправить отчёт клиенту'} />
              </Field>
              <Field label="Описание правила" wide><RichTextEditor value={description} onChange={setDescription} minHeightClassName="min-h-24" /></Field>
            </div>
          </ModuleSection>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)]"><CalendarClock size={15} />Правила проверяются автоматически каждый день в 08:00.</div>
          <button disabled={saving} className="tf-button tf-button-primary">{saving ? 'Сохранение...' : 'Сохранить правило'}</button>
        </div>
      </form>
    </div>
  );
}

function Field({ label, children, wide }: { label: string; children: ReactNode; wide?: boolean }) {
  return (
    <label className={wide ? 'md:col-span-2' : ''}>
      <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">{label}</span>
      {children}
    </label>
  );
}

function ModuleSection({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <h3 className="mb-3 flex items-center gap-2 text-sm font-black">{icon}{title}</h3>
      {children}
    </section>
  );
}
