import { request } from './client';

export type AssistantJob = {
  id: string; workspace_id: number; conversation_id: string; kind: string; message: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  position: number; cancel_requested: boolean; error: string | null; created_at: string;
  result: { answer: string; draft?: { title: string; notes: string } } | null;
};
export const assistant = {
  active: () => request<AssistantJob | null>('/api/assistant/active'),
  history: () => request<AssistantJob[]>('/api/assistant/requests'),
  submit: (message: string, kind = 'chat', conversation_id?: string) => request<AssistantJob>('/api/assistant/requests', { method: 'POST', body: JSON.stringify({ message, kind, conversation_id }) }),
  status: (id: string, workspace?: number) => request<AssistantJob>(`/api/assistant/requests/${id}${workspace ? `?workspace_id=${workspace}` : ''}`),
  cancel: (id: string, workspace?: number) => request<AssistantJob>(`/api/assistant/requests/${id}/cancel${workspace ? `?workspace_id=${workspace}` : ''}`, { method: 'POST' }),
  clear: () => request('/api/assistant/history', { method: 'DELETE' }),
};

export async function runAssistant(message: string, kind: string, onStatus?: (job: AssistantJob) => void, signal?: AbortSignal) {
  if (signal?.aborted) throw new Error('Запрос отменён');
  let job = await assistant.submit(message, kind);
  const cancel = () => { void assistant.cancel(job.id, job.workspace_id).catch(() => undefined); };
  signal?.addEventListener('abort', cancel, { once: true });
  try {
    if (signal?.aborted) { cancel(); throw new Error('Запрос отменён'); }
    while (job.status === 'queued' || job.status === 'running') {
      onStatus?.(job);
      await new Promise(resolve => setTimeout(resolve, 1500));
      if (signal?.aborted) throw new Error('Запрос отменён');
      job = await assistant.status(job.id, job.workspace_id);
    }
    onStatus?.(job);
    if (job.status !== 'completed') throw new Error(job.error || (job.status === 'cancelled' ? 'Запрос отменён' : 'Помощник недоступен'));
    return job.result!;
  } finally { signal?.removeEventListener('abort', cancel); }
}

export function queueLabel(job: AssistantJob) {
  if (job.cancel_requested && job.status === 'running') return 'Останавливаю запрос…';
  if (job.status === 'queued') return `Помощник занят. Вы в очереди: ${job.position}`;
  if (job.status === 'running') return 'Помощник готовит ответ…';
  return job.error || ({ completed: 'Готово', failed: 'Ошибка', cancelled: 'Отменено' } as Record<string, string>)[job.status];
}
