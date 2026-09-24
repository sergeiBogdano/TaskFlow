import { Check, ChevronDown, Search } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { cn } from '../lib/taskflow';

export type SelectOption = {
  value: string;
  label: string;
  hint?: string;
  color?: string;
};

type SelectProps = {
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  placeholder?: string;
  emptyLabel?: string;
  searchPlaceholder?: string;
  disabled?: boolean;
  label?: string;
  size?: 'md' | 'sm' | 'pill';
  className?: string;
  stopPropagation?: boolean;
};

/**
 * Глобальный дропдаун проекта — единый стиль везде:
 * кастомный триггер + стеклянный список вместо нативного select.
 */
export function Select({
  value,
  options,
  onChange,
  placeholder = 'Выберите',
  emptyLabel,
  searchPlaceholder,
  disabled,
  label,
  size = 'md',
  className,
  stopPropagation,
}: SelectProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const selected = options.find(option => option.value === value);

  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase('ru-RU');
    if (!needle) return options;
    return options.filter(option =>
      `${option.label} ${option.hint || ''}`.toLocaleLowerCase('ru-RU').includes(needle),
    );
  }, [options, query]);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', onKey);
    };
  }, [open ]);

  useEffect(() => {
    if (open) {
      setQuery('');
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open ]);

  const choose = (nextValue: string) => {
    onChange(nextValue);
    setOpen(false);
  };

  const triggerSize =
    size === 'sm'
      ? 'h-8 text-[12.5px] rounded-[10px] px-2.5 gap-1.5'
      : size === 'pill'
        ? 'h-8 text-[13.5px] rounded-full pl-4 pr-8 font-medium'
        : 'min-h-[42px] text-[14px] rounded-[14px] px-3.5 gap-2';

  const control = (
    <div ref={rootRef} className={cn('relative', className)} onClick={stopPropagation ? event => event.stopPropagation() : undefined}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen(previous => !previous)}
        title={selected?.label || placeholder}
        className={cn(
          'flex w-full items-center border border-[var(--color-border)] bg-[var(--color-input-bg)] text-left transition',
          'hover:border-[var(--color-border-strong)] focus:outline-none focus:ring-4 focus:ring-[var(--color-ring)]',
          'disabled:cursor-not-allowed disabled:opacity-60',
          triggerSize,
          !selected && 'text-[var(--color-muted)]',
        )}
      >
        {selected?.color && <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: selected.color }} />}
        <span className="min-w-0 flex-1 truncate font-medium">{selected?.label || placeholder}</span>
        <ChevronDown size={14} className={cn('shrink-0 text-[var(--color-muted)] transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <div className="anim-modal absolute left-0 right-0 top-[calc(100%+6px)] z-[95] min-w-[180px] overflow-hidden rounded-2xl border border-[var(--color-border-strong)] bg-[var(--color-surface)]/90 shadow-[var(--shadow-panel)] backdrop-blur-xl">
          {searchPlaceholder && (
            <div className="relative border-b border-[var(--color-border)] p-2">
              <Search size={14} className="pointer-events-none absolute left-4 top-[21px] text-[var(--color-muted)]" />
              <input
                ref={inputRef}
                value={query}
                onChange={event => setQuery(event.target.value)}
                className="tf-input tf-input-icon"
                placeholder={searchPlaceholder}
              />
            </div>
          )}
          <div className="max-h-64 overflow-auto p-1.5">
            {emptyLabel && (
              <button type="button" onClick={() => choose('')} className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm transition hover:bg-[var(--color-overlay)]">
                <span className="min-w-0 flex-1 truncate text-[var(--color-text-secondary)]">{emptyLabel}</span>
                {value === '' && <Check size={14} className="shrink-0 text-[var(--color-text)]" />}
              </button>
            )}
            {filtered.map(option => {
              const active = option.value === value;
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => choose(option.value)}
                  title={option.label}
                  className={cn(
                    'flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-sm transition',
                    active ? 'bg-[var(--color-overlay-strong)]' : 'hover:bg-[var(--color-overlay)]',
                  )}
                >
                  {option.color && <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: option.color }} />}
                  <span className="min-w-0 flex-1">
                    <span className={cn('block truncate', active ? 'font-semibold' : 'font-medium')}>{option.label}</span>
                    {option.hint && <span className="block truncate text-xs text-[var(--color-muted)]">{option.hint}</span>}
                  </span>
                  {active && <Check size={14} className="shrink-0 text-[var(--color-text)]" />}
                </button>
              );
            })}
            {!filtered.length && <div className="px-3 py-6 text-center text-sm text-[var(--color-text-secondary)]">Ничего не найдено</div>}
          </div>
        </div>
      )}
    </div>
  );

  if (!label) return control;
  return (
    <label className="inline-flex items-center gap-2 text-[var(--color-text-secondary)]">
      <span className="text-[14px]">{label}</span>
      {control}
    </label>
  );
}
