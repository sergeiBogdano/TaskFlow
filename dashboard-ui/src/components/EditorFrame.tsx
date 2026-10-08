import { Maximize2, Minimize2 } from 'lucide-react';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

export function EditorButton({ children, title, onClick, active = false, disabled = false }: { children: ReactNode; title: string; onClick: () => void; active?: boolean; disabled?: boolean }) {
  return <button type="button" aria-label={title} title={title} aria-pressed={active} disabled={disabled} onClick={onClick} className={`tf-editor-button ${active ? 'is-active' : ''}`}>{children}</button>;
}

export function EditorFrame({ children, toolbar, footer, error, readOnly = false, label = 'Редактор текста' }: { children: ReactNode; toolbar: ReactNode; footer: ReactNode; error?: string; readOnly?: boolean; label?: string }) {
  const [expanded, setExpanded] = useState(false);
  const frame = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!expanded) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    (frame.current?.querySelector<HTMLElement>('[role="textbox"],textarea') || frame.current?.querySelector<HTMLElement>('button'))?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); setExpanded(false); }
      if (event.key === 'Tab') {
        const items = Array.from(frame.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),textarea,[contenteditable="true"],a[href]') || []).filter(item => item.getClientRects().length);
        const first = items[0]; const last = items.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener('keydown', handleKey, true);
    return () => { document.removeEventListener('keydown', handleKey, true); if (previousFocus?.isConnected) previousFocus.focus(); };
  }, [expanded]);
  const view = <div ref={frame} role={expanded ? 'dialog' : 'group'} aria-modal={expanded || undefined} aria-label={label} className={`tf-editor ${expanded ? 'tf-editor-expanded' : ''}`} onClick={event => event.stopPropagation()}>
    <div className="tf-editor-toolbar" role="toolbar" aria-label="Инструменты текста">
      {readOnly && <span className="px-2 text-xs text-[var(--color-muted)]">Только просмотр</span>}{toolbar}
      <span className="flex-1" />
      <EditorButton title={expanded ? 'Свернуть редактор' : 'Развернуть редактор'} active={expanded} onClick={() => setExpanded(!expanded)}>{expanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}</EditorButton>
    </div>
    <div className="tf-editor-body">{children}</div>
    <div className="tf-editor-footer">{footer}</div>
    {error && <div role="alert" className="border-t border-[var(--color-border)] px-3 py-2 text-sm text-[var(--color-danger)]">{error}</div>}
  </div>;
  return expanded ? createPortal(view, document.body) : view;
}
