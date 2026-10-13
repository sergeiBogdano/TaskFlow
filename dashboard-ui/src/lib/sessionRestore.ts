import { withRequestDeadline } from './requestDeadline.ts';
/** Bound startup across all auth/workspace requests, without treating network errors as logout. */
export async function restoreSession<T extends { must_change_password?: boolean }>(
  getMe: (signal: AbortSignal) => Promise<{ user: T }>,
  ensureWorkspace: (signal: AbortSignal) => Promise<unknown>,
  timeout = 15000,
): Promise<T> {
  return withRequestDeadline(async signal => {
    const initial = await getMe(signal);
    signal.throwIfAborted();
    if (initial.user.must_change_password) return initial.user;
    await ensureWorkspace(signal);
    signal.throwIfAborted();
    return (await getMe(signal)).user;
  }, timeout);
}

export function sessionExpired(error: unknown): boolean {
  return Boolean(error && typeof error === 'object' && 'status' in error && error.status === 401);
}
