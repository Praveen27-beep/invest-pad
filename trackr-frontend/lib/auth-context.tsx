"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "./api-client";
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
    setInvestorIdState(
      localStorage.getItem(INVESTOR_KEY) ?? process.env.NEXT_PUBLIC_DEFAULT_INVESTOR_ID ?? ""
    );
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
    setToken(res.token);
    setUser(res.user);
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
    setToken(null);
    setUser(null);
  }, []);

  const setInvestorId = useCallback((id: string) => {
    localStorage.setItem(INVESTOR_KEY, id);
    setInvestorIdState(id);
  }, []);

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
