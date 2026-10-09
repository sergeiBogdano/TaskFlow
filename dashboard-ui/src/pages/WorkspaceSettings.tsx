import { TextEditor } from '../components/TextEditor';
import { Link } from 'react-router-dom';
import { SECTION_LABELS, resolveSectionLabel, resolveFieldLabels } from '../lib/uiLabels';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { BookOpen, Eye, EyeOff, Plus, RotateCcw, Settings2, SlidersHorizontal, Trash2, UsersRound, X } from 'lucide-react';
import { api, type WorkspaceDetail, type WorkspaceMember } from '../api/client';
import { SearchSelect } from '../components/SearchSelect';
import { referenceCache } from '../api/cache';
import { useAuth } from '../hooks/useAuth';
import { applyTheme } from '../lib/theme';
import { sectionLabel, refreshUiConfig, SPRINT_FIELD_DEFAULTS, TASK_FIELD_DEFAULTS, type UiConfig } from '../lib/uiconfig';
import { FieldOrderEditor } from '../components/FieldOrderEditor';

export function WorkspaceSettings({ accessTeam = false }: { accessTeam?: boolean }) {
  const { user, hasRole } = useAuth();
  const isSuperadmin = hasRole('superadmin');
  const [tab, setTab] = useState(accessTeam ? 'team' : 'basic');
  const [detail, setDetail] = useState<WorkspaceDetail | null>(null);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [users, setUsers] = useState<{ id: number; username: string; is_root?: boolean }[]>([]);
  const [knowledge, setKnowledge] = useState<{ id: number; fact: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const [name, setName] = useState('');
  const [visibility, setVisibility] = useState('hidden');
  const [theme, setTheme] = useState('');
  const [aiInstructions, setAiInstructions] = useState('');

  const [addUserId, setAddUserId] = useState('');
  const [inviteUsername, setInviteUsername] = useState('');
  const [addRole, setAddRole] = useState('member');
  const [newFact, setNewFact] = useState('');
  const [trash, setTrash] = useState<{ id: number; name: string; deleted_at: string | null }[]>([]);

  const load = useCallback(async () => {
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
        (user?.is_root || user?.permissions?.users_manage ? api.getUsers('platform') : referenceCache.users()).catch(() => []),
        api.getWsKnowledge(active.id).catch(() => []),
      ]);
      setDetail(full);
      setMembers(memberList);
      setUsers(userList.map(u => ({ id: u.id, username: u.username, is_root: u.is_root })));
      setKnowledge(facts);
      setName(full.name);
      setTheme(full.theme || '');
      setVisibility(full.visibility || 'hidden');
      setAiInstructions(full.ai_instructions || '');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить окружение.');
    } finally {
      setLoading(false);
    }
  }, [user?.is_root, user?.permissions?.users_manage]);

  useEffect(() => {
    void load();
  }, [load]);

  const loadTrash = async () => {
    try {
      const rows = await api.getWorkspaces(true);
      setTrash(rows.map(w => ({ id: w.id, name: w.name, deleted_at: w.deleted_at || null })));
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    if (!accessTeam) void loadTrash();
  }, [accessTeam]);

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
  const administrativeLevel = isOwner || detail.role === 'admin';
  const canManage = isSuperadmin || (administrativeLevel && !!user?.permissions?.workspace_members && user?.features?.workspace_members !== false);
  const canEditSettings = isSuperadmin || (administrativeLevel && !!user?.permissions?.workspace_settings && user?.features?.workspace_settings !== false);

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
        visibility,
        theme: theme || null,
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
    if (!addUserId && !inviteUsername.trim()) return;
    setError('');
    try {
      if (inviteUsername.trim()) await api.inviteWsMember(detail.id, inviteUsername.trim(), addRole);
      else await api.addWsMember(detail.id, Number(addUserId), addRole);
      setInviteUsername('');
      setAddUserId('');
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось добавить.');
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
    if (!confirm(`Удалить окружение «${detail.name}» в корзину? Данные сохранятся 30 дней, потом удалятся навсегда.`)) return;
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

  const restoreWs = async (id: number, name: string) => {
    setError('');
    try {
      await api.restoreWorkspace(id);
      await loadTrash();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Не удалось восстановить «${name}».`);
    }
  };

  const purgeWs = async (id: number, name: string) => {
    if (!confirm(`Удалить окружение «${name}» НАВСЕГДА со всеми данными? Это необратимо.`)) return;
    setError('');
    try {
      await api.deleteWorkspace(id, true);
      await loadTrash();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Не удалось удалить «${name}».`);
    }
  };

  const memberOptions = users
    .filter(u => !members.some(m => m.user_id === u.id))
    .map(u => ({ value: String(u.id), label: u.username }));

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      {!accessTeam && <div className="flex flex-wrap items-center gap-3">
        <div>
          <h2 className="tf-page-title">{sectionLabel('/workspace')}</h2>
          <p className="tf-page-subtitle">Настройки, команда и база знаний активного окружения.</p>
        </div>
        <span className="tf-chip ml-auto">роль в окружении: {detail.role === 'owner' ? 'владелец' : detail.role === 'admin' ? 'администратор' : 'участник'}</span>
      </div>}

      {!accessTeam && <nav className="flex flex-wrap gap-2" aria-label="Настройки пространства">{[
        ['basic', 'Основное'], ['appearance', 'Оформление'], ['service', 'Обслуживание'],
      ].map(([key, label]) => <button key={key} type="button" aria-pressed={tab === key} className={tab === key ? 'tf-button tf-button-primary' : 'tf-button'} onClick={() => setTab(key)}>{label}</button>)}<Link className="tf-button" to="/access?scope=space">Команда, права и функции →</Link></nav>}

      {error && <div className="rounded-lg border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 px-3 py-2 text-sm text-[var(--color-danger)]">{error}</div>}

      {tab === 'basic' && <>
      <Link className="tf-button" to="/access?scope=space&tab=tools">Настроить модули и доступ в едином разделе →</Link>
      <section className="tf-panel-flat p-5">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-bold"><Settings2 size={16} />Основное</h3>
        <form onSubmit={saveInfo} className="grid gap-3">
          <label className="block">
            <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Название</span>
            <input className="tf-input" value={name} onChange={event => setName(event.target.value)} maxLength={200} disabled={!canEditSettings} />
          </label>
          <label className="block text-sm">Видимость пространства<select className="tf-input mt-1" value={visibility} onChange={e => setVisibility(e.target.value)} disabled={!canEditSettings}><option value="hidden">Скрытое — только по приглашению</option><option value="closed">Закрытое — видно в каталоге, доступ по приглашению</option><option value="open">Открытое — можно вступить самостоятельно</option></select></label>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Тема</span>
              <select className="tf-input" value={theme} onChange={event => setTheme(event.target.value)} disabled={!canEditSettings}>
                <option value="">Как в браузере</option>
                <option value="cream">Крем</option>
                <option value="graphite">Графит</option>
              </select>
            </label>
            <button type="button" onClick={() => setTab('appearance')} className="self-end text-left text-sm text-[var(--color-accent)] underline">Названия разделов и полей — в конструкторе интерфейса</button>
          </div>
          <label className="block">
            <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Инструкции для AI</span>
            <TextEditor minHeightClassName="min-h-24" value={aiInstructions} onChange={setAiInstructions} placeholder="Например: ты наставник по Python..." readOnly={!canEditSettings} />
          </label>
          {canEditSettings && (
            <div>
              <button type="submit" disabled={saving} className="tf-button tf-button-primary">{saving ? 'Сохранение...' : 'Сохранить'}</button>
            </div>
          )}
        </form>
      </section>

      </>}
      {accessTeam && tab === 'team' && <>
      <section className="tf-panel-flat p-5">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-bold"><UsersRound size={16} />Участники окружения · {members.length}</h3>
        <p className="mb-3 text-xs text-[var(--color-text-secondary)]">
          Уровень (владелец, администратор, участник) ограничивает управление командой.
          Рабочий профиль, личные права и доступ к полям настраиваются на вкладке «Доступ участников».
          Если профиль не назначен, действуют стандартные права уровня.
        </p>
        {canManage && (
          <div className="mb-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_160px_auto]">
            <input className="tf-input" aria-label="Логин приглашённого" placeholder="Логин пользователя" value={inviteUsername} onChange={e => setInviteUsername(e.target.value)} /><SearchSelect value={addUserId} options={memberOptions} onChange={setAddUserId} placeholder="Добавить участника..." searchPlaceholder="Найти пользователя..." />
            <select className="tf-input" value={addRole} onChange={event => setAddRole(event.target.value)}>
              <option value="member">Участник окружения</option>
              {(isOwner || isSuperadmin) && <option value="admin">Администратор окружения</option>}
            </select>
            <button type="button" onClick={addMember} disabled={!addUserId && !inviteUsername.trim()} className="tf-button tf-button-primary"><Plus size={15} />Добавить</button>
          </div>
        )}
        {(user?.is_root || user?.permissions?.users_manage) && <Link className="tf-button mb-4" to="/access?scope=app&tab=users">Создание аккаунтов и смена паролей →</Link>}
        <div className="space-y-2">
          {members.map(member => {
            const protectedOwner = member.role === 'owner';
            const canTouch = canManage && (isSuperadmin || (isOwner && !protectedOwner) || (detail.role === 'admin' && member.role === 'member'));
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
                      <option value="member">Участник окружения</option>
                      {(isOwner || isSuperadmin) && <option value="admin">Администратор окружения</option>}
                      {isSuperadmin && <option value="owner">Владелец окружения</option>}
                    </select>
                  ) : (
                    <span className="tf-chip">{member.role === 'owner' ? 'владелец' : member.role === 'admin' ? 'админ' : 'участник'}</span>
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


              </div>
            );
          })}
        </div>
      </section>

      </>}
      {tab === 'appearance' && <section className="tf-panel-flat p-5">
        <h3 id="interface-settings" className="mb-1 flex scroll-mt-24 items-center gap-2 text-sm font-bold"><SlidersHorizontal size={16} />Конструктор интерфейса</h3>
        <p className="mb-3 text-xs text-[var(--color-text-secondary)]">Единые названия разделов для меню и страниц. Подписи полей используются в формах, фильтрах и таблице задач. {(isOwner || isSuperadmin) ? 'Изменения действуют после нажатия «Применить».' : 'Для изменения нужно разрешение «Настройки и оформление окружения».'}</p>
        <UiEditor detail={detail} canManage={canEditSettings} onSaved={load} />
      </section>}

      {tab === 'service' && <>
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
          <p className="mb-3 text-xs text-[var(--color-text-secondary)]">Удаление отправляет окружение в корзину на 30 дней — потом всё удалится само. Можно удалить навсегда сразу.</p>
          <button type="button" onClick={deleteWorkspace} className="tf-button text-[var(--color-danger)]"><Trash2 size={15} />Удалить в корзину</button>
        </section>
      )}

      {trash.length > 0 && (
        <section className="tf-panel-flat p-5">
          <h3 className="mb-1 text-sm font-bold">Корзина окружений</h3>
          <p className="mb-3 text-xs text-[var(--color-text-secondary)]">Автоматически удаляются навсегда через 30 дней после удаления.</p>
          <div className="space-y-2">
            {trash.map(ws => (
              <div key={ws.id} className="flex flex-wrap items-center gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2.5">
                <span className="min-w-0 flex-1 truncate text-sm font-semibold">{ws.name}</span>
                <button type="button" onClick={() => restoreWs(ws.id, ws.name)} className="tf-button h-9 px-3 text-xs">Восстановить</button>
                {(isOwner || isSuperadmin) && (
                  <button type="button" onClick={() => purgeWs(ws.id, ws.name)} className="tf-button h-9 px-3 text-xs text-[var(--color-danger)]">Навсегда</button>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
      </>}
    </div>
  );
}

const KNOWN_ROUTES = Object.entries(SECTION_LABELS).filter(([route]) => !['/work', '/manage', '/admin', '/users'].includes(route)).map(([to, label]) => ({ to, label }));

function UiEditor({ detail, canManage, onSaved }: {
  detail: WorkspaceDetail;
  canManage: boolean;
  onSaved: () => void;
}) {
  const [tab, setTab] = useState<'menu' | 'tasks' | 'sprints'>('menu');
  const [cfg, setCfg] = useState<UiConfig>(() => (
    detail.ui_config && typeof detail.ui_config === 'object' ? detail.ui_config as UiConfig : {}
  ));
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');

  const setNav = (to: string, patch: Record<string, any>) => {
    setCfg(prev => {
      const titles = { ...prev.titles };
      if ('label' in patch) delete titles[to];
      return { ...prev, titles, nav: { ...prev.nav, [to]: { ...prev.nav?.[to], ...patch } } };
    });
  };
  const setTaskField = (key: string, patch: Record<string, any>) => {
    setCfg(prev => ({
      ...prev,
      tasks: { ...prev.tasks, fields: { ...((prev.tasks || {}).fields || {}), [key]: { ...((prev.tasks || {}).fields || {})[key], ...patch } } },
    }));
  };
  const setSprintField = (key: string, patch: Record<string, any>) => {
    setCfg(prev => ({
      ...prev,
      sprints: { ...prev.sprints, fields: { ...((prev.sprints || {}).fields || {}), [key]: { ...((prev.sprints || {}).fields || {})[key], ...patch } } },
    }));
  };

  const save = async () => {
    setSaving(true);
    setMsg('');
    try {
      const updated = await api.updateWorkspace(detail.id, { ui_config: cfg });
      try {
        localStorage.setItem('taskflow:workspace-detail', JSON.stringify({ ...detail, ui_config: (updated as any).ui_config ?? cfg }));
      } catch {
        /* ignore */
      }
      refreshUiConfig();
      setMsg('Применено. Откройте разделы — увидите изменения.');
      onSaved();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : 'Не удалось сохранить.');
    } finally {
      setSaving(false);
    }
  };

  const reset = () => {
    if (!confirm('Сбросить всё оформление к стандартному?')) return;
    setCfg({});
  };

  const clientsLabel = typeof detail.dictionary?.clients === 'string' ? detail.dictionary.clients : 'Клиенты';
  const currentSectionLabel = (route: string) => resolveSectionLabel(cfg, route, clientsLabel);
  const taskLabels = resolveFieldLabels(TASK_FIELD_DEFAULTS, cfg.tasks?.fields);
  const sprintLabels = resolveFieldLabels(SPRINT_FIELD_DEFAULTS, cfg.sprints?.fields);
  const visibleNav = KNOWN_ROUTES.filter(r => cfg.nav?.[r.to]?.visible !== false);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {([
          ['menu', 'Названия разделов'],
          ['tasks', `Поля: ${resolveSectionLabel(cfg, '/tasks')}`],
          ['sprints', `Поля: ${resolveSectionLabel(cfg, '/sprints')}`],
        ] as const).map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={tab === key ? 'tf-button tf-button-primary' : 'tf-button'}
          >
            {label}
          </button>
        ))}
        <div className="ml-auto flex gap-2">
          <button type="button" onClick={reset} disabled={!canManage} className="tf-button" title="Сбросить к стандартному">
            <RotateCcw size={15} />Сброс
          </button>
          <button type="button" onClick={save} disabled={saving || !canManage} className="tf-button tf-button-primary">
            {saving ? 'Сохранение...' : 'Применить'}
          </button>
        </div>
      </div>

      {tab === 'menu' && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_240px]">
          <div className="space-y-2">
            {KNOWN_ROUTES.map(route => {
              const item = cfg.nav?.[route.to] || {};
              const hidden = item.visible === false;
              return (
                <div key={route.to} className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2">
                  <div className="flex items-center gap-2">
                    <input
                      className="tf-input h-9 min-w-0 flex-1 text-sm"
                      value={item.label?.trim() || cfg.titles?.[route.to]?.trim() || ''}
                      aria-label={`Название раздела «${currentSectionLabel(route.to)}»`}
                      onChange={event => setNav(route.to, { label: event.target.value })}
                      placeholder={route.to === '/clients' ? clientsLabel : route.label}
                      maxLength={40}
                      disabled={!canManage}
                    />
                    <button
                      type="button"
                      onClick={() => setNav(route.to, { visible: hidden ? undefined : false })}
                      disabled={!canManage}
                      title={hidden ? 'Показать' : 'Скрыть'}
                      aria-label={hidden ? `Показать ${currentSectionLabel(route.to)}` : `Скрыть ${currentSectionLabel(route.to)}`}
                      className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-[var(--color-border)] text-[var(--color-text-secondary)] transition hover:text-[var(--color-text)]"
                    >
                      {hidden ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  </div>
                  <input
                    className="tf-input mt-2 h-8 min-w-0 flex-1 text-xs"
                    value={item.hint ?? ''}
                    onChange={event => setNav(route.to, { hint: event.target.value })}
                    placeholder="Подсказка под пунктом"
                    maxLength={80}
                    disabled={!canManage}
                  />
                </div>
              );
            })}
            <p className="text-xs text-[var(--color-muted)]">Название раздела одинаково в меню и заголовках страниц. Порядок пунктов меняется перетаскиванием в самом меню. Скрытый пункт не удаляется — его можно вернуть.</p>
          </div>
          <div>
            <div className="mb-2 text-xs font-semibold text-[var(--color-text-secondary)]">Предпросмотр</div>
            <div className="space-y-1 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-2">
              {visibleNav.map(route => (
                <div key={route.to} className="truncate rounded-lg bg-[var(--color-overlay)] px-3 py-2 text-sm font-medium">
                  {currentSectionLabel(route.to)}
                </div>
              ))}
              {visibleNav.length === 0 && <div className="p-3 text-sm text-[var(--color-danger)]">Скрыто всё — так нельзя, оставьте хоть один пункт.</div>}
            </div>
          </div>
        </div>
      )}

      {tab === 'tasks' && (
        <div className="space-y-2">
          <FieldOrderEditor labels={taskLabels} order={cfg.tasks?.order} disabled={!canManage} onChange={order => setCfg(c => ({ ...c, tasks: { ...c.tasks, order } }))} />
          {Object.entries(TASK_FIELD_DEFAULTS).map(([key, defLabel]) => {
            const item = cfg.tasks?.fields?.[key] || {};
            const hideable = key !== 'title';
            const hidden = hideable && item.visible === false;
            return (
              <div key={key} className="flex items-center gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2">
                <span className="hidden w-32 shrink-0 truncate text-xs text-[var(--color-muted)] sm:block">{taskLabels[key]}</span>
                <input
                  className="tf-input h-9 min-w-0 flex-1 text-sm"
                  aria-label={`Название поля «${taskLabels[key]}»`}
                  value={item.label ?? ''}
                  onChange={event => setTaskField(key, { label: event.target.value })}
                  placeholder={defLabel}
                  maxLength={60}
                  disabled={!canManage}
                />
                {hideable ? (
                  <button
                    type="button"
                    onClick={() => setTaskField(key, { visible: hidden ? undefined : false })}
                    disabled={!canManage}
                    title={hidden ? 'Показать' : 'Скрыть'}
                    aria-label={hidden ? `Показать ${taskLabels[key]}` : `Скрыть ${taskLabels[key]}`}
                    className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-[var(--color-border)] text-[var(--color-text-secondary)] transition hover:text-[var(--color-text)]"
                  >
                    {hidden ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                ) : (
                  <span className="tf-chip shrink-0">обязательно</span>
                )}
              </div>
            );
          })}
        </div>
      )}

      {tab === 'sprints' && (
        <div className="space-y-2">
          <FieldOrderEditor labels={sprintLabels} order={cfg.sprints?.order} disabled={!canManage} onChange={order => setCfg(c => ({ ...c, sprints: { ...c.sprints, order } }))} />
          {Object.entries(SPRINT_FIELD_DEFAULTS).map(([key, defLabel]) => {
            const item = cfg.sprints?.fields?.[key] || {};
            const hideable = key !== 'name';
            const hidden = hideable && item.visible === false;
            return (
              <div key={key} className="flex items-center gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2">
                <span className="hidden w-32 shrink-0 truncate text-xs text-[var(--color-muted)] sm:block">{sprintLabels[key]}</span>
                <input
                  className="tf-input h-9 min-w-0 flex-1 text-sm"
                  aria-label={`Название поля «${sprintLabels[key]}»`}
                  value={item.label ?? ''}
                  onChange={event => setSprintField(key, { label: event.target.value })}
                  placeholder={defLabel}
                  maxLength={60}
                  disabled={!canManage}
                />
                {hideable ? (
                  <button
                    type="button"
                    onClick={() => setSprintField(key, { visible: hidden ? undefined : false })}
                    disabled={!canManage}
                    title={hidden ? 'Показать' : 'Скрыть'}
                    aria-label={hidden ? `Показать ${sprintLabels[key]}` : `Скрыть ${sprintLabels[key]}`}
                    className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-[var(--color-border)] text-[var(--color-text-secondary)] transition hover:text-[var(--color-text)]"
                  >
                    {hidden ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                ) : (
                  <span className="tf-chip shrink-0">обязательно</span>
                )}
              </div>
            );
          })}
        </div>
      )}


      {msg && <div className="text-sm font-semibold text-[var(--color-text-secondary)]">{msg}</div>}
    </div>
  );
}
