import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';

const dom = new JSDOM('');
globalThis.window = dom.window;
globalThis.DOMParser = dom.window.DOMParser;
const { sanitizeEditorHtml, convertNoteFormat, richInputHtml, markdownHtml } = await import('../src/lib/editorHtml.ts');

test('editor preview strips executable HTML and remote images while retaining tables', () => {
  const html = sanitizeEditorHtml('<script>evil()</script><img src="https://outside.example/pixel"><p onclick="evil()">safe <a href="javascript:evil()">link</a></p><table><tr><td>cell</td></tr></table>');
  assert.equal(/script|onclick|javascript:|<img/.test(html), false);
  assert.match(html, /<table>/);
  assert.match(html, /cell/);
  assert.equal(/onerror|<img/.test(markdownHtml('![tracking](https://outside.example/pixel)\n<img src=x onerror=evil()>')), false);
});
test('checklists round-trip between Markdown and document without losing checked state', () => {
  const source = '# Heading\n\n- [x] Done\n- [ ] Todo\n\n**Important**';
  const html = convertNoteFormat(source, 'markdown', 'html');
  assert.match(html, /data-type="taskList"/);
  assert.match(html, /data-checked="true"/);
  assert.match(html, /data-checked="false"/);
  const markdown = convertNoteFormat(html, 'html', 'markdown');
  assert.match(markdown, /- \[x\] Done/);
  assert.match(markdown, /- \[ \] Todo/);
  assert.match(markdown, /\*\*Important\*\*/);
});
test('text/code conversions preserve literal markup and line breaks', () => {
  const source = '<script>example()</script>\nnext & last   \n';
  const html = convertNoteFormat(source, 'code', 'html');
  assert.equal(convertNoteFormat(html, 'html', 'code'), source);
  assert.equal(richInputHtml('first\nsecond'), '<p>first</p><p>second</p>');
  assert.equal(convertNoteFormat('**hello**', 'markdown', 'text'), 'hello');
});
