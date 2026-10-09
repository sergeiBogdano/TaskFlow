import { sectionLabel } from '../lib/uiconfig';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bell, CheckCheck, ChevronRight, Trash2 } from 'lucide-react';
import { api, type Notification } from '../api/client';

export function Notifications() {
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [loading, setLoading] = useState(true);

  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const revision = useRef(0);
  const load = useCallback(async () => {
    const current = ++revision.current;
    setLoading(true); setError('');
    try {
      const data = await api.getNotifications();
      if (current === revision.current) { setNotifications(data.notifications); setUnreadCount(data.unread_count); }
    } catch (err) { if (current === revision.current) setError(err instanceof Error ? err.message : 'Не удалось загрузить уведомления'); }
    finally { if (current === revision.current) setLoading(false); }
  }, []);
  useEffect(() => { void load(); return () => { revision.current++; }; }, [load]);
  const perform = async (operation: () => Promise<unknown>) => {
    if (busyRef.current) return false;
    busyRef.current = true; setBusy(true); setError('');
    try { await operation(); return true; }
    catch (err) { setError(err instanceof Error ? err.message : 'Не удалось изменить уведомления'); return false; }
    finally { busyRef.current = false; setBusy(false); }
  };

  const refreshBadge = () => {
    window.dispatchEvent(new Event('taskflow:notifications-updated'));
  };

  const markRead = async (id: number) => {
    const wasUnread = notifications.some(item => item.id === id && !item.read);
    if (!await perform(() => api.markNotificationRead(id))) return;
    setNotifications(prev => prev.map(item => item.id === id ? { ...item, read: true } : item));
    if (wasUnread) setUnreadCount(prev => Math.max(0, prev - 1));
    refreshBadge();
  };

  const markAllRead = async () => {
    if (!await perform(() => api.markAllRead())) return;
    setNotifications(prev => prev.map(item => ({ ...item, read: true })));
    setUnreadCount(0);
    refreshBadge();
  };

  const deleteOne = async (id: number) => {
    const notification = notifications.find(item => item.id === id);
    if (!await perform(() => api.deleteNotification(id))) return;
    setNotifications(prev => prev.filter(item => item.id !== id));
    setSelectedIds(prev => prev.filter(item => item !== id));
    if (notification && !notification.read) setUnreadCount(prev => Math.max(0, prev - 1));
    refreshBadge();
  };

  const deleteSelected = async () => {
    if (!selectedIds.length) return;
    if (!await perform(() => api.deleteNotifications(selectedIds))) return;
    const selectedUnread = notifications.filter(item => selectedIds.includes(item.id) && !item.read).length;
    setNotifications(prev => prev.filter(item => !selectedIds.includes(item.id)));
    setSelectedIds([]);
    setUnreadCount(prev => Math.max(0, prev - selectedUnread));
    refreshBadge();
  };

  const deleteAll = async () => {
    if (!notifications.length || !window.confirm('Удалить все уведомления?')) return;
    if (!await perform(() => api.deleteAllNotifications())) return;
    setNotifications([]);
    setSelectedIds([]);
    setUnreadCount(0);
    refreshBadge();
  };

  const openNotification = async (notification: Notification) => {
    if (!notification.read) await markRead(notification.id);
    if (notification.task_id) navigate(`/tasks?task=${notification.task_id}`);
    else if (notification.client_id) navigate(`/clients/${notification.client_id}`);
  };

  if (loading) return <div className="grid h-64 place-items-center text-sm text-[var(--color-text-secondary)]">Загрузка уведомлений...</div>;

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-xl font-black"><Bell size={22} />{sectionLabel('/notifications')}</h2>
          <p className="text-sm text-[var(--color-text-secondary)]">События по задачам, клиентам и срокам. Клик открывает связанный объект.</p>
        </div>
        <div className="ml-auto flex flex-wrap gap-2">
          {unreadCount > 0 && <button disabled={busy} onClick={markAllRead} className="tf-button"><CheckCheck size={16} />Прочитать все</button>}
          {selectedIds.length > 0 && <button disabled={busy} onClick={deleteSelected} className="tf-button text-[var(--color-danger)]"><Trash2 size={15} />Удалить выбранные ({selectedIds.length})</button>}
          {notifications.length > 0 && <button disabled={busy} onClick={deleteAll} className="tf-button text-[var(--color-danger)]"><Trash2 size={15} />Удалить все</button>}
        </div>
      </div>

      {error && <div role="alert" className="tf-alert-error flex flex-wrap items-center gap-3"><span className="min-w-0 flex-1">{error}</span><button disabled={busy} className="tf-button" onClick={() => void load()}>Повторить загрузку</button></div>}
      <section className="space-y-2">
        {notifications.map(notification => (
          <article
            key={notification.id}
            className={`tf-notification flex w-full items-start gap-3 rounded-lg border p-4 text-left transition-colors hover:border-[var(--color-border-strong)] ${notification.read ? 'tf-notification-read' : 'tf-notification-unread'}`}
          >
            <input type="checkbox" disabled={busy} checked={selectedIds.includes(notification.id)} onClick={event => event.stopPropagation()} onChange={() => setSelectedIds(prev => prev.includes(notification.id) ? prev.filter(id => id !== notification.id) : [...prev, notification.id])} className="mt-1 accent-[var(--color-accent)]" aria-label={`Выбрать уведомление ${notification.id}`} />
            <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${notification.read ? 'bg-transparent' : 'bg-[var(--color-accent)]'}`} />
            <button type="button" disabled={busy} onClick={() => void openNotification(notification)} className="tf-notification-content min-w-0 flex-1 text-left">
              <span className="block break-words text-sm font-semibold">{notification.title}</span>
              {notification.message && <span className="mt-1 block text-xs text-[var(--color-text-secondary)]">{notification.message}</span>}
              <span className="mt-1 block text-[11px] text-[var(--color-muted)]">{notification.created_at ? new Date(notification.created_at).toLocaleString('ru-RU') : ''}</span>
            </button>
            {(notification.task_id || notification.client_id) && <ChevronRight size={16} className="text-[var(--color-muted)]" />}
            <button type="button" disabled={busy} onClick={event => { event.stopPropagation(); void deleteOne(notification.id); }} className="tf-button h-8 w-8 shrink-0 px-0 text-[var(--color-muted)] hover:text-[var(--color-danger)]" aria-label="Удалить уведомление"><Trash2 size={15} /></button>
          </article>
        ))}
        {notifications.length === 0 && !error && <div className="tf-panel-flat p-8 text-center text-sm text-[var(--color-text-secondary)]">Уведомлений пока нет.</div>}
      </section>
    </div>
  );
}
