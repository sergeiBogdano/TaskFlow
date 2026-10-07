import { useEffect, useState } from 'react';
import { Puzzle } from 'lucide-react';
import { api } from '../api/client';
import { useAuth } from '../hooks/useAuth';

export function SpaceModulesPanel({ id, onSaved }: { id: number; onSaved: () => void }) {
  const { user } = useAuth();
  const [catalog, setCatalog] = useState<Record<string, { label: string }>>({});
  const [enabled, setEnabled] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { api.getSpaceModules(id).then(data => { setCatalog(data.catalog); setEnabled(data.enabled); }).catch(e => setError(e.message)); }, [id]);
  const toggle = async (key: string) => {
    const next = enabled.includes(key) ? enabled.filter(x => x !== key) : [...enabled, key];
    setBusy(true); setError('');
    try { await api.setSpaceModules(id, next); setEnabled(next); onSaved(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Не удалось сохранить'); }
    finally { setBusy(false); }
  };
  return <section className="tf-panel-flat p-5"><h3 className="mb-2 flex items-center gap-2 font-bold"><Puzzle size={16} />Модули пространства</h3><p className="tf-page-subtitle mb-4">Выберите инструменты для этой команды. Отключённый модуль исчезнет из меню и закроется для запросов. Данные сохранятся. После возвращения модуля явно включите нужные функции для участников в панели ниже. Настройка доступна суперадмину.</p><div className="grid gap-2 sm:grid-cols-2">{Object.entries(catalog).map(([key, item]) => <label key={key} className="flex items-center justify-between gap-3 rounded-xl border border-[var(--color-border)] p-3 text-sm"><span>{item.label}</span><input type="checkbox" checked={enabled.includes(key)} disabled={!user?.is_root || busy} onChange={() => void toggle(key)} /></label>)}</div>{error && <p role="alert" className="tf-alert-error mt-3">{error}</p>}</section>;
}
