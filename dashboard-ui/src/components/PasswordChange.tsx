import { useState, type FormEvent } from 'react';
import { KeyRound } from 'lucide-react';
import { api } from '../api/client';

export function PasswordChange({ required = false }: { required?: boolean }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [repeat, setRepeat] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (next !== repeat) { setMessage('Пароли не совпадают'); return; }
    setBusy(true); setMessage('');
    try { await api.changePassword(current, next); window.location.href = '/'; }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Не удалось сменить пароль'); }
    finally { setBusy(false); }
  };
  return <section className="tf-panel-flat mx-auto w-full max-w-md p-6">
    <KeyRound className="mb-3 text-[var(--color-accent)]" />
    <h2 className="text-xl font-bold">{required ? 'Задайте постоянный пароль' : 'Смена пароля'}</h2>
    <p className="tf-page-subtitle mb-5">{required ? 'Перед началом работы замените временный пароль.' : 'После смены пароля другие сеансы будут завершены.'}</p>
    <form onSubmit={submit} className="space-y-3">
      <label className="block text-sm">Текущий пароль<input className="tf-input mt-1" type="password" autoComplete="current-password" required value={current} onChange={e => setCurrent(e.target.value)} /></label>
      <label className="block text-sm">Новый пароль<input className="tf-input mt-1" type="password" autoComplete="new-password" required minLength={8} value={next} onChange={e => setNext(e.target.value)} /></label>
      <label className="block text-sm">Повторите пароль<input className="tf-input mt-1" type="password" autoComplete="new-password" required minLength={8} value={repeat} onChange={e => setRepeat(e.target.value)} /></label>
      {message && <p role="alert" className="text-sm text-[var(--color-danger)]">{message}</p>}
      <button disabled={busy} className="tf-button tf-button-primary w-full">{busy ? 'Сохранение…' : 'Сохранить пароль'}</button>
    </form>
  </section>;
}
