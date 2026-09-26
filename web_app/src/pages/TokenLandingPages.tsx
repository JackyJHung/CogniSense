/* The two pages a user reaches by clicking a link in an email.
 *
 * Both read their token from the query string and are reachable without a
 * session — the token in the link IS the credential. Neither ever displays the
 * token, so it does not end up in a screenshot or a support message.
 */
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { CheckCircle2, TriangleAlert } from "lucide-react";
import { CenteredShell } from "@/components/Shell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Disclaimer } from "@/components/Disclaimer";
import { api, type AuthResult, type GenericMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/* ---------------------------------------------------------------- verify */

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [outcome, setOutcome] = useState<{ ok: boolean; message: string } | null>(null);

  // The token is single-use, so it is sent at most once per token. StrictMode
  // runs effects twice in development, and the second POST -- finding the token
  // already consumed -- came back "invalid or expired" and could overwrite the
  // success that preceded it. For the same reason there is no ignore flag: the
  // one response that is ever requested must be the one shown.
  const sentFor = useRef<string | null>(null);

  useEffect(() => {
    if (!token || sentFor.current === token) return;
    sentFor.current = token;
    api.post<GenericMessage>("/recovery/email/verify", { token }).then(
      (r) => setOutcome({ ok: true, message: r.message }),
      (err) =>
        setOutcome({
          ok: false,
          message: err instanceof Error ? err.message : "That link is invalid or has expired.",
        }),
    );
  }, [token]);

  // A link with no token never reaches the server, so it is failed outright
  // rather than through state.
  const state: "working" | "done" | "failed" = !token
    ? "failed"
    : outcome === null
      ? "working"
      : outcome.ok
        ? "done"
        : "failed";
  const message = !token ? "That link is missing its confirmation code." : (outcome?.message ?? "");

  return (
    <CenteredShell>
      <Card>
        <CardHeader>
          <CardTitle>
            {state === "working" ? "Confirming your email…" : "Email confirmation"}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {state === "done" && (
            <p className="flex items-start gap-2 text-sm leading-relaxed text-emerald-700 dark:text-emerald-300">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
              {message}
            </p>
          )}
          {state === "failed" && (
            <p className="flex items-start gap-2 text-sm leading-relaxed text-amber-900 dark:text-amber-200">
              <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
              {message}
            </p>
          )}
          <Link to="/dashboard">
            <Button variant="secondary" className="w-full">
              Go to CogniSense
            </Button>
          </Link>
        </CardContent>
      </Card>
      <Disclaimer />
    </CenteredShell>
  );
}

/* ------------------------------------------------------- reset password */

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { signIn } = useAuth();
  const token = params.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("The two passwords don't match.");
      return;
    }
    setLoading(true);
    try {
      const auth = await api.post<AuthResult>("/recovery/reset-token", {
        token,
        new_password: password,
      });
      signIn(auth.user);
      navigate("/dashboard");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "That reset link is invalid or has expired.",
      );
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <CenteredShell>
        <Card>
          <CardHeader>
            <CardTitle>Reset link incomplete</CardTitle>
            <CardDescription>
              That link is missing its reset code. Request a new one.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link to="/recover">
              <Button className="w-full">Back to recovery</Button>
            </Link>
          </CardContent>
        </Card>
        <Disclaimer />
      </CenteredShell>
    );
  }

  return (
    <CenteredShell>
      <Card>
        <CardHeader>
          <CardTitle>Choose a new password</CardTitle>
          <CardDescription>
            Setting it signs out every device, including any you don't recognise.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="password">New password</Label>
              <Input
                id="password"
                type="password"
                autoFocus
                autoComplete="new-password"
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <p className="text-xs text-slate-500 dark:text-slate-400">
                At least 8 characters.
              </p>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="confirm">Repeat new password</Label>
              <Input
                id="confirm"
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
              />
            </div>
            {error && <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>}
            <Button type="submit" loading={loading}>
              Set new password
            </Button>
          </form>
        </CardContent>
      </Card>
      <Disclaimer />
    </CenteredShell>
  );
}
