import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, getToken, setToken } from "../api/client";
import type { Token, User } from "../types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName: string) => Promise<void>;
  loginWithToken: (token: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const loadMe = useCallback(async () => {
    if (!getToken()) {
      setLoading(false);
      return;
    }
    try {
      const me = await api.get<User>("/api/auth/me");
      setUser(me);
    } catch {
      setToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadMe();
  }, [loadMe]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.post<Token>("/api/auth/login", { email, password });
    setToken(res.access_token);
    setUser(res.user);
  }, []);

  const register = useCallback(
    async (email: string, password: string, displayName: string) => {
      const res = await api.post<Token>("/api/auth/register", {
        email,
        password,
        display_name: displayName,
      });
      setToken(res.access_token);
      setUser(res.user);
    },
    [],
  );

  const loginWithToken = useCallback(async (token: string) => {
    setToken(token);
    const me = await api.get<User>("/api/auth/me");
    setUser(me);
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, register, loginWithToken, logout }),
    [user, loading, login, register, loginWithToken, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
