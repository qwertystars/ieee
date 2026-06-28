const API_BASE = '/api';

function getToken(): string | null {
  return localStorage.getItem('drp_token');
}

function setToken(token: string | null): void {
  if (token) localStorage.setItem('drp_token', token);
  else localStorage.removeItem('drp_token');
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options.headers as Record<string, string>) ?? {}),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const resp = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ error: { message: resp.statusText } }));
    throw new Error(body?.error?.message ?? `HTTP ${resp.status}`);
  }

  const contentType = resp.headers.get('Content-Type') ?? '';
  if (contentType.includes('application/json')) return resp.json() as Promise<T>;
  return resp.text() as unknown as Promise<T>;
}

export const api = {
  getToken,
  setToken,

  async login(email: string, password: string): Promise<{ token: string; user: { id: string; email: string; name: string; role: string } }> {
    const result = await request<{ token: string; user: { id: string; email: string; name: string; role: string } }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    setToken(result.token);
    return result;
  },

  async logout(): Promise<void> {
    try { await request('/auth/logout', { method: 'POST' }); } catch { /* ignore */ }
    setToken(null);
  },

  async me(): Promise<{ id: string; email: string; name: string; role: string; orgId: string; status: string }> {
    return request('/auth/me');
  },

  async seedDemo(): Promise<Record<string, unknown>> {
    return request('/seed/demo', { method: 'POST' });
  },

  async getEvents(): Promise<{ items: Array<{ id: string; name: string; type: string; status: string; incidentId: string }> }> {
    return request('/events');
  },

  async getDashboardSummary(incidentId: string): Promise<{
    total_reports: number; roads_blocked: number; pending_tasks: number;
    shelters_open: number; alerts_active: number; critical_areas: number;
    high_areas: number; last_updated: number;
  }> {
    return request(`/events/${incidentId}/dashboard-summary`);
  },

  async getMapLayers(incidentId: string, bbox?: string): Promise<{
    areas: unknown[]; reports: unknown[]; roads: unknown[];
    shelters: unknown[]; teams: unknown[]; observations: unknown[]; tasks: unknown[];
  }> {
    const query = bbox ? `?bbox=${bbox}` : '';
    return request(`/events/${incidentId}/map-layers${query}`);
  },

  async getTasks(incidentId: string): Promise<{ items: Array<{ id: string; title: string; status: string; priority: string }> }> {
    return request(`/events/${incidentId}/tasks`);
  },

  async getReports(incidentId: string): Promise<{ items: unknown[] }> {
    return request(`/events/${incidentId}/reports`);
  },

  async getRoads(incidentId: string): Promise<{ items: Array<{ id: string; roadName: string; status: string }> }> {
    return request(`/events/${incidentId}/roads/status`);
  },

  async getTeams(incidentId: string): Promise<{ items: unknown[] }> {
    return request(`/events/${incidentId}/teams`);
  },

  async getShelters(incidentId: string): Promise<{ items: unknown[] }> {
    return request(`/events/${incidentId}/shelters`);
  },

  async getRecommendations(incidentId: string): Promise<{ items: Array<{ id: string; title: string; status: string }> }> {
    return request(`/events/${incidentId}/recommendations`);
  },

  async getAlerts(incidentId: string): Promise<{ items: unknown[] }> {
    return request(`/events/${incidentId}/alerts`);
  },

  async createReport(incidentId: string, data: {
    reporterType: string; reportCategory: string; description: string;
    geometry: { type: string; coordinates: number[] }; urgency: string;
  }): Promise<Record<string, unknown>> {
    return request(`/events/${incidentId}/reports`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async updateRoadStatus(roadId: string, data: { status: string; reason?: string; confidenceScore?: number }): Promise<Record<string, unknown>> {
    return request(`/roads/${roadId}/status`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  async updateTaskStatus(taskId: string, status: string): Promise<Record<string, unknown>> {
    return request(`/tasks/${taskId}`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    });
  },

  async approveRecommendation(incidentId: string, recId: string): Promise<Record<string, unknown>> {
    return request(`/events/${incidentId}/recommendations/${recId}/approve`, { method: 'POST' });
  },

  async dismissRecommendation(incidentId: string, recId: string): Promise<Record<string, unknown>> {
    return request(`/events/${incidentId}/recommendations/${recId}/dismiss`, { method: 'POST' });
  },

  async getSituationReport(incidentId: string, format: string = 'text'): Promise<string> {
    return request(`/events/${incidentId}/situation-report`, {
      method: 'POST',
      body: JSON.stringify({ format }),
    });
  },
};
