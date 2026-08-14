import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Sun, Sunrise, Sunset, Moon, TrendingUp, Sparkles, ListChecks, LogOut } from "lucide-react";
import { Shell } from "@/components/Shell";
import { Card, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Disclaimer } from "@/components/Disclaimer";
import { useAuth } from "@/lib/auth";

function greeting(hour: number) {
  if (hour < 11) return { label: "Good morning", icon: Sun };
  if (hour < 16) return { label: "Good afternoon", icon: Sun };
  if (hour < 21) return { label: "Good evening", icon: Sunset };
  return { label: "Hello", icon: Moon };
}

const TILES = [
  {
    to: "/morning",
    title: "Morning check-in",
    desc: "Log today's plans and view 5 image associations.",
    icon: Sunrise,
    accent: "from-orange-300/60 via-rose-200/40 to-amber-200/20",
    iconColor: "text-orange-500 dark:text-orange-300",
  },
  {
    to: "/midday",
    title: "Midday check-in",
    desc: "Quick recall of what you've done so far.",
    icon: Sun,
    accent: "from-yellow-200/60 to-amber-100/30",
    iconColor: "text-amber-500 dark:text-amber-300",
  },
  {
    to: "/evening",
    title: "Evening check-in",
    desc: "Recall today and take the image-association test.",
    icon: Moon,
    accent: "from-indigo-700/45 via-purple-800/35 to-violet-900/30",
    iconColor: "text-indigo-300 dark:text-indigo-200",
  },
  {
    to: "/report",
    title: "Risk report",
    desc: "Your scores compared to peer benchmarks.",
    icon: TrendingUp,
    accent: "from-rose-400/45 via-red-300/30 to-rose-200/20",
    iconColor: "text-rose-500 dark:text-rose-300",
  },
  {
    to: "/suggestions",
    title: "Daily suggestions",
    desc: "Personalized prevention guidance from research.",
    icon: Sparkles,
    accent: "from-emerald-300/55 via-teal-200/35 to-emerald-100/20",
    iconColor: "text-emerald-600 dark:text-emerald-300",
  },
  {
    to: "/reminders",
    title: "Things to remember",
    desc: "Save what you mean to do, then be reminded and tested on it.",
    icon: ListChecks,
    accent: "from-sky-300/55 via-cyan-200/35 to-sky-100/20",
    iconColor: "text-sky-600 dark:text-sky-300",
  },
];

export function DashboardPage() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  if (!user) return null;
  const { label } = greeting(new Date().getHours());

  const onLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <Shell
      sidebar={
        <>
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 text-lg font-semibold uppercase text-white shadow-md shadow-brand-500/30">
                  {user.username.slice(0, 2)}
                </div>
                <div>
                  <p className="text-sm text-slate-500 dark:text-slate-400">{label},</p>
                  <p className="text-lg font-semibold text-slate-900 dark:text-slate-100">{user.username}</p>
                </div>
              </div>
              <dl className="mt-5 grid grid-cols-2 gap-3 text-sm">
                <div>
                  <dt className="text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400">Age</dt>
                  <dd className="font-medium text-slate-900 dark:text-slate-100">{user.age}</dd>
                </div>
                <div>
                  <dt className="text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400">Wake</dt>
                  <dd className="font-medium text-slate-900 dark:text-slate-100">{user.wake_time.slice(0, 5)}</dd>
                </div>
                <div>
                  <dt className="text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400">Sleep</dt>
                  <dd className="font-medium text-slate-900 dark:text-slate-100">{user.sleep_time.slice(0, 5)}</dd>
                </div>
              </dl>
            </CardContent>
          </Card>
          <Button variant="ghost" onClick={onLogout} className="justify-start">
            <LogOut className="h-4 w-4" /> Log out
          </Button>
        </>
      }
    >
      <header className="mb-8">
        <p className="text-sm font-medium text-brand-600 dark:text-brand-400">{label}</p>
        <h1 className="mt-1 text-4xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
          What would you like to do?
        </h1>
      </header>

      <div className="grid gap-4 sm:grid-cols-2">
        {TILES.map((tile, i) => {
          const Icon = tile.icon;
          return (
            <motion.div
              key={tile.to}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.05 * i, ease: [0.22, 1, 0.36, 1] }}
              whileHover={{ y: -3 }}
            >
              <Link to={tile.to} className="block">
                <Card className="relative overflow-hidden transition-shadow hover:shadow-2xl hover:shadow-brand-500/10">
                  <div className={`absolute inset-0 -z-10 bg-gradient-to-br ${tile.accent} opacity-60`} />
                  <CardContent className="pt-6">
                    <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-white/85 dark:bg-white/10 shadow-sm ring-1 ring-black/5 dark:ring-white/10">
                      <Icon className={`h-5 w-5 ${tile.iconColor}`} />
                    </div>
                    <h3 className="mt-4 text-lg font-semibold text-slate-900 dark:text-slate-100">
                      {tile.title}
                    </h3>
                    <p className="mt-1 text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
                      {tile.desc}
                    </p>
                  </CardContent>
                </Card>
              </Link>
            </motion.div>
          );
        })}
      </div>

      <Disclaimer />
    </Shell>
  );
}
