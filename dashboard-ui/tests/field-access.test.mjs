import test from 'node:test';
import assert from 'node:assert/strict';
import { writableFields } from '../src/lib/fieldAccess.ts';

test('forms cannot write hidden or read-only fields, including aliased assignment fields', () => {
  const input = { title: 'Task', deadline: '2026-12-12', assignee_id: 8, co_executor_ids: [9], priority: 'high' };
  const result = writableFields('tasks', input, { tasks: { deadline: 'view', assignee: 'hidden', coExecutors: 'view' } });
  assert.deepEqual(result, { title: 'Task', priority: 'high' });
  assert.equal(input.deadline, '2026-12-12');
});

test('sprint field access is independent of task field access', () => {
  assert.deepEqual(writableFields('sprints', { name: 'Week', goal: 'Goal', start_date: '2026-12-12' },
    { sprints: { goal: 'hidden', start: 'view' } }), { name: 'Week' });
});
