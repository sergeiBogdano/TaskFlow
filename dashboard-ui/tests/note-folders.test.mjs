import test from 'node:test';
import assert from 'node:assert/strict';
import { folderMatches, folderSelection } from '../src/lib/noteFolders.ts';

test('local and server folders with the same id never mix', () => {
  assert.equal(folderMatches('local:12', 'local', '12'), true);
  assert.equal(folderMatches('local:12', 'server', '12'), false);
  assert.equal(folderMatches('server:12', 'server', '12'), true);
  assert.equal(folderMatches('server:12', 'local', '12'), false);
  assert.equal(folderMatches('server:12', 'server', '13'), false);
});

test('all notes and unfiled notes work for both storage locations and trash', () => {
  for (const origin of ['local', 'server']) {
    assert.equal(folderMatches('', origin, '12'), true);
    assert.equal(folderMatches('root', origin, ''), true);
    assert.equal(folderMatches('root', origin, '12'), false);
  }
});

test('selected folder preserves storage and id for new note defaults', () => {
  assert.deepEqual(folderSelection('server:42'), { origin: 'server', id: '42' });
  assert.deepEqual(folderSelection('local:some-uuid'), { origin: 'local', id: 'some-uuid' });
  assert.deepEqual(folderSelection('root'), { origin: null, id: 'root' });
});
