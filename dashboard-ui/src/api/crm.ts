import { request } from './client';
export type Stage = { id: string; label: string; outcome: 'open' | 'won' | 'lost' };
export type Pipeline = { id: number; name: string; stages: Stage[] };
export type Contact = { id: number; name: string; client_id: number | null; email: string; phone: string; position: string };
export type Deal = { id: number; title: string; pipeline_id: number; stage: string; amount: string; currency: string; client_id: number | null; contact_id: number | null; contract_id: number | null; task_id: number | null; assignee_id: number | null; custom_fields: Record<string, string | number | boolean>; notes: string; archived: boolean };
export type Activity = { id: number; deal_id: number; title: string; kind: string; due_at: string | null; completed: boolean };
export type CrmField = { id: number; key: string; label: string; kind: 'text' | 'number' | 'date' | 'checkbox'; required: boolean; position: number };
export type LinkedTask = { id: number; title: string; status: string; contract_id: number | null; deadline: string | null };
export const crm = {
  tasks: (id: number) => request<LinkedTask[]>(`/api/crm/deals/${id}/tasks`),
  createTask: (id: number, data: unknown) => request<LinkedTask>(`/api/crm/deals/${id}/tasks`, { method: 'POST', body: JSON.stringify(data) }),
  list: <T>(kind: string, query = '') => request<T[]>(`/api/crm/${kind}${query ? `?${query}` : ''}`),
  create: <T>(kind: string, data: unknown) => request<T>(`/api/crm/${kind}`, { method: 'POST', body: JSON.stringify(data) }),
  update: <T>(kind: string, id: number, data: unknown) => request<T>(`/api/crm/${kind}/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  remove: (kind: string, id: number, permanent = false) => request(`/api/crm/${kind}/${id}?permanent=${permanent}`, { method: 'DELETE' }),
  restore: (kind: string, id: number) => request(`/api/crm/${kind}/${id}/restore`, { method: 'POST' }),
  renew: (id: number, end_date: string) => request<{ task_id: number | null }>(`/api/crm/contracts/${id}/renew`, { method: 'POST', body: JSON.stringify({ end_date, create_task: true }) }),
};
