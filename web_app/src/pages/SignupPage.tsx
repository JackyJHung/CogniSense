import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { CenteredShell } from "@/components/Shell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Disclaimer } from "@/components/Disclaimer";
import { api, type AuthResult } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const GENDERS = ["female", "male", "nonbinary", "other", "prefer_not"] as const;
const RACES = ["white", "black", "hispanic", "aapi", "ai_an", "other", "prefer_not"] as const;

const RACE_LABELS: Record<string, string> = {
  white: "White",
  black: "Black or African American",
  hispanic: "Hispanic or Latino",
  aapi: "Asian American / Pacific Islander",
  ai_an: "American Indian / Alaska Native",
  other: "Other",
  prefer_not: "Prefer not to say",
};

const GENDER_LABELS: Record<string, string> = {
  female: "Female",
  male: "Male",
  nonbinary: "Non-binary",
  other: "Other",
  prefer_not: "Prefer not to say",
};

export function SignupPage() {
  const navigate = useNavigate();
  const { signIn } = useAuth();
  const [form, setForm] = useState({
    username: "",
    password: "",
    age: "",
    gender: "female",
    race: "white",
    wake_time: "07:00",
    sleep_time: "23:00",
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const update = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const ageNum = Number.parseInt(form.age, 10);
      if (!Number.isFinite(ageNum) || ageNum < 18 || ageNum > 120) {
        throw new Error("Age must be between 18 and 120");
      }
      const payload = {
        ...form,
        age: ageNum,
        wake_time: form.wake_time.length === 5 ? `${form.wake_time}:00` : form.wake_time,
        sleep_time: form.sleep_time.length === 5 ? `${form.sleep_time}:00` : form.sleep_time,
      };
      const auth = await api.post<AuthResult>("/users/signup", payload);
      signIn(auth.user);
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-up failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <CenteredShell>
      <Card>
        <CardHeader>
          <CardTitle>Create your account</CardTitle>
          <CardDescription>
            Demographics help us compare your scores against age- and ethnicity-matched
            research benchmarks. They never leave your device.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2 flex flex-col gap-1.5">
                <Label htmlFor="username">Username</Label>
                <Input
                  id="username"
                  value={form.username}
                  onChange={(e) => update("username", e.target.value)}
                  required
                  minLength={3}
                />
              </div>
              <div className="col-span-2 flex flex-col gap-1.5">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  value={form.password}
                  onChange={(e) => update("password", e.target.value)}
                  required
                  minLength={6}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="age">Age</Label>
                <Input
                  id="age"
                  type="number"
                  min={18}
                  max={120}
                  value={form.age}
                  onChange={(e) => update("age", e.target.value)}
                  required
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="gender">Gender</Label>
                <Select id="gender" value={form.gender} onChange={(e) => update("gender", e.target.value as typeof form.gender)}>
                  {GENDERS.map((g) => <option key={g} value={g}>{GENDER_LABELS[g]}</option>)}
                </Select>
              </div>
              <div className="col-span-2 flex flex-col gap-1.5">
                <Label htmlFor="race">Race / ethnicity</Label>
                <Select id="race" value={form.race} onChange={(e) => update("race", e.target.value as typeof form.race)}>
                  {RACES.map((r) => <option key={r} value={r}>{RACE_LABELS[r]}</option>)}
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="wake_time">Wake time</Label>
                <Input id="wake_time" type="time" value={form.wake_time} onChange={(e) => update("wake_time", e.target.value)} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="sleep_time">Sleep time</Label>
                <Input id="sleep_time" type="time" value={form.sleep_time} onChange={(e) => update("sleep_time", e.target.value)} />
              </div>
            </div>
            {error && <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>}
            <Button type="submit" loading={loading} size="lg" className="mt-2">
              Create account
            </Button>
            <p className="text-center text-sm text-slate-500 dark:text-slate-400">
              Already have one?{" "}
              <Link to="/login" className="font-medium text-brand-600 dark:text-brand-400 hover:underline">
                Log in
              </Link>
            </p>
          </form>
        </CardContent>
      </Card>
      <Disclaimer />
    </CenteredShell>
  );
}
