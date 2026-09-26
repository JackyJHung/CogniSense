import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { CenteredShell } from "@/components/Shell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Disclaimer } from "@/components/Disclaimer";
import { api, type AuthResult } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { deviceTimeZone } from "@/lib/timezone";

export function LoginPage() {
  const navigate = useNavigate();
  const { signIn } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      // An account from before time zones existed adopts this device's; the
      // server never lets a login move a zone that is already set.
      const auth = await api.post<AuthResult>("/users/login", {
        username,
        password,
        timezone: deviceTimeZone(),
      });
      signIn(auth.user);
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <CenteredShell>
      <Card>
        <CardHeader>
          <CardTitle>Welcome back</CardTitle>
          <CardDescription>Sign in to continue your daily check-in.</CardDescription>
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
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {error && (
              <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>
            )}
            <Button type="submit" loading={loading} size="lg" className="mt-2">
              Log in
            </Button>
            <p className="text-center text-sm text-slate-500 dark:text-slate-400">
              No account?{" "}
              <Link to="/signup" className="font-medium text-brand-600 dark:text-brand-400 hover:underline">
                Create one
              </Link>
            </p>
            <p className="text-center text-sm text-slate-500 dark:text-slate-400">
              <Link to="/recover" className="font-medium text-brand-600 dark:text-brand-400 hover:underline">
                Forgotten your password?
              </Link>
            </p>
          </form>
        </CardContent>
      </Card>
      <Disclaimer />
    </CenteredShell>
  );
}
