import test from 'node:test';
import assert from 'node:assert/strict';
import { createLocalNote, listLocalNotes, pickNotesDirectory } from '../src/lib/localNotes.ts';

function storage({ abortWrite = false, failRead = false } = {}) {
  const databases = new Map(); let account = 'one'; let requests = 0;
  globalThis.localStorage = { getItem: () => account };
  globalThis.window = {};
  globalThis.fetch = () => { requests++; throw new Error('Local notes must never use HTTP'); };
  globalThis.indexedDB = { open(name) {
    if (!databases.has(name)) databases.set(name, new Map());
    const values = databases.get(name);
    const db = { close() {}, transaction() {
      const tx = { error: new Error('Disk quota'), objectStore() { return {
        get(key) { const req = { result: structuredClone(values.get(key)), error: new Error('Read failed') }; queueMicrotask(() => failRead ? req.onerror?.() : req.onsuccess?.()); return req; },
        put(value, key) {
          const req = {};
          queueMicrotask(() => {
            req.onsuccess?.(); // A request can succeed before its transaction aborts.
            queueMicrotask(() => { if (abortWrite) tx.onabort?.(); else { values.set(key, structuredClone(value)); tx.oncomplete?.(); } });
          }); return req;
        },
        delete(key) { const req = {}; queueMicrotask(() => { values.delete(key); req.onsuccess?.(); }); return req; },
      }; } }; return tx;
    } };
    const req = { result: db }; queueMicrotask(() => req.onsuccess?.()); return req;
  } };
  return { databases, switchAccount(value) { account = value; }, requests: () => requests };
}
const draft = { title: 'Local plan', content: '```sh\nrm -rf /\n```', format: 'markdown', tags: [], folderId: '' };

test('local draft survives reopening, belongs to its account and makes no HTTP writes', async () => {
  const mock = storage();
  await createLocalNote(draft);
  assert.equal((await listLocalNotes()).notes[0].content, draft.content);
  mock.switchAccount('two'); assert.equal((await listLocalNotes()).total, 0);
  mock.switchAccount('one'); assert.equal((await listLocalNotes()).total, 1);
  assert.equal(mock.requests(), 0);
});

test('local save reports a transaction abort instead of falsely confirming success', async () => {
  storage({ abortWrite: true });
  await assert.rejects(createLocalNote(draft), /quota/);
  assert.equal((await listLocalNotes()).total, 0);
});

test('failed folder migration preserves original notes and does not switch storage', async () => {
  const mock = storage(); await createLocalNote(draft);
  window.showDirectoryPicker = async () => ({
    name: 'Selected folder', requestPermission: async () => 'granted',
    getFileHandle: async () => ({ createWritable: async () => { throw new Error('Folder full'); } }),
  });
  await assert.rejects(pickNotesDirectory(), /Folder full/);
  assert.equal((await listLocalNotes()).notes[0].title, draft.title);
  assert.equal(mock.databases.get('taskflow-local-notes-account-one').has('notesDir'), false);
});


test('failed local reads never become an empty notebook that overwrites previous notes', async () => {
  const mock = storage({ failRead: true });
  const original = [{ ...draft, id: 'existing' }];
  mock.databases.set('taskflow-local-notes-account-one', new Map([['notesFallback', original]]));
  await assert.rejects(createLocalNote(draft), /Read failed/);
  assert.deepEqual(mock.databases.get('taskflow-local-notes-account-one').get('notesFallback'), original);
});
