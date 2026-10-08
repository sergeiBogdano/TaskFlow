import { useEditor, EditorContent } from '@tiptap/react';
import { Extension } from '@tiptap/core';
import { Plugin } from '@tiptap/pm/state';
import { DOMSerializer } from '@tiptap/pm/model';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import { TaskList, TaskItem } from '@tiptap/extension-list';
import { TableKit } from '@tiptap/extension-table';
import { Bold, CheckSquare, Code2, Eraser, Eye, Heading2, Italic, Link2, List, ListOrdered, Loader2, Mic, Minus, Pilcrow, Quote, Redo2, SquareCode, Strikethrough, Table2, Underline, Undo2, Unlink, Wand2 } from 'lucide-react';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { runAssistant, queueLabel, type AssistantJob } from '../api/assistant';
import { useAuth } from '../hooks/useAuth';
import { EditorButton, EditorFrame } from './EditorFrame';
import { MAX_EDITOR_HTML, safeEditorLink } from '../lib/editorText';
import { richInputHtml } from '../lib/editorHtml';

type Props = { readOnly?: boolean; value: string; onChange: (value: string) => void; minHeightClassName?: string; placeholder?: string; label?: string };

export function RichTextEditor({ readOnly = false, value, onChange, minHeightClassName = 'min-h-28', placeholder = 'Начните писать…', label = 'Редактор текста' }: Props) {
  const { user } = useAuth();
  const aiEnabled = user?.features?.ai !== false && Boolean(user?.is_root || user?.permissions?.ai);
  const [preview, setPreview] = useState(false);
  const [listening, setListening] = useState(false);
  const [polishing, setPolishing] = useState(false);
  const [aiJob, setAiJob] = useState<AssistantJob>();
  const aiAbort = useRef<AbortController | null>(null);
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkUrl, setLinkUrl] = useState('');
  const [error, setError] = useState('');
  const lastEmitted = useRef(value);
  const change = useRef(onChange);
  const current = useRef({ value, readOnly, preview });
  useEffect(() => { change.current = onChange; current.current = { value, readOnly, preview }; }, [onChange, value, readOnly, preview]);
  const mounted = useRef(true);
  const recognitionRef = useRef<any>(null);
  const editor = useEditor({
    extensions: [
      StarterKit.configure({ heading: { levels: [1, 2, 3] }, link: { openOnClick: false, protocols: ['http', 'https', 'mailto'] } }),
      Placeholder.configure({ placeholder }), TaskList,
      TaskItem.configure({ nested: true, HTMLAttributes: { 'data-type': 'taskItem' }, a11y: { checkboxLabel: node => `Выполнено: ${node.textContent || 'пункт списка'}` } }),
      TableKit.configure({ table: { resizable: false } }),
      Extension.create({ name: 'textLimits', addProseMirrorPlugins() {
        return [new Plugin({ filterTransaction: (transaction, state) => {
          if (!transaction.docChanged) return true;
          const container = document.createElement('div');
          container.append(DOMSerializer.fromSchema(state.schema).serializeFragment(transaction.doc.content));
          const previous = document.createElement('div');
          previous.append(DOMSerializer.fromSchema(state.schema).serializeFragment(state.doc.content));
          if (container.innerHTML.length > MAX_EDITOR_HTML && container.innerHTML.length > previous.innerHTML.length) {
            setError('Максимум 100 000 символов вместе с форматированием.'); return false;
          }
          setError(''); return true;
        } })];
      } }),
    ],
    content: richInputHtml(value || ''), editable: !readOnly, shouldRerenderOnTransaction: true,
    onUpdate: ({ editor }) => { const html = editor.isEmpty ? '' : editor.getHTML(); lastEmitted.current = html; change.current(html); },
    editorProps: {
      attributes: { role: 'textbox', 'aria-label': label, 'aria-multiline': 'true', class: minHeightClassName },
      transformPastedHTML: richInputHtml,
      handlePaste: (_view, event) => {
        if (event.clipboardData?.files.length) { setError('Добавьте файл через раздел вложений.'); return true; }
        if ((event.clipboardData?.getData('text/plain').length || 0) > MAX_EDITOR_HTML || (event.clipboardData?.getData('text/html').length || 0) > MAX_EDITOR_HTML * 5) { setError('Вставляемый фрагмент слишком большой. Максимум 100 000 символов.'); return true; }
        return false;
      },
    },
  });
  useEffect(() => {
    if (!editor || value === lastEmitted.current) return;
    lastEmitted.current = value; editor.commands.setContent(richInputHtml(value || ''), { emitUpdate: false });
  }, [editor, value]);
  useEffect(() => { editor?.setEditable(!readOnly && !preview && !polishing); }, [editor, readOnly, preview, polishing]);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; recognitionRef.current?.abort(); aiAbort.current?.abort(); }; }, []);
  useEffect(() => { if (readOnly || preview) { recognitionRef.current?.abort(); setLinkOpen(false); } }, [readOnly, preview]);
  if (!editor) return null;
  const disabled = readOnly || preview || polishing;
  const setLink = () => {
    const href = safeEditorLink(linkUrl);
    if (!href) { setError('Введите полный адрес: https://…, http://… или mailto:…'); return; }
    editor.chain().focus().extendMarkRange('link').setLink({ href }).run(); setLinkOpen(false); setError('');
  };
  const voice = () => {
    if (listening) { recognitionRef.current?.stop(); return; }
    const Recognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!Recognition) { setError('Голосовой ввод недоступен в этом браузере.'); return; }
    const recognition = new Recognition(); recognitionRef.current = recognition;
    recognition.lang = 'ru-RU'; recognition.interimResults = false;
    recognition.onstart = () => mounted.current && setListening(true);
    recognition.onend = () => mounted.current && setListening(false);
    recognition.onerror = () => mounted.current && setError('Проверьте разрешение микрофона и защищённое соединение.');
    recognition.onresult = (event: any) => { if (!mounted.current || current.current.readOnly || current.current.preview) return; const text = event.results?.[0]?.[0]?.transcript?.trim(); if (text) editor.chain().focus().insertContent({ type: 'text', text }).run(); };
    try { recognition.start(); } catch { setError('Не удалось включить микрофон.'); }
  };
  const polish = async () => {
    if (editor.isEmpty || polishing) return;
    const snapshot = current.current.value; setPolishing(true); setError('');
    try {
      if (editor.getHTML().length > 6000) { setError('Для ИИ нужен текст до 6 000 символов вместе с форматированием.'); return; }
      const controller = new AbortController(); aiAbort.current = controller;
      const result = await runAssistant(editor.getHTML(), 'polish', job => { if (mounted.current) setAiJob(job); }, controller.signal);
      if (!mounted.current || current.current.readOnly || current.current.value !== snapshot) return;
      editor.commands.setContent(richInputHtml(result.answer || snapshot), { emitUpdate: true });
    } catch (err) { if (mounted.current) setError(err instanceof Error ? err.message : 'Не удалось улучшить текст.'); }
    finally { aiAbort.current = null; if (mounted.current) { setPolishing(false); setAiJob(undefined); } }
  };
  const button = (title: string, icon: ReactNode, action: () => unknown, active = false, extraDisabled = false) => <EditorButton key={title} title={title} active={active} disabled={disabled || extraDisabled} onClick={() => { if (!disabled) action(); }}>{icon}</EditorButton>;
  return <EditorFrame label={label} readOnly={readOnly} error={error} footer={<div>{polishing && <div role="status">{aiJob ? queueLabel(aiJob) : 'Отправляю запрос…'} <button type="button" className="tf-button" onClick={() => aiAbort.current?.abort()}>Отменить ИИ</button></div>}<span>{editor.getText().length.toLocaleString('ru-RU')} символов · Ctrl+Z — отменить · Shift+Enter — новая строка</span></div>} toolbar={<>
    {!readOnly && <>
      {button('Жирный (Ctrl+B)', <Bold size={16} />, () => editor.chain().focus().toggleBold().run(), editor.isActive('bold'))}
      {button('Курсив (Ctrl+I)', <Italic size={16} />, () => editor.chain().focus().toggleItalic().run(), editor.isActive('italic'))}
      {button('Подчёркнутый (Ctrl+U)', <Underline size={16} />, () => editor.chain().focus().toggleUnderline().run(), editor.isActive('underline'))}
      {button('Зачёркнутый', <Strikethrough size={16} />, () => editor.chain().focus().toggleStrike().run(), editor.isActive('strike'))}
      {button('Обычный текст', <Pilcrow size={16} />, () => editor.chain().focus().setParagraph().run(), editor.isActive('paragraph'))}
      {button('Заголовок', <Heading2 size={16} />, () => editor.chain().focus().toggleHeading({ level: 2 }).run(), editor.isActive('heading'))}
      {button('Маркированный список', <List size={16} />, () => editor.chain().focus().toggleBulletList().run(), editor.isActive('bulletList'))}
      {button('Нумерованный список', <ListOrdered size={16} />, () => editor.chain().focus().toggleOrderedList().run(), editor.isActive('orderedList'))}
      {button('Чек-лист', <CheckSquare size={16} />, () => editor.chain().focus().toggleTaskList().run(), editor.isActive('taskList'))}
      {button('Цитата', <Quote size={16} />, () => editor.chain().focus().toggleBlockquote().run(), editor.isActive('blockquote'))}
      {button('Код в строке', <Code2 size={16} />, () => editor.chain().focus().toggleCode().run(), editor.isActive('code'))}
      {button('Блок кода', <SquareCode size={16} />, () => editor.chain().focus().toggleCodeBlock().run(), editor.isActive('codeBlock'))}
      {button('Разделитель', <Minus size={16} />, () => editor.chain().focus().setHorizontalRule().run())}
      {button('Ссылка', <Link2 size={16} />, () => { setLinkUrl(editor.getAttributes('link').href || ''); setLinkOpen(!linkOpen); }, editor.isActive('link'))}
      {button('Убрать ссылку', <Unlink size={16} />, () => editor.chain().focus().unsetLink().run(), false, !editor.isActive('link'))}
      {button('Вставить таблицу', <Table2 size={16} />, () => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run(), false, editor.isActive('table'))}
      {button('Очистить форматирование', <Eraser size={16} />, () => editor.chain().focus().clearNodes().unsetAllMarks().run())}
      {button('Отменить (Ctrl+Z)', <Undo2 size={16} />, () => editor.chain().focus().undo().run(), false, !editor.can().undo())}
      {button('Повторить (Ctrl+Shift+Z)', <Redo2 size={16} />, () => editor.chain().focus().redo().run(), false, !editor.can().redo())}
      {button(listening ? 'Остановить диктовку' : 'Надиктовать текст', <Mic size={16} />, voice, listening)}
      {aiEnabled && button('Улучшить текст ИИ', polishing ? <Loader2 size={16} className="animate-spin" /> : <Wand2 size={16} />, polish, polishing)}
      <EditorButton title={preview ? 'Вернуться к редактированию' : 'Предпросмотр'} active={preview} disabled={polishing} onClick={() => setPreview(!preview)}><Eye size={16} /></EditorButton>
    </>}
  </>}>
    {linkOpen && !disabled && <div className="flex flex-wrap gap-2 border-b border-[var(--color-border)] p-3">
      <input autoFocus aria-label="Адрес ссылки" className="tf-input flex-1" value={linkUrl} placeholder="https://example.com" maxLength={2048} onChange={event => setLinkUrl(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); setLink(); } if (event.key === 'Escape') { event.stopPropagation(); setLinkOpen(false); } }} />
      <button type="button" className="tf-button tf-button-primary" onClick={setLink}>Применить</button><button type="button" className="tf-button" onClick={() => setLinkOpen(false)}>Отмена</button>
    </div>}
    {editor.isActive('table') && !disabled && <div className="flex flex-wrap gap-2 border-b border-[var(--color-border)] p-2 text-xs">
      <button type="button" className="tf-button" onClick={() => editor.chain().focus().addRowAfter().run()}>+ Строка</button><button type="button" className="tf-button" onClick={() => editor.chain().focus().addColumnAfter().run()}>+ Столбец</button>
      <button type="button" className="tf-button" onClick={() => editor.chain().focus().deleteRow().run()}>Удалить строку</button><button type="button" className="tf-button" onClick={() => editor.chain().focus().deleteColumn().run()}>Удалить столбец</button><button type="button" className="tf-button" onClick={() => editor.chain().focus().deleteTable().run()}>Удалить таблицу</button>
    </div>}
    <EditorContent editor={editor} className={`tf-editor-document ${minHeightClassName}`} onClick={event => { const anchor = (event.target as HTMLElement).closest('a'); if (anchor) { event.preventDefault(); if (disabled) { const href = safeEditorLink(anchor.href); if (href) window.open(href, '_blank', 'noopener,noreferrer'); } } }} />
  </EditorFrame>;
}
