export type FieldMode = 'hidden' | 'view' | 'edit';
export type FieldAccess = Record<string, Record<string, FieldMode>>;
export const FIELD_ALIASES: Record<string, Record<string, string[]>> = {
  tasks: { title: ['title'], status: ['status'], priority: ['priority'], taskType: ['task_type'],
    client: ['client_id'], assignee: ['assignee_id'], coExecutors: ['co_executor_id', 'co_executor_ids'],
    completionDate: ['completion_date'], deadline: ['deadline'], visibility: ['visibility'],
    noContract: ['no_contract'], notes: ['notes'], comment: ['comment'], sprint: ['sprint_id', 'sprint_ids'] },
  sprints: { name: ['name'], goal: ['goal'], start: ['start_date'], end: ['end_date'] },
};

export function writableFields<T extends Record<string, unknown>>(entity: string, data: T, access: FieldAccess): Partial<T> {
  const result = { ...data };
  for (const [key, aliases] of Object.entries(FIELD_ALIASES[entity] || {})) {
    if (access[entity]?.[key] && access[entity][key] !== 'edit') {
      for (const alias of aliases) delete result[alias];
    }
  }
  return result;
}

export function currentFieldAccess(): FieldAccess {
  try { return JSON.parse(localStorage.getItem('taskflow:workspace-detail') || '{}').field_access || {}; }
  catch { return {}; }
}
