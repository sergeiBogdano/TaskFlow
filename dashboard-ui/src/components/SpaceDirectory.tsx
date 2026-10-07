import { useEffect, useState } from 'react';
import { Building2 } from 'lucide-react';
import { api } from '../api/client';
import { switchWorkspace } from '../lib/workspace';

export function SpaceDirectory() {
  const [spaces, setSpaces] = useState<{ id: number; name: string; visibility: string; joined: boolean }[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState<number | null>(null);
  useEffect(() => { api.getSpaceDirectory().then(setSpaces).catch(e => setError(e.message)); }, []);
  const join = async (id: number) => {
    setBusy(id); setError('');
    try { await api.joinSpace(id); await switchWorkspace(String(id)); }
    catch (e) { setError(e instanceof Error ? e.message : 'Не удалось вступить'); }
    finally { setBusy(null); }
  };
  return <section className="tf-panel-flat p-6 space-y-5">
    <div className="flex items-center gap-3"><Building2 /><div><h1 className="text-xl font-semibold">Пространства</h1><p className="text-sm text-[var(--color-text-secondary)]">Выберите открытое пространство или попросите администратора пригласить вас.</p></div></div>
    {error && <p role="alert" className="tf-alert-error">{error}</p>}
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{spaces.map(s => <article key={s.id} className="tf-panel-flat p-4 space-y-3">
      <h2 className="font-semibold">{s.name}</h2><p className="text-sm text-[var(--color-text-secondary)]">{s.visibility === 'open' ? 'Открыто для вступления' : 'Вступление по приглашению'}</p>
      {s.joined ? <button className="tf-button" onClick={() => switchWorkspace(String(s.id))}>Открыть</button> : s.visibility === 'open' ? <button disabled={busy !== null} className="tf-button tf-button-primary" onClick={() => join(s.id)}>{busy === s.id ? 'Вступаем...' : 'Вступить'}</button> : <span className="text-sm">Обратитесь к администратору</span>}
    </article>)}</div>
    {!spaces.length && <p className="text-sm text-[var(--color-text-secondary)]">Доступных пространств пока нет. Администратор может создать их и пригласить вас.</p>}
  </section>;
}
