import { useEffect, useState } from 'react';
import { Puzzle } from 'lucide-react';
import { api } from '../api/client';
import { useAuth } from '../hooks/useAuth';

export function SpaceModulesPanel({ id, onSaved, onAccess }: { id: number; onSaved: () => void; onAccess?: () => void }) {
  const { user } = useAuth();
  const [catalog, setCatalog] = useState<Record<string, { label: string }>>({});
  const [enabled, setEnabled] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { api.getSpaceModules(id).then(data => { setCatalog(data.catalog); setEnabled(data.enabled); }).catch(e => setError(e.message)); }, [id]);
  const toggle = async (key: string) => {
    const next = enabled.includes(key) ? enabled.filter(x => x !== key) : [...enabled, key];
    setBusy(true); setError('');
    try { await api.setSpaceModules(id, next); setEnabled(next); window.dispatchEvent(new Event('taskflow:access-updated')); onSaved(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Не удалось сохранить'); }
    finally { setBusy(false); }
  };
  return <section className="tf-panel-flat p-5"><h3 className="mb-2 flex items-center gap-2 font-bold"><Puzzle size={16} />Модули пространства</h3><p className="tf-page-subtitle mb-4">Выберите инструменты для этой команды. Отключённый модуль исчезнет из меню и закроется для запросов. Данные сохранятся. Галочка включает инструмент для пространства, но не выдаёт участникам права. После возвращения модуля проверьте его функции и права пользователей на вкладке «Доступ». Настройка доступна суперадмину.</p>{onAccess && <button type="button" className="tf-button mb-4" onClick={onAccess}>Проверить доступ пользователей →</button>}<div className="grid gap-2 sm:grid-cols-2">{Object.entries(catalog).map(([key, item]) => <label key={key} className="flex items-center justify-between gap-3 rounded-xl border border-[var(--color-border)] p-3 text-sm"><span>{item.label}</span><input type="checkbox" checked={enabled.includes(key)} disabled={!user?.is_root || busy} onChange={() => void toggle(key)} /></label>)}</div>{error && <p role="alert" className="tf-alert-error mt-3">{error}</p>}</section>;
}
