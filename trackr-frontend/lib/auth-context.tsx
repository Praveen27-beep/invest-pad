"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, ApiError, setUnauthorizedHandler } from "./api-client";
import type { LoginRequest, RegisterRequest, TokenResponse, UserResponse } from "./api-types";

const TOKEN_KEY = "trackr.token";
const USER_KEY = "trackr.user";
const INVESTOR_KEY = "trackr.investor_id";
const ADVISED_ONLY_KEY = "trackr.advised_only";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

interface AuthState {
  token: string | null;
  user: UserResponse | null;
  investorId: string;
  ready: boolean;
  login: (body: LoginRequest) => Promise<void>;
  register: (body: RegisterRequest) => Promise<void>;
  logout: () => void;
  setInvestorId: (id: string) => void;
  // Shared header controls -- as_of and advised_only are query params every
  // holdings/summary/performance call accepts (contracts/openapi.yaml), kept here so
  // every page reads/writes the same value instead of duplicating local state.
  asOf: string;
  setAsOf: (date: string) => void;
  advisedOnly: boolean;
  setAdvisedOnly: (value: boolean) => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<UserResponse | null>(null);
  const [investorId, setInvestorIdState] = useState<string>("");
  const [asOf, setAsOfState] = useState<string>(today());
  const [advisedOnly, setAdvisedOnlyState] = useState<boolean>(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setToken(localStorage.getItem(TOKEN_KEY));
    const storedUser = localStorage.getItem(USER_KEY);
    if (storedUser) {
      try {
        setUser(JSON.parse(storedUser));
      } catch {
        /* ignore malformed cache */
      }
    }
    // The investor id is NOT restored from a shared default: two browsers (or two
    // accounts on one machine) reading one localStorage key -- or worse, one
    // build-time env var -- is exactly how different accounts ended up looking at the
    // same portfolio. It arrives per-login in TokenResponse and lives only for this
    // session.
    setInvestorIdState(localStorage.getItem(INVESTOR_KEY) ?? "");
    setAdvisedOnlyState(localStorage.getItem(ADVISED_ONLY_KEY) === "true");
    setReady(true);
  }, []);

  const setAsOf = useCallback((date: string) => setAsOfState(date), []);

  const setAdvisedOnly = useCallback((value: boolean) => {
    localStorage.setItem(ADVISED_ONLY_KEY, String(value));
    setAdvisedOnlyState(value);
  }, []);

  const applySession = useCallback((res: TokenResponse) => {
    localStorage.setItem(TOKEN_KEY, res.token);
    localStorage.setItem(USER_KEY, JSON.stringify(res.user));
    // The server is the only source of "which investor am I". Overwrite whatever a
    // previous session left here -- never merge across accounts.
    if (res.investor_id) {
      localStorage.setItem(INVESTOR_KEY, res.investor_id);
    } else {
      localStorage.removeItem(INVESTOR_KEY);
    }
    setToken(res.token);
    setUser(res.user);
    setInvestorIdState(res.investor_id ?? "");
  }, []);

  const login = useCallback(
    async (body: LoginRequest) => {
      const res = await api.post<TokenResponse>("/auth/login", { json: body });
      applySession(res);
    },
    [applySession]
  );

  const register = useCallback(
    async (body: RegisterRequest) => {
      const res = await api.post<TokenResponse>("/auth/register", { json: body });
      applySession(res);
    },
    [applySession]
  );

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    // The investor id belongs to the session, not the browser -- leaving it behind is
    // how the next login starts from someone else's portfolio.
    localStorage.removeItem(INVESTOR_KEY);
    setToken(null);
    setUser(null);
    setInvestorIdState("");
  }, []);

  const setInvestorId = useCallback((id: string) => {
    localStorage.setItem(INVESTOR_KEY, id);
    setInvestorIdState(id);
  }, []);

  useEffect(() => {
    // One in-flight refresh shared by every request that hits a dead token at the
    // same moment -- N pages loading at once must not fire N refreshes. The current
    // token is read from localStorage at call time, not from this closure's state,
    // so a second tab that already rotated the session picks up the newer token
    // instead of replaying the revoked one.
    let refreshInFlight: Promise<string | null> | null = null;
    setUnauthorizedHandler(async () => {
      const current = localStorage.getItem(TOKEN_KEY);
      if (!current) return null;
      if (!refreshInFlight) {
        const run = async (): Promise<string | null> => {
          try {
            const res = await api.post<TokenResponse>("/auth/refresh", { token: current });
            applySession(res);
            return res.token;
          } catch {
            logout();
            return null;
          }
        };
        refreshInFlight = run().finally(() => {
          refreshInFlight = null;
        });
      }
      return refreshInFlight;
    });
    return () => setUnauthorizedHandler(null);
  }, [applySession, logout]);

  const value = useMemo(
    () => ({
      token,
      user,
      investorId,
      ready,
      login,
      register,
      logout,
      setInvestorId,
      asOf,
      setAsOf,
      advisedOnly,
      setAdvisedOnly,
    }),
    [
      token,
      user,
      investorId,
      ready,
      login,
      register,
      logout,
      setInvestorId,
      asOf,
      setAsOf,
      advisedOnly,
      setAdvisedOnly,
    ]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

export { ApiError };
