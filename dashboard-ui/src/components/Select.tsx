import { Check, ChevronDown, Search, X } from 'lucide-react';
import { createPortal } from 'react-dom';
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { cn } from '../lib/taskflow';
import { useFloatingMenu } from './useFloatingMenu';

export type SelectOption = {
  value: string;
  label: string;
  hint?: string;
  color?: string;
  searchText?: string;
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
  clearable?: boolean;
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
  clearable,
}: SelectProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const id = useId();
  const [activeIndex, setActiveIndex] = useState(0);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const menuStyle = useFloatingMenu(open, rootRef, 180);
  const selected = options.find(option => option.value === value);

  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase('ru-RU');
    const matches = options.filter(option =>
      `${option.label} ${option.hint || ''} ${option.searchText || ''}`.toLocaleLowerCase('ru-RU').includes(needle),
    );
    return emptyLabel && !options.some(option => option.value === '')
      ? [{ value: '', label: emptyLabel }, ...matches] : matches;
  }, [options, query, emptyLabel]);
  const active = Math.min(activeIndex, Math.max(0, filtered.length - 1));

  useEffect(() => {
    if (!open) return;
    const close = (event: Event) => {
      const target = event.target as Node;
      if (!rootRef.current?.contains(target) && !menuRef.current?.contains(target)) setOpen(false);
    };
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault(); event.stopPropagation(); setOpen(false); triggerRef.current?.focus();
      }
    };
    document.addEventListener('pointerdown', close);
    document.addEventListener('focusin', close);
    document.addEventListener('keydown', onKey, true);
    return () => {
      document.removeEventListener('pointerdown', close);
      document.removeEventListener('focusin', close);
      document.removeEventListener('keydown', onKey, true);
    };
  }, [open ]);

  useEffect(() => {
    if (open) {
      setQuery('');
      const frame = requestAnimationFrame(() => inputRef.current?.focus());
      return () => cancelAnimationFrame(frame);
    }
  }, [open ]);

  const choose = (nextValue: string) => {
    onChange(nextValue);
    setOpen(false);
    triggerRef.current?.focus();
  };
  useEffect(() => {
    if (open) menuRef.current?.querySelector(`[data-option-index="${active}"]`)?.scrollIntoView({ block: 'nearest' });
  }, [active, open]);
  useEffect(() => { if (disabled) setOpen(false); }, [disabled]);
  const show = () => {
    setActiveIndex(Math.max(0, filtered.findIndex(option => option.value === value)));
    setOpen(true);
  };
  const keys = (event: KeyboardEvent) => {
    if (event.key === 'Tab') { setOpen(false); triggerRef.current?.focus(); return; }
    if (!open && ['ArrowDown', 'ArrowUp'].includes(event.key)) { event.preventDefault(); show(); return; }
    if (!open) return;
    const searching = event.target === inputRef.current;
    if (searching && ['Home', 'End', ' '].includes(event.key)) return;
    if (['ArrowDown', 'ArrowUp', 'Home', 'End', 'Enter', ' '].includes(event.key)) {
      event.preventDefault(); event.stopPropagation();
      if (event.key === 'ArrowDown') setActiveIndex(Math.min(active + 1, filtered.length - 1));
      if (event.key === 'ArrowUp') setActiveIndex(Math.max(active - 1, 0));
      if (event.key === 'Home') setActiveIndex(0);
      if (event.key === 'End') setActiveIndex(filtered.length - 1);
      if (['Enter', ' '].includes(event.key) && filtered[active]) choose(filtered[active].value);
    }
  };

  const triggerSize =
    size === 'sm'
      ? 'h-8 text-[12.5px] rounded-[10px] px-2.5 gap-1.5'
      : size === 'pill'
        ? 'h-8 text-[13.5px] rounded-full pl-4 pr-8 font-medium'
        : 'min-h-[42px] text-[14px] rounded-[14px] px-3.5 gap-2';

  const control = (
    <div ref={rootRef} className={cn('relative min-w-0', className)} onClick={stopPropagation ? event => event.stopPropagation() : undefined}>
      <div className="flex items-center gap-1">
      <button
        ref={triggerRef}
        id={`${id}-trigger`}
        role="combobox"
        aria-label={label || selected?.label || (value === '' && emptyLabel) || placeholder}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={`${id}-list`}
        aria-activedescendant={open && filtered[active] ? `${id}-option-${active}` : undefined}
        type="button"
        disabled={disabled}
        onKeyDown={keys}
        onClick={() => open ? setOpen(false) : show()}
        title={selected?.label || placeholder}
        className={cn(
          'tf-select-trigger flex min-w-0 w-full items-center border border-[var(--color-border)] bg-[var(--color-input-bg)] text-[var(--color-text)] text-left transition',
          'hover:border-[var(--color-border-strong)] focus:outline-none focus:ring-4 focus:ring-[var(--color-ring)]',
          'disabled:cursor-not-allowed disabled:opacity-60',
          triggerSize,
          !selected && 'text-[var(--color-muted)]',
        )}
      >
        {selected?.color && <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: selected.color }} />}
        <span className="min-w-0 flex-1 truncate font-medium">{selected?.label || (value === '' && emptyLabel) || placeholder}</span>
        <ChevronDown size={14} className={cn('shrink-0 text-[var(--color-muted)] transition-transform', open && 'rotate-180')} />
      </button>
      {clearable && value && <button type="button" disabled={disabled} aria-label={`Очистить ${label || placeholder}`} title="Очистить"
        className="tf-button h-8 w-8 shrink-0 px-0" onClick={() => choose('')}><X size={14} /></button>}
      </div>

      {open && createPortal(
        <div ref={menuRef} style={menuStyle} onKeyDown={keys} className="tf-floating-menu z-[1000] rounded-2xl border border-[var(--color-border-strong)] bg-[var(--color-surface)] text-[var(--color-text)] shadow-[var(--shadow-panel)]">
          {searchPlaceholder && (
            <div className="relative shrink-0 border-b border-[var(--color-border)] p-2">
              <Search size={14} className="pointer-events-none absolute left-4 top-[21px] text-[var(--color-muted)]" />
              <input
                ref={inputRef}
                role="combobox"
                aria-label={searchPlaceholder}
                aria-expanded={open}
                aria-controls={`${id}-list`}
                aria-activedescendant={filtered[active] ? `${id}-option-${active}` : undefined}
                autoComplete="off"
                value={query}
                onChange={event => { setQuery(event.target.value); setActiveIndex(0); }}
                className="tf-input tf-input-icon"
                placeholder={searchPlaceholder}
              />
            </div>
          )}
          <div id={`${id}-list`} role="listbox" aria-label={label || placeholder} className="tf-menu-options p-1.5">
            {filtered.map((option, index) => {
              const selectedOption = option.value === value;
              return (
                <button
                  key={option.value}
                  id={`${id}-option-${index}`}
                  data-option-index={index}
                  role="option"
                  aria-selected={selectedOption}
                  tabIndex={-1}
                  type="button"
                  onClick={() => choose(option.value)}
                  title={option.label}
                  className={cn(
                    'flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-sm transition',
                    index === active ? 'bg-[var(--color-overlay-strong)]' : 'hover:bg-[var(--color-overlay)]',
                  )}
                >
                  {option.color && <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: option.color }} />}
                  <span className="min-w-0 flex-1">
                    <span className={cn('block break-words', selectedOption ? 'font-semibold' : 'font-medium')}>{option.label}</span>
                    {option.hint && <span className="block break-words text-xs text-[var(--color-muted)]">{option.hint}</span>}
                  </span>
                  {selectedOption && <Check size={14} className="shrink-0 text-[var(--color-text)]" />}
                </button>
              );
            })}
            {!filtered.length && <div className="px-3 py-6 text-center text-sm text-[var(--color-text-secondary)]">Ничего не найдено</div>}
          </div>
        </div>,
        document.body,
      )}
    </div>
  );

  if (!label) return control;
  return (
    <div className="tf-select-labeled flex min-w-0 items-center gap-2 text-[var(--color-text-secondary)]">
      <label htmlFor={`${id}-trigger`} className="shrink-0 text-[14px]">{label}</label>
      {control}
    </div>
  );
}
