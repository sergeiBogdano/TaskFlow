import { requestErrorMessage } from '../lib/requestDeadline';
import { useState, useEffect, useCallback, useRef, type ReactNode } from 'react';
import { AuthContext } from '../hooks/useAuth';
import { api, type User } from '../api/client';
import { referenceCache } from '../api/cache';
import { ensureWorkspace, clearWorkspace } from '../lib/workspace';
import { restoreSession, sessionExpired } from '../lib/sessionRestore';


function storeAccount(user: User | null) {
  try {
    if (user) localStorage.setItem('taskflow:account', user.account_key || String(user.id));
    else localStorage.removeItem('taskflow:account');
  } catch { /* storage may be unavailable */ }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const refreshInFlight = useRef<Promise<void> | null>(null);
  const lastRefresh = useRef(0);


  const [startupError, setStartupError] = useState('');
  const startupRevision = useRef(0);
  const bootstrap = useCallback(async () => {
    const revision = ++startupRevision.current;
    setLoading(true); setStartupError('');
    try {
      const current = await restoreSession(api.getMe, ensureWorkspace);
      if (revision !== startupRevision.current) return;
      storeAccount(current); setUser(current);
    } catch (error) {
      if (revision !== startupRevision.current) return;
      if (sessionExpired(error)) { clearWorkspace(); storeAccount(null); setUser(null); }
      else setStartupError(requestErrorMessage(error));
    } finally { if (revision === startupRevision.current) setLoading(false); }
  }, []);
  useEffect(() => { void bootstrap(); return () => { startupRevision.current++; }; }, [bootstrap]);

  const login = useCallback(async (username: string, password: string) => {
    startupRevision.current++;
    referenceCache.invalidate();
    const res = await api.login(username, password);
    // Куку сессии ставит бэкенд (HttpOnly, SameSite=Lax). Через document.cookie
    // её писать нельзя — кука станет читаемой из JS и HttpOnly-защита пропадёт.
    clearWorkspace();
    if (!res.user.must_change_password) await ensureWorkspace();
    const currentUser = (await api.getMe()).user;
    storeAccount(currentUser);
    setUser(currentUser); setStartupError(''); setLoading(false);
  }, []);

  const logout = useCallback(async () => {
    startupRevision.current++;
    await api.logout().catch(() => {});
    referenceCache.invalidate();
    // Куку стирает бэкенд (delete_cookie). Локально чистить нечего.
    clearWorkspace();
    storeAccount(null);
    setUser(null);
  }, []);

  const refresh = useCallback((): Promise<void> => {
    if (refreshInFlight.current) return refreshInFlight.current;
    const revision = startupRevision.current;
    const request = (async () => {
      try {
        const current = await restoreSession(api.getMe, ensureWorkspace);
        if (revision !== startupRevision.current) return;
        storeAccount(current);
        setUser(previous => {
          // The same account response must not restart every page's data effects.
          if (JSON.stringify(previous) === JSON.stringify(current)) return previous;
          referenceCache.invalidate();
          return current;
        });
      } catch (error) {
        if (revision !== startupRevision.current) return;
        if ((error as { status?: number }).status === 401) {
          clearWorkspace(); storeAccount(null); setUser(null);
        }
      } finally { lastRefresh.current = Date.now(); }
    })();
    refreshInFlight.current = request;
    void request.finally(() => { refreshInFlight.current = null; });
    return request;
  }, []);
  const authenticated = Boolean(user);
  useEffect(() => {
    if (!authenticated) return;
    const update = () => { void refresh(); };
    const onFocus = () => { if (Date.now() - lastRefresh.current >= 60000) update(); };
    window.addEventListener('taskflow:access-updated', update);
    window.addEventListener('focus', onFocus);
    return () => {
      window.removeEventListener('taskflow:access-updated', update);
      window.removeEventListener('focus', onFocus);
    };
  }, [authenticated, refresh]);

  const hasRole = useCallback((role: string) => {
    return user?.roles?.some(r => r.name === role) ?? false;
  }, [user]);

  if (startupError) return <main className="mx-auto max-w-xl space-y-4 p-6" role="alert">
    <h1 className="text-xl font-semibold">Не удалось загрузить приложение</h1>
    <p>{startupError}</p>
    <button className="tf-button tf-button-primary" disabled={loading} onClick={() => void bootstrap()}>Повторить загрузку</button>
  </main>;

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, hasRole, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}
