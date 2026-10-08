import test from 'node:test';
import assert from 'node:assert/strict';
import { availableWorkAreas, workAreaForRoute } from '../src/lib/workAreas.ts';
import { linkedNotes, noteLinks } from '../src/lib/noteLinks.ts';

test('administration and workspace management are distinct capabilities', () => {
  assert.deepEqual(availableWorkAreas(null), []);
  assert.deepEqual(availableWorkAreas({ permissions: { tasks: true } }), ['work']);
  assert.deepEqual(availableWorkAreas({ permissions: { workspace_profiles: true } }), ['work', 'manage']);
  assert.deepEqual(availableWorkAreas({ permissions: { users_manage: true } }), ['work', 'admin']);
  assert.deepEqual(availableWorkAreas({ is_root: true }), ['work', 'manage', 'admin']);
  assert.equal(workAreaForRoute('/workspace'), 'manage');
  assert.equal(workAreaForRoute('/users'), 'admin');
  assert.equal(workAreaForRoute('/notes'), 'work');
});

test('note links retain ambiguity and backlink context without inventing targets', () => {
  assert.deepEqual(noteLinks('[[ Math ]] and [[Math|Alias]] and [[Missing]]'), ['Math', 'Missing']);
  const current = { uid: 'a', title: 'Study', content: '[[Math]] [[Missing]]' };
  const result = linkedNotes(current, [current, { uid: 'b', title: 'Math', content: '[[Study]]' }, { uid: 'c', title: 'Math', content: '' }]);
  assert.equal(result.outgoing[0].matches.length, 2);
  assert.equal(result.outgoing[1].matches.length, 0);
  assert.deepEqual(result.incoming.map(note => note.uid), ['b']);
});
