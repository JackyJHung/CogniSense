import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { CenteredShell } from "@/components/Shell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Disclaimer } from "@/components/Disclaimer";
import { api, type AuthResult } from "@/lib/api";
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

  return (
    <CenteredShell>
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
            No codes saved? CogniSense holds no email address, so there is no
            reset link it could send. Without a code the account cannot be
            recovered — sign up again, and generate codes from Password &amp;
            recovery straight away.
          </p>
        </CardContent>
      </Card>
      <Disclaimer />
    </CenteredShell>
  );
}
