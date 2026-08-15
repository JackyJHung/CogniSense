import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, CheckCircle2, KeyRound, Mail, ShieldCheck, TriangleAlert } from "lucide-react";
import { Shell } from "@/components/Shell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Disclaimer } from "@/components/Disclaimer";
import {
  api,
  type AuthResult,
  type GenericMessage,
  type RecoveryCodes,
  type RecoveryStatus,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

export function SecurityPage() {
  const navigate = useNavigate();
  const { user, signIn } = useAuth();

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [pwBusy, setPwBusy] = useState(false);
  const [pwError, setPwError] = useState<string | null>(null);
  const [pwDone, setPwDone] = useState(false);

  const [email, setEmail] = useState("");
  const [emailPassword, setEmailPassword] = useState("");
  const [emailBusy, setEmailBusy] = useState(false);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [emailNote, setEmailNote] = useState<string | null>(null);

  const [status, setStatus] = useState<RecoveryStatus | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [codeWarning, setCodeWarning] = useState<string>("");
  const [codeBusy, setCodeBusy] = useState(false);
  const [codeError, setCodeError] = useState<string | null>(null);

  const refreshStatus = useCallback(async () => {
    try {
      setStatus(await api.get<RecoveryStatus>("/recovery/status"));
    } catch {
      /* not fatal; the card just shows nothing */
    }
  }, []);

  useEffect(() => {
    void refreshStatus();
  }, [refreshStatus]);

  if (!user) return null;

  async function changePassword(e: FormEvent) {
    e.preventDefault();
    setPwError(null);
    setPwDone(false);
    if (next !== confirm) {
      setPwError("The two new passwords don't match.");
      return;
    }
    setPwBusy(true);
    try {
      const auth = await api.post<AuthResult>("/users/password", {
        current_password: current,
        new_password: next,
      });
      // Every other session was revoked; this one was re-issued.
      signIn(auth.user);
      setCurrent("");
      setNext("");
      setConfirm("");
      setPwDone(true);
    } catch (err) {
      setPwError(err instanceof Error ? err.message : "Could not change the password");
    } finally {
      setPwBusy(false);
    }
  }

  async function saveEmail(e: FormEvent) {
    e.preventDefault();
    setEmailBusy(true);
    setEmailError(null);
    setEmailNote(null);
    try {
      const r = await api.post<GenericMessage>("/recovery/email", {
        current_password: emailPassword,
        email,
      });
      setEmailNote(r.message);
      setEmailPassword("");
      await refreshStatus();
    } catch (err) {
      setEmailError(err instanceof Error ? err.message : "Could not save that address");
    } finally {
      setEmailBusy(false);
    }
  }

  async function generateCodes() {
    setCodeBusy(true);
    setCodeError(null);
    try {
      const r = await api.post<RecoveryCodes>("/recovery/codes");
      setCodes(r.codes);
      setCodeWarning(r.warning);
      await refreshStatus();
    } catch (err) {
      setCodeError(err instanceof Error ? err.message : "Could not generate codes");
    } finally {
      setCodeBusy(false);
    }
  }

  return (
    <Shell>
      <Button variant="ghost" onClick={() => navigate("/dashboard")} className="mb-6">
        <ArrowLeft className="h-4 w-4" /> Back to dashboard
      </Button>

      <header className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
          Password &amp; recovery
        </h1>
        <p className="mt-2 text-slate-600 dark:text-slate-400">
          Change your password, and set up a way back in if you forget it.
        </p>
      </header>

      <div className="space-y-6">
        {/* -------- password change -------- */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <KeyRound className="h-4 w-4 text-brand-500" /> Change password
            </CardTitle>
            <CardDescription>
              Changing it signs you out everywhere else. You'll stay signed in here.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={changePassword} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="current">Current password</Label>
                <Input
                  id="current"
                  type="password"
                  autoComplete="current-password"
                  value={current}
                  onChange={(e) => setCurrent(e.target.value)}
                  required
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="next">New password</Label>
                <Input
                  id="next"
                  type="password"
                  autoComplete="new-password"
                  minLength={8}
                  value={next}
                  onChange={(e) => setNext(e.target.value)}
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
              {pwError && <p className="text-sm text-rose-600 dark:text-rose-400">{pwError}</p>}
              {pwDone && (
                <p className="text-sm text-emerald-700 dark:text-emerald-300">
                  Password changed. Any other device is now signed out.
                </p>
              )}
              <Button type="submit" loading={pwBusy}>
                Change password
              </Button>
            </form>
          </CardContent>
        </Card>

        {/* -------- recovery email -------- */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Mail className="h-4 w-4 text-brand-500" /> Recovery email
            </CardTitle>
            <CardDescription>
              Optional. With a confirmed address you can have a reset link
              emailed to you instead of keeping codes.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {status?.email && (
              <p className="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-300">
                {status.email_verified ? (
                  <>
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                    <span>
                      <strong>{status.email}</strong> is confirmed and can reset
                      your password.
                    </span>
                  </>
                ) : (
                  <>
                    <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
                    <span>
                      <strong>{status.email}</strong> is not confirmed yet, so it
                      cannot be used to reset your password. Check your inbox for
                      the link, or enter the address again to resend it.
                    </span>
                  </>
                )}
              </p>
            )}

            {status && !status.email_delivery_enabled && (
              <p className="rounded-xl bg-amber-500/10 px-4 py-3 text-xs leading-relaxed text-amber-900 dark:text-amber-200">
                This server has no mail configured, so nothing is actually sent —
                confirmation and reset links are written to the server log
                instead. Recovery codes below work regardless.
              </p>
            )}

            <form onSubmit={saveEmail} className="flex flex-col gap-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="email">Email address</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="emailpw">Confirm with your password</Label>
                <Input
                  id="emailpw"
                  type="password"
                  autoComplete="current-password"
                  value={emailPassword}
                  onChange={(e) => setEmailPassword(e.target.value)}
                  required
                />
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Required so that nobody using your unlocked device can point
                  recovery at their own inbox.
                </p>
              </div>
              {emailError && (
                <p className="text-sm text-rose-600 dark:text-rose-400">{emailError}</p>
              )}
              {emailNote && (
                <p className="text-sm text-emerald-700 dark:text-emerald-300">{emailNote}</p>
              )}
              <Button type="submit" loading={emailBusy} variant="secondary">
                {status?.email ? "Update address" : "Add address"}
              </Button>
            </form>
          </CardContent>
        </Card>

        {/* -------- recovery codes -------- */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-brand-500" /> Recovery codes
            </CardTitle>
            <CardDescription>
              CogniSense has no email on file, so these codes are the only way back
              in if you forget your password.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {status && !codes && (
              <p className="text-sm text-slate-700 dark:text-slate-300">
                {status.has_codes
                  ? `${status.codes_remaining} unused code${
                      status.codes_remaining === 1 ? "" : "s"
                    } remaining${status.codes_used ? `, ${status.codes_used} already used` : ""}.`
                  : "You don't have any recovery codes yet."}
              </p>
            )}

            {codes && (
              <div>
                <p className="flex items-start gap-2 rounded-xl bg-amber-500/10 px-4 py-3 text-sm leading-relaxed text-amber-900 dark:text-amber-200">
                  <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
                  {codeWarning}
                </p>
                <ul className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {codes.map((c) => (
                    <li
                      key={c}
                      className="rounded-lg bg-slate-900/[0.04] dark:bg-white/[0.06] px-3 py-2 text-center font-mono text-sm tracking-wider text-slate-800 dark:text-slate-200"
                    >
                      {c}
                    </li>
                  ))}
                </ul>
                <Button
                  variant="secondary"
                  className="mt-3"
                  onClick={() => window.print()}
                >
                  Print these
                </Button>
              </div>
            )}

            {codeError && <p className="text-sm text-rose-600 dark:text-rose-400">{codeError}</p>}

            <Button variant={codes ? "ghost" : "primary"} onClick={generateCodes} loading={codeBusy}>
              {status?.has_codes ? "Generate a new set" : "Generate recovery codes"}
            </Button>
            {status?.has_codes && (
              <p className="text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                Generating a new set immediately cancels every unused code from
                before — do that if you think somebody else has seen them.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <Disclaimer />
    </Shell>
  );
}
