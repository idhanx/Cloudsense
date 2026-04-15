// API client with automatic Bearer token injection
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function getAuthToken() {
  return localStorage.getItem('authToken');
}

export async function apiCall(endpoint, options = {}) {
  const token = getAuthToken();
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };
  
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  
  const response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers,
  });
  
  if (response.status === 401) {
    // Token invalid/expired, clear storage and redirect to login
    localStorage.removeItem('authToken');
    localStorage.removeItem('user');
    window.location.href = '/login';
  }
  
  return response;
}

export default apiCall;

