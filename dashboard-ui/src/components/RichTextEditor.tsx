import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import { Bold, Code2, Eraser, Eye, Heading1, Heading2, Italic, List, ListOrdered, Loader2, Mic, Pilcrow, Quote, Redo2, Strikethrough, Undo2, Wand2 } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { api } from '../api/client';

type Props = {
  value: string;
  onChange: (value: string) => void;
  minHeightClassName?: string;
  placeholder?: string;
};

export function RichTextEditor({ value, onChange, minHeightClassName = 'min-h-28', placeholder }: Props) {
  const [listening, setListening] = useState(false);
  const [polishing, setPolishing] = useState(false);
  const [sourceMode, setSourceMode] = useState(false);
  const [sourceValue, setSourceValue] = useState(value || '');
  const [error, setError] = useState('');
  const editor = useEditor({
    extensions: [
      StarterKit,
      Placeholder.configure({ placeholder: placeholder || '' }),
    ],
    content: value || '',
    onUpdate: ({ editor }) => onChange(editor.getHTML()),
  });

  useEffect(() => {
    if (!editor || !editor.schema) return;
    if (editor.getHTML() !== (value || '')) {
      editor.commands.setContent(value || '', { emitUpdate: false });
    }
    setSourceValue(value || '');
  }, [editor, value]);

  if (!editor || !editor.schema) return null;

  const toggleSource = () => {
    if (!sourceMode) setSourceValue(editor.getHTML());
    setSourceMode(previous => !previous);
  };

  const applySource = () => {
    editor.commands.setContent(sourceValue || '', { emitUpdate: true });
    onChange(editor.getHTML());
    setSourceMode(false);
  };

  const startListening = () => {
    const Recognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!Recognition) {
      setError('Браузер не поддерживает голосовой ввод.');
      return;
    }
    setError('');
    const recognition = new Recognition();
    recognition.lang = 'ru-RU';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onstart = () => setListening(true);
    recognition.onerror = () => {
      setListening(false);
      setError('Не удалось распознать голос.');
    };
    recognition.onend = () => setListening(false);
    recognition.onresult = (event: any) => {
      const spoken = event.results?.[0]?.[0]?.transcript || '';
      if (spoken.trim()) editor.chain().focus().insertContent(`<p>${spoken.trim()}</p>`).run();
    };
    recognition.start();
  };

  const polish = async () => {
    const current = sourceMode ? sourceValue : editor.getHTML();
    if (!(sourceMode ? sourceValue : editor.getText()).trim()) return;
    setPolishing(true);
    setError('');
    try {
      const result = await api.polishText(current);
      editor.commands.setContent(result.html || current);
      setSourceValue(result.html || current);
      onChange(result.html || current);
      setSourceMode(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось улучшить текст.');
    } finally {
      setPolishing(false);
    }
  };

  return (
    <div className="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)]">
      <div className="flex flex-wrap items-center gap-1 border-b border-[var(--color-border)] bg-[var(--color-surface)] p-2">
        <ToolbarButton onClick={() => editor.chain().focus().toggleBold().run()} active={editor.isActive('bold')} title="Жирный"><Bold size={15} /></ToolbarButton>
        <ToolbarButton onClick={() => editor.chain().focus().toggleItalic().run()} active={editor.isActive('italic')} title="Курсив"><Italic size={15} /></ToolbarButton>
        <ToolbarButton onClick={() => editor.chain().focus().toggleStrike().run()} active={editor.isActive('strike')} title="Зачеркнутый"><Strikethrough size={15} /></ToolbarButton>
        <ToolbarButton onClick={() => editor.chain().focus().clearNodes().unsetAllMarks().run()} title="Очистить форматирование"><Eraser size={15} /></ToolbarButton>
        <Separator />
        <ToolbarButton onClick={() => editor.chain().focus().setParagraph().run()} active={editor.isActive('paragraph')} title="Обычный текст"><Pilcrow size={15} /></ToolbarButton>
        <ToolbarButton onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()} active={editor.isActive('heading', { level: 1 })} title="Заголовок 1"><Heading1 size={15} /></ToolbarButton>
        <ToolbarButton onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()} active={editor.isActive('heading', { level: 2 })} title="Заголовок 2"><Heading2 size={15} /></ToolbarButton>
        <ToolbarButton onClick={() => editor.chain().focus().toggleBulletList().run()} active={editor.isActive('bulletList')} title="Маркированный список"><List size={15} /></ToolbarButton>
        <ToolbarButton onClick={() => editor.chain().focus().toggleOrderedList().run()} active={editor.isActive('orderedList')} title="Нумерованный список"><ListOrdered size={15} /></ToolbarButton>
        <ToolbarButton onClick={() => editor.chain().focus().toggleBlockquote().run()} active={editor.isActive('blockquote')} title="Цитата"><Quote size={15} /></ToolbarButton>
        <ToolbarButton onClick={() => editor.chain().focus().toggleCodeBlock().run()} active={editor.isActive('codeBlock')} title="Блок кода"><Code2 size={15} /></ToolbarButton>
        <Separator />
        <ToolbarButton onClick={() => editor.chain().focus().undo().run()} title="Отменить"><Undo2 size={15} /></ToolbarButton>
        <ToolbarButton onClick={() => editor.chain().focus().redo().run()} title="Повторить"><Redo2 size={15} /></ToolbarButton>
        <Separator />
        <ToolbarButton onClick={toggleSource} active={sourceMode} title={sourceMode ? 'Визуальный режим' : 'HTML-код'}>{sourceMode ? <Eye size={15} /> : <Code2 size={15} />}</ToolbarButton>
        <ToolbarButton onClick={startListening} active={listening} title={listening ? 'Слушаю...' : 'Надиктовать текст'}><Mic size={15} /></ToolbarButton>
        <ToolbarButton onClick={polish} active={polishing} title="Улучшить текст ИИ">{polishing ? <Loader2 size={15} className="animate-spin" /> : <Wand2 size={15} />}</ToolbarButton>
      </div>
      {sourceMode ? (
        <div>
          <textarea
            className={`w-full resize-y bg-transparent px-3 py-2 font-mono text-sm leading-6 outline-none ${minHeightClassName}`}
            value={sourceValue}
            onChange={event => {
              setSourceValue(event.target.value);
              onChange(event.target.value);
            }}
            spellCheck={false}
          />
          <div className="flex justify-end border-t border-[var(--color-border)] px-3 py-2">
            <button type="button" onClick={applySource} className="tf-button tf-button-primary">Применить HTML</button>
          </div>
        </div>
      ) : (
        <EditorContent
          editor={editor}
          className={`w-full px-3 py-2 text-sm leading-6 [&_.ProseMirror]:outline-none [&_.ProseMirror_blockquote]:border-l-2 [&_.ProseMirror_blockquote]:border-[var(--color-accent)] [&_.ProseMirror_blockquote]:pl-3 [&_.ProseMirror_code]:rounded [&_.ProseMirror_code]:bg-black/20 [&_.ProseMirror_code]:px-1 [&_.ProseMirror_h1]:text-xl [&_.ProseMirror_h1]:font-black [&_.ProseMirror_h2]:text-lg [&_.ProseMirror_h2]:font-bold [&_.ProseMirror_ol]:list-decimal [&_.ProseMirror_ul]:list-disc [&_.ProseMirror_li]:ml-5 [&_.ProseMirror_pre]:overflow-auto [&_.ProseMirror_pre]:rounded-lg [&_.ProseMirror_pre]:bg-black/25 [&_.ProseMirror_pre]:p-3 ${minHeightClassName}`}
        />
      )}
      {error && <div className="border-t border-[var(--color-border)] px-3 py-2 text-xs font-semibold text-[var(--color-danger)]">{error}</div>}
    </div>
  );
}

function Separator() {
  return <div className="mx-1 h-8 w-px bg-[var(--color-border)]" />;
}

function ToolbarButton({ children, onClick, active, title }: { children: ReactNode; onClick: () => void; active?: boolean; title: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-label={title}
      className={`grid h-8 w-8 place-items-center rounded-md border transition-colors ${
        active
          ? 'border-[var(--color-accent)] bg-[var(--color-accent)] text-white'
          : 'border-[var(--color-border)] bg-[var(--color-surface-2)] text-[var(--color-text)] hover:border-[var(--color-border-strong)] hover:bg-[var(--color-surface-3)]'
      }`}
    >
      {children}
    </button>
  );
}
