import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Brain,
  CalendarDays,
  ChartLine,
  ChevronLeft,
  ListChecks,
  LogOut,
  Settings,
  type LucideIcon,
} from "lucide-react";
import { IconTile } from "@/components/ui/List";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

/* The frame of every signed-in page, built the way an iOS app is: a large
 * title that hands over to a small one in a translucent navigation bar as the
 * page scrolls, a back button to the parent screen, and a tab bar. From lg up
 * the tab bar becomes an iPadOS-style sidebar. */

interface Tab {
  to: string;
  label: string;
  icon: LucideIcon;
  tone: Parameters<typeof IconTile>[0]["tone"];
  /** Screens opened from this tab, which keep it selected. */
  also: string[];
}

const TABS: Tab[] = [
  {
    to: "/dashboard",
    label: "Today",
    icon: CalendarDays,
    tone: "red",
    also: ["/morning", "/midday", "/evening", "/suggestions"],
  },
  { to: "/report", label: "Report", icon: ChartLine, tone: "pink", also: [] },
  { to: "/reminders", label: "Remember", icon: ListChecks, tone: "blue", also: [] },
  { to: "/security", label: "Settings", icon: Settings, tone: "gray", also: [] },
];

function useActiveTab(): string | null {
  const { pathname } = useLocation();
  return TABS.find((t) => t.to === pathname || t.also.includes(pathname))?.to ?? null;
}

interface ShellProps {
  title: string;
  children: ReactNode;
  /** Small caps line above the title, e.g. the date. */
  eyebrow?: ReactNode;
  subtitle?: ReactNode;
  /** The parent screen, shown as "‹ Today". */
  back?: { to: string; label: string };
  actions?: ReactNode;
}

