import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ShieldCheck } from 'lucide-react';
import { api, type WorkspaceDetail } from '../api/client';
import { useAuth } from '../hooks/useAuth';
import { accessSections, resolveAccessSelection, type AccessScope } from '../lib/accessCenter';
import { getActiveWorkspaceId, WORKSPACE_EVENT, WORKSPACE_KEY } from '../lib/workspace';
import { sectionLabel } from '../lib/uiconfig';
import { FeaturesPanel } from '../components/FeaturesPanel';
import { SpaceModulesPanel } from '../components/SpaceModulesPanel';
import { WorkspaceAccessPanel } from '../components/WorkspaceAccessPanel';
import { WsRolesPanel } from '../components/WsRolesPanel';
import { Users } from './Users';
import { WorkspaceSettings } from './WorkspaceSettings';

export function AccessCenter() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const [workspace, setWorkspace] = useState<WorkspaceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    let revision = 0; let active = true;
    const load = async () => {
      const current = ++revision; setLoading(true); setWorkspace(null); setError('');
      try {
        const list = await api.getWorkspaces();
        const chosen = list.find(item => String(item.id) === getActiveWorkspaceId()) || list[0];
        if (!active || current !== revision) return;
        try { if (chosen) localStorage.setItem(WORKSPACE_KEY, String(chosen.id)); else localStorage.removeItem(WORKSPACE_KEY); } catch { /* storage unavailable */ }
        const detail = chosen ? await api.getWorkspace(chosen.id) : null;
        if (active && current === revision) setWorkspace(detail);
      } catch (err) { if (active && current === revision) setError(err instanceof Error ? err.message : 'Не удалось загрузить пространство'); }
      finally { if (active && current === revision) setLoading(false); }
    };
    void load(); window.addEventListener(WORKSPACE_EVENT, load);
    return () => { active = false; window.removeEventListener(WORKSPACE_EVENT, load); };
  }, []);
  const sections = accessSections(user, workspace?.role);
  if (!workspace) sections.space = [];
  const selection = resolveAccessSelection(sections, params.get('scope'), params.get('tab'));
  const choose = (scope: AccessScope, tab?: string) => {
    const nextTab = tab || sections[scope][0]?.id || '';
    if (scope === selection.scope && nextTab === selection.tab?.id) return;
    if (dirty && !confirm('Есть несохранённые изменения доступа. Перейти на другую вкладку без сохранения?')) return;
    setParams({ scope, tab: nextTab });
  };
  const selectedUser = Number(params.get('user')) || undefined;
  return <div className="mx-auto max-w-6xl space-y-5">
    <header><h2 className="tf-page-title flex items-center gap-2"><ShieldCheck />{sectionLabel('/access')}</h2><p className="tf-page-subtitle">Единое место для пользователей, профилей, групп, функций и доступа к полям.</p></header>
    {loading ? <p className="tf-panel-flat p-6">Загрузка доступа…</p> : <>
      {error && <p role="alert" className="tf-alert-error">{error}</p>}
      <div className="tf-panel-flat flex flex-wrap gap-2 p-2" aria-label="Область настройки доступа">
        {sections.space.length > 0 && <button className={`tf-button ${selection.scope === 'space' ? 'tf-button-primary' : ''}`} aria-pressed={selection.scope === 'space'} onClick={() => choose('space')}>Пространство: {workspace?.name}</button>}
        {sections.app.length > 0 && <button className={`tf-button ${selection.scope === 'app' ? 'tf-button-primary' : ''}`} aria-pressed={selection.scope === 'app'} onClick={() => choose('app')}>Приложение</button>}
      </div>
      {selection.tab ? <>
        <nav className="flex flex-wrap gap-2" aria-label="Разделы прав и доступа">{sections[selection.scope].map(tab => <button key={tab.id} className={`tf-button ${tab.id === selection.tab?.id ? 'tf-button-primary' : ''}`} aria-pressed={tab.id === selection.tab?.id} onClick={() => choose(selection.scope, tab.id)}>{tab.label}</button>)}</nav>
        <p className="text-sm text-[var(--color-text-secondary)]">{selection.tab.hint} {selection.scope === 'space' ? 'Для другого пространства выберите его в переключателе слева.' : 'Эти настройки общие для приложения; они не добавляют членство в пространствах.'}</p>
        {selection.scope === 'space' && workspace && <div key={`${workspace.id}:${selection.tab.id}`}>
          {selection.tab.id === 'members' && <WorkspaceAccessPanel workspaceId={workspace.id} level={workspace.role} initialUserId={selectedUser} onDirtyChange={setDirty} />}
          {selection.tab.id === 'profiles' && <WsRolesPanel workspaceId={workspace.id} canManage />}
          {selection.tab.id === 'team' && <WorkspaceSettings accessTeam />}
          {selection.tab.id === 'tools' && <div className="space-y-4"><SpaceModulesPanel id={workspace.id} onSaved={() => window.dispatchEvent(new Event('taskflow:access-updated'))} onAccess={() => choose('space', 'members')} /><FeaturesPanel scope="workspace" targetId={workspace.id} title="Функции выбранного пространства" description="Отключение модуля закрывает все его функции. После повторного включения модуля разрешите нужные функции здесь. Права участников проверяются на вкладке «Доступ участников»." /></div>}
        </div>}
        {selection.scope === 'app' && ['users', 'roles', 'groups'].includes(selection.tab.id) && <Users key={selection.tab.id} embedded section={selection.tab.id as 'users' | 'roles' | 'groups'} />}
        {selection.scope === 'app' && selection.tab.id === 'features' && <FeaturesPanel scope="global" title="Функции всего приложения" description="Общий запрет имеет приоритет над настройками групп, пространств и пользователей. После возвращения функции доступ включается явно. Здесь не назначаются права и участники пространств." />}
      </> : <section className="tf-panel-flat p-6"><p>Нет прав на управление доступом в выбранном пространстве или приложении.</p><Link className="tf-button mt-3" to="/work">К работе</Link></section>}
    </>}
  </div>;
}
