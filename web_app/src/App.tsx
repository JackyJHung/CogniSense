import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import { AuthProvider, useAuth } from "@/lib/auth";
import { PageTransition } from "@/components/PageTransition";
import { LoginPage } from "@/pages/LoginPage";
import { SignupPage } from "@/pages/SignupPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { MorningPage } from "@/pages/MorningPage";
import { MiddayPage } from "@/pages/MiddayPage";
import { EveningPage } from "@/pages/EveningPage";
import { ReportPage } from "@/pages/ReportPage";
import { SuggestionsPage } from "@/pages/SuggestionsPage";
import { RemindersPage } from "@/pages/RemindersPage";
import type { JSX } from "react";

function RequireAuth({ children }: { children: JSX.Element }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function AnimatedRoutes() {
  const location = useLocation();
  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/login" element={<PageTransition><LoginPage /></PageTransition>} />
        <Route path="/signup" element={<PageTransition><SignupPage /></PageTransition>} />
        <Route path="/dashboard" element={<RequireAuth><PageTransition><DashboardPage /></PageTransition></RequireAuth>} />
        <Route path="/morning" element={<RequireAuth><PageTransition><MorningPage /></PageTransition></RequireAuth>} />
        <Route path="/midday" element={<RequireAuth><PageTransition><MiddayPage /></PageTransition></RequireAuth>} />
        <Route path="/evening" element={<RequireAuth><PageTransition><EveningPage /></PageTransition></RequireAuth>} />
        <Route path="/report" element={<RequireAuth><PageTransition><ReportPage /></PageTransition></RequireAuth>} />
        <Route path="/suggestions" element={<RequireAuth><PageTransition><SuggestionsPage /></PageTransition></RequireAuth>} />
        <Route path="/reminders" element={<RequireAuth><PageTransition><RemindersPage /></PageTransition></RequireAuth>} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AnimatePresence>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AnimatedRoutes />
      </BrowserRouter>
    </AuthProvider>
  );
}
