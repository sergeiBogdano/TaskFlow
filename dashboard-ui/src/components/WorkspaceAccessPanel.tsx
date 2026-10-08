import { useCallback, useEffect, useState } from 'react';
import { api, type WorkspaceAccessReport } from '../api/client';
import { useAuth } from '../hooks/useAuth';
import type { FieldAccess } from '../lib/fieldAccess';
import { FieldAccessEditor } from './FieldAccessEditor';

const levels: Record<string, string> = { owner: 'Владелец', admin: 'Администратор окружения', member: 'Участник' };
const ranks: Record<string, number> = { owner: 3, admin: 2, member: 1 };

export function WorkspaceAccessPanel({ workspaceId, level }: { workspaceId: number; level: string }) {
  const { user } = useAuth();
  const [report, setReport] = useState<WorkspaceAccessReport | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [permissions, setPermissions] = useState<Record<string, boolean>>({});
  const [fields, setFields] = useState<FieldAccess>({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try { setReport(await api.getWorkspaceAccess(workspaceId)); }
    catch (err) { setError(err instanceof Error ? err.message : 'Не удалось загрузить доступ'); }
  }, [workspaceId]);
  useEffect(() => { void load(); }, [load]);
  const member = report?.members.find(item => item.user_id === selected);
  const canEdit = !!member && !member.is_root && member.user_id !== user?.id &&
    (user?.is_root || (ranks[level] || 0) > (ranks[member.level] || 0));
  const select = (id: number) => {
    const item = report?.members.find(row => row.user_id === id);
    setSelected(id); setPermissions({ ...item?.overrides.permissions }); setFields({ ...item?.overrides.fields }); setError('');
  };
  const save = async (reset = false) => {
    if (!member) return;
    setBusy(true); setError('');
    try { await api.setWorkspaceAccess(workspaceId, member.user_id, { permissions: reset ? {} : permissions, fields: reset ? {} : fields });
      if (reset) { setPermissions({}); setFields({}); } await load(); }
    catch (err) { setError(err instanceof Error ? err.message : 'Не удалось сохранить'); }
    finally { setBusy(false); }
  };
  return <section className="tf-panel-flat space-y-4 p-5">
    <h3 className="text-lg font-bold">Кому что доступно</h3>
    <p className="text-sm text-[var(--color-text-secondary)]">Выберите участника: здесь показан итоговый доступ и его источник. Личные исключения действуют только в этом окружении. Запрет функции или модуля имеет приоритет.</p>
    <select className="tf-input" aria-label="Проверить доступ участника" value={selected ?? ''} onChange={e => select(Number(e.target.value))}>
      <option value="" disabled>Выберите участника</option>{report?.members.map(item => <option key={item.user_id} value={item.user_id}>{item.username} · {levels[item.level]} · {item.profile}</option>)}
    </select>
    {error && <div role="alert" className="tf-alert-error">{error}</div>}
    {member && <><div className="rounded-xl bg-[var(--color-surface-2)] p-3 text-sm"><strong>{member.username}</strong> · {levels[member.level]}<br />Профиль: {member.profile}
      {!canEdit && <p className="mt-2 text-[var(--color-muted)]">Просмотр. Собственный доступ, root и участников своего или более высокого уровня здесь менять нельзя.</p>}</div>
      {report?.groups.map(group => <details key={group.id} className="rounded-xl border border-[var(--color-border)] p-3" open><summary className="cursor-pointer font-semibold">{group.title}</summary>
        <div className="mt-2 space-y-2">{group.items.map(item => {
          const actual = member.permissions[item.key];
          return <div key={item.key} className="grid gap-2 rounded-lg bg-[var(--color-surface-2)] p-3 sm:grid-cols-[1fr_180px]">
            <div className="text-sm"><strong>{item.label}</strong><p className={actual?.allowed ? 'text-[var(--color-success)]' : 'text-[var(--color-muted)]'}>{actual?.allowed ? 'Доступно' : 'Недоступно'} · {actual?.source} · {actual?.reason}</p><p className="text-xs text-[var(--color-muted)]">{item.hint}</p></div>
            <select aria-label={`Исключение: ${item.label}`} disabled={!canEdit || busy} className="tf-input" value={item.key in permissions ? String(permissions[item.key]) : ''}
              onChange={e => setPermissions(prev => { const next = { ...prev }; if (!e.target.value) delete next[item.key]; else next[item.key] = e.target.value === 'true'; return next; })}>
              <option value="">Как в профиле</option><option value="false">Запретить лично</option><option value="true" disabled={!user?.is_root && !user?.permissions[item.key]}>Разрешить лично</option>
            </select></div>;
        })}</div></details>)}
      <h4 className="font-semibold">Личные исключения для полей</h4>
      <FieldAccessEditor value={fields} onChange={setFields} disabled={!canEdit || busy} personal />
      <details className="text-sm"><summary className="cursor-pointer">Итоговый доступ к полям</summary><div className="mt-2 grid gap-2 sm:grid-cols-2">{Object.entries(member.fields).flatMap(([entity, values]) => Object.entries(values).map(([key, mode]) => <div key={`${entity}.${key}`} className="tf-chip">{report?.fields[entity]?.[key]?.label}: {mode === 'edit' ? 'редактирование' : mode === 'view' ? 'просмотр' : 'скрыто'}</div>))}</div></details>
      {canEdit && <div className="flex flex-wrap gap-2"><button className="tf-button tf-button-primary" disabled={busy} onClick={() => void save()}>Сохранить исключения</button><button className="tf-button" disabled={busy} onClick={() => void save(true)}>Убрать личные исключения</button></div>}
    </>}
  </section>;
}
