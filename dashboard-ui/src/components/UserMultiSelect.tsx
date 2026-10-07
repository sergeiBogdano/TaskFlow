import { ChevronDown } from 'lucide-react';
import { createPortal } from 'react-dom';
import { useEffect, useId, useRef, useState } from 'react';
import { useFloatingMenu } from './useFloatingMenu';

export function UserMultiSelect({ users, selected, onChange }: {
  users: { id: number; username: string }[];
  selected: number[];
  onChange: (ids: number[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const rootRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const id = useId();
  const style = useFloatingMenu(open, rootRef, 220);
  useEffect(() => {
    if (!open) return;
    const outside = (event: Event) => {
      if (!rootRef.current?.contains(event.target as Node) && !menuRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); setOpen(false); triggerRef.current?.focus(); }
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('focusin', outside);
    document.addEventListener('keydown', escape, true);
    const frame = requestAnimationFrame(() => searchRef.current?.focus());
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('focusin', outside);
      document.removeEventListener('keydown', escape, true);
    };
  }, [open]);
  const matches = users.filter(user => user.username.toLocaleLowerCase('ru').includes(search.toLocaleLowerCase('ru')));
  return <div ref={rootRef} className="min-w-0">
    <button ref={triggerRef} type="button" aria-expanded={open} aria-controls={id} aria-label="Выбрать сотрудников"
      className="tf-input flex items-center justify-between gap-2 text-left" onClick={() => { setSearch(''); setOpen(!open); }}>
      <span className="min-w-0 truncate">{selected.length ? `Выбрано: ${selected.length}` : 'Выберите сотрудников'}</span><ChevronDown size={15} className="shrink-0" />
    </button>
    {open && createPortal(<div ref={menuRef} id={id} style={style} className="tf-floating-menu z-[1000] rounded-2xl border border-[var(--color-border-strong)] bg-[var(--color-surface)] text-[var(--color-text)] shadow-[var(--shadow-panel)]">
      <div className="shrink-0 space-y-2 border-b border-[var(--color-border)] p-2"><input ref={searchRef} className="tf-input" aria-label="Поиск сотрудников" placeholder="Поиск сотрудников" value={search} onChange={e => setSearch(e.target.value)} />
        <div className="flex gap-2"><button type="button" className="tf-button h-7 px-2 text-xs" onClick={() => onChange(users.map(user => user.id))}>Все</button>
          <button type="button" className="tf-button h-7 px-2 text-xs" onClick={() => onChange([])}>Снять</button>
          <button type="button" className="tf-button ml-auto h-7 px-2 text-xs" onClick={() => { setOpen(false); triggerRef.current?.focus(); }}>Готово</button></div>
      </div>
      <div className="tf-menu-options p-2">{matches.map(user => <label key={user.id} className="flex cursor-pointer items-center gap-2 rounded-xl px-2 py-2 text-sm hover:bg-[var(--color-overlay)]">
        <input type="checkbox" className="accent-[var(--color-accent)]" checked={selected.includes(user.id)}
          onChange={e => onChange(e.target.checked ? [...selected, user.id] : selected.filter(id => id !== user.id))} /><span className="min-w-0 break-words">{user.username}</span>
      </label>)}{!matches.length && <p className="p-3 text-sm text-[var(--color-muted)]">Сотрудники не найдены</p>}</div>
    </div>, document.body)}
  </div>;
}
