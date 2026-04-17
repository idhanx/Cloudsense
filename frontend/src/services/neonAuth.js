/**
 * CloudSense — Auth Service
 * Authenticates against the CloudSense backend (/api/auth/login, /api/auth/signup).
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const authClient = {
  signIn: {
    email: async ({ email, password }) => {
      if (!email || !password) {
        return { data: null, error: { message: 'Email and password are required' } };
      }
      try {
        const response = await fetch(`${API_BASE}/api/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        });
        const body = await response.json();
        if (!response.ok) {
          return { data: null, error: { message: body.detail || 'Login failed' } };
        }
        return { data: { user: body.user, token: body.access_token }, error: null };
      } catch (err) {
        return { data: null, error: { message: 'Network error. Please try again.' } };
      }
    },
  },

  signUp: {
    email: async ({ email, password, name }) => {
      if (!email || !password) {
        return { data: null, error: { message: 'Email and password are required' } };
      }
      try {
        const response = await fetch(`${API_BASE}/api/auth/signup`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password, username: name || email.split('@')[0] }),
        });
        const body = await response.json();
        if (!response.ok) {
          return { data: null, error: { message: body.detail || 'Signup failed' } };
        }
        return { data: { user: body.user, token: body.access_token }, error: null };
      } catch (err) {
        return { data: null, error: { message: 'Network error. Please try again.' } };
      }
    },
  },

  getSession: async () => {
    const userId = localStorage.getItem('cloudsense_user_id');
    const email = localStorage.getItem('cloudsense_user_email');
    const name = localStorage.getItem('cloudsense_user_name');
    if (!userId) return { data: null, error: { message: 'No session' } };
    return {
      data: { user: { id: userId, email, name } },
      error: null,
    };
  },

  signOut: async () => {
    localStorage.removeItem('cloudsense_user_id');
    localStorage.removeItem('cloudsense_user_email');
    localStorage.removeItem('cloudsense_user_name');
    return { error: null };
  },
};
