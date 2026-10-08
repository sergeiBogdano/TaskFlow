import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

async function load(request) {
  const source = (await readFile(new URL('../src/api/assistant.ts', import.meta.url), 'utf8')).replace("import { request } from './client';", 'const request = globalThis.taskflowAssistantRequest;');
  globalThis.taskflowAssistantRequest = request;
  const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(compiled + `\n// ${Math.random()}`).toString('base64')}`);
}
const job = { id: 'job', workspace_id: 9, status: 'queued', position: 2, conversation_id: 'chat' };

test('assistant keeps request scope when active workspace changes', async () => {
  const calls = [];
  const { runAssistant } = await load(async (url, options) => {
    calls.push([url, options?.method]);
    return options?.method === 'POST' ? job : { ...job, status: 'completed', result: { answer: 'Ответ' } };
  });
  assert.deepEqual(await runAssistant('Вопрос', 'chat'), { answer: 'Ответ' });
  assert.deepEqual(calls.map(call => call[0]), ['/api/assistant/requests', '/api/assistant/requests/job?workspace_id=9']);
});

test('aborting pending inference cancels the server job in its original space', async () => {
  const calls = []; const controller = new AbortController();
  const { runAssistant } = await load(async (url, options) => { calls.push(url); return job; });
  await assert.rejects(runAssistant('Вопрос', 'chat', () => controller.abort(), controller.signal), /отменён/);
  assert.equal(calls.filter(url => url.endsWith('/cancel?workspace_id=9')).length, 1);
});

test('already cancelled input never consumes a queue slot', async () => {
  let called = false; const controller = new AbortController(); controller.abort();
  const { runAssistant } = await load(async () => { called = true; return job; });
  await assert.rejects(runAssistant('Вопрос', 'chat', undefined, controller.signal), /отменён/);
  assert.equal(called, false);
});

test('queue labels distinguish waiting, running and stopping', async () => {
  const { queueLabel } = await load(async () => job);
  assert.match(queueLabel(job), /очереди: 2/);
  assert.match(queueLabel({ ...job, status: 'running' }), /готовит ответ/);
  assert.match(queueLabel({ ...job, status: 'running', cancel_requested: true }), /Останавливаю/);
});
