"""
CogniSense desktop client (Tkinter).

Talks to the FastAPI backend at COGNISENSE_BACKEND (default
http://127.0.0.1:8000) through api_client.py, which holds the session token and
sends it with every request. Single-window multi-screen app:

  [Login / Signup]  ->  [Dashboard]  ->  one of:
      * Morning check-in
      * Midday check-in
      * Evening check-in (image-association test)
      * Report / risk comparison
      * Daily suggestions
      * Log out

Run:
    python desktop_app/main.py
The backend must be running first.
"""
from __future__ import annotations

import time
import tkinter as tk
import traceback
from datetime import datetime
from tkinter import ttk, messagebox, scrolledtext

try:
    import requests  # noqa: F401 -- api_client's transport
except ImportError:
    raise SystemExit("The desktop app needs the 'requests' package: pip install requests")

from api_client import (
    AlreadySubmitted,
    ApiError,
    CogniSenseClient,
    ServerUnreachable,
    SessionExpired,
    local_timezone,
)

BG = "#f5f6fa"

SESSION_ENDED = (
    "Your session has ended, so you have been signed out. This happens after "
    "a long time away, or when you change your password or sign out "
    "everywhere from another device. Please log in again."
)


def _clock(value: str, label: str) -> str:
    """'7:30' or '07:30' -> '07:30:00', the form the API expects."""
    try:
        return datetime.strptime(value.strip(), "%H:%M").strftime("%H:%M:00")
    except ValueError:
        raise ValueError(f"{label} should look like 07:30 (24-hour clock).") from None


