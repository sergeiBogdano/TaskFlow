import { useState } from 'react';
import { GripVertical } from 'lucide-react';

export function FieldOrderEditor({ labels, order = [], disabled, onChange }: { labels: Record<string, string>; order?: string[]; disabled: boolean; onChange: (order: string[]) => void }) {
  const keys = [...order.filter(k => k in labels), ...Object.keys(labels).filter(k => !order.includes(k))];
  const [dragged, setDragged] = useState<string | null>(null);
  const move = (key: string, to: number) => { const next = keys.filter(k => k !== key); next.splice(to, 0, key); onChange(next); };
  return <div className="rounded-xl border border-[var(--color-border)] p-3"><p className="mb-2 text-xs text-[var(--color-muted)]">Перетащите поля или используйте стрелки. Порядок применяется внутри групп карточки.</p><div className="flex flex-wrap gap-2">{keys.map((key, index) => <div key={key} draggable={!disabled} onDragStart={() => setDragged(key)} onDragOver={e => { if (!disabled) e.preventDefault(); }} onDrop={() => { if (dragged && !disabled) move(dragged, index); setDragged(null); }} className="flex items-center gap-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2 py-1 text-xs"><GripVertical size={12} /><span>{labels[key]}</span><button type="button" aria-label={`Поднять ${labels[key]}`} disabled={disabled || !index} onClick={() => move(key, index - 1)}>↑</button><button type="button" aria-label={`Опустить ${labels[key]}`} disabled={disabled || index === keys.length - 1} onClick={() => move(key, index + 1)}>↓</button></div>)}</div></div>;
}
