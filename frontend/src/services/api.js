/**
 * CloudSense — API Client
 * Centralized API communication with Neon Auth (x-user-id header).
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

class ApiClient {
  constructor() {
    this.baseURL = API_BASE;
    this._userId = localStorage.getItem('cloudsense_user_id');
    this._userEmail = localStorage.getItem('cloudsense_user_email');
    this._userName = localStorage.getItem('cloudsense_user_name');
  }

  // ── Neon Auth User Management ──
  setUser(user) {
    this._userId = user.id;
    this._userEmail = user.email;
    this._userName = user.name || user.email?.split('@')[0] || 'User';
    localStorage.setItem('cloudsense_user_id', user.id);
    localStorage.setItem('cloudsense_user_email', user.email || '');
    localStorage.setItem('cloudsense_user_name', this._userName);
  }

  getUser() {
    if (!this._userId) return null;
    return {
      id: this._userId,
      email: this._userEmail,
      name: this._userName,
    };
  }

  isLoggedIn() {
    return !!this._userId;
  }

  logout() {
    this._userId = null;
    this._userEmail = null;
    this._userName = null;
    localStorage.removeItem('cloudsense_user_id');
    localStorage.removeItem('cloudsense_user_email');
    localStorage.removeItem('cloudsense_user_name');
    window.location.href = '/';
  }

  // ── Internal: build headers with x-user-id ──
  _authHeaders(extra = {}) {
    const headers = { ...extra };
    if (this._userId) {
      headers['x-user-id'] = this._userId;
    }
    return headers;
  }

  // ── Request helper ──
  async request(method, path, body = null, options = {}) {
    const headers = this._authHeaders({ 'Content-Type': 'application/json' });

    const config = { method, headers, ...options };
    if (body && method !== 'GET') config.body = JSON.stringify(body);

    const response = await fetch(`${this.baseURL}${path}`, config);

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(err.detail || `Error ${response.status}`);
    }

    return response.json();
  }

  // ── Upload (requires Neon Auth) ──
  async uploadFile(file, onProgress = null) {
    const formData = new FormData();
    formData.append('file', file);

    if (!this._userId) {
      throw new Error('Authentication required. Please log in first.');
    }

    const response = await fetch(`${this.baseURL}/api/upload`, {
      method: 'POST',
      headers: { 'x-user-id': this._userId },
      body: formData,
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(err.detail || 'Upload failed');
    }

    return response.json();
  }

  // ── Dashboard (public — no auth needed) ──
  async getDashboardStats() {
    return this.request('GET', '/api/dashboard/stats');
  }

  async getRecentAnalyses(limit = 10) {
    return this.request('GET', `/api/analyses/recent?limit=${limit}`);
  }

  async getClusters(limit = 50) {
    return this.request('GET', `/api/analysis/clusters?limit=${limit}`);
  }

  // ── Exports (public) ──
  async getExports() {
    return this.request('GET', '/api/exports');
  }

  // ── Downloads ──
  async downloadFile(path, filename) {
    const response = await fetch(`${this.baseURL}${path}`, {
      headers: this._authHeaders(),
    });
    if (!response.ok) throw new Error('Download failed');

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  }

  // ── MOSDAC SSE ──
  startMosdacDownload(username, password, hoursBack) {
    const url = `${this.baseURL}/api/mosdac/download`;

    return new Promise((resolve, reject) => {
      fetch(url, {
        method: 'POST',
        headers: this._authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          username,
          password,
          hours_back: hoursBack,
        }),
      }).then(response => {
        if (!response.ok) {
          reject(new Error('MOSDAC download failed'));
          return;
        }
        resolve(response);
      }).catch(reject);
    });
  }
}

const apiClient = new ApiClient();
export default apiClient;
