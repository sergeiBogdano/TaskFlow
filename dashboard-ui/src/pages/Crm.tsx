import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { ArrowRight, Archive, Building2, GripVertical, Plus, Search, Settings2, Trash2, Users, X } from 'lucide-react';
import { Link } from 'react-router-dom';
import { api, type Client, type Task, type User } from '../api/client';
import { crm, type Activity, type Contact, type CrmField, type Deal, type Pipeline, type LinkedTask } from '../api/crm';
import { useAuth } from '../hooks/useAuth';

type Tab = 'deals' | 'contacts' | 'settings';
const starterStages = [
  { id: 'new', label: 'Новая', outcome: 'open' }, { id: 'discussion', label: 'Обсуждение', outcome: 'open' },
  { id: 'contract', label: 'Договор', outcome: 'open' }, { id: 'won', label: 'Успешно', outcome: 'won' },
  { id: 'lost', label: 'Отказ', outcome: 'lost' },
];

export function Crm() {
  const { user } = useAuth();
  const can = (key: string) => Boolean(user?.is_root || user?.permissions?.all || (user?.permissions?.[key] && user?.features?.[key] !== false));
  const [tab, setTab] = useState<Tab>('deals');
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [fields, setFields] = useState<CrmField[]>([]);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [pipelineId, setPipelineId] = useState<number>(0);
  const [mode, setMode] = useState<'active' | 'archive' | 'trash'>('active');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [draft, setDraft] = useState<Partial<Deal> | null>(null);
  const [contactDraft, setContactDraft] = useState<Partial<Contact> | null>(null);
  const [contractClient, setContractClient] = useState<Client | null>(null);
  const [pipelineName, setPipelineName] = useState('');
  const [fieldName, setFieldName] = useState('');
  const [fieldKind, setFieldKind] = useState<CrmField['kind']>('text');
  const [activityTitle, setActivityTitle] = useState('');
  const [activityDate, setActivityDate] = useState('');
  const [activityKind, setActivityKind] = useState('call');
  const [stagesText, setStagesText] = useState('');
  const [dragField, setDragField] = useState<number | null>(null);
  const [renewalContract, setRenewalContract] = useState<number | null>(null);
  const [renewalDate, setRenewalDate] = useState('');
  const [linkedTasks, setLinkedTasks] = useState<LinkedTask[]>([]);
  const [taskTitle, setTaskTitle] = useState('');
  const [taskDate, setTaskDate] = useState('');
  const [taskAssignee, setTaskAssignee] = useState('');
  const [dragDeal, setDragDeal] = useState<number | null>(null);
  const load = useCallback(async () => {
    setError('');
    try {
      const [p, d, c, f, a] = await Promise.all([
        crm.list<Pipeline>('pipelines'), crm.list<Deal>('deals', mode === 'archive' ? 'archived=true' : mode === 'trash' ? 'deleted=true' : ''),
        crm.list<Contact>('contacts', mode === 'trash' ? 'deleted=true' : ''), crm.list<CrmField>('fields'), crm.list<Activity>('activities'),
      ]);
      setPipelines(p); setDeals(d); setContacts(c); setFields(f); setActivities(a);
      setPipelineId(previous => p.some(item => item.id === previous) ? previous : p[0]?.id || 0);
    } catch (err) { setError(err instanceof Error ? err.message : 'Не удалось загрузить CRM'); }
    finally { setLoading(false); }
  }, [mode]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    api.getClients().then(setClients).catch(() => setClients([]));
    api.getTasks('scope=all').then(setTasks).catch(() => setTasks([]));
    api.getUsers().then(setUsers).catch(() => setUsers([]));
  }, []);
  useEffect(() => {
    setContractClient(null);
    let active = true;
    if (draft?.client_id) api.getClient(draft.client_id).then(client => { if (active) setContractClient(client); }).catch(() => {});
    return () => { active = false; };
  }, [draft?.client_id]);
  useEffect(() => {
    setLinkedTasks([]);
    if (!draft?.id || !(user?.permissions?.all || user?.permissions?.tasks) || user?.features?.tasks === false) return;
    let active = true;
    crm.tasks(draft.id).then(rows => { if (active) setLinkedTasks(rows); }).catch(() => {});
    return () => { active = false; };
  }, [draft?.id, draft?.task_id, user]);
  const run = async (operation: () => Promise<unknown>) => {
    setBusy(true); setError('');
    try { await operation(); await load(); }
    catch (err) { setError(err instanceof Error ? err.message : 'Не удалось сохранить'); }
    finally { setBusy(false); }
  };
  const pipeline = pipelines.find(p => p.id === pipelineId);
  const visible = deals.filter(d => d.pipeline_id === pipelineId && `${d.title} ${clients.find(c => c.id === d.client_id)?.org_name || ''}`.toLowerCase().includes(search.toLowerCase()));
  const patch = (key: keyof Deal, value: unknown) => setDraft(prev => ({ ...prev, [key]: value }));
  const saveDeal = async (event: FormEvent) => {
    event.preventDefault(); if (!draft) return;
    const { id, ...data } = draft;
    // Send only editable schema fields; backend owns identity and space.
    const payload = Object.fromEntries(['title', 'pipeline_id', 'stage', 'amount', 'currency', 'client_id', 'contact_id', 'contract_id', 'task_id', 'assignee_id', 'custom_fields', 'notes', 'archived'].filter(k => k in data).map(k => [k, data[k as keyof typeof data]]));
    await run(async () => { if (id) await crm.update('deals', id, payload); else await crm.create('deals', payload); setDraft(null); });
  };
  const newDeal = () => setDraft({ title: '', pipeline_id: pipelineId, stage: pipeline?.stages[0]?.id || '', amount: '0', currency: 'RUB', custom_fields: {}, archived: false });
  const money = (deal: Deal) => `${Number(deal.amount).toLocaleString('ru-RU')} ${deal.currency}`;
  const move = (id: number, stage: string) => run(() => crm.update('deals', id, { stage }));
  const reorderField = (from: number, to: number) => {
    const reordered = [...fields]; const [item] = reordered.splice(from, 1); reordered.splice(to, 0, item);
    void run(async () => { for (let index = 0; index < reordered.length; index++) await crm.update('fields', reordered[index].id, { position: index }); });
  };

  return <div className="mx-auto max-w-[1500px] space-y-5">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><div className="tf-eyebrow">Клиенты и продажи</div><h2 className="tf-page-title">CRM</h2><p className="tf-page-subtitle">От первого контакта до договора и выполненной работы.</p></div>
      <Link className="tf-button" to="/clients"><Building2 size={16} />Организации и договоры<ArrowRight size={14} /></Link>
    </div>
    <div className="tf-panel-flat flex flex-wrap items-center gap-2 p-2">
      {([['deals', 'Сделки'], ['contacts', 'Контакты'], ...(can('crm_configure') ? [['settings', 'Настройка']] : [])] as [Tab, string][]).map(([key, label]) => <button key={key} className={`tf-button ${tab === key ? 'tf-button-primary' : ''}`} onClick={() => setTab(key)}>{key === 'settings' ? <Settings2 size={15} /> : key === 'contacts' ? <Users size={15} /> : null}{label}</button>)}
      <span className="ml-auto px-3 text-xs text-[var(--color-muted)]">Данные текущего пространства</span>
    </div>
    {error && <div role="alert" className="tf-alert-error">{error}</div>}
    {loading ? <div className="tf-panel-flat p-12 text-center">Загрузка CRM…</div> : tab === 'deals' ? <>
      <div className="grid gap-3 sm:grid-cols-3">
        {[['Сделок', String(visible.length)], ['Открытые', String(visible.filter(d => pipeline?.stages.find(s => s.id === d.stage)?.outcome === 'open').length)], ['Успешные', String(visible.filter(d => pipeline?.stages.find(s => s.id === d.stage)?.outcome === 'won').length)]].map(([label, value]) => <div key={label} className="tf-panel-flat p-4"><p className="text-xs text-[var(--color-muted)]">{label}</p><p className="mt-1 text-2xl font-bold">{value}</p></div>)}
      </div>
      <div className="flex flex-wrap gap-2">
        <select aria-label="Воронка" className="tf-input" style={{ width: 'auto', minWidth: 160 }} value={pipelineId} onChange={e => setPipelineId(Number(e.target.value))}>{pipelines.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
        <select aria-label="Состояние сделок" className="tf-input" style={{ width: 'auto' }} value={mode} onChange={e => setMode(e.target.value as typeof mode)}><option value="active">Активные</option><option value="archive">Архив</option><option value="trash">Корзина</option></select>
        <label className="flex min-w-48 flex-1 items-center gap-2 rounded-xl border border-[var(--color-border)] px-3"><Search size={16} /><input className="min-w-0 flex-1 bg-transparent py-2 outline-none" placeholder="Найти сделку или клиента" value={search} onChange={e => setSearch(e.target.value)} /></label>
        {can('crm_edit') && <button disabled={!pipeline || busy} className="tf-button tf-button-primary" onClick={newDeal}><Plus size={16} />Сделка</button>}
      </div>
      {!pipeline ? <div className="tf-panel-flat p-12 text-center"><h3 className="mb-2 text-lg font-bold">Начните с воронки</h3><p className="tf-page-subtitle">{can('crm_configure') ? 'Создайте воронку во вкладке «Настройка», затем добавьте первую сделку.' : 'Попросите администратора настроить воронку продаж.'}</p></div> :
      <div className="flex gap-3 overflow-x-auto pb-4">
        {pipeline.stages.map(stage => <section key={stage.id} className="min-w-[260px] flex-1 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3" onDragOver={e => { if (can('crm_edit') && mode === 'active') e.preventDefault(); }} onDrop={() => { if (dragDeal) void move(dragDeal, stage.id); setDragDeal(null); }}>
          <div className="mb-3 flex items-center gap-2"><span className={`h-2 w-2 rounded-full ${stage.outcome === 'won' ? 'bg-emerald-500' : stage.outcome === 'lost' ? 'bg-red-400' : 'bg-[var(--color-accent)]'}`} /><h3 className="flex-1 text-sm font-bold">{stage.label}</h3><span className="tf-chip">{visible.filter(d => d.stage === stage.id).length}</span></div>
          <div className="space-y-2">{visible.filter(d => d.stage === stage.id).map(deal => <article key={deal.id} draggable={can('crm_edit') && mode === 'active'} onDragStart={() => setDragDeal(deal.id)} onDragEnd={() => setDragDeal(null)} className="tf-crm-card">
            <button className="block w-full text-left text-sm font-bold hover:text-[var(--color-accent)]" onClick={() => setDraft(deal)}>{deal.title}</button>
            <div className="mt-2 text-xs text-[var(--color-text-secondary)]">{clients.find(c => c.id === deal.client_id)?.org_name || 'Без организации'}</div><div className="my-3 text-lg font-semibold">{money(deal)}</div>
            <div className="flex flex-wrap gap-1 text-xs">{deal.contract_id && <span className="tf-chip">Договор</span>}{deal.task_id && <Link to={`/tasks?task=${deal.task_id}`} className="tf-chip">Задача #{deal.task_id}</Link>}{activities.filter(a => a.deal_id === deal.id && !a.completed).length > 0 && <span className="tf-chip">Есть дела</span>}</div>
            {can('crm_edit') && mode === 'active' && <select aria-label={`Этап сделки ${deal.title}`} className="tf-input mt-3 h-8 text-xs" value={deal.stage} onChange={e => void move(deal.id, e.target.value)}>{pipeline.stages.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}</select>}
            <div className="mt-3 flex justify-end gap-2">{mode === 'trash' ? can('crm_delete') && <><button className="tf-button h-8 text-xs" disabled={busy} onClick={() => void run(() => crm.restore('deals', deal.id))}>Восстановить</button><button aria-label="Удалить навсегда" className="tf-button h-8" onClick={() => { if (confirm('Удалить сделку и её активности навсегда?')) void run(() => crm.remove('deals', deal.id, true)); }}><Trash2 size={14} /></button></> : <>{can('crm_edit') && <button title={deal.archived ? 'Вернуть из архива' : 'Архивировать'} className="tf-button h-8" onClick={() => void run(() => crm.update('deals', deal.id, { archived: !deal.archived }))}><Archive size={14} /></button>}{can('crm_delete') && <button title="В корзину" className="tf-button h-8" onClick={() => { if (confirm('Переместить сделку в корзину?')) void run(() => crm.remove('deals', deal.id)); }}><Trash2 size={14} /></button>}</>}</div>
          </article>)}</div>
        </section>)}
      </div>}
    </> : tab === 'contacts' ? <>
      <div className="flex items-center justify-between"><h3 className="text-lg font-bold">Контакты · {contacts.length}</h3><select aria-label="Контакты или корзина" className="tf-input" style={{ width: 'auto' }} value={mode === 'trash' ? 'trash' : 'active'} onChange={e => setMode(e.target.value as typeof mode)}><option value="active">Активные</option><option value="trash">Корзина</option></select>{can('crm_edit') && <button className="tf-button tf-button-primary" onClick={() => setContactDraft({ name: '', email: '', phone: '', position: '' })}><Plus size={16} />Контакт</button>}</div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{contacts.map(contact => <article key={contact.id} className="tf-panel-flat p-5"><h4 className="font-bold">{contact.name}</h4><p className="tf-page-subtitle">{contact.position || 'Контактное лицо'}</p><p className="mt-3 text-sm">{contact.email || '—'}</p><p className="text-sm">{contact.phone || '—'}</p><p className="mt-2 text-xs text-[var(--color-muted)]">{clients.find(c => c.id === contact.client_id)?.org_name || 'Без организации'}</p><div className="mt-4 flex gap-2">{mode === 'trash' && can('crm_delete') && <button className="tf-button text-xs" onClick={() => void run(() => crm.restore('contacts', contact.id))}>Восстановить</button>}{mode !== 'trash' && can('crm_edit') && <button className="tf-button text-xs" onClick={() => setContactDraft(contact)}>Изменить</button>}{can('crm_delete') && <button className="tf-button text-xs" onClick={() => { if (confirm('Удалить контакт?')) void run(() => crm.remove('contacts', contact.id, mode === 'trash')); }}>Удалить</button>}</div></article>)}</div>
      {!contacts.length && <div className="tf-panel-flat p-10 text-center text-[var(--color-muted)]">Контактов пока нет</div>}
    </> : <div className="grid gap-5 lg:grid-cols-2">
      <section className="tf-panel-flat space-y-4 p-5"><h3 className="text-lg font-bold">Воронки продаж</h3><p className="tf-page-subtitle">Каждая воронка имеет свои этапы. Этап со сделками нельзя удалить.</p>
        <form className="flex gap-2" onSubmit={e => { e.preventDefault(); void run(async () => { await crm.create('pipelines', { name: pipelineName, stages: starterStages }); setPipelineName(''); }); }}><input required maxLength={120} className="tf-input" placeholder="Название новой воронки" value={pipelineName} onChange={e => setPipelineName(e.target.value)} /><button aria-label="Добавить" disabled={busy} className="tf-button"><Plus size={16} /></button></form>
        {pipelines.map(p => <div key={p.id} className="rounded-xl border border-[var(--color-border)] p-3"><div className="flex justify-between gap-2"><strong>{p.name}</strong><button className="text-xs text-[var(--color-danger)]" onClick={() => { if (confirm('Удалить пустую воронку?')) void run(() => crm.remove('pipelines', p.id)); }}>Удалить</button></div><p className="mt-2 text-xs text-[var(--color-muted)]">{p.stages.map(s => s.label).join(' → ')}</p><button className="tf-button mt-3 text-xs" onClick={() => { setPipelineId(p.id); setStagesText(JSON.stringify(p.stages, null, 2)); }}>Изменить этапы</button></div>)}
        {stagesText && <form onSubmit={e => { e.preventDefault(); void run(async () => { await crm.update('pipelines', pipelineId, { stages: JSON.parse(stagesText) }); setStagesText(''); }); }} className="space-y-2"><h4 className="font-semibold">Этапы: {pipeline?.name}</h4>{(JSON.parse(stagesText) as Pipeline['stages']).map((stage, index, all) => <div key={stage.id} className="flex gap-2"><input aria-label="Название этапа" required className="tf-input flex-1" value={stage.label} onChange={e => setStagesText(JSON.stringify(all.map((item, i) => i === index ? { ...item, label: e.target.value } : item)))} /><select aria-label="Результат этапа" className="tf-input" style={{ width: 'auto' }} value={stage.outcome} onChange={e => setStagesText(JSON.stringify(all.map((item, i) => i === index ? { ...item, outcome: e.target.value } : item)))}><option value="open">В работе</option><option value="won">Успех</option><option value="lost">Отказ</option></select><button type="button" aria-label="Поднять этап" disabled={!index} onClick={() => { const next = [...all]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; setStagesText(JSON.stringify(next)); }}>↑</button><button type="button" aria-label="Удалить этап" onClick={() => setStagesText(JSON.stringify(all.filter((_, i) => i !== index)))}><Trash2 size={14} /></button></div>)}<div className="flex gap-2"><button type="button" className="tf-button" onClick={() => setStagesText(JSON.stringify([...JSON.parse(stagesText), { id: `stage_${Date.now()}`, label: 'Новый этап', outcome: 'open' }]))}>Добавить этап</button><button disabled={busy} className="tf-button tf-button-primary">Сохранить этапы</button><button type="button" className="tf-button" onClick={() => setStagesText('')}>Отмена</button></div></form>}
      </section>
      <section className="tf-panel-flat space-y-4 p-5"><h3 className="text-lg font-bold">Поля карточки сделки</h3><p className="tf-page-subtitle">Перетащите поле или используйте стрелки. Порядок общий для пространства.</p>
        <form className="grid gap-2 sm:grid-cols-2" onSubmit={e => { e.preventDefault(); void run(async () => { await crm.create('fields', { key: `field_${crypto.randomUUID().replaceAll('-', '')}`, label: fieldName, kind: fieldKind, position: fields.length }); setFieldName(''); }); }}><input required maxLength={120} className="tf-input" placeholder="Название поля" value={fieldName} onChange={e => setFieldName(e.target.value)} /><select className="tf-input" value={fieldKind} onChange={e => setFieldKind(e.target.value as typeof fieldKind)}><option value="text">Текст</option><option value="number">Число</option><option value="date">Дата</option><option value="checkbox">Флажок</option></select><button disabled={busy} className="tf-button tf-button-primary">Добавить поле</button></form>
        {fields.map((field, index) => <div key={field.id} draggable={!busy} onDragStart={() => setDragField(index)} onDragOver={e => e.preventDefault()} onDrop={() => { if (dragField !== null) reorderField(dragField, index); setDragField(null); }} className="flex items-center gap-2 rounded-xl border border-[var(--color-border)] p-3"><GripVertical size={15} /><span className="flex-1 text-sm font-medium">{field.label}</span><label className="text-xs"><input type="checkbox" checked={field.required} onChange={e => void run(() => crm.update('fields', field.id, { required: e.target.checked }))} /> Обязательно</label><button aria-label={`Поднять ${field.label}`} disabled={!index || busy} onClick={() => reorderField(index, index - 1)}>↑</button><button aria-label={`Опустить ${field.label}`} disabled={index === fields.length - 1 || busy} onClick={() => reorderField(index, index + 1)}>↓</button><button aria-label={`Удалить ${field.label}`} onClick={() => { if (confirm('Удалить поле и его значения во всех сделках?')) void run(() => crm.remove('fields', field.id)); }}><Trash2 size={14} /></button></div>)}
      </section>
    </div>}
    {draft && <div className="tf-modal-backdrop" onClick={() => setDraft(null)}><section role="dialog" aria-modal="true" aria-label="Карточка сделки" className="tf-modal-shell w-full max-w-3xl p-6" onClick={e => e.stopPropagation()}><div className="mb-5 flex justify-between"><h3 className="text-xl font-bold">{draft.id ? 'Карточка сделки' : 'Новая сделка'}</h3><button aria-label="Закрыть" onClick={() => setDraft(null)}><X /></button></div>
      {error && <p role="alert" className="tf-alert-error mb-3">{error}</p>}
      <form onSubmit={saveDeal} className="grid gap-3 sm:grid-cols-2">
        <label className="sm:col-span-2 text-sm">Название<input className="tf-input mt-1" required maxLength={200} value={draft.title || ''} onChange={e => patch('title', e.target.value)} /></label>
        <label className="text-sm">Сумма<input className="tf-input mt-1" type="number" min="0" step="0.01" value={draft.amount || '0'} onChange={e => patch('amount', e.target.value)} /></label><label className="text-sm">Валюта<select className="tf-input mt-1" value={draft.currency || 'RUB'} onChange={e => patch('currency', e.target.value)}>{['RUB', 'AMD', 'USD', 'EUR'].map(v => <option key={v}>{v}</option>)}</select></label>
        <label className="text-sm">Организация<select className="tf-input mt-1" value={draft.client_id || ''} onChange={e => setDraft(d => ({ ...d, client_id: Number(e.target.value) || null, contact_id: null, contract_id: null, task_id: null }))}><option value="">Без организации</option>{clients.map(c => <option key={c.id} value={c.id}>{c.org_name}</option>)}</select></label>
        <label className="text-sm">Контакт<select className="tf-input mt-1" value={draft.contact_id || ''} onChange={e => patch('contact_id', Number(e.target.value) || null)}><option value="">Не выбран</option>{contacts.filter(c => !c.client_id || c.client_id === draft.client_id).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        <label className="text-sm">Договор<select className="tf-input mt-1" value={draft.contract_id || ''} onChange={e => patch('contract_id', Number(e.target.value) || null)}><option value="">Не выбран</option>{(contractClient?.contracts || []).map(c => <option key={c.id} value={c.id}>{c.contract_type || 'Договор'} · {c.end_date?.slice(0, 10)}</option>)}</select></label>
        <label className="text-sm">Связанная задача<select className="tf-input mt-1" value={draft.task_id || ''} onChange={e => patch('task_id', Number(e.target.value) || null)}><option value="">Не выбрана</option>{tasks.filter(t => !t.client_id || t.client_id === draft.client_id).map(t => <option key={t.id} value={t.id}>{t.title}</option>)}</select></label>
        <label className="text-sm">Ответственный<select className="tf-input mt-1" value={draft.assignee_id || ''} onChange={e => patch('assignee_id', Number(e.target.value) || null)}><option value="">Не выбран</option>{users.filter(u => u.is_active !== false).map(u => <option key={u.id} value={u.id}>{u.username}</option>)}</select></label>
        <label className="text-sm">Воронка<select className="tf-input mt-1" value={draft.pipeline_id || ''} onChange={e => { const selected = pipelines.find(p => p.id === Number(e.target.value)); setDraft(d => ({ ...d, pipeline_id: selected?.id, stage: selected?.stages[0]?.id || '' })); }}>{pipelines.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <label className="text-sm">Этап<select className="tf-input mt-1" value={draft.stage || ''} onChange={e => patch('stage', e.target.value)}>{pipelines.find(p => p.id === draft.pipeline_id)?.stages.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}</select></label>
        {fields.map(field => <label key={field.key} className="text-sm">{field.label}{field.required ? ' *' : ''}<input className="tf-input mt-1" required={field.required && field.kind !== 'checkbox'} type={field.kind === 'checkbox' ? 'checkbox' : field.kind === 'number' ? 'number' : field.kind === 'date' ? 'date' : 'text'} checked={Boolean(draft.custom_fields?.[field.key])} value={field.kind === 'checkbox' ? undefined : String(draft.custom_fields?.[field.key] ?? '')} onChange={e => patch('custom_fields', { ...draft.custom_fields, [field.key]: field.kind === 'checkbox' ? e.target.checked : field.kind === 'number' && e.target.value ? Number(e.target.value) : e.target.value })} /></label>)}
        <label className="sm:col-span-2 text-sm">Примечание<textarea className="tf-input mt-1 min-h-20" value={draft.notes || ''} onChange={e => patch('notes', e.target.value)} /></label>
        {can('crm_edit') && mode !== 'trash' && <button disabled={busy} className="tf-button tf-button-primary sm:col-span-2">{busy ? 'Сохранение…' : 'Сохранить сделку'}</button>}
      </form>
      {draft.id && user?.features?.tasks !== false && (can('tasks')) && <section className="mt-6 border-t border-[var(--color-border)] pt-4"><h4 className="font-bold">Связанные задачи</h4><div className="my-3 space-y-2">{linkedTasks.map(task => <Link key={task.id} to={`/tasks?task=${task.id}`} className="flex items-center gap-2 rounded-xl border border-[var(--color-border)] p-3 text-sm"><span className="text-[var(--color-muted)]">#{task.id}</span><span className="flex-1">{task.title}</span><span>{({ todo: 'Создана', in_progress: 'В работе', done: 'Готово' } as Record<string,string>)[task.status] || task.status}</span><ArrowRight size={14} /></Link>)}{!linkedTasks.length && <p className="text-sm text-[var(--color-muted)]">Задач пока нет.</p>}</div>
        {can('crm_edit') && mode === 'active' && <form className="grid gap-2 sm:grid-cols-2" onSubmit={e => { e.preventDefault(); void run(async () => { const task = await crm.createTask(draft.id!, { title: taskTitle, deadline: taskDate ? `${taskDate}T12:00:00Z` : null, assignee_id: Number(taskAssignee) || null }); setDraft(d => d ? { ...d, task_id: task.id } : d); setTaskTitle(''); setTaskDate(''); api.getTasks('scope=all').then(setTasks).catch(() => {}); }); }}><label className="text-sm sm:col-span-2">Название задачи<input required maxLength={200} className="tf-input mt-1" value={taskTitle} onChange={e => setTaskTitle(e.target.value)} /></label><label className="text-sm">Исполнитель<select className="tf-input mt-1" value={taskAssignee} onChange={e => setTaskAssignee(e.target.value)}><option value="">Не назначен</option>{users.filter(u => u.is_active !== false).map(u => <option key={u.id} value={u.id}>{u.username}</option>)}</select></label><label className="text-sm">Крайний срок<input type="date" className="tf-input mt-1" value={taskDate} onChange={e => setTaskDate(e.target.value)} /></label><button disabled={busy} className="tf-button sm:col-span-2"><Plus size={16} />Создать связанную задачу</button></form>}
      </section>}
      {draft.id && <section className="mt-6 border-t border-[var(--color-border)] pt-4"><h4 className="font-bold">Дела по сделке</h4><div className="my-3 space-y-2">{activities.filter(a => a.deal_id === draft.id).map(a => <label key={a.id} className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={!can('crm_edit') || busy} checked={a.completed} onChange={e => void run(() => crm.update('activities', a.id, { completed: e.target.checked }))} /><span className={a.completed ? 'line-through text-[var(--color-muted)]' : ''}>{a.title}</span><span className="ml-auto text-xs text-[var(--color-muted)]">{a.due_at?.slice(0, 10)}</span></label>)}</div>
        {can('crm_edit') && mode !== 'trash' && <form className="flex flex-wrap gap-2" onSubmit={e => { e.preventDefault(); void run(async () => { await crm.create('activities', { deal_id: draft.id, title: activityTitle, kind: activityKind, due_at: activityDate ? new Date(activityDate).toISOString() : null }); setActivityTitle(''); }); }}><input required className="tf-input min-w-40 flex-1" placeholder="Следующий шаг" value={activityTitle} onChange={e => setActivityTitle(e.target.value)} /><select aria-label="Тип дела" className="tf-input" style={{ width: 'auto' }} value={activityKind} onChange={e => setActivityKind(e.target.value)}><option value="call">Звонок</option><option value="meeting">Встреча</option><option value="task">Дело</option><option value="note">Заметка</option></select><input aria-label="Дата дела" className="tf-input" style={{ width: 'auto' }} type="date" value={activityDate} onChange={e => setActivityDate(e.target.value)} /><button aria-label="Добавить" disabled={busy} className="tf-button"><Plus size={16} /></button></form>}
        {draft.contract_id && can('crm_edit') && <button className="tf-button mt-4" disabled={busy} onClick={() => { setRenewalContract(draft.contract_id!); setRenewalDate(''); }}>Продлить договор и создать задачу</button>}
      </section>}
    </section></div>}
    {renewalContract && <div className="tf-modal-backdrop"><form role="dialog" aria-modal="true" aria-label="Продление договора" className="tf-modal-shell w-full max-w-md space-y-4 p-6" onSubmit={e => { e.preventDefault(); void run(async () => { const result = await crm.renew(renewalContract, `${renewalDate}T12:00:00Z`); setDraft(prev => prev ? { ...prev, task_id: result.task_id } : prev); setRenewalContract(null); api.getTasks('scope=all').then(setTasks).catch(() => {}); }); }}>
      <h3 className="text-lg font-bold">Продление договора</h3><p className="text-sm text-[var(--color-text-secondary)]">Укажите новую дату окончания. Создадим связанную задачу, сохранив предыдущие продления в истории задач.</p>
      {error && <p role="alert" className="tf-alert-error">{error}</p>}
      <label className="block text-sm">Новая дата окончания<input required type="date" className="tf-input mt-1" value={renewalDate} onChange={e => setRenewalDate(e.target.value)} /></label>
      <div className="flex gap-2"><button type="button" className="tf-button" onClick={() => setRenewalContract(null)}>Отмена</button><button disabled={busy} className="tf-button tf-button-primary">Продлить и создать задачу</button></div>
    </form></div>}
    {contactDraft && <div className="tf-modal-backdrop" onClick={() => setContactDraft(null)}><form role="dialog" aria-modal="true" aria-label="Контакт" className="tf-modal-shell w-full max-w-md space-y-3 p-6" onClick={e => e.stopPropagation()} onSubmit={e => { e.preventDefault(); void run(async () => { const data = { name: contactDraft.name, email: contactDraft.email || '', phone: contactDraft.phone || '', position: contactDraft.position || '', client_id: contactDraft.client_id || null }; if (contactDraft.id) await crm.update('contacts', contactDraft.id, data); else await crm.create('contacts', data); setContactDraft(null); }); }}><div className="flex justify-between"><h3 className="text-lg font-bold">Контакт</h3><button type="button" aria-label="Закрыть" onClick={() => setContactDraft(null)}><X /></button></div>{error && <p className="tf-alert-error">{error}</p>}{(['name', 'email', 'phone', 'position'] as const).map(key => <label key={key} className="block text-sm">{{ name: 'Имя', email: 'Email', phone: 'Телефон', position: 'Должность' }[key]}<input required={key === 'name'} className="tf-input mt-1" type={key === 'email' ? 'email' : 'text'} value={contactDraft[key] || ''} onChange={e => setContactDraft(c => ({ ...c, [key]: e.target.value }))} /></label>)}<label className="block text-sm">Организация<select className="tf-input mt-1" value={contactDraft.client_id || ''} onChange={e => setContactDraft(c => ({ ...c, client_id: Number(e.target.value) || null }))}><option value="">Без организации</option>{clients.map(c => <option key={c.id} value={c.id}>{c.org_name}</option>)}</select></label><button disabled={busy} className="tf-button tf-button-primary w-full">Сохранить</button></form></div>}
  </div>;
}
