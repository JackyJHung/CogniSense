"""
CogniSense desktop client (Tkinter).

Talks to the FastAPI backend at BACKEND_URL. Single-window multi-screen app:

  [Login / Signup]  ->  [Dashboard]  ->  one of:
      * Morning check-in
      * Midday check-in
      * Evening check-in (image-association test)
      * Report / risk comparison
      * Daily suggestions

Run:
    python desktop_app/main.py
Backend must be running at localhost:8000 (or set BACKEND_URL env var).
"""

import os
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from datetime import datetime

try:
    import requests
except ImportError:
    raise SystemExit("pip install requests")


BACKEND_URL = os.getenv("COGNISENSE_BACKEND", "http://127.0.0.1:8000")


# ---------- HTTP helpers ----------

# Bearer token for the logged-in session, set by login/signup.
_access_token = None


def set_access_token(token):
    global _access_token
    _access_token = token


def _auth_headers():
    return {"Authorization": f"Bearer {_access_token}"} if _access_token else {}


def api_post(path, json=None):
    r = requests.post(f"{BACKEND_URL}{path}", json=json, headers=_auth_headers(), timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"{r.status_code}: {r.text}")
    return r.json()


def api_get(path):
    r = requests.get(f"{BACKEND_URL}{path}", headers=_auth_headers(), timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"{r.status_code}: {r.text}")
    return r.json()


# ---------- Main App ----------

class CogniSenseApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CogniSense")
        self.geometry("780x620")
        self.configure(bg="#f5f6fa")
        self.current_user = None
        self.current_morning = None   # most recent morning check-in dict

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TButton", padding=8, font=("Helvetica", 11))
        style.configure("TLabel", background="#f5f6fa", font=("Helvetica", 11))
        style.configure("Header.TLabel", font=("Helvetica", 18, "bold"), background="#f5f6fa")
        style.configure("Disclaimer.TLabel", font=("Helvetica", 9, "italic"),
                        foreground="#606060", background="#f5f6fa", wraplength=700)

        self._container = tk.Frame(self, bg="#f5f6fa")
        self._container.pack(fill="both", expand=True, padx=20, pady=20)

        self.show_login()

    def _clear(self):
        for w in self._container.winfo_children():
            w.destroy()

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

    def show_login(self):
        self._clear()
        ttk.Label(self._container, text="CogniSense", style="Header.TLabel").pack(pady=(10, 4))
        ttk.Label(
            self._container,
            text="Early-risk screening for memory & cognition",
        ).pack(pady=(0, 20))

        frm = tk.Frame(self._container, bg="#f5f6fa")
        frm.pack()

        tk.Label(frm, text="Username", bg="#f5f6fa").grid(row=0, column=0, sticky="e", padx=6, pady=6)
        username_e = ttk.Entry(frm, width=30)
        username_e.grid(row=0, column=1, pady=6)

        tk.Label(frm, text="Password", bg="#f5f6fa").grid(row=1, column=0, sticky="e", padx=6, pady=6)
        password_e = ttk.Entry(frm, show="*", width=30)
        password_e.grid(row=1, column=1, pady=6)

        def do_login():
            try:
                auth = api_post("/users/login", {
                    "username": username_e.get(),
                    "password": password_e.get(),
                })
                set_access_token(auth["access_token"])
                self.current_user = auth["user"]
                self.show_dashboard()
            except Exception as e:
                messagebox.showerror("Login failed", str(e))

        ttk.Button(self._container, text="Log in", command=do_login).pack(pady=10)
        ttk.Button(self._container, text="Create account", command=self.show_signup).pack()
        self._disclaimer(self._container)

    def show_signup(self):
        self._clear()
        ttk.Label(self._container, text="Create account", style="Header.TLabel").pack(pady=(10, 20))

        frm = tk.Frame(self._container, bg="#f5f6fa")
        frm.pack()

        fields = {}
        for i, (label, key, widget) in enumerate([
            ("Username", "username", "entry"),
            ("Password", "password", "password"),
            ("Age", "age", "entry"),
            ("Gender", "gender", ("female", "male", "nonbinary", "other", "prefer_not")),
            ("Race/Ethnicity", "race", ("white", "black", "hispanic", "aapi", "ai_an", "other", "prefer_not")),
            ("Wake time (HH:MM)", "wake_time", "entry"),
            ("Sleep time (HH:MM)", "sleep_time", "entry"),
        ]):
            tk.Label(frm, text=label, bg="#f5f6fa").grid(row=i, column=0, sticky="e", padx=6, pady=4)
            if widget == "entry":
                e = ttk.Entry(frm, width=30)
            elif widget == "password":
                e = ttk.Entry(frm, show="*", width=30)
            else:
                e = ttk.Combobox(frm, values=widget, width=28, state="readonly")
                e.set(widget[0])
            e.grid(row=i, column=1, pady=4)
            fields[key] = e

        def do_signup():
            try:
                wake = fields["wake_time"].get()
                sleep = fields["sleep_time"].get()
                payload = {
                    "username": fields["username"].get(),
                    "password": fields["password"].get(),
                    "age": int(fields["age"].get()),
                    "gender": fields["gender"].get(),
                    "race": fields["race"].get(),
                    "wake_time": f"{wake}:00" if len(wake) == 5 else wake,
                    "sleep_time": f"{sleep}:00" if len(sleep) == 5 else sleep,
                }
                auth = api_post("/users/signup", payload)
                set_access_token(auth["access_token"])
                user = auth["user"]
                self.current_user = user
                messagebox.showinfo("Welcome", f"Account created for {user['username']}.")
                self.show_dashboard()
            except Exception as e:
                messagebox.showerror("Sign-up failed", str(e))

        ttk.Button(self._container, text="Create", command=do_signup).pack(pady=10)
        ttk.Button(self._container, text="Back to login", command=self.show_login).pack()
        self._disclaimer(self._container)

    # ---------- Dashboard ----------

    def show_dashboard(self):
        self._clear()
        u = self.current_user
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
        set_access_token(None)
        self.current_user = None
        self.current_morning = None
        self.show_login()

    # ---------- Morning ----------

    def show_morning(self):
        self._clear()
        ttk.Label(self._container, text="Morning check-in", style="Header.TLabel").pack(pady=(0, 10))
        ttk.Label(self._container, text="What do you plan to do today? (one per line)").pack(anchor="w")

        plans = scrolledtext.ScrolledText(self._container, height=6, font=("Helvetica", 11))
        plans.pack(fill="x", pady=6)

        def submit():
            text = plans.get("1.0", "end").strip()
            if not text:
                messagebox.showwarning("Empty", "Please enter at least one activity.")
                return
            try:
                morning = api_post("/checkins/morning", {
                    "planned_activities": text,
                })
                self.current_morning = morning
                self._show_associations(morning)
            except Exception as e:
                messagebox.showerror("Error", str(e))

        ttk.Button(self._container, text="Submit & show associations", command=submit).pack(pady=6)
        ttk.Button(self._container, text="Back", command=self.show_dashboard).pack()
        self._disclaimer(self._container)

    def _show_associations(self, morning):
        self._clear()
        ttk.Label(self._container, text="Remember these — you'll be tested tonight",
                  style="Header.TLabel").pack(pady=(0, 10))

        frm = tk.Frame(self._container, bg="#f5f6fa")
        frm.pack()
        for i, a in enumerate(morning["presented_associations"]):
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
        self._clear()
        ttk.Label(self._container, text="Midday check-in", style="Header.TLabel").pack(pady=(0, 10))
        ttk.Label(self._container, text="What have you done so far today?").pack(anchor="w")
        done = scrolledtext.ScrolledText(self._container, height=4, font=("Helvetica", 11))
        done.pack(fill="x", pady=6)

        ttk.Label(self._container, text="What do you still plan to do?").pack(anchor="w")
        plan = scrolledtext.ScrolledText(self._container, height=3, font=("Helvetica", 11))
        plan.pack(fill="x", pady=6)

        start = time.time()

        def submit():
            latency_ms = int((time.time() - start) * 1000)
            try:
                api_post("/checkins/midday", {
                    "morning_checkin_id": self.current_morning["id"] if self.current_morning else None,
                    "what_user_has_done": done.get("1.0", "end").strip(),
                    "planned_remainder": plan.get("1.0", "end").strip(),
                    "response_latency_ms": latency_ms,
                })
                messagebox.showinfo("Recorded", "Midday check-in saved.")
                self.show_dashboard()
            except Exception as e:
                messagebox.showerror("Error", str(e))

        ttk.Button(self._container, text="Submit", command=submit).pack(pady=6)
        ttk.Button(self._container, text="Back", command=self.show_dashboard).pack()
        self._disclaimer(self._container)

    # ---------- Evening ----------

    def show_evening(self):
        self._clear()
        if not self.current_morning:
            ttk.Label(self._container, text="No morning check-in to grade against.",
                      style="Header.TLabel").pack(pady=20)
            ttk.Button(self._container, text="Back", command=self.show_dashboard).pack()
            return

        ttk.Label(self._container, text="Evening check-in", style="Header.TLabel").pack(pady=(0, 10))
        ttk.Label(self._container, text="First: what do you remember doing today?").pack(anchor="w")
        recalled = scrolledtext.ScrolledText(self._container, height=5, font=("Helvetica", 11))
        recalled.pack(fill="x", pady=6)

        ttk.Label(self._container,
                  text="Now, for each cue word, type the object you were shown this morning:").pack(anchor="w", pady=(8, 0))

        frm = tk.Frame(self._container, bg="#f5f6fa")
        frm.pack(fill="x", pady=6)

        answers = []      # (assoc_id, entry_widget, start_time)
        for i, a in enumerate(self.current_morning["presented_associations"]):
            row = tk.Frame(frm, bg="#f5f6fa")
            row.pack(fill="x", pady=2)
            tk.Label(row, text=f"Cue: {a['cue_word']}", width=20, anchor="w",
                     bg="#f5f6fa", font=("Helvetica", 11, "bold")).pack(side="left")
            e = ttk.Entry(row, width=30)
            e.pack(side="left")
            answers.append((a["id"], e, time.time()))

        def submit():
            now = time.time()
            responses = []
            for assoc_id, e, start in answers:
                responses.append({
                    "association_id": assoc_id,
                    "user_answer": e.get(),
                    "response_latency_ms": int((now - start) * 1000),
                })
            try:
                ev = api_post("/checkins/evening", {
                    "morning_checkin_id": self.current_morning["id"],
                    "recalled_activities": recalled.get("1.0", "end").strip(),
                    "association_responses": responses,
                })
                self._show_evening_result(ev)
            except Exception as e:
                messagebox.showerror("Error", str(e))

        ttk.Button(self._container, text="Submit evening check-in", command=submit).pack(pady=8)
        ttk.Button(self._container, text="Back", command=self.show_dashboard).pack()
        self._disclaimer(self._container)

    def _show_evening_result(self, ev):
        self._clear()
        ttk.Label(self._container, text="Daily results", style="Header.TLabel").pack(pady=(0, 10))

        lines = [
            f"Daily cognitive score:        {ev['daily_cognitive_score']:.2f} / 1.00",
            f"Image-association accuracy:   {ev['association_accuracy']*100:.0f}%",
            f"Activity-recall accuracy:     {(ev['activity_recall_accuracy'] or 0)*100:.0f}%",
            f"Average response latency:     {ev['avg_response_latency_ms']} ms",
            f"Speech biomarker score:       {(ev['speech_biomarker_score'] or 0):.2f}",
        ]
        for line in lines:
            ttk.Label(self._container, text=line, font=("Courier", 12)).pack(anchor="w", padx=20, pady=2)

        ttk.Button(self._container, text="View risk report",
                   command=self.show_report).pack(pady=12)
        ttk.Button(self._container, text="Back to dashboard",
                   command=self.show_dashboard).pack()
        self._disclaimer(self._container)

    # ---------- Report ----------

    def show_report(self):
        self._clear()
        ttk.Label(self._container, text="Risk report", style="Header.TLabel").pack(pady=(0, 8))
        try:
            rc = api_get(f"/reports/risk-comparison/{self.current_user['id']}")
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return

        summary = (
            f"Your recent average daily score:  {rc['user_recent_avg_score']:.2f}\n"
            f"Peer expected prevalence (age+gender+race):  {rc['peer_expected_prevalence_pct']:.1f}%\n"
            f"Peer subjective cognitive decline rate:      {rc['scd_peer_prevalence_pct']:.1f}%\n"
        )
        tk.Label(self._container, text=summary, font=("Courier", 11),
                 bg="#f5f6fa", justify="left").pack(anchor="w", padx=20)

        if rc["elevated_concern"]:
            warn = tk.Frame(self._container, bg="#fff3cd", bd=1, relief="solid")
            warn.pack(fill="x", pady=10, padx=10)
            tk.Label(warn, text="⚠ Attention",
                     font=("Helvetica", 12, "bold"), bg="#fff3cd").pack(anchor="w", padx=10, pady=(8, 0))
            tk.Label(warn, text=rc["concern_reason"], bg="#fff3cd", wraplength=680,
                     justify="left").pack(anchor="w", padx=10, pady=(0, 8))

        ttk.Label(self._container, text="Suggestions:", font=("Helvetica", 12, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
        for s in rc["suggestions"]:
            tk.Label(self._container, text=f"• {s}", wraplength=700, justify="left",
                     bg="#f5f6fa").pack(anchor="w", padx=20, pady=2)

        ttk.Label(self._container, text="Sources:", font=("Helvetica", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
        for c in rc["citations"]:
            tk.Label(self._container, text=f"– {c}", wraplength=700, justify="left",
                     bg="#f5f6fa", font=("Helvetica", 9)).pack(anchor="w", padx=20)

        ttk.Button(self._container, text="Back to dashboard", command=self.show_dashboard).pack(pady=10)
        self._disclaimer(self._container)

    # ---------- Daily suggestions ----------

    def show_suggestions(self):
        self._clear()
        ttk.Label(self._container, text="Daily suggestions", style="Header.TLabel").pack(pady=(0, 10))
        try:
            ds = api_get(f"/reports/daily-suggestions/{self.current_user['id']}")
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return
        for s in ds["suggestions"]:
            tk.Label(self._container, text=f"• {s}", wraplength=700, justify="left",
                     bg="#f5f6fa", font=("Helvetica", 11)).pack(anchor="w", padx=20, pady=4)

        tk.Label(self._container, text=f"Source: {ds['lancet_risk_factor_source']}",
                 wraplength=700, font=("Helvetica", 9, "italic"), bg="#f5f6fa").pack(
                     anchor="w", padx=20, pady=(10, 0))
        ttk.Button(self._container, text="Back", command=self.show_dashboard).pack(pady=10)
        self._disclaimer(self._container)


if __name__ == "__main__":
    app = CogniSenseApp()
    app.mainloop()
