import test from 'node:test';
import assert from 'node:assert/strict';
import { taskMatchesScope } from '../src/lib/taskScope.ts';

const task = { assignee_id: 2, creator_id: 3, co_executor_id: null, co_executor_ids: [4] };
test('personal scopes include only the specified relationship', () => {
  assert.equal(taskMatchesScope(task, { id: 2 }, 'assigned'), true);
  assert.equal(taskMatchesScope(task, { id: 3 }, 'created'), true);
  assert.equal(taskMatchesScope(task, { id: 4 }, 'coassigned'), true);
  assert.equal(taskMatchesScope(task, { id: 5 }, 'involved'), false);
});
test('selecting a colleague requires team permission', () => {
  assert.equal(taskMatchesScope(task, { id: 5, permissions: {} }, 'user', '2'), false);
  assert.equal(taskMatchesScope(task, { id: 5, permissions: { tasks_view_team: true } }, 'user', '2'), true);
  assert.equal(taskMatchesScope(task, { id: 5, permissions: { tasks_view_team: true } }, 'user', '2,4'), true);
});
test('all-task scope requires explicit visibility permission', () => {
  assert.equal(taskMatchesScope(task, { id: 5, permissions: {} }, 'all'), false);
  assert.equal(taskMatchesScope(task, { id: 5, permissions: { tasks_view_all: true } }, 'all'), true);
  assert.equal(taskMatchesScope(task, null, 'all'), false);
});
