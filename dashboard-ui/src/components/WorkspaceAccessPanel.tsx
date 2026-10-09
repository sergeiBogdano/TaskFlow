import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, type WorkspaceAccessReport, type WorkspaceRole } from '../api/client';
import { useAuth } from '../hooks/useAuth';
import type { FieldAccess } from '../lib/fieldAccess';
import { FieldAccessEditor } from './FieldAccessEditor';

const levels: Record<string, string> = { owner: 'Владелец', admin: 'Администратор пространства', member: 'Участник' };
const ranks: Record<string, number> = { owner: 3, admin: 2, member: 1 };
export function WorkspaceAccessPanel({ workspaceId, level, initialUserId, onDirtyChange }: { workspaceId: number; level: string; initialUserId?: number; onDirtyChange?: (dirty: boolean) => void }) {
  const { user } = useAuth();
  const currentWorkspace = useRef(workspaceId); currentWorkspace.current = workspaceId;
  const revision = useRef(0); const initialSelection = useRef('');
  const [report, setReport] = useState<WorkspaceAccessReport | null>(null);
  const [reportWorkspace, setReportWorkspace] = useState<number | null>(null);
  const [roles, setRoles] = useState<WorkspaceRole[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [permissions, setPermissions] = useState<Record<string, boolean>>({});
  const [fields, setFields] = useState<FieldAccess>({});
  const [featureEdits, setFeatureEdits] = useState<Record<string, boolean | null>>({});
  const [tab, setTab] = useState('rights'); const [query, setQuery] = useState(''); const [blocked, setBlocked] = useState(false);
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    if (currentWorkspace.current !== workspaceId) return;
    const current = ++revision.current;
    try {
      const [data, profiles] = await Promise.all([api.getWorkspaceAccess(workspaceId), api.getWsRoles(workspaceId)]);
      if (currentWorkspace.current === workspaceId && revision.current === current) { setReport(data); setReportWorkspace(workspaceId); setRoles(profiles.roles); }
    } catch (err) { if (currentWorkspace.current === workspaceId && revision.current === current) setError(err instanceof Error ? err.message : 'Не удалось загрузить доступ'); }
  }, [workspaceId]);
  useEffect(() => { void load(); const reload = () => { void load(); }; window.addEventListener('taskflow:access-updated', reload); return () => { revision.current++; window.removeEventListener('taskflow:access-updated', reload); }; }, [load]);
  useEffect(() => { setReport(null); setSelected(null); setPermissions({}); setFields({}); setFeatureEdits({}); setError(''); initialSelection.current = ''; }, [workspaceId]);
  const member = reportWorkspace === workspaceId ? report?.members.find(item => item.user_id === selected) : undefined;
  const canEdit = Boolean(member && !member.is_root && member.user_id !== user?.id && (user?.is_root || (ranks[level] || 0) > (ranks[member.level] || 0)));
  const dirty = !!member && (Object.keys(featureEdits).length > 0 || JSON.stringify(permissions) !== JSON.stringify(member.overrides.permissions || {}) || JSON.stringify(fields) !== JSON.stringify(member.overrides.fields || {}));
  useEffect(() => { onDirtyChange?.(dirty); return () => onDirtyChange?.(false); }, [dirty, onDirtyChange]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);
  const select = (id: number) => {
    const item = report?.members.find(row => row.user_id === id);
    setSelected(id); setPermissions({ ...item?.overrides.permissions }); setFields({ ...item?.overrides.fields }); setFeatureEdits({}); setError(''); setTab('rights'); setQuery('');
  };
  useEffect(() => {
    const key = `${workspaceId}:${initialUserId}`;
    if (initialUserId && reportWorkspace === workspaceId && report?.members.some(item => item.user_id === initialUserId) && initialSelection.current !== key) { select(initialUserId); initialSelection.current = key; }
  }, [initialUserId, workspaceId, reportWorkspace, report]);
  const save = async (reset = false) => {
    if (!member || !canEdit) return;
    setBusy(true); setError('');
    try {
      await api.setWorkspaceAccess(workspaceId, member.user_id, { permissions: reset ? {} : permissions, fields: reset ? {} : fields, ...(!reset && user?.is_root ? { function_availability: featureEdits } : {}) });
      if (reset) { setPermissions({}); setFields({}); }
      setFeatureEdits({}); await load(); window.dispatchEvent(new Event('taskflow:access-updated'));
    } catch (err) { setError(err instanceof Error ? err.message : 'Не удалось сохранить'); await load(); }
    finally { setBusy(false); }
  };
  const assignProfile = async (roleId: number | null) => {
    if (!member || !canEdit || (dirty && !confirm('Есть несохранённые изменения. Сменить профиль и загрузить сохранённые настройки?'))) return;
    setBusy(true); setError('');
    try { await api.setWsMemberRole(workspaceId, member.user_id, roleId); setPermissions({ ...member.overrides.permissions }); setFields({ ...member.overrides.fields }); setFeatureEdits({}); await load(); window.dispatchEvent(new Event('taskflow:access-updated')); }
    catch (err) { setError(err instanceof Error ? err.message : 'Не удалось назначить профиль'); }
    finally { setBusy(false); }
  };
  return <section className="tf-panel-flat space-y-4 p-5">
    <h3 className="text-lg font-bold">Доступ участника</h3>
    <p className="text-sm text-[var(--color-text-secondary)]">Профиль задаёт рабочие права. Личные настройки уточняют их. Ниже виден сохранённый результат и причина каждого запрета.</p>
    <label className="block text-sm">Участник<select className="tf-input mt-1" disabled={busy || reportWorkspace !== workspaceId} value={selected ?? ''} onChange={e => { if (!dirty || confirm('Переключить участника без сохранения изменений?')) select(Number(e.target.value)); }}><option value="" disabled>Выберите участника</option>{reportWorkspace === workspaceId && report?.members.map(item => <option key={item.user_id} value={item.user_id}>{item.username} · {levels[item.level]}</option>)}</select></label>
    {error && <p role="alert" className="tf-alert-error">{error}</p>}
    {member && <>
      <div className="grid gap-3 rounded-xl bg-[var(--color-surface-2)] p-4 sm:grid-cols-2"><div><strong>{member.username}</strong><p className="text-sm">{levels[member.level]}</p><p className="mt-1 text-xs text-[var(--color-muted)]">Уровень управления меняется на вкладке «Состав команды».</p></div><label className="text-sm">Рабочий профиль<select aria-label="Рабочий профиль участника" className="tf-input mt-1" disabled={!canEdit || busy} value={member.profile_id ?? ''} onChange={e => void assignProfile(e.target.value ? Number(e.target.value) : null)}><option value="">Стандартный профиль уровня</option>{roles.map(role => <option key={role.id} value={role.id}>{role.name}</option>)}</select></label>
      {!canEdit && <p className="text-xs text-[var(--color-muted)] sm:col-span-2">Только просмотр: свой доступ, суперадмина и участников равного или более высокого уровня здесь менять нельзя.</p>}</div>
      <nav className="flex gap-2" aria-label="Настройки выбранного участника">{[['rights', 'Права и функции'], ['fields', 'Доступ к полям']].map(([key, title]) => <button key={key} className={`tf-button ${tab === key ? 'tf-button-primary' : ''}`} aria-pressed={tab === key} onClick={() => setTab(key)}>{title}</button>)}</nav>
      {tab === 'rights' ? <>
        <div className="flex flex-wrap items-center gap-3"><input aria-label="Поиск права" placeholder="Найти: ИИ, задачи, заметки…" className="tf-input flex-1" value={query} onChange={e => setQuery(e.target.value)} /><label className="flex gap-2 text-sm"><input type="checkbox" checked={blocked} onChange={e => setBlocked(e.target.checked)} />Только недоступные</label></div>
        {user?.is_root && <p className="text-xs text-[var(--color-muted)]">«Право» действует в этом пространстве. «Личная доступность функции» действует во всех пространствах пользователя. Общие запреты приложения и пространства имеют приоритет.</p>}
        {report?.groups.map(group => {
          const items = group.items.filter(item => `${item.label} ${item.hint} ${item.key}`.toLowerCase().includes(query.toLowerCase()) && (!blocked || !member.permissions[item.key]?.allowed));
          if (!items.length) return null;
          return <details key={group.id} className="rounded-xl border border-[var(--color-border)] p-3" open={query || blocked ? true : undefined}><summary className="cursor-pointer font-semibold">{group.title} · {items.length}</summary><div className="mt-3 space-y-2">{items.map(item => {
            const actual = member.permissions[item.key];
            const availability = item.key in featureEdits ? featureEdits[item.key] : actual?.availability_override;
            return <div key={item.key} className="grid gap-3 rounded-lg bg-[var(--color-surface-2)] p-3 lg:grid-cols-[1fr_180px_210px]">
              <div className="text-sm"><strong>{item.label}</strong><p className={actual?.allowed ? 'text-[var(--color-success)]' : 'text-[var(--color-muted)]'}>{actual?.allowed ? 'Сейчас доступно' : 'Сейчас недоступно'} · {actual?.source}</p><p className="text-xs">{actual?.reason}</p><p className="mt-1 text-xs text-[var(--color-muted)]">{item.hint}</p>{user?.is_root && actual && !actual.available && !actual.reason.includes('лично') && !actual.reason.includes('Скрытые') && <Link className="text-xs underline" to={actual.reason.includes('приложения') ? '/access?scope=app&tab=features' : actual.reason.includes('группе') ? '/access?scope=app&tab=groups' : '/access?scope=space&tab=tools'}>Открыть источник ограничения →</Link>}{actual?.reason.includes('Скрытые') && <button className="text-xs underline" onClick={() => setTab('fields')}>Проверить доступ к полям →</button>}</div>
              <label className="text-xs">Право в пространстве<select aria-label={`Право: ${item.label}`} className="tf-input mt-1" disabled={!canEdit || busy} value={item.key in permissions ? String(permissions[item.key]) : ''} onChange={e => setPermissions(previous => { const next = { ...previous }; if (!e.target.value) delete next[item.key]; else next[item.key] = e.target.value === 'true'; return next; })}><option value="">Как в профиле</option><option value="false">Запретить</option><option value="true" disabled={!user?.is_root && !user?.permissions[item.key]}>Разрешить</option></select></label>
              {user?.is_root && <label className="text-xs">Личная доступность функции<select aria-label={`Функция: ${item.label}`} className="tf-input mt-1" disabled={!canEdit || busy} value={availability == null ? '' : String(availability)} onChange={e => setFeatureEdits(previous => ({ ...previous, [item.key]: e.target.value === '' ? null : e.target.value === 'true' }))}><option value="">Наследовать</option><option value="true">Разрешить функцию</option><option value="false">Запретить функцию</option></select></label>}
            </div>;
          })}</div></details>;
        })}
      </> : <><FieldAccessEditor value={fields} onChange={setFields} disabled={!canEdit || busy} personal /><details className="text-sm"><summary>Сохранённый итоговый доступ к полям</summary><div className="mt-2 grid gap-2 sm:grid-cols-2">{Object.entries(member.fields).flatMap(([entity, values]) => Object.entries(values).map(([key, mode]) => <div key={`${entity}.${key}`} className="tf-chip">{report?.fields[entity]?.[key]?.label}: {mode === 'edit' ? 'редактирование' : mode === 'view' ? 'просмотр' : 'скрыто'}</div>))}</div></details></>}
      {canEdit && <div className="sticky bottom-2 flex flex-wrap items-center gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3"><button className="tf-button tf-button-primary" disabled={busy || !dirty} onClick={() => void save()}>Сохранить доступ</button><button className="tf-button" disabled={busy} onClick={() => { if (confirm('Убрать личные права и исключения полей в этом пространстве? Личная доступность функций во всём приложении сохранится.')) void save(true); }}>Вернуть права профиля</button>{dirty && <span role="status" className="text-xs text-[var(--color-muted)]">Есть несохранённые изменения</span>}</div>}
    </>}
  </section>;
}
