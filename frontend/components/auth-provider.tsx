"use client";

import {
  createContext,
  PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState
} from "react";

import { getApiBaseUrl, readError } from "@/lib/api";
import type { AuthSessionResponse, AuthUser } from "@/lib/types";

type AuthContextValue = {
  user: AuthUser | null;
  ready: boolean;
  publicDemoEnabled: boolean;
  isPublicDemo: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<string | null>;
  authFetch: (path: string, init?: RequestInit) => Promise<Response>;
};

const AuthContext = createContext<AuthContextValue | null>(null);
const appEnv = (process.env.NEXT_PUBLIC_APP_ENV ?? "local").toLowerCase();
const publicDemoEnabled =
  (process.env.NEXT_PUBLIC_AUTH_PUBLIC_READONLY_DEMO ?? (appEnv === "production" ? "false" : "true")).toLowerCase() === "true" &&
  appEnv !== "production";

const publicDemoUser: AuthUser = {
  id: 0,
  email: "public-demo@invoice-audit.local",
  full_name: "Public Demo",
  role: "ops",
  is_public_demo: true
};

async function parseSessionResponse(response: Response) {
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return (await response.json()) as AuthSessionResponse;
}

export function AuthProvider({ children }: PropsWithChildren) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  const refreshSession = useCallback(async () => {
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/auth/me`, {
        credentials: "include",
        cache: "no-store"
      });
      if (!response.ok) {
        setUser(publicDemoEnabled ? publicDemoUser : null);
        setAccessToken(null);
        return null;
      }
      const payload = await parseSessionResponse(response);
      setUser(payload.user);
      setAccessToken(payload.access_token);
      return payload.access_token;
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    void refreshSession();
  }, [refreshSession]);

  const login = useCallback(async (email: string, password: string) => {
    const response = await fetch(`${getApiBaseUrl()}/api/auth/login`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password })
    });
    const payload = await parseSessionResponse(response);
    setUser(payload.user);
    setAccessToken(payload.access_token);
    setReady(true);
  }, []);

  const logout = useCallback(async () => {
    await fetch(`${getApiBaseUrl()}/api/auth/logout`, {
      method: "POST",
      credentials: "include"
    }).catch(() => undefined);
    setUser(null);
    setAccessToken(null);
  }, []);

  const authFetch = useCallback(
    async (path: string, init: RequestInit = {}) => {
      const execute = async (token: string | null) => {
        const headers = new Headers(init.headers);
        if (token) {
          headers.set("Authorization", `Bearer ${token}`);
        }
        return fetch(`${getApiBaseUrl()}${path}`, {
          ...init,
          headers,
          credentials: "include",
          cache: "no-store"
        });
      };

      let token = accessToken;
      if (!token) {
        token = await refreshSession();
      }

      const method = String(init.method || "GET").toUpperCase();
      if (!token && publicDemoEnabled && method === "GET") {
        const response = await execute(null);
        if (!response.ok) {
          throw new Error(await readError(response));
        }
        return response;
      }

      let response = await execute(token);
      if (response.status === 401) {
        token = await refreshSession();
        response = await execute(token);
      }

      if (!response.ok) {
        throw new Error(await readError(response));
      }
      return response;
    },
    [accessToken, refreshSession]
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      ready,
      publicDemoEnabled,
      isPublicDemo: Boolean(user?.is_public_demo),
      login,
      logout,
      refreshSession,
      authFetch
    }),
    [authFetch, login, logout, ready, refreshSession, user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
