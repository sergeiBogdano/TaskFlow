import DOMPurify from 'dompurify';
import { marked } from 'marked';
import TurndownService from 'turndown';
import { plainTextHtml } from './editorText.ts';

export function sanitizeEditorHtml(value: string): string {
  return DOMPurify.sanitize(value, {
    ALLOWED_TAGS: ['p', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'strike', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'blockquote', 'pre', 'code', 'hr', 'a', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'colgroup', 'col'],
    ALLOWED_ATTR: ['href', 'title', 'colspan', 'rowspan', 'colwidth', 'start', 'data-type', 'data-checked'],
    ALLOW_DATA_ATTR: false,
  });
}

export function markdownHtml(value: string): string {
  const doc = new DOMParser().parseFromString(marked.parse(value, { async: false, breaks: true }) as string, 'text/html');
  doc.querySelectorAll('input[type="checkbox"]').forEach(node => {
    const item = node.closest('li');
    if (item) { item.setAttribute('data-type', 'taskItem'); item.setAttribute('data-checked', String(node.hasAttribute('checked'))); item.parentElement?.setAttribute('data-type', 'taskList'); }
    node.remove();
  });
  return sanitizeEditorHtml(doc.body.innerHTML);
}

export function htmlText(value: string): string {
  const doc = new DOMParser().parseFromString(sanitizeEditorHtml(value), 'text/html');
  Array.from(doc.body.childNodes).forEach(node => { if (node.nodeType === 3 && !node.textContent?.trim()) node.remove(); });
  doc.querySelectorAll('p').forEach(node => { if (node.childNodes.length === 1 && node.firstElementChild?.tagName === 'BR') node.firstElementChild.remove(); });
  doc.querySelectorAll('br').forEach(node => node.replaceWith('\n'));
  doc.querySelectorAll('p,h1,h2,h3,li,blockquote,pre,tr').forEach(node => node.append('\n'));
  return (doc.body.textContent || '').replace(/\n$/, '');
}

export function richInputHtml(value: string): string {
  return /<\/?[a-z][^>]*>/i.test(value) ? sanitizeEditorHtml(value) : plainTextHtml(value);
}

export function convertNoteFormat(value: string, from: string, to: string): string {
  if (from === to) return value;
  if (to === 'html') return from === 'markdown' ? markdownHtml(value) : plainTextHtml(value);
  if (from === 'html') {
    if (to !== 'markdown') return htmlText(value);
    const converter = new TurndownService({ headingStyle: 'atx', codeBlockStyle: 'fenced' });
    converter.addRule('checklist', { filter: node => node.nodeName === 'LI' && node.getAttribute('data-type') === 'taskItem', replacement: (content, node) => `\n- [${(node as HTMLElement).getAttribute('data-checked') === 'true' ? 'x' : ' '}] ${content.trim()}\n` });
    return converter.turndown(sanitizeEditorHtml(value));
  }
  if (from === 'markdown' && to === 'text') return htmlText(markdownHtml(value));
  return value;
}
