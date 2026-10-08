import { prepareUpload } from '../lib/uploads';
import { currentFieldAccess, writableFields, type FieldAccess } from '../lib/fieldAccess';
const API_BASE = '';
export { request };

const WORKSPACE_KEY = 'taskflow:workspace';

function activeWorkspaceId(): string | null {
  try {
    return localStorage.getItem(WORKSPACE_KEY);
  } catch {
    return null;
  }
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  let finalUrl = url;
  // Активный воркспейс подмешивается ко всем API-запросам (кроме логина/логаута).
  // /api/auth/me тоже получает workspace_id: права и функции считаются для окружения (Ф8).
  // Бэкенд неизвестные query-параметры игнорирует, так что безопасно везде.
  const ws = activeWorkspaceId();
  const isSessionWrite = url.startsWith('/api/auth/login') || url.startsWith('/api/auth/logout');
  if (ws && url.startsWith('/api/') && !isSessionWrite && !new URL(url, 'http://local').searchParams.has('workspace_id')) {
    finalUrl += (url.includes('?') ? '&' : '?') + `workspace_id=${encodeURIComponent(ws)}`;
  }
  const res = await fetch(`${API_BASE}${finalUrl}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    const detail = err.error || (Array.isArray(err.detail) ? err.detail.map((item: { msg?: string }) => item.msg || 'Некорректное значение').join('; ') : err.detail);
    const error = new Error(detail || `API error: ${res.status}`) as Error & { status?: number };
    error.status = res.status;
    throw error;
  }
  return res.json();
}

export type User = {
  field_access?: FieldAccess;
  account_key?: string;
  is_root?: boolean;
  is_active?: boolean;
  must_change_password?: boolean;
  id: number;
  username: string;
  created_at: string;
  roles: { id: number; name: string }[];
  permissions: Record<string, boolean>;
  group_ids?: number[];
  features?: Record<string, boolean>;
};

export type Group = {
  deleted_at?: string | null;
  id: number;
  name: string;
  permissions: Record<string, boolean>;
  user_ids?: number[];
};

export type Task = {
  contract_id?: number | null;
  id: number;
  title: string;
  status: string;
  priority: string;
  task_type: string;
  client: string;
  client_id: number | null;
  client_warning: string;
  notes: string;
  comment: string;
  deadline: string | null;
  completion_date: string | null;
  checklist: { text: string; done: boolean; reminder?: string }[];
  sort_order: number;
  created_at: string;
  updated_at: string;
  recurring_interval: string | null;
  recurring_count: number | null;
  recurring_remaining: number | null;
  creator_id: number | null;
  assignee_id: number | null;
  co_executor_id: number | null;
  co_executor_ids: number[];
  no_contract: boolean;
  module_id: number | null;
  visibility: 'public' | 'private';
  client_access_ids: number[];
  sprint_ids?: number[];
  deleted_at?: string | null;
};

export type TaskListResponse = {
  items: Task[];
  total: number;
  page: number;
  page_size: number;
};

export type Client = {
  id: number;
  org_name: string;
  domain: string;
  favicon_url?: string;
  status: string;
  contract_start: string;
  contract_end: string;
  org_data: string;
  client_warning: string;
  client_notes?: string;
  competitors?: string;
  accesses: any[];
  allowed_user_ids?: number[];
  responsible_user_ids?: number[];
  health?: OrganizationHealth;
  deleted_at?: string | null;
  contacts: { id: number; fio: string; position: string; phone: string; email: string }[];
  contracts: { id: number; contract_type: string; start_date: string; end_date: string; amount: number; status: string }[];
  created_at: string;
};

export type TaskComment = {
  id: number;
  user_id: number;
  content: string;
  mentions: number[];
  created_at: string;
};

export type TaskFile = {
  id: number;
  name: string;
  size: number;
  content_type: string;
  uploaded_at: string;
};

export type ClientFile = TaskFile;

export type Role = {
  deleted_at?: string | null;
  id: number;
  name: string;
  permissions: Record<string, boolean>;
};

export type PermissionItem = {
  key: string;
  label: string;
  hint: string;
  level?: 'basic' | 'advanced' | 'sensitive';
  scope: 'app' | 'work';
};

export type PermissionGroup = {
  id: string;
  scope: 'app' | 'work';
  title: string;
  description: string;
  items: PermissionItem[];
};

export type PermissionCatalog = {
  fields: Record<string, Record<string, { label: string; required: boolean }>>;
  groups: PermissionGroup[];
  presets: Record<string, string[]>;
  scopes: Record<string, 'app' | 'work'>;
};

export type FeatureOverride = {
  id: number;
  scope: 'global' | 'workspace' | 'group' | 'user';
  target_id: number | null;
  key: string;
  enabled: boolean;
};

export type FeaturesResponse = {
  catalog: PermissionGroup[];
  effective: Record<string, boolean>;
  scope_effective: Record<string, boolean>;
  overrides: FeatureOverride[];
};

export type Notification = {
  id: number;
  type: string;
  title: string;
  message: string;
  task_id: number | null;
  client_id: number | null;
  read: boolean;
  created_at: string;
};

export type DashboardStats = {
  total: number;
  done: number;
  in_progress: number;
  overdue: number;
  active_clients: number;
  ending_clients: number;
};

export type DashboardChart = {
  labels: string[];
  created: number[];
  done: number[];
};

export type ClientTableItem = {
  id: number;
  name: string;
  total: number;
  done: number;
  status: string;
};

export type OrganizationOverviewItem = {
  id: number;
  name: string;
  domain: string;
  status: string;
  active: number;
  overdue: number;
  due_soon: number;
  done_this_month: number;
  last_activity: string | null;
  inactive_days: number | null;
  is_stale: boolean;
  needs_attention: boolean;
  nearest_task: { id: number; title: string; date: string } | null;
  responsible_user_ids: number[];
  responsible_users: string[];
  participants: string[];
};

export type OrganizationOverview = {
  items: OrganizationOverviewItem[];
  scope: string;
  selected_user_id: number;
  can_view_team: boolean;
  users: { id: number; username: string }[];
};

export type ClientWorkSummary = {
  client_id: number;
  total: number;
  active: number;
  overdue: number;
  last_activity: string | null;
};

export type ClientAnalytics = {
  period: { start: string; end: string };
  summary: { organizations: number; total: number; completed: number; other: number; overdue: number; without_modules?: number };
  by_type: { type: string; count: number }[];
  by_client: {
    id: number;
    name: string;
    domain: string;
    total: number;
    completed: number;
    other: number;
    overdue: number;
    module_count?: number;
    modules?: string[];
    completed_tasks: ClientAnalyticsTask[];
    other_tasks: ClientAnalyticsTask[];
  }[];
  modules?: { id: number; name: string; domain: string; module_count: number; modules: string[] }[];
};

export type ClientAnalyticsTask = {
  id: number;
  title: string;
  status: string;
  task_type: string;
  completion_date: string | null;
  deadline: string | null;
  assignee: string;
};

export type GeneratedReport = {
  id: number;
  client_id: number | null;
  client: string;
  title: string;
  period_start: string | null;
  period_end: string | null;
  status: 'queued' | 'running' | 'done' | 'error';
  settings: Record<string, any>;
  summary: Record<string, any>;
  html: string;
  error: string;
  ai_model: string;
  created_by: string;
  created_at: string;
  updated_at: string | null;
  deleted_at?: string | null;
};

export type ReportGeneratePayload = {
  client_id: number;
  period_start: string;
  period_end: string;
  blocks: string[];
  use_ai: boolean;
  ai_model?: string;
};

export type ActivityItem = {
  id: number;
  action: string;
  field_name: string | null;
  old_value: string | null;
  new_value: string | null;
  summary: string;
  created_at: string;
  actor?: string;
};

export type OrganizationHealth = {
  score: number;
  level: 'good' | 'watch' | 'critical';
  active_tasks: number;
  overdue_tasks: number;
  stale_tasks: number;
  done_this_month: number;
  inactive_days: number | null;
  contract_days_left: number | null;
  has_responsible: boolean;
  reasons: string[];
};

export type SavedView = {
  id: number;
  user_id: number | null;
  name: string;
  view_type: string;
  filters: Record<string, any>;
  sort_field: string | null;
  sort_order: string;
  created_at: string;
};

export type QuickTaskTemplate = {
  id: number;
  title: string;
  task_type: string;
  priority: string;
};

export type VoiceTaskDraft = Partial<Task> & {
  client_name?: string;
  assignee_name?: string;
};

export type VoiceTaskParseResult = {
  draft: VoiceTaskDraft;
  missing: string[];
  questions: string[];
  clients: { id: number; name: string; domain: string }[];
  users: { id: number; username: string }[];
};

export type Workspace = {
  visibility?: 'open' | 'closed' | 'hidden';
  enabled_modules?: string[];
  id: number;
  name: string;
  preset: string;
  theme: string | null;
  dictionary: Record<string, string>;
  has_ai_instructions: boolean;
  role: string;
  created_at: string | null;
  deleted_at?: string | null;
};

export type WorkspaceDetail = Workspace & {
  permissions?: Record<string, boolean>;
  field_access?: FieldAccess;
  ai_instructions: string;
  ui_config?: Record<string, any>;
};

export type WorkspaceMember = {
  user_id: number;
  username: string | null;
  role: string;
  custom_role_id: number | null;
  custom_role: string | null;
  created_at: string | null;
};

export type WorkspaceRole = {
  deleted_at?: string | null;
  field_access?: FieldAccess;
  id: number;
  workspace_id: number;
  name: string;
  permissions: Record<string, boolean>;
  created_at: string | null;
};

export type WorkspaceAccessReport = {
  groups: PermissionGroup[];
  fields: Record<string, Record<string, { label: string; required: boolean }>>;
  members: { user_id: number; username: string; is_root: boolean; level: string; profile: string;
    profile_id: number | null; overrides: { permissions?: Record<string, boolean>; fields?: FieldAccess };
    fields: FieldAccess; permissions: Record<string, { granted: boolean; available: boolean; allowed: boolean; source: string; reason: string }> }[];
};

export type WorkspaceRolesResponse = {
  roles: WorkspaceRole[];
  features: Record<string, boolean>;
};

export type Sprint = {
  id: number;
  workspace_id: number;
  name: string;
  goal: string;
  start_date: string | null;
  end_date: string | null;
  status: string;
  progress: { total: number; done: number; percent: number };
  created_at: string | null;
};

export type SprintDetail = Sprint & {
  tasks: { id: number; title: string; status: string }[];
};

export type AiAnalyticsResult = {
  facts: Record<string, any>;
  analysis: string;
  model: string;
};

export type AiTaskDescription = {
  description: string;
  model: string;
};

export type AiSeoReport = {
  report: string;
  facts: Record<string, any>;
  model: string;
};

export type AiChatMessage = {
  answer: string;
  intent: string;
  facts: Record<string, any>;
  model: string;
};

export type Note = {
  id: number;
  title: string;
  content: string;
  format: string;
  tags: string[];
  is_public: boolean;
  folder_id: number | null;
  folder_name: string | null;
  user_id: number;
  username: string | null;
  is_owner: boolean;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
};

export type NoteFolder = {
  id: number;
  name: string;
  parent_id: number | null;
  user_id: number;
  created_at: string;
};

export type NotesListResponse = {
  notes: Note[];
  tags: string[];
  total: number;
};

export const api = {
  // Auth
  login: (username: string, password: string) =>
    request<{ user: User; token: string }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<{ ok: boolean }>('/api/auth/logout', { method: 'POST' }),
  getMe: () => request<{ user: User }>('/api/auth/me'),

  parseVoiceTask: (text: string, draft?: VoiceTaskDraft) =>
    request<VoiceTaskParseResult>('/api/ai/task-command', {
      method: 'POST',
      body: JSON.stringify({ text, draft: draft || {} }),
    }),
  polishText: (text: string) =>
    request<{ html: string }>('/api/ai/text-polish', {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),

  // Users
  getUsers: (scope: 'space' | 'platform' = 'space') => request<User[]>(`/api/users?scope=${scope}`),
  createUser: (username: string, password: string, extra?: { workspace_id?: number; role?: string; must_change_password?: boolean }) =>
    request<{ id: number; username: string }>('/api/users', {
      method: 'POST',
      body: JSON.stringify({ username, password, ...extra }),
    }),
  setUserPassword: (userId: number, password: string) =>
    request<{ ok: boolean }>(`/api/users/${userId}/password`, {
      method: 'PUT',
      body: JSON.stringify({ password }),
    }),
  setUserRole: (userId: number, roleId: number) =>
    request<{ ok: boolean }>(`/api/users/${userId}/role`, {
      method: 'PUT',
      body: JSON.stringify({ role_id: roleId }),
    }),
  deleteUser: (userId: number) =>
    request<{ ok: boolean }>(`/api/users/${userId}`, { method: 'DELETE' }),

  setUserStatus: (id: number, is_active: boolean) => request(`/api/users/${id}/status`, { method: 'PATCH', body: JSON.stringify({ is_active }) }),
  getUserAccess: (id: number) => request<{ app_permissions: Record<string, boolean>; spaces: { id: number; name: string; rank: string; permissions: Record<string, boolean>; features: Record<string, boolean>; feature_reasons: Record<string, string> }[] }>(`/api/users/${id}/access`),
  changePassword: (current_password: string, new_password: string) => request('/api/users/change-password', { method: 'POST', body: JSON.stringify({ current_password, new_password }) }),
  getSpaceModules: (id: number) => request<{ catalog: Record<string, { label: string; keys: string[] }>; enabled: string[] }>(`/api/workspaces/${id}/modules`),
  setSpaceModules: (id: number, enabled: string[]) => request(`/api/workspaces/${id}/modules`, { method: 'PUT', body: JSON.stringify({ enabled }) }),
  getSpaceDirectory: () => request<{ id: number; name: string; visibility: string; joined: boolean }[]>('/api/workspaces/directory/list'),
  joinSpace: (id: number) => request(`/api/workspaces/${id}/join`, { method: 'POST' }),

  // Roles
  getRoles: (deleted = false) => request<Role[]>(`/api/roles${deleted ? '?deleted=true' : ''}`),
  getPermissionCatalog: () => request<PermissionCatalog>('/api/permissions/catalog'),

  // Features (кран доступности, Ф6)
  getFeatures: (scope: 'global' | 'workspace' | 'group' | 'user' = 'global', targetId?: number) => request<FeaturesResponse>(`/api/features?scope=${scope}${targetId == null ? '' : `&target_id=${targetId}`}`),
  setFeature: (data: {
    scope: 'global' | 'workspace' | 'group' | 'user';
    target_id?: number | null;
    key: string;
    enabled: boolean | null;
  }) => request<{ ok: boolean }>('/api/features', { method: 'PUT', body: JSON.stringify(data) }),
  createRole: (data: { name: string; permissions?: Record<string, boolean> }) =>
    request<Role>('/api/roles', { method: 'POST', body: JSON.stringify(data) }),
  updateRole: (id: number, data: Record<string, any>) =>
    request<{ ok: boolean }>(`/api/roles/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteRole: (id: number) => request<{ ok: boolean }>(`/api/roles/${id}`, { method: 'DELETE' }),

  restoreRole: (id: number) => request<{ ok: boolean }>(`/api/roles/${id}/restore`, { method: 'POST' }),

  // Groups (глобальные, только суперадмин)
  getGroups: (deleted = false) => request<Group[]>(`/api/groups${deleted ? '?deleted=true' : ''}`),
  createGroup: (data: { name: string; permissions?: Record<string, boolean> }) =>
    request<Group>('/api/groups', { method: 'POST', body: JSON.stringify(data) }),
  updateGroup: (id: number, data: Record<string, any>) =>
    request<{ ok: boolean }>(`/api/groups/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteGroup: (id: number) => request<{ ok: boolean }>(`/api/groups/${id}`, { method: 'DELETE' }),
  restoreGroup: (id: number) => request<{ ok: boolean }>(`/api/groups/${id}/restore`, { method: 'POST' }),
  setGroupMembers: (id: number, userIds: number[]) =>
    request<{ ok: boolean }>(`/api/groups/${id}/members`, { method: 'PUT', body: JSON.stringify({ user_ids: userIds }) }),

  // Tasks
  getTasks: (params?: string) => request<Task[]>(`/api/tasks/all${params ? `?${params}` : ''}`),
  getTasksPage: (params?: string) =>
    request<TaskListResponse>(`/api/tasks/all?paginated=1${params ? `&${params}` : ''}`),
  getTask: (id: number) => request<Task>(`/api/tasks/${id}`),
  getTaskAccesses: (id: number) => request<any[]>(`/api/tasks/${id}/accesses`),
  createTask: (data: Partial<Task>) =>
    request<Task>('/api/tasks', { method: 'POST', body: JSON.stringify(writableFields('tasks', data, currentFieldAccess())) }),
  updateTask: (id: number, data: Partial<Task>) =>
    request<{ ok: boolean }>(`/api/tasks/${id}`, { method: 'PUT', body: JSON.stringify(writableFields('tasks', data, currentFieldAccess())) }),
  deleteTask: (id: number) =>
    request<{ ok: boolean }>(`/api/tasks/${id}`, { method: 'DELETE' }),
  bulkUpdateTasks: (ids: number[], fields: Record<string, any>) =>
    request<{ ok: boolean; count: number }>('/api/tasks/bulk', {
      method: 'POST',
      body: JSON.stringify({ ids, fields }),
    }),
  getTaskTrash: () => request<Task[]>('/api/tasks/trash'),
  restoreTask: (id: number) =>
    request<{ ok: boolean }>(`/api/tasks/${id}/restore`, { method: 'POST' }),
  emptyTaskTrash: () =>
    request<{ ok: boolean; count: number }>('/api/tasks/trash/empty', { method: 'POST' }),
  moveTask: (id: number, status: string) =>
    request<{ ok: boolean }>(`/api/tasks/${id}/move`, {
      method: 'POST',
      body: JSON.stringify({ status }),
    }),
  getComments: (taskId: number) =>
    request<TaskComment[]>(`/api/tasks/${taskId}/comments`),
  addComment: (taskId: number, content: string, mentions?: number[]) =>
    request<{ id: number; content: string; created_at: string }>(`/api/tasks/${taskId}/comments`, {
      method: 'POST',
      body: JSON.stringify({ content, mentions: mentions || [] }),
    }),
  getTaskActivity: (taskId: number) => request<ActivityItem[]>(`/api/tasks/${taskId}/activity`),
  uploadFile: async (taskId: number, file: File) => {
    const formData = new FormData();
    formData.append('file', await prepareUpload(file));
    return fetch(`${API_BASE}/api/tasks/${taskId}/upload${activeWorkspaceId() ? `?workspace_id=${activeWorkspaceId()}` : ''}`, {
      method: 'POST',
      credentials: 'include',
      body: formData,
    }).then(async r => {
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.error || body.detail || `API error: ${r.status}`);
      return body;
    });
  },
  getTaskFiles: (taskId: number) => request<TaskFile[]>(`/api/tasks/${taskId}/files`),
  deleteFile: (taskId: number, fileId: number) =>
    request<{ ok: boolean }>(`/api/tasks/${taskId}/files/${fileId}`, { method: 'DELETE' }),

  // Clients
  getClients: () => request<Client[]>('/api/clients'),
  getClient: (id: number) => request<Client>(`/api/clients/${id}`),
  createClient: (data: Record<string, any>) =>
    request<{ id: number; org_name: string }>('/api/clients', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateClient: (id: number, data: Record<string, any>) =>
    request<{ ok: boolean }>(`/api/clients/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deleteClient: (id: number) =>
    request<{ ok: boolean }>(`/api/clients/${id}`, { method: 'DELETE' }),
  uploadClientFile: async (clientId: number, file: File) => {
    const formData = new FormData();
    formData.append('file', await prepareUpload(file));
    return fetch(`${API_BASE}/api/clients/${clientId}/upload${activeWorkspaceId() ? `?workspace_id=${activeWorkspaceId()}` : ''}`, { method: 'POST', credentials: 'include', body: formData }).then(async response => {
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.error || body.detail || `API error: ${response.status}`);
      return body;
    });
  },
  getClientFiles: (clientId: number) => request<ClientFile[]>(`/api/clients/${clientId}/files`),
  deleteClientFile: (clientId: number, fileId: number) => request<{ ok: boolean }>(`/api/clients/${clientId}/files/${fileId}`, { method: 'DELETE' }),
  getClientFileUrl: (clientId: number, fileId: number) => `${API_BASE}/api/clients/${clientId}/files/${fileId}/download`,
  uploadContractFile: async (clientId: number, contractId: number, file: File) => {
    const formData = new FormData();
    formData.append('file', await prepareUpload(file));
    return fetch(`${API_BASE}/api/clients/${clientId}/contracts/${contractId}/upload`, { method: 'POST', credentials: 'include', body: formData }).then(async response => {
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.error || body.detail || `API error: ${response.status}`);
      return body;
    });
  },
  getContractFiles: (clientId: number, contractId: number) => request<ClientFile[]>(`/api/clients/${clientId}/contracts/${contractId}/files`),
  bulkClients: (ids: number[], action: 'delete' | 'restore') =>
    request<{ ok: boolean; count: number }>('/api/clients/bulk', {
      method: 'POST',
      body: JSON.stringify({ ids, action }),
    }),
  getClientTrash: () => request<Client[]>('/api/clients/trash'),
  restoreClient: (id: number) =>
    request<{ ok: boolean }>(`/api/clients/${id}/restore`, { method: 'POST' }),
  getClientActivity: (id: number) => request<ActivityItem[]>(`/api/clients/${id}/activity`),
  getClientHealth: (id: number) => request<OrganizationHealth>(`/api/clients/${id}/health`),

  // Modules
  getModules: () => request<any[]>('/api/modules'),
  createModule: (data: Record<string, any>) =>
    request<{ id: number; name: string }>('/api/modules', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateModule: (id: number, data: Record<string, any>) =>
    request<{ ok: boolean }>(`/api/modules/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deleteModule: (id: number) => request<{ ok: boolean }>(`/api/modules/${id}`, { method: 'DELETE' }),
  generateModuleTasks: (id: number, count?: number) =>
    request<{ ok: boolean; count: number }>(`/api/modules/${id}/generate`, {
      method: 'POST',
      body: JSON.stringify({ count: count || 1 }),
    }),

  // Client modules
  getClientModules: (clientId: number) =>
    request<any[]>(`/api/clients/${clientId}/modules`),
  addClientModule: (clientId: number, moduleId: number) =>
    request<{ ok: boolean }>(`/api/clients/${clientId}/modules`, {
      method: 'POST',
      body: JSON.stringify({ module_id: moduleId }),
    }),
  removeClientModule: (clientId: number, moduleId: number) =>
    request<{ ok: boolean }>(`/api/clients/${clientId}/modules/${moduleId}`, { method: 'DELETE' }),

  // Dashboard
  getDashboardStats: () => request<DashboardStats>('/api/dashboard/stats'),
  getDashboardChart: (period?: string) =>
    request<DashboardChart>(`/api/dashboard/chart?period=${period || 'month'}`),
  getDashboardFocus: (limit = 7) => request<Partial<Task>[]>(`/api/dashboard/focus?limit=${limit}`),
  getClientTable: () => request<ClientTableItem[]>('/api/dashboard/client-table'),
  getOrganizationOverview: (scope = 'mine', userId?: number) =>
    request<OrganizationOverview>(`/api/dashboard/organizations?scope=${scope}${userId ? `&user_id=${userId}` : ''}`),
  getClientWorkSummaries: () => request<ClientWorkSummary[]>('/api/dashboard/client-summaries'),
  getExpiring: () => request<{ id: number; org_name: string; contract_end: string; status: string }[]>('/api/dashboard/expiring'),

  // Calendar
  getCalendarEvents: (start: string, end: string, assignee?: number, extraQuery?: string) =>
    request<any[]>(`/api/calendar?start=${start}&end=${end}${assignee ? `&assignee=${assignee}` : ''}${extraQuery ? `&${extraQuery}` : ''}`),
  getCalendarTasks: (start: string, end: string) =>
    request<any[]>(`/api/calendar?start=${start}&end=${end}`),
  updateCalendarEvent: (id: number, data: Record<string, any>) =>
    request<{ ok: boolean }>(`/api/calendar/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  updateTaskDate: (id: number, deadline: string) =>
    request<{ ok: boolean }>(`/api/calendar/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ deadline }),
    }),

  // Notifications
  getNotifications: () => request<{ unread_count: number; notifications: Notification[] }>('/api/notifications'),
  markNotificationRead: (id: number) =>
    request<{ ok: boolean }>(`/api/notifications/${id}/read`, { method: 'POST' }),
  markAllRead: () => request<{ ok: boolean }>('/api/notifications/read-all', { method: 'POST' }),
  markAllNotificationsRead: () => request<{ ok: boolean }>('/api/notifications/read-all', { method: 'POST' }),
  deleteNotification: (id: number) => request<{ ok: boolean }>(`/api/notifications/${id}`, { method: 'DELETE' }),
  deleteNotifications: (ids: number[]) => request<{ ok: boolean }>('/api/notifications/delete-many', { method: 'POST', body: JSON.stringify({ ids }) }),
  deleteAllNotifications: () => request<{ ok: boolean }>('/api/notifications/delete-all', { method: 'DELETE' }),
  getUnreadCount: () => request<{ count: number }>('/api/notifications/unread-count'),

  // Saved views
  getSavedViews: (viewType: string) => request<SavedView[]>(`/api/saved-views?view_type=${viewType}`),
  createSavedView: (data: Record<string, any>) =>
    request<SavedView>('/api/saved-views', { method: 'POST', body: JSON.stringify(data) }),
  updateSavedView: (id: number, data: Record<string, any>) =>
    request<SavedView>(`/api/saved-views/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteSavedView: (id: number) => request<{ ok: boolean }>(`/api/saved-views/${id}`, { method: 'DELETE' }),

  // Quick task templates
  getQuickTasks: () => request<QuickTaskTemplate[]>('/api/quick-tasks'),
  createQuickTask: (data: Record<string, any>) =>
    request<QuickTaskTemplate>('/api/quick-tasks', { method: 'POST', body: JSON.stringify(data) }),
  deleteQuickTask: (id: number) => request<{ ok: boolean }>(`/api/quick-tasks/${id}`, { method: 'DELETE' }),

  // Reports (existing endpoint)
  getGeneratedReports: () => request<GeneratedReport[]>('/api/reports'),
  getGeneratedReport: (id: number) => request<GeneratedReport>(`/api/reports/${id}`),
  generateReport: (data: ReportGeneratePayload) =>
    request<GeneratedReport>('/api/reports/generate', { method: 'POST', body: JSON.stringify(data) }),
  deleteGeneratedReport: (id: number) =>
    request<{ ok: boolean }>(`/api/reports/${id}`, { method: 'DELETE' }),
  getReportTrash: () => request<GeneratedReport[]>('/api/reports/trash'),
  getClientAnalytics: (data: { client_ids: number[]; period_start: string; period_end: string; scope?: string; scope_user_id?: string }) =>
    request<ClientAnalytics>('/api/reports/analytics', { method: 'POST', body: JSON.stringify(data) }),
  restoreGeneratedReport: (id: number) =>
    request<{ ok: boolean }>(`/api/reports/${id}/restore`, { method: 'POST' }),
  emptyReportTrash: () => request<{ ok: boolean; count: number }>('/api/reports/trash/empty', { method: 'DELETE' }),
  getOllamaModels: () => request<{ models: string[] }>('/api/reports/ollama-models'),

  // AI-аналитика (Ollama)
  aiOverdue: (model?: string, workspaceId?: number | null) =>
    request<AiAnalyticsResult>('/api/ai/analytics/overdue', {
      method: 'POST',
      body: JSON.stringify({ model: model ?? null, workspace_id: workspaceId ?? null }),
    }),
  aiWorkload: (model?: string, workspaceId?: number | null) =>
    request<AiAnalyticsResult>('/api/ai/analytics/workload', {
      method: 'POST',
      body: JSON.stringify({ model: model ?? null, workspace_id: workspaceId ?? null }),
    }),
  aiDaily: (model?: string, workspaceId?: number | null) =>
    request<AiAnalyticsResult>('/api/ai/analytics/daily', {
      method: 'POST',
      body: JSON.stringify({ model: model ?? null, workspace_id: workspaceId ?? null }),
    }),
  aiProject: (clientId: number, model?: string, workspaceId?: number | null) =>
    request<AiAnalyticsResult>('/api/ai/analytics/project', {
      method: 'POST',
      body: JSON.stringify({ client_id: clientId, model: model ?? null, workspace_id: workspaceId ?? null }),
    }),
  aiBottlenecks: (model?: string, workspaceId?: number | null) =>
    request<AiAnalyticsResult>('/api/ai/analytics/bottlenecks', {
      method: 'POST',
      body: JSON.stringify({ model: model ?? null, workspace_id: workspaceId ?? null }),
    }),
  describeTask: (title: string, client?: string, taskType?: string, model?: string, workspaceId?: number | null) =>
    request<AiTaskDescription>('/api/ai/task-description', {
      method: 'POST',
      body: JSON.stringify({ title, client: client || null, task_type: taskType || null, model: model ?? null, workspace_id: workspaceId ?? null }),
    }),
  seoReport: (data: { traffic?: string; positions: { key: string; was?: number | null; now?: number | null }[]; pages?: string; notes?: string }, model?: string) =>
    request<AiSeoReport>('/api/ai/seo-report', {
      method: 'POST',
      body: JSON.stringify({ ...data, model: model ?? null }),
    }),
  aiChat: (message: string, model?: string, workspaceId?: number | null) =>
    request<AiChatMessage>('/api/ai/chat', {
      method: 'POST',
      body: JSON.stringify({ message, model: model ?? null, workspace_id: workspaceId ?? null }),
    }),
  // Notes
  getNotes: (params?: string) => request<NotesListResponse>(`/api/notes${params ? `?${params}` : ''}`),
  getNote: (id: number) => request<Note>(`/api/notes/${id}`),
  createNote: (data: Record<string, any>) =>
    request<Note>('/api/notes', { method: 'POST', body: JSON.stringify(data) }),
  updateNote: (id: number, data: Record<string, any>) =>
    request<Note>(`/api/notes/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteNote: (id: number, permanent?: boolean) =>
    request<{ ok: boolean; permanent: boolean }>(`/api/notes/${id}${permanent ? '?permanent=true' : ''}`, { method: 'DELETE' }),
  archiveNote: (id: number) =>
    request<{ ok: boolean }>(`/api/notes/${id}/archive`, { method: 'POST' }),
  restoreNote: (id: number) =>
    request<Note>(`/api/notes/${id}/restore`, { method: 'POST' }),
  duplicateNote: (id: number) =>
    request<Note>(`/api/notes/${id}/duplicate`, { method: 'POST' }),
  getNoteFolders: () => request<NoteFolder[]>('/api/notes/folders'),
  createNoteFolder: (data: Record<string, any>) =>
    request<NoteFolder>('/api/notes/folders', { method: 'POST', body: JSON.stringify(data) }),
  updateNoteFolder: (id: number, data: Record<string, any>) =>
    request<NoteFolder>(`/api/notes/folders/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteNoteFolder: (id: number) =>
    request<{ ok: boolean; moved_notes: number }>(`/api/notes/folders/${id}`, { method: 'DELETE' }),

  // Workspaces
  getWorkspaces: (deleted?: boolean) => request<Workspace[]>(`/api/workspaces${deleted ? '?deleted=true' : ''}`),
  createWorkspace: (name: string, preset: string) =>
    request<Workspace>('/api/workspaces', { method: 'POST', body: JSON.stringify({ name, preset }) }),
  getWorkspace: (id: number) => request<WorkspaceDetail>(`/api/workspaces/${id}`),
  updateWorkspace: (id: number, data: Record<string, any>) =>
    request<Workspace>(`/api/workspaces/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteWorkspace: (id: number, permanent?: boolean) =>
    request<{ ok: boolean; permanent: boolean }>(`/api/workspaces/${id}${permanent ? '?permanent=true' : ''}`, { method: 'DELETE' }),
  restoreWorkspace: (id: number) =>
    request<{ ok: boolean }>(`/api/workspaces/${id}/restore`, { method: 'POST' }),
  getWsMembers: (id: number) => request<WorkspaceMember[]>(`/api/workspaces/${id}/members`),
  inviteWsMember: (id: number, username: string, role: string) => request(`/api/workspaces/${id}/members`, { method: 'POST', body: JSON.stringify({ username, role }) }),
  addWsMember: (id: number, userId: number, role: string) =>
    request<WorkspaceMember>(`/api/workspaces/${id}/members`, {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, role }),
    }),
  updateWsMember: (id: number, userId: number, role: string) =>
    request<WorkspaceMember>(`/api/workspaces/${id}/members/${userId}`, {
      method: 'PATCH',
      body: JSON.stringify({ role }),
    }),
  removeWsMember: (id: number, userId: number) =>
    request<{ ok: boolean }>(`/api/workspaces/${id}/members/${userId}`, { method: 'DELETE' }),
  getWsKnowledge: (id: number) => request<{ id: number; fact: string; created_at: string | null }[]>(`/api/workspaces/${id}/knowledge`),
  addWsKnowledge: (id: number, fact: string) =>
    request<{ id: number; fact: string }>(`/api/workspaces/${id}/knowledge`, {
      method: 'POST',
      body: JSON.stringify({ fact }),
    }),
  deleteWsKnowledge: (id: number, factId: number) =>
    request<{ ok: boolean }>(`/api/workspaces/${id}/knowledge/${factId}`, { method: 'DELETE' }),

  // Workspace roles (Ф7)
  getWorkspaceAccess: (id: number) => request<WorkspaceAccessReport>(`/api/workspaces/${id}/access`),
  setWorkspaceAccess: (id: number, userId: number, data: { permissions: Record<string, boolean>; fields: FieldAccess }) =>
    request<{ ok: boolean }>(`/api/workspaces/${id}/members/${userId}/access`, { method: 'PUT', body: JSON.stringify(data) }),
  getWsRoles: (id: number, deleted = false) => request<WorkspaceRolesResponse>(`/api/workspaces/${id}/roles${deleted ? '?deleted=true' : ''}`),
  createWsRole: (id: number, data: { name: string; permissions: Record<string, boolean>; field_access?: FieldAccess }) =>
    request<WorkspaceRole>(`/api/workspaces/${id}/roles`, { method: 'POST', body: JSON.stringify(data) }),
  updateWsRole: (id: number, roleId: number, data: { name?: string; permissions?: Record<string, boolean>; field_access?: FieldAccess }) =>
    request<WorkspaceRole>(`/api/workspaces/${id}/roles/${roleId}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteWsRole: (id: number, roleId: number) =>
    request<{ ok: boolean }>(`/api/workspaces/${id}/roles/${roleId}`, { method: 'DELETE' }),
  restoreWsRole: (id: number, roleId: number) => request<{ ok: boolean }>(`/api/workspaces/${id}/roles/${roleId}/restore`, { method: 'POST' }),
  setWsMemberRole: (id: number, userId: number, roleId: number | null) =>
    request<WorkspaceMember>(`/api/workspaces/${id}/members/${userId}/custom-role`, {
      method: 'PUT',
      body: JSON.stringify({ role_id: roleId }),
    }),

  // Sprints
  getSprints: () => request<Sprint[]>('/api/sprints'),
  createSprint: (data: Record<string, any>) =>
    request<Sprint>('/api/sprints', { method: 'POST', body: JSON.stringify(writableFields('sprints', data, currentFieldAccess())) }),
  getSprint: (id: number) => request<SprintDetail>(`/api/sprints/${id}`),
  updateSprint: (id: number, data: Record<string, any>) =>
    request<Sprint>(`/api/sprints/${id}`, { method: 'PATCH', body: JSON.stringify(writableFields('sprints', data, currentFieldAccess())) }),
  deleteSprint: (id: number) =>
    request<{ ok: boolean }>(`/api/sprints/${id}`, { method: 'DELETE' }),
  addSprintTasks: (id: number, taskIds: number[]) =>
    request<{ ok: boolean }>(`/api/sprints/${id}/tasks`, {
      method: 'POST',
      body: JSON.stringify({ task_ids: taskIds }),
    }),
  removeSprintTask: (id: number, taskId: number) =>
    request<{ ok: boolean }>(`/api/sprints/${id}/tasks/${taskId}`, { method: 'DELETE' }),
};
