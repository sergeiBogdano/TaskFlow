import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { api, type User } from '../api/client';
import { referenceCache } from '../api/cache';
import { ensureWorkspace, clearWorkspace } from '../lib/workspace';

type AuthContextType = {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hasRole: (role: string) => boolean;
};

const AuthContext = createContext<AuthContextType>(null!);

function storeAccount(user: User | null) {
  try {
    if (user) localStorage.setItem('taskflow:account', user.account_key || String(user.id));
    else localStorage.removeItem('taskflow:account');
  } catch { /* storage may be unavailable */ }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);


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

  const hasRole = useCallback((role: string) => {
    return user?.roles?.some(r => r.name === role) ?? false;
  }, [user]);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, hasRole }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
