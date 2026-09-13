import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import * as api from "./api";
import type { AuthUser, RateStatus } from "./types";

interface AuthCtx {
  user: AuthUser | null;
  loading: boolean;
  login: (u: string, p: string) => Promise<void>;
  signup: (u: string, p: string) => Promise<void>;
  logout: () => void;
  refreshRate: () => Promise<void>;
  setRate: (r: RateStatus) => void;
}

const Ctx = createContext<AuthCtx>(null as unknown as AuthCtx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!api.getToken()) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then((u) => {
        api.setToken(u.token);
        setUser(u);
      })
      .catch(() => {
        api.setToken(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (u: string, p: string) => {
    const res = await api.login(u, p);
    api.setToken(res.token);
    setUser(res);
  }, []);

  const signup = useCallback(async (u: string, p: string) => {
    const res = await api.signup(u, p);
    api.setToken(res.token);
    setUser(res);
  }, []);

  const logout = useCallback(() => {
    api.setToken(null);
    setUser(null);
  }, []);

  const refreshRate = useCallback(async () => {
    try {
      const rate = await api.getRate();
      setUser((u) => (u ? { ...u, rate } : u));
    } catch {
      /* ignore */
    }
  }, []);

  const setRate = useCallback((rate: RateStatus) => {
    setUser((u) => (u ? { ...u, rate } : u));
  }, []);

  return (
    <Ctx.Provider value={{ user, loading, login, signup, logout, refreshRate, setRate }}>
      {children}
    </Ctx.Provider>
  );
}

export const useAuth = () => useContext(Ctx);

export function formatCooldown(seconds: number): string {
  if (seconds <= 0) return "now";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}