export function Shell({ title, eyebrow, subtitle, back, actions, children }: ShellProps) {
  const titleRef = useRef<HTMLHeadingElement>(null);
  const [compact, setCompact] = useState(false);

  useEffect(() => {
    document.title = `${title} · CogniSense`;
  }, [title]);

  // Once the large title has scrolled under the bar, the bar takes its
  // material and shows the title small, as UINavigationController does.
  useEffect(() => {
    const el = titleRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(([entry]) => setCompact(!entry.isIntersecting), {
      rootMargin: "-52px 0px 0px 0px",
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="min-h-dvh">
      <Sidebar />
      <div className="lg:pl-[272px]">
        <header
          className={cn(
            "sticky top-0 z-30 pt-[env(safe-area-inset-top)] transition-[background-color,box-shadow] duration-200",
            compact
              ? "bg-bar shadow-[0_0.5px_0_var(--separator)] backdrop-blur-xl backdrop-saturate-[1.8]"
              : "bg-canvas/0",
          )}
        >
          <div className="mx-auto grid h-[52px] max-w-3xl grid-cols-[1fr_auto_1fr] items-center px-2 sm:px-4">
            <div className="justify-self-start">{back && <BackLink {...back} />}</div>
            <p
              aria-hidden="true"
              className={cn(
                "max-w-[50vw] truncate text-body font-semibold text-label transition-opacity duration-200",
                compact ? "opacity-100" : "opacity-0",
              )}
            >
              {title}
            </p>
            <div className="justify-self-end">{actions}</div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-3xl px-4 pb-[calc(env(safe-area-inset-bottom)+6rem)] sm:px-6 lg:pb-16">
          <div className="pt-1 pb-6">
            {eyebrow && <p className="text-footnote font-semibold uppercase text-label-2">{eyebrow}</p>}
            <h1 ref={titleRef} className="text-large-title font-bold tracking-tight text-label">
              {title}
            </h1>
            {subtitle && <p className="mt-1 text-subhead text-label-2">{subtitle}</p>}
          </div>
          {children}
        </main>
      </div>
      <TabBar />
    </div>
  );
}

function BackLink({ to, label }: { to: string; label: string }) {
  return (
    <Link
      to={to}
      className="-ml-1 flex h-11 items-center rounded-lg pr-2 text-body text-link outline-none active:opacity-60 focus-visible:ring-[3px] focus-visible:ring-tint/50"
    >
      <ChevronLeft aria-hidden="true" className="h-[26px] w-[26px]" strokeWidth={2.4} />
      {label}
    </Link>
  );
}

function TabBar() {
  const active = useActiveTab();
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-40 border-t-[0.5px] border-separator bg-bar pb-[env(safe-area-inset-bottom)] backdrop-blur-xl backdrop-saturate-[1.8] lg:hidden"
    >
      <ul className="mx-auto grid max-w-lg grid-cols-4">
        {TABS.map((tab) => {
          const on = active === tab.to;
          const Icon = tab.icon;
          return (
            <li key={tab.to}>
              <Link
                to={tab.to}
                aria-current={on ? "page" : undefined}
                className={cn(
                  "flex h-[50px] flex-col items-center justify-center gap-0.5 text-[10px] font-medium outline-none",
                  "focus-visible:bg-fill-2",
                  on ? "text-tint" : "text-ios-gray",
                )}
              >
                <Icon aria-hidden="true" className="h-6 w-6" strokeWidth={on ? 2.25 : 1.75} />
                {tab.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function Sidebar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const active = useActiveTab();
  return (
    <aside className="fixed inset-y-0 left-0 z-40 hidden w-[272px] flex-col border-r-[0.5px] border-separator bg-surface/70 px-3 pt-5 pb-4 backdrop-blur-xl lg:flex">
      <Link to="/dashboard" className="mb-6 flex items-center gap-2.5 rounded-lg px-2 outline-none focus-visible:ring-[3px] focus-visible:ring-tint/50">
        <AppIcon className="h-8 w-8" />
        <span className="text-title3 font-bold tracking-tight text-label">CogniSense</span>
      </Link>
      <nav aria-label="Main">
        <ul className="space-y-0.5">
          {TABS.map((tab) => {
            const on = active === tab.to;
            return (
              <li key={tab.to}>
                <Link
                  to={tab.to}
                  aria-current={on ? "page" : undefined}
                  className={cn(
                    "flex h-11 items-center gap-3 rounded-[10px] px-2 text-body outline-none transition-colors",
                    "focus-visible:ring-[3px] focus-visible:ring-tint/50",
                    on ? "bg-accent text-white" : "text-label hover:bg-fill-2",
                  )}
                >
                  <IconTile icon={tab.icon} tone={tab.tone} />
                  {tab.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="mt-auto border-t-[0.5px] border-separator pt-3">
        {user && (
          <div className="flex items-center gap-2.5 px-2 py-1.5">
            <Avatar name={user.username} className="h-8 w-8 text-footnote" />
            <span className="truncate text-subhead font-medium text-label">{user.username}</span>
          </div>
        )}
        <button
          type="button"
          onClick={() => {
            logout();
            navigate("/login");
          }}
          className="mt-1 flex h-11 w-full items-center gap-3 rounded-[10px] px-2 text-body text-danger outline-none transition-colors hover:bg-fill-2 focus-visible:ring-[3px] focus-visible:ring-tint/50"
        >
          <span className="flex h-[30px] w-[30px] items-center justify-center">
            <LogOut aria-hidden="true" className="h-5 w-5" />
          </span>
          Log Out
        </button>
      </div>
    </aside>
  );
}

/** A contact-style monogram: the first two letters on Apple's gray gradient. */
export function Avatar({ name, className }: { name: string; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "flex shrink-0 items-center justify-center rounded-full bg-gradient-to-b from-[#a5abb9] to-[#858994] font-semibold uppercase text-white",
        className,
      )}
    >
      {name.slice(0, 2)}
    </span>
  );
}

/** The app icon: a white mark on a blue gradient, in the iOS icon's rounded square. */
export function AppIcon({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "flex shrink-0 items-center justify-center rounded-[22.5%] bg-gradient-to-b from-[#3d9bff] to-[#0062e0]",
        className,
      )}
    >
      <Brain className="h-[58%] w-[58%] text-white" strokeWidth={1.75} />
    </span>
  );
}

/* Signed-out pages: centred like Apple's own sign-in, the app icon above the
 * title and the form below. */
export function CenteredShell({
  children,
  title = "CogniSense",
  subtitle,
}: {
  children: ReactNode;
  title?: string;
  subtitle?: ReactNode;
}) {
  useEffect(() => {
    document.title = title === "CogniSense" ? title : `${title} · CogniSense`;
  }, [title]);

  return (
    <div className="flex min-h-dvh justify-center px-4 pt-[max(3.5rem,env(safe-area-inset-top))] pb-12 sm:items-center">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
        className="w-full max-w-sm"
      >
        <div className="mb-7 flex flex-col items-center text-center">
          <AppIcon className="h-[72px] w-[72px] shadow-[0_10px_24px_-10px_rgb(0_98_224/0.6)]" />
          <h1 className="mt-5 text-title1 font-bold tracking-tight text-label">{title}</h1>
          {subtitle && <p className="mt-1.5 text-subhead text-label-2">{subtitle}</p>}
        </div>
        {children}
      </motion.div>
    </div>
  );
}
