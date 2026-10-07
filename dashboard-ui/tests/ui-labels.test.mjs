import test from 'node:test';
import assert from 'node:assert/strict';
import { resolveSectionLabel, resolveFieldLabels } from '../src/lib/uiLabels.ts';

test('a section name overrides conflicting legacy page titles', () => {
  const config = { nav: { '/tasks': { label: '  Работа команды  ' } }, titles: { '/tasks': 'Старый заголовок' } };
  assert.equal(resolveSectionLabel(config, '/tasks'), 'Работа команды');
});

test('legacy titles and workspace dictionaries remain readable', () => {
  assert.equal(resolveSectionLabel({ titles: { '/tasks': 'План' } }, '/tasks'), 'План');
  assert.equal(resolveSectionLabel({}, '/clients', 'Учебные проекты'), 'Учебные проекты');
  assert.equal(resolveSectionLabel({ nav: { '/clients': { label: 'Заказчики' } } }, '/clients', 'Организации'), 'Заказчики');
  assert.equal(resolveSectionLabel({ nav: { '/tasks': { label: '   ' } } }, '/tasks'), 'Задачи');
});

test('field names and section names stay scoped to their workspace', () => {
  const defaults = { deadline: 'Крайний срок', assignee: 'Исполнитель' };
  assert.deepEqual(resolveFieldLabels(defaults, { deadline: { label: 'Сдать до' } }), { deadline: 'Сдать до', assignee: 'Исполнитель' });
  assert.deepEqual(resolveFieldLabels(defaults, {}), defaults);
  assert.equal(resolveSectionLabel({ nav: { '/tasks': { label: 'Уроки' } } }, '/tasks'), 'Уроки');
  assert.equal(resolveSectionLabel({}, '/tasks'), 'Задачи');
});
