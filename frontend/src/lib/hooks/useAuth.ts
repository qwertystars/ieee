import { create } from 'zustand';

interface AuthState {
  user: { id: string; name: string; email: string; role: string } | null;
  token: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

// Renamed from p4's `useAuth` to avoid conflicting with the current repo's
// existing `useAuth()` hook exported from auth/AuthContext.tsx.
export const useP4Auth = create<AuthState>((set) => ({
  user: null,
  token: localStorage.getItem('token'),
  login: async (email, password) => {
    const res = await fetch('/api/security/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) throw new Error('Login failed');
    const data = await res.json();
    localStorage.setItem('token', data.token);
    set({ user: data.user, token: data.token });
  },
  logout: () => {
    localStorage.removeItem('token');
    set({ user: null, token: null });
  },
}));
