import { createContext, useContext } from 'react';
import type { User } from '../api/client';

type AuthContextType = {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hasRole: (role: string) => boolean;
  refresh: () => Promise<void>;
};

export const AuthContext = createContext<AuthContextType>(null!);

export function useAuth() { return useContext(AuthContext); }
