import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { User, MorningCheckin } from "./api";

interface AuthState {
  user: User | null;
  morning: MorningCheckin | null;
  setUser: (u: User | null) => void;
  setMorning: (m: MorningCheckin | null) => void;
  logout: () => void;
}

const STORAGE_KEY = "cognisense.session";

const AuthCtx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    try { return JSON.parse(raw).user ?? null; } catch { return null; }
  });
  const [morning, setMorning] = useState<MorningCheckin | null>(() => {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    try { return JSON.parse(raw).morning ?? null; } catch { return null; }
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ user, morning }));
  }, [user, morning]);

  const logout = () => {
    setUser(null);
    setMorning(null);
    localStorage.removeItem(STORAGE_KEY);
  };

  return (
    <AuthCtx.Provider value={{ user, morning, setUser, setMorning, logout }}>
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
