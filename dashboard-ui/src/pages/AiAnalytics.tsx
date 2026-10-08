import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bot, Copy, FilePlus2, Mic, Plus, Send, Square, Trash2 } from 'lucide-react';
import { assistant, queueLabel, type AssistantJob } from '../api/assistant';
import { TextEditor } from '../components/TextEditor';
import { useAuth } from '../hooks/useAuth';
import { useAssistantVoice } from '../hooks/useAssistantVoice';
import { getActiveWorkspaceId } from '../lib/workspace';
import { cn } from '../lib/taskflow';
import { sectionLabel } from '../lib/uiconfig';

export function AiAnalytics() {
  const { user } = useAuth(); const navigate = useNavigate();
  const [jobs, setJobs] = useState<AssistantJob[]>([]);
  const [otherActive, setOtherActive] = useState<AssistantJob | null>(null);
  const [conversation, setConversation] = useState<string>();
  const [text, setText] = useState(''); const [kind, setKind] = useState('chat');
  const [error, setError] = useState(''); const [sending, setSending] = useState(false);
  const [copyStatus, setCopyStatus] = useState(''); const mounted = useRef(true);
  const voice = useAssistantVoice(spoken => setText(prev => [prev, spoken].filter(Boolean).join(' ').slice(0, 6000)));
  const active = jobs.find(job => job.status === 'queued' || job.status === 'running') || otherActive;
  const canDraft = user?.features?.tasks !== false && Boolean(user?.is_root || user?.permissions?.all || user?.permissions?.tasks_create);
  const refresh = useCallback(async () => {
    try { const [result, pending] = await Promise.all([assistant.history(), assistant.active()]); if (mounted.current) { setJobs(result.filter(job => job.message)); setOtherActive(pending && !result.some(job => job.id === pending.id) ? pending : null); } }
    catch (err) { if (mounted.current) setError(err instanceof Error ? err.message : 'Не удалось загрузить диалоги'); }
  }, []);
  useEffect(() => { mounted.current = true; void refresh(); return () => { mounted.current = false; }; }, [refresh]);
  useEffect(() => {
    if (!active) return;
    let waiting = false;
    const timer = setInterval(async () => {
      if (waiting) return; waiting = true;
      try {
        if (otherActive?.id === active.id) { const pending = await assistant.active(); if (mounted.current) setOtherActive(pending); }
        else { const job = await assistant.status(active.id, active.workspace_id); if (mounted.current) setJobs(prev => prev.map(item => item.id === job.id ? job : item)); }
      }
      catch (err) { if (mounted.current) setError(String(err)); }
      finally { waiting = false; }
    }, 2000);
    return () => clearInterval(timer);
  }, [active?.id, otherActive?.id]);
  const send = async (event: FormEvent) => {
    event.preventDefault(); if (!text.trim() || active || sending) return;
    setSending(true); setError('');
    try { const job = await assistant.submit(text.trim(), kind, conversation || undefined); if (!mounted.current) return; setJobs(prev => [...prev, job]); setConversation(job.conversation_id); setText(''); }
    catch (err) { if (mounted.current) setError(err instanceof Error ? err.message : 'Не удалось отправить запрос'); }
    finally { if (mounted.current) setSending(false); }
  };
  const cancel = async () => { if (!active) return; try { await assistant.cancel(active.id, active.workspace_id); await refresh(); } catch (err) { setError(String(err)); } };
  const conversations = [...new Set(jobs.map(job => job.conversation_id))].reverse();
  const selected = conversation === '' ? '' : conversation || conversations[0];
  const visible = jobs.filter(job => job.conversation_id === selected);
  const openDraft = (job: AssistantJob) => { if (job.result?.draft && canDraft) navigate('/tasks', { state: { assistantDraft: job.result.draft, workspace: getActiveWorkspaceId(), userId: user?.id } }); };
  return <div className="mx-auto max-w-6xl space-y-5">
    <header><h2 className="tf-page-title flex items-center gap-2"><Bot />{sectionLabel('/ai')}</h2><p className="tf-page-subtitle">Обсуждайте работу и учёбу, готовьте отчёты и черновики. Проверяйте важные сведения в ответах.</p></header>
    <div className="tf-panel-flat p-4 text-sm leading-6">Помощник видит ограниченную выборку доступных вам задач и заметок выбранного пространства. Он не сохраняет задачи, не меняет настройки и не выполняет команды на сервере. История хранится 30 дней.</div>
    <div className="grid gap-4 md:grid-cols-[220px_minmax(0,1fr)]">
      <aside className="tf-panel-flat space-y-2 p-3">
        <button className="tf-button w-full" onClick={() => { setConversation(''); setText(''); setKind('chat'); }}><Plus size={16} />Новый диалог</button>
        <div className="max-h-96 space-y-1 overflow-auto">{conversations.map(id => <button key={id} onClick={() => setConversation(id)} className={cn('w-full rounded-lg p-2 text-left text-sm', selected === id && 'bg-[var(--color-surface-3)]')}><span className="line-clamp-2">{jobs.find(job => job.conversation_id === id)?.message}</span></button>)}</div>
        <button className="tf-button w-full text-[var(--color-danger)]" disabled={Boolean(active)} onClick={async () => { if (!confirm('Удалить текст своих диалогов в этом пространстве? Статистика использования останется.')) return; try { await assistant.clear(); setJobs([]); setConversation(''); } catch (err) { setError(String(err)); } }}><Trash2 size={15} />Очистить историю</button>
      </aside>
      <section className="tf-panel-flat min-w-0 space-y-4 p-4 sm:p-5">
        <div role="log" aria-label="Диалог с помощником" className="max-h-[55vh] min-h-48 space-y-4 overflow-auto">
          {!visible.length && <div className="py-8 text-center text-[var(--color-muted)]">Задайте вопрос или опишите задачу. Голосовой ввод сначала добавляет текст — вы проверяете его и отправляете сами.</div>}
          {visible.map(job => <div key={job.id} className="space-y-2">
            <div className="ml-auto max-w-[90%] whitespace-pre-wrap break-words rounded-xl bg-[var(--color-accent)] p-3 text-sm text-white">{job.message}</div>
            <div className="rounded-xl bg-[var(--color-surface-2)] p-3 text-sm leading-6">
              {job.result ? <><div className="whitespace-pre-wrap break-words">{job.result.draft ? `${job.result.draft.title}\n\n${job.result.draft.notes}` : job.result.answer}</div><div className="mt-3 flex flex-wrap gap-2"><button className="tf-button" onClick={async () => { try { await navigator.clipboard.writeText(job.result!.draft ? `${job.result!.draft.title}\n${job.result!.draft.notes}` : job.result!.answer); setCopyStatus('Скопировано'); } catch { setCopyStatus('Выделите текст и скопируйте вручную.'); } }}><Copy size={14} />Копировать</button>{job.result.draft && canDraft && <button className="tf-button" onClick={() => openDraft(job)}><FilePlus2 size={14} />Открыть черновик задачи</button>}</div></> : <span>{queueLabel(job)}</span>}
            </div>
          </div>)}
        </div>
        {active && <div role="status" className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[var(--color-border)] p-3 text-sm"><span>{otherActive ? `Ваш запрос в пространстве №${active.workspace_id}. ` : ''}{queueLabel(active)}</span><button className="tf-button" disabled={active.cancel_requested} onClick={() => void cancel()}><Square size={14} />Отменить запрос</button></div>}
        <form onSubmit={send} className="space-y-3">
          <label className="flex flex-wrap items-center gap-2 text-sm">Режим<select className="tf-input max-w-xs" value={kind} disabled={Boolean(active)} onChange={event => setKind(event.target.value)}><option value="chat">Диалог и вопросы</option><option value="report">Подготовить отчёт</option>{canDraft && <option value="task">Черновик задачи</option>}<option value="polish">Улучшить текст</option></select></label>
          <TextEditor value={text} onChange={setText} maxLength={6000} label="Запрос помощнику" placeholder="Чем помочь? Опишите вопрос, задачу или нужный отчёт…" minHeightClassName="min-h-28" />
          <div className="flex flex-wrap gap-2"><button type="button" className="tf-button" onClick={voice.toggle}><Mic size={16} />{voice.listening ? 'Остановить запись' : 'Голосовой ввод'}</button><button className="tf-button tf-button-primary" disabled={Boolean(active) || sending || !text.trim()}><Send size={16} />{sending ? 'Отправляю…' : 'Отправить'}</button></div>
          <p className="text-xs text-[var(--color-muted)]">Речь распознаёт браузер; он может использовать свой внешний сервис. Доступность зависит от браузера и HTTPS.</p>
        </form>
        {(error || voice.error) && <p role="alert" className="text-sm text-[var(--color-danger)]">{error || voice.error}</p>}
        {copyStatus && <p role="status" className="text-xs">{copyStatus}</p>}
      </section>
    </div>
  </div>;
}
