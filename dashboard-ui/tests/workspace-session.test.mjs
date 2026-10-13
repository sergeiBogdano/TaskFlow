import test from 'node:test';
import assert from 'node:assert/strict';
import { createWorkspaceStore, WORKSPACE_KEY, WORKSPACE_DETAIL_KEY } from '../src/lib/workspaceSession.ts';
function store(initial = {}) {
 const entries = new Map(Object.entries(initial));
 return { getItem:key=>entries.get(key)??null, setItem:(key,value)=>entries.set(key,value), removeItem:key=>entries.delete(key) };
}
test('two tabs keep independent workspaces and reload restores the same tab', () => {
 const defaults=store({[WORKSPACE_KEY]:'A',[WORKSPACE_DETAIL_KEY]:JSON.stringify({id:'A'})});
 const aSession=store(), bSession=store();
 const a=createWorkspaceStore(aSession,defaults), b=createWorkspaceStore(bSession,defaults);
 assert.equal(a.get(WORKSPACE_KEY),'A'); assert.equal(b.get(WORKSPACE_KEY),'A');
 b.set(WORKSPACE_KEY,'B'); b.set(WORKSPACE_DETAIL_KEY,JSON.stringify({id:'B'}));
 assert.equal(a.get(WORKSPACE_KEY),'A'); assert.equal(JSON.parse(a.get(WORKSPACE_DETAIL_KEY)).id,'A');
 assert.equal(createWorkspaceStore(aSession,defaults).get(WORKSPACE_KEY),'A');
 assert.equal(createWorkspaceStore(store(),defaults).get(WORKSPACE_KEY),'B');
});
test('blocked session storage still pins the workspace in memory', () => {
 const blocked={getItem(){throw Error('blocked');},setItem(){throw Error('blocked');},removeItem(){throw Error('blocked');}};
 const defaults=store({[WORKSPACE_KEY]:'A'});const a=createWorkspaceStore(blocked,defaults);
 assert.equal(a.get(WORKSPACE_KEY),'A'); defaults.setItem(WORKSPACE_KEY,'B');assert.equal(a.get(WORKSPACE_KEY),'A');
 a.set(WORKSPACE_KEY,'C');assert.equal(a.get(WORKSPACE_KEY),'C');
});
test('switch and clear cannot retain another workspace field policy', () => {
 const defaults=store({[WORKSPACE_KEY]:'A',[WORKSPACE_DETAIL_KEY]:JSON.stringify({id:'B',field_access:{}})});
 const a=createWorkspaceStore(store(),defaults);assert.equal(a.get(WORKSPACE_DETAIL_KEY),null);
 a.set(WORKSPACE_DETAIL_KEY,JSON.stringify({id:'A'}));a.set(WORKSPACE_KEY,'B');assert.equal(a.get(WORKSPACE_DETAIL_KEY),null);
 a.clear();assert.equal(a.get(WORKSPACE_KEY),null);assert.equal(a.get(WORKSPACE_DETAIL_KEY),null);
});
