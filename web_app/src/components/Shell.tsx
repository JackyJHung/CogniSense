import { motion } from "framer-motion";
import { Brain } from "lucide-react";
import type { ReactNode } from "react";

interface ShellProps {
  children: ReactNode;
  sidebar?: ReactNode;
}

export function Shell({ children, sidebar }: ShellProps) {
  return (
    <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-8 px-6 py-8 lg:flex-row">
      {/* Below lg the sidebar follows the page instead of disappearing. It
          holds Log out and Settings, and on a phone -- where the
          installed web app is the only app -- hiding it left no way to reach
          either. */}
      {sidebar && (
        <motion.aside
          initial={{ opacity: 0, x: -16 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4, ease: "easeOut" }}
          className="order-last flex w-full flex-col gap-6 lg:order-none lg:w-72 lg:shrink-0"
        >
          {sidebar}
        </motion.aside>
      )}
      <main className="flex-1 min-w-0">{children}</main>
    </div>
  );
}

export function CenteredShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <motion.div
        initial={{ opacity: 0, y: 12, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
        className="w-full max-w-md"
      >
        <div className="mb-8 flex items-center justify-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 shadow-lg shadow-brand-500/30">
            <Brain className="h-6 w-6 text-white" />
          </div>
          <span className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
            CogniSense
          </span>
        </div>
        {children}
      </motion.div>
    </div>
  );
}
