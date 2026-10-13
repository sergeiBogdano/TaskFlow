import test from 'node:test';
import assert from 'node:assert/strict';
import { restoreSession, sessionExpired } from '../src/lib/sessionRestore.ts';
test('startup resolves workspace then loads effective user permissions', async () => {
 const calls=[];let count=0;
 const user=await restoreSession(async signal=>{assert.equal(signal.aborted,false);calls.push('me');return {user:{id:++count}};},async()=>{calls.push('workspace');});
 assert.deepEqual(calls,['me','workspace','me']);assert.equal(user.id,2);
});
test('temporary errors remain retryable and are not mistaken for expired auth', async () => {
 for (const error of [new Error('Network offline'),Object.assign(new Error('Service unavailable'),{status:503})]) {
  await assert.rejects(restoreSession(async()=>{throw error;},async()=>{}), e=>e===error);
  assert.equal(sessionExpired(error),false);
 }
 const error=Object.assign(new Error('Unauthorized'),{status:401});assert.equal(sessionExpired(error),true);
});
test('stalled request times out, aborts transport, and cannot later select a workspace', async () => {
 let release, signal, selected=false;
 await assert.rejects(restoreSession(s=>{signal=s;return new Promise(resolve=>{release=resolve;});},async()=>{selected=true;},15),/не ответил вовремя/);
 assert.equal(signal.aborted,true);release({user:{id:1}});await new Promise(resolve=>setTimeout(resolve,5));assert.equal(selected,false);
});
test('temporary password account does not enter workspace startup', async () => {
 const user=await restoreSession(async()=>({user:{must_change_password:true}}),async()=>{throw Error('must not load workspace');});assert.equal(user.must_change_password,true);
});

import { requestErrorMessage } from '../src/lib/requestDeadline.ts';
test('request errors distinguish expired sessions, connectivity, and field permissions', () => {
 assert.match(requestErrorMessage(new TypeError('Failed to fetch')), /Нет связи/);
 assert.match(requestErrorMessage(Object.assign(new Error('private server diagnostic'),{status:503})), /временно недоступен/);
 assert.match(requestErrorMessage(Object.assign(new Error('Unauthorized'),{status:401})), /Сессия завершилась/);
 assert.equal(requestErrorMessage(Object.assign(new Error('Нет просмотра дат'),{status:403})), 'Нет просмотра дат');
});
