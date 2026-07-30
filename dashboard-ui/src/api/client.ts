const API_BASE = '';

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || err.detail || `API error: ${res.status}`);
  }
  return res.json();
}

export type User = {
  id: number;
  username: string;
  created_at: string;
  roles: { id: number; name: string }[];
  permissions: Record<string, boolean>;
};

export type Task = {
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
  id: number;
  name: string;
  permissions: Record<string, boolean>;
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

export type ReportsData = {
  labels: string[];
  created: number[];
  done: number[];
  overdue: number[];
  status_dist: Record<string, number>;
  client_funnel: { total: number; active: number; paused: number; closed: number };
  client_tasks: { name: string; active: number; done: number }[];
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
  getUsers: () => request<User[]>('/api/users'),
  createUser: (username: string, password: string) =>
    request<{ id: number; username: string }>('/api/users', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  setUserRole: (userId: number, roleId: number) =>
    request<{ ok: boolean }>(`/api/users/${userId}/role`, {
      method: 'PUT',
      body: JSON.stringify({ role_id: roleId }),
    }),
  deleteUser: (userId: number) =>
    request<{ ok: boolean }>(`/api/users/${userId}`, { method: 'DELETE' }),

  // Roles
  getRoles: () => request<Role[]>('/api/roles'),
  createRole: (data: { name: string; permissions?: Record<string, boolean> }) =>
    request<Role>('/api/roles', { method: 'POST', body: JSON.stringify(data) }),
  updateRole: (id: number, data: Record<string, any>) =>
    request<{ ok: boolean }>(`/api/roles/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteRole: (id: number) => request<{ ok: boolean }>(`/api/roles/${id}`, { method: 'DELETE' }),

  // Tasks
  getTasks: (params?: string) => request<Task[]>(`/api/tasks/all${params ? `?${params}` : ''}`),
  getTasksPage: (params?: string) =>
    request<TaskListResponse>(`/api/tasks/all?paginated=1${params ? `&${params}` : ''}`),
  getTask: (id: number) => request<Task>(`/api/tasks/${id}`),
  getTaskAccesses: (id: number) => request<any[]>(`/api/tasks/${id}/accesses`),
  createTask: (data: Partial<Task>) =>
    request<Task>('/api/tasks', { method: 'POST', body: JSON.stringify(data) }),
  updateTask: (id: number, data: Partial<Task>) =>
    request<{ ok: boolean }>(`/api/tasks/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
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
  uploadFile: (taskId: number, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return fetch(`${API_BASE}/api/tasks/${taskId}/upload`, {
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
  uploadClientFile: (clientId: number, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return fetch(`${API_BASE}/api/clients/${clientId}/upload`, { method: 'POST', credentials: 'include', body: formData }).then(async response => {
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.error || body.detail || `API error: ${response.status}`);
      return body;
    });
  },
  getClientFiles: (clientId: number) => request<ClientFile[]>(`/api/clients/${clientId}/files`),
  deleteClientFile: (clientId: number, fileId: number) => request<{ ok: boolean }>(`/api/clients/${clientId}/files/${fileId}`, { method: 'DELETE' }),
  getClientFileUrl: (clientId: number, fileId: number) => `${API_BASE}/api/clients/${clientId}/files/${fileId}/download`,
  uploadContractFile: (clientId: number, contractId: number, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
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
  getReports: (months = 12) => request<ReportsData>(`/api/reports/data?months=${months}`),
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
};
