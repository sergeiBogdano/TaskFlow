import { api, type Client, type SavedView, type User } from './client';

const TTL = 60_000;

type Entry<T> = {
  expires: number;
  promise: Promise<T>;
};

const cache = new Map<string, Entry<any>>();

function cached<T>(key: string, loader: () => Promise<T>, ttl = TTL): Promise<T> {
  const now = Date.now();
  const hit = cache.get(key);
  if (hit && hit.expires > now) return hit.promise;
  const promise = loader().catch(error => {
    cache.delete(key);
    throw error;
  });
  cache.set(key, { expires: now + ttl, promise });
  return promise;
}

export const referenceCache = {
  clients: () => cached<Client[]>('clients', () => api.getClients()),
  users: () => cached<User[]>('users', () => api.getUsers()),
  savedViews: (type: string) => cached<SavedView[]>(`saved-views:${type}`, () => api.getSavedViews(type), 20_000),
  invalidate(keys?: string[]) {
    if (!keys) {
      cache.clear();
      return;
    }
    keys.forEach(key => cache.delete(key));
  },
};
