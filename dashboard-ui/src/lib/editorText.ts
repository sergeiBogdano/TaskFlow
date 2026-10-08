export const MAX_EDITOR_HTML = 100_000;
export const MAX_EDITOR_TEXT = 100_000;

export function escapeText(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

export function plainTextHtml(text: string): string {
  return text ? text.split(/\r?\n/).map(line => `<p>${escapeText(line) || '<br>'}</p>`).join('') : '';
}

export function safeEditorLink(value: string): string | null {
  const url = value.trim();
  if (!/^(https?:\/\/|mailto:)/i.test(url) || /\s/.test(url) || Array.from(url).some(char => char.charCodeAt(0) < 32)) return null;
  try {
    const parsed = new URL(url);
    return ['http:', 'https:', 'mailto:'].includes(parsed.protocol) ? url : null;
  } catch { return null; }
}

export type TextCommand = 'bold' | 'italic' | 'heading' | 'bullet' | 'ordered' | 'check' | 'quote' | 'code' | 'link';
export function editMarkdown(value: string, start: number, end: number, command: TextCommand) {
  const selected = value.slice(start, end);
  const wrappers: Partial<Record<TextCommand, [string, string, string]>> = {
    bold: ['**', '**', 'текст'], italic: ['*', '*', 'текст'], code: ['`', '`', 'код'], link: ['[', '](https://example.com)', 'название'],
  };
  let inserted: string;
  let selectionStart: number;
  let selectionEnd: number;
  const wrap = wrappers[command];
  if (wrap) {
    inserted = wrap[0] + (selected || wrap[2]) + wrap[1];
    selectionStart = start + wrap[0].length;
    selectionEnd = selectionStart + (selected || wrap[2]).length;
  } else {
    start = start === 0 ? 0 : value.lastIndexOf('\n', start - 1) + 1;
    const lineEnd = value.indexOf('\n', end);
    end = lineEnd < 0 ? value.length : lineEnd;
    inserted = value.slice(start, end).split('\n').map((line, index) => {
      const prefix = command === 'heading' ? '## ' : command === 'bullet' ? '- ' : command === 'ordered' ? `${index + 1}. ` : command === 'check' ? '- [ ] ' : '> ';
      return prefix + line;
    }).join('\n');
    selectionStart = start;
    selectionEnd = start + inserted.length;
  }
  return { value: value.slice(0, start) + inserted + value.slice(end), selectionStart, selectionEnd };
}
