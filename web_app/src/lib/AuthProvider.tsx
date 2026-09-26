import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  api,
  setUnauthorizedHandler,
  type MorningCheckin,
  type User,
} from "./api";
import { AuthCtx } from "./auth";

const STORAGE_KEY = "cognisense.session";

function readStored<T>(field: "user" | "morning"): T | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return (JSON.parse(raw)[field] as T) ?? null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => readStored<User>("user"));
  const [morning, setMorning] = useState<MorningCheckin | null>(() =>
    readStored<MorningCheckin>("morning"),
  );
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ user, morning }));
  }, [user, morning]);

  const clearLocal = useCallback(() => {
    setUser(null);
    setMorning(null);
    // Only cached profile data is dropped here. The session cookie is HttpOnly
    // and can only be cleared by the server, which /users/logout does.
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  // Any 401 from anywhere in the app drops us to the login screen. Without
  // this, a revoked or expired token leaves the UI rendering a logged-in shell
  // over endpoints that all fail.
  useEffect(() => {
    setUnauthorizedHandler(clearLocal);
    return () => setUnauthorizedHandler(null);
  }, [clearLocal]);

  // A cached user object is not proof of a valid session -- the cookie may have
  // expired or been revoked on another device, and we cannot inspect it from
  // script. Ask the server who we are before trusting it.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await api.get<User>("/users/me");
        if (!cancelled) setUser(me);
      } catch {
        if (!cancelled) clearLocal();
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // Runs once on mount; the token is read from module state inside api.ts.
  }, [clearLocal]);

  const signIn = useCallback((u: User) => {
    setUser(u);
  }, []);

  const logout = useCallback(() => {
    // Tell the server to actually end the session, then clear locally
    // regardless -- a failed call must not strand the user in a logged-in UI.
    void api.post("/users/logout", { all_devices: false }).catch(() => undefined);
    clearLocal();
  }, [clearLocal]);

  return (
    <AuthCtx.Provider
      value={{ user, morning, signIn, setUser, setMorning, logout, loading }}
    >
      {children}
    </AuthCtx.Provider>
  );
}
