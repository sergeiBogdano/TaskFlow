import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { Bold, CheckSquare, Code2, Eye, Heading2, Italic, Link2, List, ListOrdered, Quote, Redo2, Undo2 } from 'lucide-react';
import { EditorButton, EditorFrame } from './EditorFrame';
import { editMarkdown, MAX_EDITOR_TEXT, type TextCommand } from '../lib/editorText';
import { markdownHtml } from '../lib/editorHtml';

type Props = { value: string; onChange: (value: string) => void; readOnly?: boolean; format?: 'text' | 'markdown' | 'code'; placeholder?: string; minHeightClassName?: string; label?: string; maxLength?: number; autoFocus?: boolean; onKeyDown?: (event: KeyboardEvent<HTMLTextAreaElement>) => void };
export function TextEditor({ value, onChange, readOnly = false, format = 'text', placeholder = 'Начните писать…', minHeightClassName = 'min-h-28', label = 'Редактор текста', maxLength = MAX_EDITOR_TEXT, autoFocus, onKeyDown }: Props) {
  const [preview, setPreview] = useState(false);
  const [error, setError] = useState('');
  const [historyState, setHistoryState] = useState({ canUndo: false, canRedo: false });
  const input = useRef<HTMLTextAreaElement>(null);
  const history = useRef([value]);
  const position = useRef(0);
  const last = useRef(value);
  const refreshHistory = () => setHistoryState({ canUndo: position.current > 0, canRedo: position.current < history.current.length - 1 });
  useEffect(() => {
    if (last.current !== value) { history.current = [value]; position.current = 0; last.current = value; setHistoryState({ canUndo: false, canRedo: false }); }
  }, [value]);
  const change = (next: string) => {
    if (next.length > maxLength) { setError(`Максимум ${maxLength.toLocaleString('ru-RU')} символов.`); return; }
    if (next === value) return;
    history.current = [...history.current.slice(0, position.current + 1), next].slice(-100);
    position.current = history.current.length - 1; last.current = next; setError(''); onChange(next); refreshHistory();
  };
  const undo = (direction: number) => {
    const next = position.current + direction;
    if (readOnly || preview || next < 0 || next >= history.current.length) return;
    position.current = next; last.current = history.current[next]; onChange(last.current); setError(''); refreshHistory(); input.current?.focus();
  };
  const command = (name: TextCommand) => {
    if (!input.current || readOnly || preview) return;
    const next = editMarkdown(value, input.current.selectionStart, input.current.selectionEnd, name);
    change(next.value);
    requestAnimationFrame(() => { input.current?.focus(); input.current?.setSelectionRange(next.selectionStart, next.selectionEnd); });
  };
  const controls: [TextCommand, string, React.ReactNode][] = [
    ['bold', 'Жирный (Ctrl+B)', <Bold size={16} />], ['italic', 'Курсив (Ctrl+I)', <Italic size={16} />], ['heading', 'Заголовок', <Heading2 size={16} />], ['bullet', 'Маркированный список', <List size={16} />], ['ordered', 'Нумерованный список', <ListOrdered size={16} />], ['check', 'Чек-лист', <CheckSquare size={16} />], ['quote', 'Цитата', <Quote size={16} />], ['code', 'Код в строке', <Code2 size={16} />], ['link', 'Ссылка', <Link2 size={16} />],
  ];
  return <EditorFrame label={label} readOnly={readOnly} error={error} footer={<span>{value.length.toLocaleString('ru-RU')} / {maxLength.toLocaleString('ru-RU')} символов · {format === 'markdown' ? 'Markdown · [[Название]] — связь с заметкой' : format === 'code' ? 'Код · Tab — отступ' : 'Обычный текст'}</span>} toolbar={<>
    {!readOnly && <>
      {format === 'markdown' && controls.map(([name, title, icon]) => <EditorButton key={name} title={title} disabled={preview} onClick={() => command(name)}>{icon}</EditorButton>)}
      <EditorButton title="Отменить (Ctrl+Z)" disabled={preview || !historyState.canUndo} onClick={() => undo(-1)}><Undo2 size={16} /></EditorButton>
      <EditorButton title="Повторить (Ctrl+Shift+Z)" disabled={preview || !historyState.canRedo} onClick={() => undo(1)}><Redo2 size={16} /></EditorButton>
      <EditorButton title={preview ? 'Вернуться к редактированию' : 'Предпросмотр'} active={preview} onClick={() => setPreview(!preview)}><Eye size={16} /></EditorButton>
    </>}
  </>}>
    {(preview || readOnly) ? (format === 'markdown' ? <div className={`tf-editor-document ${minHeightClassName}`} dangerouslySetInnerHTML={{ __html: markdownHtml(value) }} onClick={event => { const anchor = (event.target as HTMLElement).closest('a'); if (anchor) { event.preventDefault(); window.open(anchor.href, '_blank', 'noopener,noreferrer'); } }} /> : <pre className={`tf-editor-plain whitespace-pre-wrap break-words ${minHeightClassName} ${format === 'code' ? 'font-mono' : ''}`}>{value || 'Нет текста'}</pre>) : <textarea ref={input} autoFocus={autoFocus} aria-label={label} className={`tf-editor-plain w-full resize-y ${minHeightClassName} ${format !== 'text' ? 'font-mono' : ''}`} value={value} maxLength={maxLength} placeholder={placeholder} spellCheck={format !== 'code'} onChange={event => change(event.target.value)} onKeyDown={event => {
      onKeyDown?.(event); if (event.defaultPrevented) return;
      const key = event.key.toLowerCase();
      if ((event.ctrlKey || event.metaKey) && ['z', 'y'].includes(key)) { event.preventDefault(); undo(key === 'y' || event.shiftKey ? 1 : -1); }
      if ((event.ctrlKey || event.metaKey) && format === 'markdown' && ['b', 'i'].includes(key)) { event.preventDefault(); command(key === 'b' ? 'bold' : 'italic'); }
      if (event.key === 'Tab' && format === 'code' && !event.shiftKey) {
        event.preventDefault(); const start = event.currentTarget.selectionStart; const end = event.currentTarget.selectionEnd;
        change(value.slice(0, start) + '  ' + value.slice(end)); requestAnimationFrame(() => input.current?.setSelectionRange(start + 2, start + 2));
      }
    }} />}
  </EditorFrame>;
}
