import { createContext, useContext } from "react";
import type { User } from "./api";

/* The context and its hook live apart from <AuthProvider> (AuthProvider.tsx) so
 * that each module exports one kind of thing. React Fast Refresh can only
 * hot-swap a file whose exports are all components; mixing in a hook makes
 * every edit to the provider a full page reload. */

export interface AuthState {
  user: User | null;
  /** Records a successful login/signup. The session itself lives in an
   *  HttpOnly cookie the server set on the response, so there is no token to
   *  hold here -- only the profile, for rendering. */
  signIn: (user: User) => void;
  setUser: (u: User | null) => void;
  logout: () => void;
  /** True until the stored token has been checked against the server. */
  loading: boolean;
}

export const AuthCtx = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
