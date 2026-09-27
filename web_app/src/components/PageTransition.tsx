import { motion } from "framer-motion";
import type { ReactNode } from "react";

/* A short fade, as between iOS tabs. A long slide would fight the tab bar and
 * the navigation bar, which stay put while the page changes under them. */
export function PageTransition({ children }: { children: ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.18, ease: "easeOut" }}
      className="w-full"
    >
      {children}
    </motion.div>
  );
}
