"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api, getRefreshToken, getToken, setTokens } from "./api";
import type { Role, TokenPair, User } from "./types";

const RANK: Record<Role, number> = { viewer: 0, operator: 1, admin: 2 };

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hasRole: (required: Role) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    (async () => {
      if (getToken()) {
        try {
          const me = await api.get<User>("/auth/me");
          if (active) setUser(me);
        } catch {
          setTokens(null, null);
        }
      }
      if (active) setLoading(false);
    })();
    return () => {
      active = false;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const tp = await api.post<TokenPair>("/auth/login", { email, password });
    setTokens(tp.access_token, tp.refresh_token);
    setUser(await api.get<User>("/auth/me"));
  }, []);

  const logout = useCallback(async () => {
    const refresh = getRefreshToken();
    if (refresh) {
      try {
        await api.post("/auth/logout", { refresh_token: refresh });
      } catch {
        // best-effort; clear locally regardless
      }
    }
    setTokens(null, null);
    setUser(null);
  }, []);

  const hasRole = useCallback(
    (required: Role) => Boolean(user) && RANK[user!.role] >= RANK[required],
    [user],
  );

  const value = useMemo(
    () => ({ user, loading, login, logout, hasRole }),
    [user, loading, login, logout, hasRole],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
