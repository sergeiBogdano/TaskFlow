import { api, type Workspace } from '../api/client';
import { applyTheme } from './theme';

export const WORKSPACE_KEY = 'taskflow:workspace';
const DETAIL_KEY = 'taskflow:workspace-detail';
export const WORKSPACE_EVENT = 'taskflow:workspace-changed';

export function getActiveWorkspaceId(): string | null {
  try {
    return localStorage.getItem(WORKSPACE_KEY);
  } catch {
    return null;
  }
}

export function getActiveWorkspaceDetail(): Record<string, any> | null {
  try {
    const raw = localStorage.getItem(DETAIL_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function workspaceClientsLabel(): string {
  const detail = getActiveWorkspaceDetail();
  const label = detail?.dictionary?.clients;
  return typeof label === 'string' && label.trim() ? label.trim() : 'Клиенты';
}

/** Гарантирует выбранный воркспейс: чинит протухший id, возвращает список + активный. */
export async function ensureWorkspace(): Promise<{ workspaces: Workspace[]; activeId: string | null }> {
  const workspaces = await api.getWorkspaces().catch(() => null);
  if (workspaces === null) {
    // Ошибка сети/авторизации — не трогаем сохранённый выбор.
    return { workspaces: [], activeId: null };
  }
  if (!workspaces.length) {
    // Окружений нет — чистим протухший id, иначе все API будут ходить
    // с чужим workspace_id и возвращать 403 «Нет доступа».
    try {
      localStorage.removeItem(WORKSPACE_KEY);
      localStorage.removeItem(DETAIL_KEY);
    } catch {
      /* ignore */
    }
    return { workspaces, activeId: null };
  }
  const stored = getActiveWorkspaceId();
  const ok = stored && workspaces.some(w => String(w.id) === stored);
  const activeId = ok && stored ? stored : String(workspaces[0].id);
  try {
    localStorage.setItem(WORKSPACE_KEY, activeId);
  } catch {
    /* ignore */
  }
  if (stored && !ok) {
    // Сохранённый id больше не наш (другой аккаунт или удалили из окружения):
    // страница уже загрузилась с чужим workspace_id — перезагружаем данные.
    window.location.reload();
  }
  return { workspaces, activeId };
}

export async function switchWorkspace(id: string): Promise<void> {
  try {
    localStorage.setItem(WORKSPACE_KEY, id);
  } catch {
    /* ignore */
  }
  try {
    const detail = await api.getWorkspace(Number(id));
    try {
      localStorage.setItem(DETAIL_KEY, JSON.stringify(detail));
    } catch {
      /* ignore */
    }
    if (detail.theme === 'cream' || detail.theme === 'graphite') {
      applyTheme(detail.theme);
    }
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new CustomEvent(WORKSPACE_EVENT, { detail: { id } }));
  window.location.reload();
}
