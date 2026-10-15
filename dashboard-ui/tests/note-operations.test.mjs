import test from 'node:test';
import assert from 'node:assert/strict';
import { moveNote, runNoteBatch } from '../src/lib/noteOperations.ts';

const note = { id: 1, origin: 'server', is_owner: true, title: 'Research', content: 'old', format: 'markdown', tags: ['study'] };
function fixture(overrides = {}) {
  const calls = [];
  const ports = {
    assertScope() {},
    read: async () => ({ ...note, content: 'latest' }),
    move: async (_note, folder) => { calls.push(['move', folder]); },
    create: async (current, target) => { calls.push(['create', current.content, target]); },
    archive: async () => { calls.push(['archive']); },
    ...overrides,
  };
  return { calls, ports };
}
test('moving inside storage updates only folder, never deletes content', async () => {
  const { calls, ports } = fixture();
  await moveNote(note, { origin: 'server', folderId: '42' }, ports);
  assert.deepEqual(calls, [['move', '42']]);
});
test('cross-storage move reads latest content and commits destination before archiving', async () => {
  for (const origin of ['server', 'local']) {
    const { calls, ports } = fixture();
    await moveNote({ ...note, origin }, { origin: origin === 'local' ? 'server' : 'local', folderId: '' }, ports);
    assert.equal(calls[0][0], 'create'); assert.equal(calls[0][1], 'latest');
    assert.equal(calls[1][0], 'archive');
  }
});
test('destination write failure never removes source', async () => {
  const { calls, ports } = fixture({ create: async () => { throw new Error('Disk full'); } });
  await assert.rejects(moveNote(note, { origin: 'local', folderId: '' }, ports), /Disk full/);
  assert.deepEqual(calls, []);
});
test('source archive failure preserves saved copy and reports original retention', async () => {
  const { calls, ports } = fixture({ archive: async () => { throw new Error('Offline'); } });
  assert.deepEqual(await moveNote(note, { origin: 'local', folderId: '' }, ports), { sourceRetained: true });
  assert.equal(calls[0][0], 'create');
});
test('foreign notes and changed workspace cannot be transferred', async () => {
  const { calls, ports } = fixture();
  await assert.rejects(moveNote({ ...note, is_owner: false }, { origin: 'local', folderId: '' }, ports), /свои/);
  ports.assertScope = () => { throw new Error('Workspace changed'); };
  await assert.rejects(moveNote(note, { origin: 'local', folderId: '' }, ports), /Workspace changed/);
  assert.deepEqual(calls, []);
});
test('scope change after reading blocks copying data to another workspace', async () => {
  let checks = 0;
  const { calls, ports } = fixture({ assertScope() { if (++checks > 1) throw new Error('Changed'); } });
  await assert.rejects(moveNote(note, { origin: 'local', folderId: '' }, ports), /Changed/);
  assert.deepEqual(calls, []);
});
test('batch writes are sequential and partial failures remain available for retry', async () => {
  let active = 0; const order = [];
  const result = await runNoteBatch([1, 2, 3], async id => {
    assert.equal(active++, 0); await new Promise(resolve => setTimeout(resolve, 2)); active--;
    order.push(id); if (id === 2) throw new Error('Forbidden');
  });
  assert.deepEqual(order, [1, 2, 3]); assert.deepEqual(result.completed, [1, 3]);
  assert.deepEqual(result.failed, [{ item: 2, message: 'Forbidden' }]);
});
