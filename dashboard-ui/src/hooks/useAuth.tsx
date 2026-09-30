import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { api, type User } from '../api/client';
import { referenceCache } from '../api/cache';

type AuthContextType = {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hasRole: (role: string) => boolean;
};

const AuthContext = createContext<AuthContextType>(null!);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getMe()
      .then(({ user }) => setUser(user))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    referenceCache.invalidate();
    const res = await api.login(username, password);
    // Куку сессии ставит бэкенд (HttpOnly, SameSite=Lax). Через document.cookie
    // её писать нельзя — кука станет читаемой из JS и HttpOnly-защита пропадёт.
    setUser(res.user);
    // права активного окружения (Ф8) /me считает по workspace_id — перечитываем
    api.getMe()
      .then(({ user }) => setUser(user))
      .catch(() => {});
  }, []);

  const logout = useCallback(async () => {
    await api.logout().catch(() => {});
    referenceCache.invalidate();
    // Куку стирает бэкенд (delete_cookie). Локально чистить нечего.
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
