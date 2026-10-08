import type { FieldAccess, FieldMode } from '../lib/fieldAccess';
import { TASK_FIELD_DEFAULTS, SPRINT_FIELD_DEFAULTS, taskField, sprintField } from '../lib/uiconfig';

export function FieldAccessEditor({ value, onChange, disabled = false, personal = false }: {
  value: FieldAccess; onChange: (value: FieldAccess) => void; disabled?: boolean; personal?: boolean;
}) {
  return <div className="space-y-3">{Object.entries({ tasks: TASK_FIELD_DEFAULTS, sprints: SPRINT_FIELD_DEFAULTS }).map(([entity, fields]) =>
    <details key={entity} className="rounded-xl border border-[var(--color-border)] p-3" open>
      <summary className="cursor-pointer font-semibold">Поля {entity === 'tasks' ? 'задач' : 'спринтов'}</summary>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">{Object.keys(fields).map(key => {
        const label = (entity === 'tasks' ? taskField(key) : sprintField(key)).label;
        const required = (entity === 'tasks' && ['title', 'status'].includes(key)) || (entity === 'sprints' && key === 'name');
        return <label key={key} className="flex min-w-0 flex-col gap-1 text-sm"><span>{label}</span>
          <select aria-label={`Доступ к полю «${label}»`} className="tf-input" disabled={disabled} value={value[entity]?.[key] || ''}
            onChange={event => { const next = { ...value[entity] }; if (event.target.value) next[key] = event.target.value as FieldMode; else delete next[key]; onChange({ ...value, [entity]: next }); }}>
            <option value="">{personal ? 'Как в профиле' : 'Стандарт: редактирование'}</option>
            {!required && <option value="hidden">Скрыто</option>}<option value="view">Только просмотр</option><option value="edit">Редактирование</option>
          </select></label>;
      })}</div>
    </details>)}</div>;
}
