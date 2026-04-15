/**
 * CloudSense — Auth Service
 * Local auth using localStorage. No external auth service required.
 */

// Minimal auth client — stores user locally, no backend auth needed
export const authClient = {
  signIn: {
    email: async ({ email, password }) => {
      // Simple local auth — accept any email/password
      if (!email || !password) {
        return { data: null, error: { message: 'Email and password are required' } };
      }
      const user = {
        id: email,
        email,
        name: email.split('@')[0],
      };
      return { data: { user }, error: null };
    },
  },

  signUp: {
    email: async ({ email, password, name }) => {
      if (!email || !password) {
        return { data: null, error: { message: 'Email and password are required' } };
      }
      const user = {
        id: email,
        email,
        name: name || email.split('@')[0],
      };
      return { data: { user }, error: null };
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
