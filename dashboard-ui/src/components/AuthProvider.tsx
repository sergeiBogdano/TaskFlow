import { useState, useEffect, useCallback, useRef, type ReactNode } from 'react';
import { AuthContext } from '../hooks/useAuth';
import { api, type User } from '../api/client';
import { referenceCache } from '../api/cache';
import { ensureWorkspace, clearWorkspace } from '../lib/workspace';


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


  useEffect(() => {
    api.getMe().then(async initial => {
      if (initial.user.must_change_password) return initial;
      await ensureWorkspace();
      return api.getMe();
    })
      .then(({ user }) => { storeAccount(user); setUser(user); })
      .catch(() => { storeAccount(null); setUser(null); })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    referenceCache.invalidate();
    const res = await api.login(username, password);
    // Куку сессии ставит бэкенд (HttpOnly, SameSite=Lax). Через document.cookie
    // её писать нельзя — кука станет читаемой из JS и HttpOnly-защита пропадёт.
    clearWorkspace();
    if (!res.user.must_change_password) await ensureWorkspace();
    const currentUser = (await api.getMe()).user;
    storeAccount(currentUser);
    setUser(currentUser);
  }, []);

  const logout = useCallback(async () => {
    await api.logout().catch(() => {});
    referenceCache.invalidate();
    // Куку стирает бэкенд (delete_cookie). Локально чистить нечего.
    clearWorkspace();
    storeAccount(null);
    setUser(null);
  }, []);

  const refresh = useCallback((): Promise<void> => {
    if (refreshInFlight.current) return refreshInFlight.current;
    const request = (async () => {
      try {
        await ensureWorkspace();
        const current = (await api.getMe()).user;
        storeAccount(current);
        setUser(previous => {
          // The same account response must not restart every page's data effects.
          if (JSON.stringify(previous) === JSON.stringify(current)) return previous;
          referenceCache.invalidate();
          return current;
        });
      } catch (error) {
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

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, hasRole, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}
