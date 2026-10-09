import { createPortal } from 'react-dom';
import { useEffect, useRef, useState } from 'react';
import { Plus, X } from 'lucide-react';
import { api, type Workspace } from '../api/client';
import { useAuth } from '../hooks/useAuth';
import { Select } from './Select';
import { ensureWorkspace, getActiveWorkspaceId, switchWorkspace } from '../lib/workspace';

const PRESETS = [
  { value: 'seo', label: 'SEO-команда', hint: 'Задачи, клиенты, договоры' },
  { value: 'study', label: 'Учёба', hint: 'Задачи, спринты и заметки' },
  { value: 'project', label: 'Проект', hint: 'Командная разработка, спринты, фичи' },
  { value: 'empty', label: 'Пустой', hint: 'Стандартные названия, с нуля' },
];

export function WorkspaceSwitcher(_props: { compact: boolean }) {
  const { user } = useAuth();
  const canCreate = Boolean(user?.is_root || user?.permissions?.workspaces_create);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [activeId, setActiveId] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [name, setName] = useState('');
  const [preset, setPreset] = useState('seo');
  const [saving, setSaving] = useState(false);
  const dialogRef = useRef<HTMLFormElement>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    ensureWorkspace()
      .then(({ workspaces, activeId }) => {
        setWorkspaces(workspaces);
        setActiveId(activeId || '');
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!modalOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const keys = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); setModalOpen(false); }
      if (event.key === 'Tab') {
        const elements = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex="0"]') || []);
        const first = elements[0], last = elements[elements.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener('keydown', keys, true);
    return () => { document.removeEventListener('keydown', keys, true); document.body.style.overflow = previousOverflow; previous?.focus(); };
  }, [modalOpen]);

  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    const clean = name.trim();
    if (!clean) {
      setError('Нужно название.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const ws = await api.createWorkspace(clean, preset);
      setModalOpen(false);
      setName('');
      await switchWorkspace(String(ws.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось создать.');
    } finally {
      setSaving(false);
    }
  };

  const renderModal = () => modalOpen && createPortal((
    <div className="tf-modal-backdrop anim-modal" onClick={() => setModalOpen(false)}>
      <form ref={dialogRef} role="dialog" aria-modal="true" aria-label="Новое окружение" onSubmit={create} className="tf-modal-shell w-full max-w-sm p-5" onClick={event => event.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between gap-3"><h2 className="text-base font-bold">Новое окружение</h2><button type="button" className="tf-button h-8 w-8 shrink-0 px-0" aria-label="Закрыть создание окружения" onClick={() => setModalOpen(false)}><X size={16} /></button></div>
        <div className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Название</span>
            <input className="tf-input" value={name} onChange={event => setName(event.target.value)} placeholder="Например: Учёба" maxLength={200} autoFocus />
          </label>
          <div>
            <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Пресет</span>
            <div className="grid gap-2">
              {PRESETS.map(p => (
                <button
                  key={p.value}
                  type="button"
                  onClick={() => setPreset(p.value)}
                  className={preset === p.value
                    ? 'rounded-xl border border-[var(--color-accent)] bg-[var(--color-accent)]/10 px-3 py-2.5 text-left'
                    : 'rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2.5 text-left hover:border-[var(--color-border-strong)]'}
                >
                  <span className="block text-sm font-bold">{p.label}</span>
                  <span className="block text-xs text-[var(--color-text-secondary)]">{p.hint}</span>
                </button>
              ))}
            </div>
          </div>
          {error && <div className="text-sm font-semibold text-[var(--color-danger)]">{error}</div>}
          <div className="flex gap-2">
            <button type="button" onClick={() => setModalOpen(false)} className="tf-button flex-1">Отмена</button>
            <button type="submit" disabled={saving} className="tf-button tf-button-primary flex-1">
              {saving ? 'Создаём...' : 'Создать'}
            </button>
          </div>
          <p className="text-xs leading-5 text-[var(--color-text-secondary)]">Вы станете владельцем пространства и сможете приглашать участников. Учётными записями управляет администратор приложения.</p>
        </div>
      </form>
    </div>
  ), document.body);

  if (!workspaces.length) {
    return (
      <div className="px-2 pb-2">
        <div className="mb-1 px-1 text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--color-muted)]">
          Окружение
        </div>
        <div className="rounded-xl border border-dashed border-[var(--color-border)] p-4 text-center">
          <p className="mb-3 text-xs leading-5 text-[var(--color-text-secondary)]">
            У вас пока нет пространства. Попросите администратора пригласить вас.
          </p>
          {canCreate && <button
            type="button"
            onClick={() => setModalOpen(true)}
            className="tf-button tf-button-primary h-9 px-4 text-sm"
          >
            Создать пространство
          </button>}
        </div>
        {renderModal()}
      </div>
    );
  }

  return (
    <div className="min-w-0 px-2 pb-2">
      <div className="mb-1 px-1 text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--color-muted)]">
        Окружение
      </div>
      <div className="flex items-center gap-1.5">
        <div className="min-w-0 flex-1">
          <Select
            value={activeId || getActiveWorkspaceId() || ''}
            options={workspaces.map(w => ({
              value: String(w.id),
              label: w.name,
              hint: w.role === 'owner' ? 'владелец окружения' : w.role === 'admin' ? 'администратор окружения' : 'участник окружения',
            }))}
            onChange={value => {
              if (value && value !== activeId) void switchWorkspace(value);
            }}
            searchPlaceholder="Найти окружение..."
          />
        </div>
        {canCreate && <button
          type="button"
          onClick={() => setModalOpen(true)}
          className="tf-button h-[42px] w-10 shrink-0 px-0"
          title="Новое окружение"
          aria-label="Новое окружение"
        >
          <Plus size={16} />
        </button>}
      </div>
      {(workspaces.find(w => String(w.id) === activeId)?.name.length || 0) > 28 && <details className="mt-2 text-xs text-[var(--color-muted)]"><summary className="cursor-pointer">Полное название окружения</summary><p className="mt-1" style={{ overflowWrap: 'anywhere' }}>{workspaces.find(w => String(w.id) === activeId)?.name}</p></details>}
      {renderModal()}
    </div>
  );
}
