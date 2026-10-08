import test from 'node:test';
import assert from 'node:assert/strict';
import { editMarkdown, plainTextHtml, safeEditorLink } from '../src/lib/editorText.ts';

test('text imports preserve lines and escape executable markup', () => {
  assert.equal(plainTextHtml('one\n<script>x</script>\n'), '<p>one</p><p>&lt;script&gt;x&lt;/script&gt;</p><p><br></p>');
});
test('editor links reject active schemes and accept explicit supported URLs', () => {
  for (const url of ['javascript:alert(1)', 'data:text/html,x', 'https://', 'https://example.com\nmalicious', '/relative']) assert.equal(safeEditorLink(url), null);
  assert.equal(safeEditorLink(' https://example.com/a?q=1 '), 'https://example.com/a?q=1');
  assert.equal(safeEditorLink('mailto:friend@example.com'), 'mailto:friend@example.com');
});
test('Markdown formatting preserves surrounding text and selection', () => {
  assert.deepEqual(editMarkdown('before word after', 7, 11, 'bold'), { value: 'before **word** after', selectionStart: 9, selectionEnd: 13 });
  assert.equal(editMarkdown('one\ntwo\nthree', 5, 6, 'check').value, 'one\n- [ ] two\nthree');
  assert.equal(editMarkdown('one\ntwo', 0, 7, 'ordered').value, '1. one\n2. two');
  assert.equal(editMarkdown('\nnext', 0, 0, 'heading').value, '## \nnext');
});
