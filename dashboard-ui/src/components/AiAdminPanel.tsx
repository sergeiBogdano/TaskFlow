import { useEffect, useState } from 'react';
import { request } from '../api/client';
type Settings = { paused: boolean; daily_limit: number; queue_limit: number; timeout_seconds: number };
type Usage = { settings: Settings; stats: { username: string; status: string; requests: number; input_tokens: number; output_tokens: number; duration_ms: number }[]; queue: { id: string; username: string; workspace_id: number; kind: string; status: string }[] };
const labels: Record<string, string> = { queued: 'В очереди', running: 'Выполняется', completed: 'Готово', cancelled: 'Отменён', failed: 'Ошибка' };
export function AiAdminPanel() {
  const [data, setData] = useState<Usage>(); const [settings, setSettings] = useState<Settings>(); const [error, setError] = useState(''); const [saved, setSaved] = useState('');
  const load = async (initial = false) => { try { const result = await request<Usage>('/api/admin/ai'); setData(result); if (initial) setSettings(result.settings); } catch (err) { setError(String(err)); } };
  useEffect(() => { void load(true); const timer = setInterval(() => void load(), 5000); return () => clearInterval(timer); }, []);
  return <section className="tf-panel-flat space-y-4 p-5"><h3 className="font-semibold">Помощник: очередь и использование</h3><p className="text-sm text-[var(--color-muted)]">За 7 дней, без содержимого чужих диалогов. Один запрос выполняется одновременно; лимиты действуют на пользователя во всех пространствах.</p>
    {settings && <form className="flex flex-wrap items-end gap-3" onSubmit={async event => { event.preventDefault(); setError(''); setSaved(''); try { await request('/api/admin/ai/settings', { method: 'PUT', body: JSON.stringify(settings) }); setSaved('Настройки сохранены'); await load(); } catch (err) { setError(String(err)); } }}>
      <label className="text-sm"><input type="checkbox" checked={settings.paused} onChange={e => setSettings({ ...settings, paused: e.target.checked })} /> Приостановить новые запросы и очередь</label>
      {([['daily_limit', 'Запросов в сутки UTC', 1, 500], ['queue_limit', 'Размер очереди', 1, 100], ['timeout_seconds', 'Ожидание ответа, сек.', 30, 600]] as const).map(([key, label, min, max]) => <label key={key} className="text-sm">{label}<input className="tf-input mt-1 w-32" type="number" min={min} max={max} required value={settings[key]} onChange={e => setSettings({ ...settings, [key]: Number(e.target.value) })} /></label>)}
      <button className="tf-button tf-button-primary">Сохранить настройки</button>
    </form>}
    {!!data?.queue.length && <div className="space-y-2">{data.queue.map(job => <div key={job.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[var(--color-border)] p-3 text-sm"><span>{job.username} · пространство {job.workspace_id} · {labels[job.status]}</span><button className="tf-button" onClick={async () => { try { await request(`/api/admin/ai/requests/${job.id}/cancel`, { method: 'POST' }); await load(); } catch (err) { setError(String(err)); } }}>Отменить</button></div>)}</div>}
    <div className="overflow-auto"><table className="w-full text-left text-sm"><thead><tr>{['Пользователь', 'Статус', 'Запросы', 'Входные токены', 'Ответы: токены', 'Время, сек.'].map(label => <th key={label} className="p-2">{label}</th>)}</tr></thead><tbody>{data?.stats.map(row => <tr key={`${row.username}:${row.status}`}><td className="p-2">{row.username}</td><td className="p-2">{labels[row.status]}</td><td className="p-2">{row.requests}</td><td className="p-2">{row.input_tokens}</td><td className="p-2">{row.output_tokens}</td><td className="p-2">{Math.round(row.duration_ms / 1000)}</td></tr>)}</tbody></table></div>
    {error && <p role="alert" className="text-sm text-[var(--color-danger)]">{error}</p>}{saved && <p role="status" className="text-sm">{saved}</p>}
  </section>;
}