class _Scrollable(tk.Frame):
    """A vertically scrolling page.

    The risk report runs longer than the window, and without this its last
    lines -- the Back button and the disclaimer -- were simply cut off.
    """

    def __init__(self, parent, bg):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind(
            "<Configure>",
            lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind(
            "<Configure>", lambda e: self.canvas.itemconfigure(window, width=e.width),
        )
        self.canvas.configure(yscrollcommand=bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.canvas.bind_all(
            "<MouseWheel>",
            lambda e: self.canvas.yview_scroll(int(-e.delta / 120), "units"),
        )

    def to_top(self):
        self.canvas.yview_moveto(0)


# ---------- Main App ----------

class CogniSenseApp(tk.Tk):
    def __init__(self, api: CogniSenseClient | None = None):
        super().__init__()
        self.title("CogniSense")
        self.geometry("780x640")
        self.configure(bg=BG)
        # The machine's zone goes with signup and login, so the account's day
        # turns over at local midnight; see api_client.local_timezone.
        self.api = api or CogniSenseClient(device_timezone=local_timezone())

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TButton", padding=8, font=("Helvetica", 11))
        style.configure("TLabel", background=BG, font=("Helvetica", 11))
        style.configure("Header.TLabel", font=("Helvetica", 18, "bold"), background=BG)
        style.configure("Disclaimer.TLabel", font=("Helvetica", 9, "italic"),
                        foreground="#606060", background=BG, wraplength=700)

        self._page = _Scrollable(self, BG)
        self._page.pack(fill="both", expand=True, padx=20, pady=20)
        self._container = self._page.inner

        self.show_login()

    # ---------- plumbing ----------

    def report_callback_exception(self, exc, val, tb):
        """Where any error raised inside a button handler ends up.

        Handling it here rather than in each handler means no screen can forget
        the one case that must never become a generic error box: a session
        that has ended goes back to the login screen and says why.
        """
        if isinstance(val, SessionExpired):
            self._session_ended()
        elif isinstance(val, (ApiError, ServerUnreachable)):
            messagebox.showerror("CogniSense", str(val))
        else:
            traceback.print_exception(exc, val, tb)
            messagebox.showerror("Unexpected error", f"{exc.__name__}: {val}")

    def _session_ended(self):
        self.api.forget()
        self.show_login(notice=SESSION_ENDED)

    def _clear(self):
        for w in self._container.winfo_children():
            w.destroy()
        self._page.to_top()

    def _header(self, text):
        ttk.Label(self._container, text=text, style="Header.TLabel").pack(pady=(0, 10))

    def _panel(self, title, body, bg, fg):
        box = tk.Frame(self._container, bg=bg, bd=1, relief="solid")
        box.pack(fill="x", pady=8, padx=10)
        tk.Label(box, text=title, font=("Helvetica", 12, "bold"), bg=bg, fg=fg,
                 ).pack(anchor="w", padx=10, pady=(8, 0))
        tk.Label(box, text=body, bg=bg, fg=fg, wraplength=660, justify="left",
                 ).pack(anchor="w", padx=10, pady=(2, 8))
        return box

    def _disclaimer(self, parent):
        ttk.Label(
            parent,
            text=(
                "CogniSense is a self-tracking tool, NOT a medical diagnostic device. "
                "Any output is a suggestion, not professional advice. If you notice worsening "
                "memory concerns, please consult a licensed physician."
            ),
            style="Disclaimer.TLabel",
        ).pack(fill="x", pady=(16, 0))

    # ---------- Login / Signup ----------

    def show_login(self, notice=None):
        self._clear()
        ttk.Label(self._container, text="CogniSense", style="Header.TLabel").pack(pady=(10, 4))
        ttk.Label(
            self._container,
            text="Early-risk screening for memory & cognition",
        ).pack(pady=(0, 16))

        if notice:
            tk.Label(self._container, text=notice, bg="#fff3cd", fg="#5c4400",
                     wraplength=600, justify="left", padx=12, pady=8).pack(pady=(0, 14))

        frm = tk.Frame(self._container, bg=BG)
        frm.pack()

        tk.Label(frm, text="Username", bg=BG).grid(row=0, column=0, sticky="e", padx=6, pady=6)
        username_e = ttk.Entry(frm, width=30)
        username_e.grid(row=0, column=1, pady=6)

        tk.Label(frm, text="Password", bg=BG).grid(row=1, column=0, sticky="e", padx=6, pady=6)
        password_e = ttk.Entry(frm, show="*", width=30)
        password_e.grid(row=1, column=1, pady=6)

        def do_login(_event=None):
            try:
                self.api.login(username_e.get().strip(), password_e.get())
            except ApiError as e:
                messagebox.showerror("Login failed", str(e))
                return
            self.show_dashboard()

        password_e.bind("<Return>", do_login)
        ttk.Button(self._container, text="Log in", command=do_login).pack(pady=10)
        ttk.Button(self._container, text="Create account", command=self.show_signup).pack()
        self._disclaimer(self._container)
        username_e.focus_set()

    def show_signup(self):
        self._clear()
        ttk.Label(self._container, text="Create account", style="Header.TLabel").pack(pady=(10, 20))

        frm = tk.Frame(self._container, bg=BG)
        frm.pack()

        fields = {}
        for i, (label, key, widget) in enumerate([
            ("Username", "username", "entry"),
            ("Password (8+ characters)", "password", "password"),
            ("Age", "age", "entry"),
            ("Gender", "gender", ("female", "male", "nonbinary", "other", "prefer_not")),
            ("Race/Ethnicity", "race", ("white", "black", "hispanic", "aapi", "ai_an", "other", "prefer_not")),
            ("Wake time (HH:MM)", "wake_time", "entry"),
            ("Sleep time (HH:MM)", "sleep_time", "entry"),
        ]):
            tk.Label(frm, text=label, bg=BG).grid(row=i, column=0, sticky="e", padx=6, pady=4)
            if widget == "entry":
                e = ttk.Entry(frm, width=30)
            elif widget == "password":
                e = ttk.Entry(frm, show="*", width=30)
            else:
                e = ttk.Combobox(frm, values=widget, width=28, state="readonly")
                e.set(widget[0])
            e.grid(row=i, column=1, pady=4)
            fields[key] = e
        fields["wake_time"].insert(0, "07:00")
        fields["sleep_time"].insert(0, "22:30")

        def do_signup():
            try:
                try:
                    age = int(fields["age"].get())
                except ValueError:
                    raise ValueError("Age should be a whole number.") from None
                payload = {
                    "username": fields["username"].get().strip(),
                    "password": fields["password"].get(),
                    "age": age,
                    "gender": fields["gender"].get(),
                    "race": fields["race"].get(),
                    "wake_time": _clock(fields["wake_time"].get(), "Wake time"),
                    "sleep_time": _clock(fields["sleep_time"].get(), "Sleep time"),
                }
                user = self.api.signup(**payload)
            except (ValueError, ApiError) as e:
                messagebox.showerror("Sign-up failed", str(e))
                return
            messagebox.showinfo("Welcome", f"Account created for {user['username']}.")
            self.show_dashboard()

        ttk.Button(self._container, text="Create", command=do_signup).pack(pady=10)
        ttk.Button(self._container, text="Back to login", command=self.show_login).pack()
        self._disclaimer(self._container)

    # ---------- Dashboard ----------

    def show_dashboard(self):
        self._clear()
        u = self.api.user
        ttk.Label(self._container, text=f"Hello, {u['username']}", style="Header.TLabel").pack(pady=(0, 6))
        hour = datetime.now().hour
        if hour < 11:
            part = "Good morning"
        elif hour < 16:
            part = "Good afternoon"
        else:
            part = "Good evening"
        ttk.Label(self._container, text=f"{part} — what would you like to do?").pack(pady=(0, 16))

        btns = [
            ("Morning check-in",    self.show_morning),
            ("Midday check-in",     self.show_midday),
            ("Evening check-in",    self.show_evening),
            ("Risk & report",       self.show_report),
            ("Daily suggestions",   self.show_suggestions),
            ("Log out",             self.do_logout),
        ]
        for label, cmd in btns:
            ttk.Button(self._container, text=label, command=cmd, width=30).pack(pady=4)

        self._disclaimer(self._container)

    def do_logout(self):
        # Revokes the session on the server -- the token stops working
        # everywhere it might have been copied -- then forgets it here.
        self.api.logout()
        self.show_login(notice="You have been logged out.")

    # ---------- Morning ----------

    def show_morning(self):
        # Asked before the screen is cleared, so if the call fails the current
        # screen stays usable. Once today's check-in exists it is locked: the
        # evening test grades against these associations.
        existing = self.api.morning_today()
        if existing is not None:
            self._show_associations(existing, already_submitted=True)
            return

        self._clear()
        self._header("Morning check-in")
        ttk.Label(self._container, text="What do you plan to do today? (one per line)").pack(anchor="w")
        ttk.Label(self._container, text="You can submit once per day, so make the list complete.",
                  font=("Helvetica", 9)).pack(anchor="w")

        plans = scrolledtext.ScrolledText(self._container, height=6, font=("Helvetica", 11))
        plans.pack(fill="x", pady=6)

        def submit():
            text = plans.get("1.0", "end").strip()
            if not text:
                messagebox.showwarning("Empty", "Please enter at least one activity.")
                return
            try:
                morning, already = self.api.submit_morning(text), False
            except AlreadySubmitted as e:
                # Submitted from another device since this screen opened.
                morning, already = e.existing, True
            self._show_associations(morning, already_submitted=already)

        ttk.Button(self._container, text="Submit & show associations", command=submit).pack(pady=6)
        ttk.Button(self._container, text="Back", command=self.show_dashboard).pack()
        self._disclaimer(self._container)

    def _show_associations(self, morning, already_submitted=False):
        self._clear()
        self._header("Remember these — you'll be tested tonight")
        if already_submitted:
            ttk.Label(self._container,
                      text="You have already checked in this morning. These are today's associations.",
                      wraplength=700).pack(pady=(0, 8))

        frm = tk.Frame(self._container, bg=BG)
        frm.pack(fill="x")
        for a in morning["presented_associations"]:
            row = tk.Frame(frm, bg="#ffffff", bd=1, relief="solid")
            row.pack(fill="x", pady=4, padx=20)
            tk.Label(row, text=f"Cue: \"{a['cue_word']}\"", font=("Helvetica", 12, "bold"),
                     bg="#ffffff").pack(side="left", padx=10, pady=8)
            tk.Label(row, text=f"Object: {a['object_name']}", font=("Helvetica", 12),
                     bg="#ffffff").pack(side="left", padx=10)
            tk.Label(row, text=f"[image: {a['image_path']}]", font=("Helvetica", 9, "italic"),
                     fg="#888", bg="#ffffff").pack(side="left", padx=10)

        ttk.Label(self._container,
                  text="This evening we'll show the cue words and ask you to name each object.",
                  wraplength=700).pack(pady=12)
        ttk.Button(self._container, text="Back to dashboard", command=self.show_dashboard).pack(pady=4)
        self._disclaimer(self._container)

    # ---------- Midday ----------

    def show_midday(self):
        # Links the entry to today's morning when there is one; midday
        # check-ins are allowed without it.
        morning = self.api.morning_today()

        self._clear()
        self._header("Midday check-in")
        ttk.Label(self._container, text="What have you done so far today?").pack(anchor="w")
        done = scrolledtext.ScrolledText(self._container, height=4, font=("Helvetica", 11))
        done.pack(fill="x", pady=6)

        ttk.Label(self._container, text="What do you still plan to do?").pack(anchor="w")
        plan = scrolledtext.ScrolledText(self._container, height=3, font=("Helvetica", 11))
        plan.pack(fill="x", pady=6)

        start = time.time()

        def submit():
            what = done.get("1.0", "end").strip()
            if not what:
                messagebox.showwarning("Empty", "Please say what you've done so far.")
                return
            self.api.submit_midday(
                what_user_has_done=what,
                planned_remainder=plan.get("1.0", "end").strip(),
                response_latency_ms=int((time.time() - start) * 1000),
                morning_checkin_id=morning["id"] if morning else None,
            )
            messagebox.showinfo("Recorded", "Midday check-in saved.")
            self.show_dashboard()

        ttk.Button(self._container, text="Submit", command=submit).pack(pady=6)
        ttk.Button(self._container, text="Back", command=self.show_dashboard).pack()
        self._disclaimer(self._container)

    # ---------- Evening ----------

    def show_evening(self):
        # Always asked of the server rather than remembered from this session:
        # the app may have been restarted since the morning, and a remembered
        # morning from yesterday would grade tonight's test against the wrong
        # associations.
        morning = self.api.morning_today()

        self._clear()
        if morning is None:
            self._header("No morning check-in today")
            ttk.Label(self._container,
                      text="The evening test asks about the image associations from this "
                           "morning's check-in, so there is nothing to test yet.",
                      wraplength=700).pack(pady=(0, 12))
            ttk.Button(self._container, text="Go to morning check-in", command=self.show_morning).pack(pady=4)
            ttk.Button(self._container, text="Back", command=self.show_dashboard).pack()
            self._disclaimer(self._container)
            return

        self._header("Evening check-in")
        ttk.Label(self._container, text="First: what do you remember doing today?").pack(anchor="w")
        recalled = scrolledtext.ScrolledText(self._container, height=5, font=("Helvetica", 11))
        recalled.pack(fill="x", pady=6)

        ttk.Label(self._container,
                  text="Now, for each cue word, type the object you were shown this morning:").pack(anchor="w", pady=(8, 0))

        frm = tk.Frame(self._container, bg=BG)
        frm.pack(fill="x", pady=6)

        answers = []      # (assoc_id, entry_widget, start_time)
        for a in morning["presented_associations"]:
            row = tk.Frame(frm, bg=BG)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=f"Cue: {a['cue_word']}", width=20, anchor="w",
                     bg=BG, font=("Helvetica", 11, "bold")).pack(side="left")
            e = ttk.Entry(row, width=30)
            e.pack(side="left")
            answers.append((a["id"], e, time.time()))

        def submit():
            now = time.time()
            responses = [
                {
                    "association_id": assoc_id,
                    "user_answer": e.get(),
                    "response_latency_ms": int((now - started) * 1000),
                }
                for assoc_id, e, started in answers
            ]
            ev = self.api.submit_evening(
                morning_checkin_id=morning["id"],
                recalled_activities=recalled.get("1.0", "end").strip(),
                association_responses=responses,
            )
            self._show_evening_result(ev)

        ttk.Button(self._container, text="Submit evening check-in", command=submit).pack(pady=8)
        ttk.Button(self._container, text="Back", command=self.show_dashboard).pack()
        self._disclaimer(self._container)

    def _show_evening_result(self, ev):
        self._clear()
        self._header("Daily results")

        def pct(v):
            return "—" if v is None else f"{v * 100:.0f}%"

        def num(v, fmt):
            return "—" if v is None else format(v, fmt)

        lines = [
            f"Daily cognitive score:        {num(ev['daily_cognitive_score'], '.2f')} / 1.00",
            f"Image-association accuracy:   {pct(ev['association_accuracy'])}",
            f"Activity-recall accuracy:     {pct(ev['activity_recall_accuracy'])}",
            f"Average response latency:     {num(ev['avg_response_latency_ms'], 'd')} ms",
            "Speech biomarker score:       " + (
                "not recorded" if ev["speech_biomarker_score"] is None
                else format(ev["speech_biomarker_score"], ".2f")
            ),
        ]
        for line in lines:
            ttk.Label(self._container, text=line, font=("Courier", 12)).pack(anchor="w", padx=20, pady=2)

        ttk.Label(self._container,
                  text="One day is one data point. Trends need many days — see the risk report.",
                  font=("Helvetica", 9), wraplength=700).pack(anchor="w", padx=20, pady=(8, 0))
        ttk.Button(self._container, text="View risk report",
                   command=self.show_report).pack(pady=12)
        ttk.Button(self._container, text="Back to dashboard",
                   command=self.show_dashboard).pack()
        self._disclaimer(self._container)

    # ---------- Report ----------

    def show_report(self):
        rc = self.api.risk_report()   # before clearing: a failure leaves this screen usable

        self._clear()
        self._header("Risk report")

        # Every number carries its interval, and too few days is said plainly
        # rather than shown as a precise-looking score.
        n = rc.get("n_scored_days", 0)
        avg = rc.get("user_recent_avg_score")
        lo, hi = rc.get("user_recent_avg_ci_low"), rc.get("user_recent_avg_ci_high")
        if avg is None:
            spread = "no scored days in this period yet"
        elif lo is not None and hi is not None:
            spread = f"95% range {lo:.2f}–{hi:.2f}, {n} scored days"
        else:
            spread = f"{n} scored day{'' if n == 1 else 's'} — too few to give a range yet"

        summary = (
            f"Your recent average daily score:  {'—' if avg is None else f'{avg:.2f}'}  ({spread})\n"
            f"Peer expected prevalence (age+gender+race):  {rc['peer_expected_prevalence_pct']:.1f}%\n"
            f"Peer subjective cognitive decline rate:      {rc['scd_peer_prevalence_pct']:.1f}%\n"
        )
        tk.Label(self._container, text=summary, font=("Courier", 10),
                 bg=BG, justify="left").pack(anchor="w", padx=20)

        if rc["elevated_concern"] and rc.get("concern_reason"):
            self._panel("⚠ Attention", rc["concern_reason"], bg="#fff3cd", fg="#5c4400")

        # "Inconclusive" is not "no concern": the data cannot yet separate a
        # real change from day-to-day variation, and must say so rather than
        # read as an all-clear.
        if rc.get("inconclusive") and rc.get("inconclusive_reason"):
            body = rc["inconclusive_reason"]
            change = rc.get("trajectory_change_pct")
            c_lo, c_hi = rc.get("trajectory_change_ci_low_pct"), rc.get("trajectory_change_ci_high_pct")
            if change is not None and c_lo is not None and c_hi is not None:
                body += (f"\n\nChange vs. your baseline: {change:+.0f}% "
                         f"(95% range {c_lo:+.0f}% to {c_hi:+.0f}%)")
            self._panel("Not enough to say yet", body, bg="#e0f2fe", fg="#0c4a6e")

        ttk.Label(self._container, text="Suggestions:", font=("Helvetica", 12, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
        for s in rc["suggestions"]:
            tk.Label(self._container, text=f"• {s}", wraplength=700, justify="left",
                     bg=BG).pack(anchor="w", padx=20, pady=2)

        ttk.Label(self._container, text="Sources:", font=("Helvetica", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
        for c in rc["citations"]:
            tk.Label(self._container, text=f"– {c}", wraplength=700, justify="left",
                     bg=BG, font=("Helvetica", 9)).pack(anchor="w", padx=20)

        ttk.Button(self._container, text="Back to dashboard", command=self.show_dashboard).pack(pady=10)
        self._disclaimer(self._container)

    # ---------- Daily suggestions ----------

    def show_suggestions(self):
        ds = self.api.daily_suggestions()   # before clearing, as in show_report

        self._clear()
        self._header("Daily suggestions")
        for s in ds["suggestions"]:
            tk.Label(self._container, text=f"• {s}", wraplength=700, justify="left",
                     bg=BG, font=("Helvetica", 11)).pack(anchor="w", padx=20, pady=4)

        tk.Label(self._container, text=f"Source: {ds['lancet_risk_factor_source']}",
                 wraplength=700, font=("Helvetica", 9, "italic"), bg=BG).pack(
                     anchor="w", padx=20, pady=(10, 0))
        ttk.Button(self._container, text="Back", command=self.show_dashboard).pack(pady=10)
        self._disclaimer(self._container)


if __name__ == "__main__":
    app = CogniSenseApp()
    app.mainloop()
