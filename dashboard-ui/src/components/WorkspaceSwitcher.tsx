import { useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import { api, type Workspace } from '../api/client';
import { Select } from './Select';
import { ensureWorkspace, getActiveWorkspaceId, switchWorkspace } from '../lib/workspace';

const PRESETS = [
  { value: 'seo', label: 'SEO-команда', hint: 'Задачи, клиенты, договоры' },
  { value: 'study', label: 'Учёба', hint: 'Проекты, спринты, наставник AI' },
  { value: 'empty', label: 'Пустой', hint: 'С нуля' },
];

export function WorkspaceSwitcher({ compact }: { compact: boolean }) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [activeId, setActiveId] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [name, setName] = useState('');
  const [preset, setPreset] = useState('seo');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    ensureWorkspace()
      .then(({ workspaces, activeId }) => {
        setWorkspaces(workspaces);
        setActiveId(activeId || '');
      })
      .catch(() => {});
  }, []);

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

  if (!workspaces.length) return null;

  return (
    <div className={compact ? 'hidden' : 'px-2 pb-2 lg:block'}>
      <div className="mb-1 px-1 text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--color-muted)]">
        Окружение
      </div>
      <div className="flex items-center gap-1.5">
        <div className="min-w-0 flex-1">
          <Select
            value={activeId || getActiveWorkspaceId() || ''}
            options={workspaces.map(w => ({ value: String(w.id), label: w.name, hint: w.role === 'owner' ? 'владелец' : w.role }))}
            onChange={value => {
              if (value && value !== activeId) void switchWorkspace(value);
            }}
            searchPlaceholder="Найти окружение..."
          />
        </div>
        <button
          type="button"
          onClick={() => setModalOpen(true)}
          className="tf-button h-[42px] w-10 shrink-0 px-0"
          title="Новое окружение"
          aria-label="Новое окружение"
        >
          <Plus size={16} />
        </button>
      </div>

      {modalOpen && (
        <div className="anim-modal fixed inset-0 z-50 grid place-items-center bg-black/55 p-4" onClick={() => setModalOpen(false)}>
          <form onSubmit={create} className="tf-modal-shell w-full max-w-sm p-5" onClick={event => event.stopPropagation()}>
            <div className="mb-4 text-base font-bold">Новое окружение</div>
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
              <p className="text-xs leading-5 text-[var(--color-text-secondary)]">Ты станешь владельцем: удалить тебя и сменить тебе пароль сможет только суперадмин.</p>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
