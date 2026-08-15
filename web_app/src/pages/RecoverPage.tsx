import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { CenteredShell } from "@/components/Shell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Disclaimer } from "@/components/Disclaimer";
import { api, type AuthResult, type GenericMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export function RecoverPage() {
  const navigate = useNavigate();
  const { signIn } = useAuth();
  const [username, setUsername] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [linkIdentifier, setLinkIdentifier] = useState("");
  const [linkBusy, setLinkBusy] = useState(false);
  const [linkNote, setLinkNote] = useState<string | null>(null);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("The two passwords don't match.");
      return;
    }
    setLoading(true);
    try {
      const auth = await api.post<AuthResult>("/recovery/reset", {
        username,
        code,
        new_password: password,
      });
      signIn(auth.user);
      navigate("/dashboard");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "That username and code didn't match.",
      );
    } finally {
      setLoading(false);
    }
  };

  const emailReset = async (e: FormEvent) => {
    e.preventDefault();
    setLinkBusy(true);
    setLinkNote(null);
    try {
      const r = await api.post<GenericMessage>("/recovery/forgot", {
        identifier: linkIdentifier,
      });
      setLinkNote(r.message);
    } catch (err) {
      setLinkNote(
        err instanceof Error ? err.message : "Could not send a reset link right now.",
      );
    } finally {
      setLinkBusy(false);
    }
  };

  return (
    <CenteredShell>
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Email me a reset link</CardTitle>
          <CardDescription>
            If you added an email address and confirmed it, we can send you a
            link instead.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={emailReset} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="identifier">Username or email</Label>
              <Input
                id="identifier"
                autoComplete="username"
                value={linkIdentifier}
                onChange={(e) => setLinkIdentifier(e.target.value)}
                required
              />
            </div>
            {linkNote && (
              <p className="text-sm leading-relaxed text-slate-600 dark:text-slate-400">
                {linkNote}
              </p>
            )}
            <Button type="submit" variant="secondary" loading={linkBusy}>
              Send a reset link
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Use a recovery code</CardTitle>
          <CardDescription>
            Enter one of the codes you saved when you set up recovery. Each code
            works once.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                autoFocus
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="code">Recovery code</Label>
              <Input
                id="code"
                placeholder="ABCDE-FGHJK-MNPQR-STUVW"
                className="font-mono tracking-wider"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                required
              />
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Capitals and dashes don't matter.
              </p>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="password">New password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
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
              Reset password
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-500 dark:text-slate-400">
            Remembered it?{" "}
            <Link to="/login" className="font-medium text-brand-600 dark:text-brand-400">
              Sign in
            </Link>
          </p>
          <p className="mt-3 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
            No codes and no confirmed email? Then the account cannot be
            recovered — there is nothing left that proves it is yours. Sign up
            again, and add a recovery email or generate codes straight away.
          </p>
        </CardContent>
      </Card>
      <Disclaimer />
    </CenteredShell>
  );
}
