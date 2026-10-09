import test from 'node:test';
import assert from 'node:assert/strict';
import { accessSections, resolveAccessSelection } from '../src/lib/accessCenter.ts';

test('root has one center for application and workspace controls', () => {
  const sections = accessSections({ is_root: true });
  assert.deepEqual(sections.space.map(tab => tab.id), ['members', 'profiles', 'team', 'tools']);
  assert.deepEqual(sections.app.map(tab => tab.id), ['users', 'roles', 'groups', 'features']);
});
test('ordinary members cannot enter management by a work permission', () => {
  const sections = accessSections({ permissions: { tasks: true, ai: true, workspace_profiles: true } }, 'member');
  assert.deepEqual(sections.space, []); assert.deepEqual(sections.app, []);
});
test('space administrators get only authorized sections and cannot configure application features', () => {
  const sections = accessSections({ permissions: { workspace_members: true, workspace_profiles: true } }, 'admin');
  assert.deepEqual(sections.space.map(tab => tab.id), ['members', 'profiles', 'team']);
  assert.deepEqual(sections.app, []);
  assert.deepEqual(accessSections({ permissions: { workspace_profiles: true }, features: { workspace_profiles: false } }, 'owner').space, []);
});
test('application administrator cannot enter a workspace without its management permissions', () => {
  const sections = accessSections({ permissions: { users_manage: true } }, 'member');
  assert.deepEqual(sections.space, []); assert.deepEqual(sections.app.map(tab => tab.id), ['users']);
  assert.equal(resolveAccessSelection(sections, 'space', 'profiles').tab.id, 'users');
});
test('unauthorized or outdated deep links resolve to an allowed tab', () => {
  const sections = accessSections({ permissions: { workspace_members: true } }, 'owner');
  assert.equal(resolveAccessSelection(sections, 'app', 'features').scope, 'space');
  assert.equal(resolveAccessSelection(sections, 'app', 'features').tab.id, 'team');
  assert.equal(resolveAccessSelection(accessSections(null), 'app', 'features').tab, undefined);
});
