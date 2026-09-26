import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api, setUnauthorizedHandler, type User } from "./api";
import { AuthCtx } from "./auth";
import { deviceTimeZone } from "./timezone";

const STORAGE_KEY = "cognisense.session";

/* Only the profile is cached, for a first render before /users/me answers.
 * Today's morning check-in used to be cached here too; see useTodaysMorning
 * for why the pages now ask the server instead. */
function readStoredUser(): User | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return (JSON.parse(raw).user as User) ?? null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(readStoredUser);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ user }));
  }, [user]);

  const clearLocal = useCallback(() => {
    setUser(null);
    // Only cached profile data is dropped here. The session cookie is HttpOnly
    // and can only be cleared by the server, which /users/logout does.
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  // A lost session, once /users/me confirms it (see api.ts), drops us to the
  // login screen. Without this, a revoked or expired token leaves the UI
  // rendering a logged-in shell over endpoints that all fail.
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
        if (cancelled) return;
        setUser(me);
        // An account from before time zones existed has none, and with a
        // 30-day idle session its next login could be a month away. Fill it in
        // from this device now -- only when unset, the same rule the server
        // applies at login -- so the day starts at local midnight from today.
        const zone = deviceTimeZone();
        if (me.timezone === null && zone) {
          api.post<User>("/users/me/timezone", { timezone: zone }).then(
            (updated) => {
              if (!cancelled) setUser(updated);
            },
            () => undefined, // not fatal: Settings can still set it
          );
        }
      } catch {
        // A 401 has already signed us out through the handler above. Anything
        // else -- the server restarting during a deploy, a dropped connection --
        // says nothing about the session, and used to sign the person out all
        // the same. The cached user stays; the next real answer settles it.
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
    <AuthCtx.Provider value={{ user, signIn, setUser, logout, loading }}>
      {children}
    </AuthCtx.Provider>
  );
}
