import { useEffect, useState, type FormEvent } from 'react';
import { BookOpen, KeyRound, Plus, Settings2, Trash2, UsersRound, X } from 'lucide-react';
import { api, type WorkspaceDetail, type WorkspaceMember } from '../api/client';
import { SearchSelect } from '../components/SearchSelect';
import { referenceCache } from '../api/cache';
import { useAuth } from '../hooks/useAuth';
import { applyTheme } from '../lib/theme';

export function WorkspaceSettings() {
  const { user, hasRole } = useAuth();
  const isSuperadmin = hasRole('superadmin');
  const [detail, setDetail] = useState<WorkspaceDetail | null>(null);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [users, setUsers] = useState<{ id: number; username: string }[]>([]);
  const [knowledge, setKnowledge] = useState<{ id: number; fact: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const [name, setName] = useState('');
  const [theme, setTheme] = useState('');
  const [clientsLabel, setClientsLabel] = useState('');
  const [aiInstructions, setAiInstructions] = useState('');

  const [addUserId, setAddUserId] = useState('');
  const [addRole, setAddRole] = useState('member');
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newFact, setNewFact] = useState('');
  const [pwdUserId, setPwdUserId] = useState<number | null>(null);
  const [pwdValue, setPwdValue] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const list = await api.getWorkspaces();
      const stored = (() => {
        try {
          return localStorage.getItem('taskflow:workspace');
        } catch {
          return null;
        }
      })();
      const active = list.find(w => String(w.id) === stored) || list[0];
      if (!active) {
        setError('Нет доступных окружений.');
        return;
      }
      const [full, memberList, userList, facts] = await Promise.all([
        api.getWorkspace(active.id),
        api.getWsMembers(active.id),
        referenceCache.users().catch(() => []),
        api.getWsKnowledge(active.id).catch(() => []),
      ]);
      setDetail(full);
      setMembers(memberList);
      setUsers(userList.map(u => ({ id: u.id, username: u.username })));
      setKnowledge(facts);
      setName(full.name);
      setTheme(full.theme || '');
      setClientsLabel(full.dictionary?.clients || '');
      setAiInstructions(full.ai_instructions || '');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить окружение.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  if (loading || !detail) {
    return (
      <div className="mx-auto max-w-3xl space-y-5">
        <div className="grid h-48 place-items-center text-sm text-[var(--color-text-secondary)]">
          {error || 'Загрузка окружения...'}
        </div>
      </div>
    );
  }

  const isOwner = detail.role === 'owner';
  const canManage = isOwner || detail.role === 'admin' || isSuperadmin;

  const saveInfo = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) {
      setError('Название не может быть пустым.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const updated = await api.updateWorkspace(detail.id, {
        name: name.trim(),
        theme: theme || null,
        dictionary: clientsLabel.trim() ? { clients: clientsLabel.trim() } : {},
        ai_instructions: aiInstructions.trim() || null,
      });
      if (updated.theme === 'cream' || updated.theme === 'graphite') applyTheme(updated.theme);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить.');
    } finally {
      setSaving(false);
    }
  };

  const addMember = async () => {
    if (!addUserId) return;
    setError('');
    try {
      await api.addWsMember(detail.id, Number(addUserId), addRole);
      setAddUserId('');
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось добавить.');
    }
  };

  const createAndAdd = async () => {
    if (newUsername.trim().length < 2 || newPassword.length < 4) {
      setError('Логин от 2 символов, пароль от 4.');
      return;
    }
    setError('');
    try {
      const created = await api.createUser(newUsername.trim(), newPassword, { workspace_id: detail.id, role: 'member' });
      setNewUsername('');
      setNewPassword('');
      await load();
      setError(`Создан: ${created.username}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось создать.');
    }
  };

  const changeRole = async (userId: number, role: string) => {
    setError('');
    try {
      await api.updateWsMember(detail.id, userId, role);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Нельзя изменить роль.');
    }
  };

  const removeMember = async (member: WorkspaceMember) => {
    if (!confirm(`Убрать ${member.username || 'пользователя'} из окружения?`)) return;
    setError('');
    try {
      await api.removeWsMember(detail.id, member.user_id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Нельзя убрать.');
    }
  };

  const savePassword = async (userId: number) => {
    if (pwdValue.length < 4) {
      setError('Пароль минимум 4 символа.');
      return;
    }
    setError('');
    try {
      await api.setUserPassword(userId, pwdValue);
      setPwdUserId(null);
      setPwdValue('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сменить пароль.');
    }
  };

  const addFact = async () => {
    if (!newFact.trim()) return;
    setError('');
    try {
      await api.addWsKnowledge(detail.id, newFact.trim());
      setNewFact('');
      const facts = await api.getWsKnowledge(detail.id);
      setKnowledge(facts);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось добавить.');
    }
  };

  const deleteWorkspace = async () => {
    if (!confirm(`Удалить окружение «${detail.name}» со всеми задачами и данными? Это необратимо.`)) return;
    setError('');
    try {
      await api.deleteWorkspace(detail.id);
      try {
        localStorage.removeItem('taskflow:workspace');
        localStorage.removeItem('taskflow:workspace-detail');
      } catch {
        /* ignore */
      }
      window.location.href = '/';
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось удалить.');
    }
  };

  const memberOptions = users
    .filter(u => !members.some(m => m.user_id === u.id))
    .map(u => ({ value: String(u.id), label: u.username }));

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h2 className="tf-page-title">Окружение</h2>
          <p className="tf-page-subtitle">Настройки, команда и база знаний активного окружения.</p>
        </div>
        <span className="tf-chip ml-auto">твоя роль: {detail.role === 'owner' ? 'владелец' : detail.role === 'admin' ? 'админ' : 'участник'}</span>
      </div>

      {error && <div className="rounded-lg border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 px-3 py-2 text-sm text-[var(--color-danger)]">{error}</div>}

      <section className="tf-panel-flat p-5">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-bold"><Settings2 size={16} />Основное</h3>
        <form onSubmit={saveInfo} className="grid gap-3">
          <label className="block">
            <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Название</span>
            <input className="tf-input" value={name} onChange={event => setName(event.target.value)} maxLength={200} disabled={!canManage} />
          </label>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Тема</span>
              <select className="tf-input" value={theme} onChange={event => setTheme(event.target.value)} disabled={!canManage}>
                <option value="">Как в браузере</option>
                <option value="cream">Крем</option>
                <option value="graphite">Графит</option>
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">«Клиенты» называть</span>
              <input className="tf-input" value={clientsLabel} onChange={event => setClientsLabel(event.target.value)} placeholder="Клиенты" maxLength={40} disabled={!canManage} />
            </label>
          </div>
          <label className="block">
            <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Инструкции для AI</span>
            <textarea className="tf-input min-h-24 resize-y" value={aiInstructions} onChange={event => setAiInstructions(event.target.value)} placeholder="Например: ты наставник по Python..." disabled={!canManage} />
          </label>
          {canManage && (
            <div>
              <button type="submit" disabled={saving} className="tf-button tf-button-primary">{saving ? 'Сохранение...' : 'Сохранить'}</button>
            </div>
          )}
        </form>
      </section>

      <section className="tf-panel-flat p-5">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-bold"><UsersRound size={16} />Команда · {members.length}</h3>
        {canManage && (
          <div className="mb-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_160px_auto]">
            <SearchSelect value={addUserId} options={memberOptions} onChange={setAddUserId} placeholder="Добавить участника..." searchPlaceholder="Найти пользователя..." />
            <select className="tf-input" value={addRole} onChange={event => setAddRole(event.target.value)}>
              <option value="member">Участник</option>
              <option value="admin">Админ</option>
            </select>
            <button type="button" onClick={addMember} disabled={!addUserId} className="tf-button tf-button-primary"><Plus size={15} />Добавить</button>
          </div>
        )}
        {canManage && (
          <div className="mb-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
            <input className="tf-input" value={newUsername} onChange={event => setNewUsername(event.target.value)} placeholder="Новый логин" />
            <input className="tf-input" type="password" value={newPassword} onChange={event => setNewPassword(event.target.value)} placeholder="Пароль от 4 символов" />
            <button type="button" onClick={createAndAdd} className="tf-button"><Plus size={15} />Создать</button>
          </div>
        )}
        <div className="space-y-2">
          {members.map(member => {
            const protectedOwner = member.role === 'owner';
            const canTouch = canManage && (isSuperadmin || !protectedOwner);
            return (
              <div key={member.user_id} className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="min-w-0 flex-1 truncate text-sm font-semibold">
                    {member.username || `#${member.user_id}`}
                    {user?.id === member.user_id && <span className="ml-2 tf-chip">это вы</span>}
                  </span>
                  {canTouch && !protectedOwner ? (
                    <select
                      className="tf-input h-9 w-auto py-0 text-xs"
                      value={member.role}
                      onChange={event => changeRole(member.user_id, event.target.value)}
                    >
                      <option value="member">Участник</option>
                      <option value="admin">Админ</option>
                      {isSuperadmin && <option value="owner">Владелец</option>}
                    </select>
                  ) : (
                    <span className="tf-chip">{member.role === 'owner' ? 'владелец' : member.role === 'admin' ? 'админ' : 'участник'}</span>
                  )}
                  {canTouch && (
                    <button type="button" onClick={() => setPwdUserId(pwdUserId === member.user_id ? null : member.user_id)} className="tf-button h-9 px-2 text-xs" title="Сменить пароль">
                      <KeyRound size={14} />Пароль
                    </button>
                  )}
                  {canTouch && !protectedOwner && user?.id !== member.user_id && (
                    <button type="button" onClick={() => removeMember(member)} className="tf-button h-9 w-9 px-0 text-[var(--color-danger)]" title="Убрать" aria-label={`Убрать ${member.username}`}>
                      <X size={15} />
                    </button>
                  )}
                  {protectedOwner && !isSuperadmin && (
                    <span className="text-xs text-[var(--color-muted)]">владельца меняет только суперадмин</span>
                  )}
                </div>
                {pwdUserId === member.user_id && (
                  <div className="mt-2 flex gap-2">
                    <input
                      className="tf-input h-9 text-sm"
                      type="password"
                      value={pwdValue}
                      onChange={event => setPwdValue(event.target.value)}
                      placeholder="Новый пароль от 4 символов"
                    />
                    <button type="button" onClick={() => savePassword(member.user_id)} className="tf-button h-9 shrink-0 text-xs">OK</button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      <section className="tf-panel-flat p-5">
        <h3 className="mb-1 flex items-center gap-2 text-sm font-bold"><BookOpen size={16} />База знаний AI</h3>
        <p className="mb-3 text-xs text-[var(--color-text-secondary)]">Факты подмешиваются в ответы AI и аналитику. Добавлять можно и из чата командой «запомни ...».</p>
        {canManage && (
          <div className="mb-3 flex gap-2">
            <input className="tf-input" value={newFact} onChange={event => setNewFact(event.target.value)} placeholder="Например: клиент любит отчёты по пятницам" maxLength={2000} onKeyDown={event => { if (event.key === 'Enter') void addFact(); }} />
            <button type="button" onClick={addFact} className="tf-button shrink-0"><Plus size={15} />Добавить</button>
          </div>
        )}
        <div className="space-y-2">
          {knowledge.map(fact => (
            <div key={fact.id} className="flex items-start gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm">
              <span className="min-w-0 flex-1">{fact.fact}</span>
              {canManage && (
                <button type="button" onClick={() => api.deleteWsKnowledge(detail.id, fact.id).then(() => api.getWsKnowledge(detail.id).then(setKnowledge)).catch(() => {})} className="shrink-0 text-[var(--color-muted)] hover:text-[var(--color-danger)]" aria-label="Удалить факт">
                  <Trash2 size={14} />
                </button>
              )}
            </div>
          ))}
          {knowledge.length === 0 && <div className="text-sm text-[var(--color-text-secondary)]">Пока пусто.</div>}
        </div>
      </section>

      {(isOwner || isSuperadmin) && (
        <section className="tf-panel-flat border-[var(--color-danger)]/40 p-5">
          <h3 className="mb-1 text-sm font-bold text-[var(--color-danger)]">Опасная зона</h3>
          <p className="mb-3 text-xs text-[var(--color-text-secondary)]">Удаление сотрёт задачи, клиентов, спринты и знания окружения. Необратимо.</p>
          <button type="button" onClick={deleteWorkspace} className="tf-button text-[var(--color-danger)]"><Trash2 size={15} />Удалить окружение</button>
        </section>
      )}
    </div>
  );
}
