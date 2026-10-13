export const WORKSPACE_KEY = 'taskflow:workspace';
export const WORKSPACE_DETAIL_KEY = 'taskflow:workspace-detail';

function storage(name: 'sessionStorage' | 'localStorage'): Storage | null {
  try { return globalThis[name] || null; } catch { return null; }
}

/** A tab pins its own workspace; localStorage is only the default for new tabs. */
export function createWorkspaceStore(session: Storage | null, defaults: Storage | null) {
  let initialized = false;
  const values: Record<string, string | null> = {};
  const read = (source: Storage | null, key: string) => { try { return source?.getItem(key) ?? null; } catch { return null; } };
  const persist = (source: Storage | null, key: string, value: string | null) => { try { if (value === null) source?.removeItem(key); else source?.setItem(key, value); } catch { /* Memory remains usable when storage is blocked. */ } };
  const init = () => {
    if (initialized) return;
    initialized = true;
    const savedId = read(session, WORKSPACE_KEY);
    values[WORKSPACE_KEY] = savedId ?? read(defaults, WORKSPACE_KEY);
    values[WORKSPACE_DETAIL_KEY] = read(savedId ? session : defaults, WORKSPACE_DETAIL_KEY);
    try {
      if (String(JSON.parse(values[WORKSPACE_DETAIL_KEY] || '{}').id) !== values[WORKSPACE_KEY]) values[WORKSPACE_DETAIL_KEY] = null;
    } catch { values[WORKSPACE_DETAIL_KEY] = null; }
    for (const key of [WORKSPACE_KEY, WORKSPACE_DETAIL_KEY]) persist(session, key, values[key]);
  };
  return {
    get(key: string) { init(); return values[key] ?? null; },
    set(key: string, value: string | null) {
      init();
      if (key === WORKSPACE_KEY && values[key] !== value) {
        values[WORKSPACE_DETAIL_KEY] = null;
        persist(session, WORKSPACE_DETAIL_KEY, null); persist(defaults, WORKSPACE_DETAIL_KEY, null);
      }
      values[key] = value; persist(session, key, value); persist(defaults, key, value);
    },
    clear() { init(); for (const key of [WORKSPACE_KEY, WORKSPACE_DETAIL_KEY]) { values[key] = null; persist(session, key, null); persist(defaults, key, null); } },
  };
}
const tab = createWorkspaceStore(storage('sessionStorage'), storage('localStorage'));
export const getTabWorkspaceId = () => tab.get(WORKSPACE_KEY);
export const getTabWorkspaceDetail = () => tab.get(WORKSPACE_DETAIL_KEY);
export const setTabWorkspaceValue = (key: string, value: string | null) => tab.set(key, value);
export const clearTabWorkspace = () => tab.clear();
