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
import { SecurityPage } from "@/pages/SecurityPage";
import { RecoverPage } from "@/pages/RecoverPage";
import { ResetPasswordPage, VerifyEmailPage } from "@/pages/TokenLandingPages";
import type { JSX } from "react";

function RequireAuth({ children }: { children: JSX.Element }) {
  const { user, loading } = useAuth();

  // Wait for the stored token to be checked against /users/me before deciding.
  // Without this the redirect wins the race on every page load: `user` starts
  // null, the check is async, and a perfectly valid session gets bounced to the
  // login screen. Refreshing any page would log you out.
  if (loading) return <SessionCheck />;

  if (!user) return <Navigate to="/login" replace />;
  return children;
}

/** Shown for the moment it takes to validate a stored session. */
function SessionCheck() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <span
        className="h-6 w-6 animate-spin rounded-full border-2 border-brand-500 border-r-transparent"
        role="status"
        aria-label="Checking your session"
      />
    </div>
  );
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
        <Route path="/security" element={<RequireAuth><PageTransition><SecurityPage /></PageTransition></RequireAuth>} />
        <Route path="/recover" element={<PageTransition><RecoverPage /></PageTransition>} />
        {/* Reached from an email link; the token in the URL is the credential,
            so these must NOT sit behind RequireAuth. */}
        <Route path="/verify-email" element={<PageTransition><VerifyEmailPage /></PageTransition>} />
        <Route path="/reset-password" element={<PageTransition><ResetPasswordPage /></PageTransition>} />
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
