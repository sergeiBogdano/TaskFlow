import { useEffect, useState } from 'react';
import { api, type Group, type PermissionCatalog } from '../api/client';
import { FeaturesPanel } from './FeaturesPanel';

export function GroupAccessEditor({ group, catalog, onSaved }: { group: Group; catalog: PermissionCatalog | null; onSaved: () => Promise<void> }) {
  const [name, setName] = useState(group.name);
  const [permissions, setPermissions] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  useEffect(() => { setName(group.name); setPermissions({ ...group.permissions }); }, [group]);
  const save = async () => {
    setBusy(true); setMessage('');
    try {
      const keys = catalog?.groups.filter(item => item.scope === 'app').flatMap(item => item.items.map(value => value.key)) || [];
      await api.updateGroup(group.id, { name, permissions: Object.fromEntries(keys.map(key => [key, Boolean(permissions[key])])) });
      await onSaved(); window.dispatchEvent(new Event('taskflow:access-updated')); setMessage('Права группы сохранены');
    } catch (err) { setMessage(err instanceof Error ? err.message : 'Не удалось сохранить группу'); }
    finally { setBusy(false); }
  };
  return <div className="mt-4 space-y-4">
    <p className="text-sm text-[var(--color-text-secondary)]">Группа добавляет отмеченные права приложения всем своим участникам. Пустая группа только объединяет аккаунты. Снятая галочка не отменяет право из роли или другой группы; для запрета используйте переключатель доступности функции. Членство в пространстве и рабочие права, включая ИИ, задаются в «Окружение → Доступ».</p>
    <label className="block text-sm">Название группы<input className="tf-input mt-1" maxLength={100} value={name} disabled={busy} onChange={e => setName(e.target.value)} /></label>
    {catalog?.groups.filter(item => item.scope === 'app').map(section => <div key={section.id}><h4 className="mb-2 font-semibold">{section.title}</h4><div className="grid gap-2 sm:grid-cols-2">{section.items.map(item => <label key={item.key} className="flex items-start gap-2 rounded-lg border border-[var(--color-border)] p-3 text-sm"><input type="checkbox" disabled={busy} checked={Boolean(permissions[item.key])} onChange={e => setPermissions({ ...permissions, [item.key]: e.target.checked })} /><span>{item.label}<span className="block text-xs text-[var(--color-muted)]">{item.hint}</span></span></label>)}</div></div>)}
    <button className="tf-button tf-button-primary" disabled={busy || !catalog || !name.trim()} onClick={() => void save()}>Сохранить права группы</button>
    {message && <p role="status" className="text-sm">{message}</p>}
    <FeaturesPanel scope="group" targetId={group.id} title="Доступность функций для группы" description="Эти переключатели разрешают или ограничивают использование уже выданных прав. Включение ИИ здесь не выдаёт рабочее право на ИИ и не добавляет пользователей в пространства. Глобальные запреты и отключённые модули остаются в силе; личные настройки пользователя могут отличаться." />
  </div>;
}
