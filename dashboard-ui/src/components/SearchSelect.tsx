import { Check, ChevronDown, Search, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';

export type SearchSelectOption = {
  value: string;
  label: string;
  description?: string;
  searchText?: string;
};

type SearchSelectProps = {
  value: string;
  options: SearchSelectOption[];
  onChange: (value: string) => void;
  placeholder?: string;
  searchPlaceholder?: string;
  emptyLabel?: string;
};

export function SearchSelect({
  value,
  options,
  onChange,
  placeholder = 'Выберите',
  searchPlaceholder = 'Поиск...',
  emptyLabel,
}: SearchSelectProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const selected = options.find(option => option.value === value);
  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase('ru-RU');
    if (!needle) return options;
    return options.filter(option =>
      `${option.label} ${option.description || ''} ${option.searchText || ''}`
        .toLocaleLowerCase('ru-RU')
        .includes(needle),
    );
  }, [options, query]);

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  useEffect(() => {
    if (!open) return;
    setQuery('');
    requestAnimationFrame(() => inputRef.current?.focus());
  }, [open]);

  const choose = (nextValue: string) => {
    onChange(nextValue);
    setOpen(false);
  };

  return (
    <div ref={rootRef} className="relative">
      <button type="button" onClick={() => setOpen(previous => !previous)} className="tf-input flex min-h-[38px] w-full items-center gap-2 text-left">
        <span className={`min-w-0 flex-1 truncate ${selected ? '' : 'text-[var(--color-muted)]'}`}>
          {selected?.label || (value === '' && emptyLabel) || placeholder}
        </span>
        {value && (
          <span
            role="button"
            tabIndex={0}
            title="Очистить"
            onClick={event => { event.stopPropagation(); choose(''); }}
            onKeyDown={event => { if (event.key === 'Enter') choose(''); }}
            className="shrink-0 text-[var(--color-muted)] hover:text-[var(--color-text)]"
          >
            <X size={14} />
          </span>
        )}
        <ChevronDown size={15} className="shrink-0 text-[var(--color-muted)]" />
      </button>

      {open && (
        <div className="absolute left-0 right-0 top-[calc(100%+6px)] z-[90] overflow-hidden rounded-lg border border-[var(--color-border-strong)] bg-[var(--color-surface)] shadow-2xl">
          <div className="relative border-b border-[var(--color-border)] p-2">
            <Search size={14} className="pointer-events-none absolute left-4 top-[21px] text-[var(--color-muted)]" />
            <input
              ref={inputRef}
              value={query}
              onChange={event => setQuery(event.target.value)}
              onKeyDown={event => { if (event.key === 'Escape') setOpen(false); }}
              className="tf-input tf-input-icon"
              placeholder={searchPlaceholder}
            />
          </div>
          <div className="max-h-64 overflow-auto p-1">
            {emptyLabel && (
              <button type="button" onClick={() => choose('')} className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm hover:bg-[var(--color-surface-2)]">
                <span className="min-w-0 flex-1 text-[var(--color-text-secondary)]">{emptyLabel}</span>
                {value === '' && <Check size={14} className="text-[var(--color-accent)]" />}
              </button>
            )}
            {filtered.map(option => (
              <button key={option.value} type="button" onClick={() => choose(option.value)} className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left hover:bg-[var(--color-surface-2)]">
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold">{option.label}</span>
                  {option.description && <span className="block truncate text-xs text-[var(--color-muted)]">{option.description}</span>}
                </span>
                {option.value === value && <Check size={14} className="shrink-0 text-[var(--color-accent)]" />}
              </button>
            ))}
            {!filtered.length && <div className="px-3 py-6 text-center text-sm text-[var(--color-text-secondary)]">Ничего не найдено</div>}
          </div>
        </div>
      )}
    </div>
  );
}
