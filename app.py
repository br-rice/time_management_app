"""
Time Management App — Python/Tkinter version
Requires:  pip install customtkinter  (optional — falls back to plain tkinter)
DB file:   task_data.sqlite in same directory as this script
"""

import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import time
import os
from datetime import date, timedelta
from contextlib import contextmanager

try:
    import customtkinter as ctk
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")
except ImportError:
    class _Shim:
        class CTk(tk.Tk): pass
        class CTkFrame(tk.Frame):
            def __init__(self, *a, fg_color=None, border_width=0,
                         border_color=None, **kw): super().__init__(*a, **kw)
        class CTkTabview(tk.Frame):
            def __init__(self, parent, fg_color=None, command=None, **kw):
                super().__init__(parent, **kw)
                self._nb  = ttk.Notebook(self)
                self._nb.pack(fill="both", expand=True)
                self._tabs = {}
                self._cmd  = command
                if command:
                    self._nb.bind("<<NotebookTabChanged>>", lambda e: command())
            def add(self, name):
                f = tk.Frame(self._nb)
                self._nb.add(f, text=name)
                self._tabs[name] = f
            def tab(self, name): return self._tabs[name]
            def get(self):
                idx = self._nb.index(self._nb.select())
                return self._nb.tab(idx, "text")
    ctk = _Shim()

# ── Constants ─────────────────────────────────────────────────────────────────

DB_PATH    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "task_data.sqlite")
TABLE      = "tasks"
PRIORITIES = ["Low", "Medium", "High", "Critical"]
PRI_COLOR  = {"Low": "#28a745", "Medium": "#e07b00",
              "High": "#dc3545", "Critical": "#7b0000"}
TODAY      = str(date.today())
PURPLE     = "#6A5ACD"
LIGHT      = "#f9f9ff"
WORK_COLOR = "#2563EB"
NONW_COLOR = "#7C3AED"

# ── Database ──────────────────────────────────────────────────────────────────

@contextmanager
def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def setup_db():
    with db_conn() as conn:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if TABLE in tables:
            cols = [r[1] for r in conn.execute(
                f"PRAGMA table_info({TABLE})").fetchall()]
            for col, defn in {
                "selected_today": "INTEGER DEFAULT 0",
                "selected_date":  "TEXT",
                "priority":       "TEXT DEFAULT 'Medium'",
                "time_spent":     "REAL DEFAULT 0",
                "is_work":        "INTEGER DEFAULT 1",
                "due_date":       "TEXT",
                "created_date":   "TEXT",
            }.items():
                if col not in cols:
                    conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN {col} {defn}")
        else:
            conn.execute(f"""
                CREATE TABLE {TABLE} (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    impact_project TEXT NOT NULL,
                    goal           TEXT NOT NULL,
                    task           TEXT,
                    task_completed INTEGER DEFAULT 0,
                    selected_today INTEGER DEFAULT 0,
                    selected_date  TEXT,
                    notes          TEXT,
                    priority       TEXT DEFAULT 'Medium',
                    time_spent     REAL DEFAULT 0,
                    is_work        INTEGER DEFAULT 1,
                    due_date       TEXT
                )""")

def load_tasks():
    with db_conn() as conn:
        return [dict(r) for r in conn.execute(f"SELECT * FROM {TABLE}").fetchall()]

def db_exec(sql, params=()):
    with db_conn() as conn:
        conn.execute(sql, params)

def fmt_secs(s):
    s = max(0, int(s))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}h {m:02d}m {sec:02d}s" if h else f"{m:02d}m {sec:02d}s"

# ── Main App ──────────────────────────────────────────────────────────────────

class App(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("Time Management")
        self.geometry("1350x920")
        self.minsize(950, 680)
        setup_db()

        # Timer state
        self.timer_task_id = None
        self.timer_start_t = None
        self.timer_base_s  = 0.0
        self._after_id     = None
        self._timer_label  = None

        self._today_sel = set()

        # ── Global filter state ──────────────────────────────────────────────
        # True = Work only, False = Non-work (show everything)
        self._work_mode  = tk.BooleanVar(value=True)

        # Tab 2 filters
        self._t2_pri_filter  = tk.StringVar(value="All")
        self._t2_proj_filter = tk.StringVar(value="All")
        self._t2_goal_filter = tk.StringVar(value="All")
        self._t2_show_done   = tk.BooleanVar(value=False)

        # Tab 1 add-goal form
        self._t1g_project = tk.StringVar(value="")
        self._t1g_is_work = tk.BooleanVar(value=True)

        # Tab 1 add-task form
        self._t1t_project = tk.StringVar(value="")
        self._t1t_goal    = tk.StringVar(value="")

        self._build_ui()

    # ── UI scaffold ───────────────────────────────────────────────────────────

    def _build_ui(self):
        self.tabview = ctk.CTkTabview(self, fg_color="transparent",
                                      command=self._on_tab_change)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        self._tab_frames = {}
        for name in ["Add Tasks", "My Tasks", "Tasks for Today",
                     "Completed Tasks", "Weekly Summary"]:
            self.tabview.add(name)
            outer = ctk.CTkFrame(self.tabview.tab(name), fg_color="transparent")
            outer.pack(fill="both", expand=True)
            canvas = tk.Canvas(outer, bg="white", highlightthickness=0)
            vsb    = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=vsb.set)
            vsb.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)
            inner = tk.Frame(canvas, bg="white")
            win   = canvas.create_window((0, 0), window=inner, anchor="nw")
            inner.bind("<Configure>",
                       lambda e, c=canvas: c.configure(scrollregion=c.bbox("all")))
            canvas.bind("<Configure>",
                        lambda e, c=canvas, w=win: c.itemconfig(w, width=e.width))
            def _scroll(event, c=canvas):
                c.yview_scroll(int(-1 * (event.delta / 120)), "units")
            canvas.bind_all("<MouseWheel>", _scroll)
            self._tab_frames[name] = inner

        self._build_tab1()
        self._build_tab2()
        self._build_tab3()
        self._build_tab4()
        self._build_tab5()

    def _on_tab_change(self):
        tab = self.tabview.get()
        {
            "Add Tasks":       self._build_tab1,
            "My Tasks":        self._build_tab2,
            "Tasks for Today": self._build_tab3,
            "Completed Tasks": self._build_tab4,
            "Weekly Summary":  self._build_tab5,
        }.get(tab, lambda: None)()

    def _clear(self, name):
        for w in self._tab_frames[name].winfo_children():
            w.destroy()

    # ── Widget helpers ────────────────────────────────────────────────────────

    def _make_section(self, parent, title):
        return tk.LabelFrame(parent, text=f"  {title}  ",
                             font=("Helvetica", 11, "bold"),
                             fg=PURPLE, bg=LIGHT, bd=2, relief="groove",
                             padx=10, pady=8)

    def _lbl(self, parent, text, bold=False, color="#333", size=11, bg=LIGHT):
        return tk.Label(parent, text=text,
                        font=("Helvetica", size, "bold" if bold else "normal"),
                        fg=color, bg=bg)

    def _entry(self, parent, width=30, bg=LIGHT):
        return tk.Entry(parent, width=width, relief="flat", bd=1,
                        highlightthickness=1, bg=bg,
                        highlightcolor=PURPLE, highlightbackground="#ccc")

    def _combo(self, parent, values, width=28, textvariable=None):
        kw = {"values": values, "width": width, "state": "readonly"}
        if textvariable:
            kw["textvariable"] = textvariable
        cb = ttk.Combobox(parent, **kw)
        if values and not textvariable:
            cb.current(0)
        return cb

    def _btn(self, parent, text, color, command, width=None):
        kw = {"bg": color, "fg": "white", "relief": "flat",
              "font": ("Helvetica", 10), "padx": 10, "pady": 4,
              "cursor": "hand2", "command": command,
              "activebackground": color, "activeforeground": "white"}
        if width:
            kw["width"] = width
        return tk.Button(parent, text=text, **kw)

    def _work_toggle(self, parent, var, bg=LIGHT):
        """Work / Non-work radio pair."""
        row = tk.Frame(parent, bg=bg)
        tk.Radiobutton(row, text="Work", variable=var, value=True,
                       font=("Helvetica", 10, "bold"), fg=WORK_COLOR,
                       bg=bg, activebackground=bg,
                       selectcolor=bg).pack(side="left", padx=(0, 10))
        tk.Radiobutton(row, text="Non-work", variable=var, value=False,
                       font=("Helvetica", 10, "bold"), fg=NONW_COLOR,
                       bg=bg, activebackground=bg,
                       selectcolor=bg).pack(side="left")
        return row

    def _mode_bar(self, parent, rebuild_fn):
        """The Work / Non-work filter banner used on tabs 2–5."""
        bar = tk.Frame(parent, bg="#f0f0f8", bd=1, relief="flat")
        bar.pack(fill="x", padx=8, pady=(8, 6))
        tk.Label(bar, text="Mode:", font=("Helvetica", 10, "bold"),
                 fg="#555", bg="#f0f0f8").pack(side="left", padx=(10, 8), pady=6)
        tk.Radiobutton(bar, text="Work",
                       variable=self._work_mode, value=True,
                       font=("Helvetica", 10, "bold"), fg=WORK_COLOR,
                       bg="#f0f0f8", activebackground="#f0f0f8",
                       selectcolor="#f0f0f8",
                       command=rebuild_fn).pack(side="left", padx=(0, 16), pady=6)
        tk.Radiobutton(bar, text="Non-work  (show everything)",
                       variable=self._work_mode, value=False,
                       font=("Helvetica", 10, "bold"), fg=NONW_COLOR,
                       bg="#f0f0f8", activebackground="#f0f0f8",
                       selectcolor="#f0f0f8",
                       command=rebuild_fn).pack(side="left", pady=6)
        return bar

    def _mini_progress(self, parent, done, total, color=PURPLE, bg=LIGHT):
        pct    = done / total if total > 0 else 0
        row    = tk.Frame(parent, bg=bg)
        row.pack(fill="x", pady=(0, 4))
        tk.Label(row, text=f"{done}/{total}", font=("Helvetica", 9),
                 fg="#666", bg=bg).pack(side="left", padx=(0, 4))
        bar_bg = tk.Frame(row, bg="#e0e0e0", height=6)
        bar_bg.pack(side="left", fill="x", expand=True)
        bar_bg.update_idletasks()
        w = max(1, int(bar_bg.winfo_reqwidth() * pct))
        tk.Frame(bar_bg, bg=color, height=6, width=w).pack(side="left")

    def _work_badge(self, parent, is_work, bg=LIGHT):
        color = WORK_COLOR if is_work else NONW_COLOR
        text  = "Work" if is_work else "Non-work"
        tk.Label(parent, text=text,
                 font=("Helvetica", 8, "bold"), fg="white", bg=color,
                 padx=4, pady=1).pack(side="left", padx=(4, 0))

    # ── Shared data helpers ───────────────────────────────────────────────────

    def _all_projects(self, work_mode=None):
        tasks = load_tasks()
        if work_mode is not None:
            tasks = [t for t in tasks if bool(t.get("is_work", 1)) == work_mode]
        return sorted(set(t["impact_project"] for t in tasks if t["impact_project"]))

    def _goals_for_project(self, project, work_mode=None):
        tasks = load_tasks()
        if work_mode is not None:
            tasks = [t for t in tasks if bool(t.get("is_work", 1)) == work_mode]
        return sorted(set(t["goal"] for t in tasks
                          if t["goal"] and t["impact_project"] == project))

    def _all_goals(self, work_mode=None):
        tasks = load_tasks()
        if work_mode is not None:
            tasks = [t for t in tasks if bool(t.get("is_work", 1)) == work_mode]
        return sorted(set(t["goal"] for t in tasks if t["goal"]))

    def _is_work_for_goal(self, goal):
        """Look up is_work flag from the goal's existing DB entry."""
        row = next((t for t in load_tasks() if t["goal"] == goal), None)
        return bool(row.get("is_work", 1)) if row else True

    def _filtered_tasks(self):
        """Return tasks filtered by all active Tab 2 settings."""
        tasks     = load_tasks()
        work_mode = self._work_mode.get()
        pri_val   = self._t2_pri_filter.get()
        proj_val  = self._t2_proj_filter.get()
        goal_val  = self._t2_goal_filter.get()
        show_done = self._t2_show_done.get()

        df = [t for t in tasks if t["task"]]
        if work_mode:
            df = [t for t in df if t.get("is_work", 1) == 1]
        if not show_done:
            df = [t for t in df if not t["task_completed"]]
        if pri_val != "All":
            df = [t for t in df if t["priority"] == pri_val]
        if proj_val != "All":
            df = [t for t in df if t["impact_project"] == proj_val]
        if goal_val != "All":
            df = [t for t in df if t["goal"] == goal_val]
        return df

    def _refresh_tree(self):
        """Repopulate tree with current filter settings."""
        if not hasattr(self, "tree"):
            return
        self.tree.delete(*self.tree.get_children())
        for t in self._filtered_tasks():
            self.tree.insert("", "end", iid=str(t["id"]), values=(
                t["id"],
                t["task"],
                t["goal"],
                t["impact_project"],
                t["priority"],
                "Work" if t.get("is_work", 1) else "Non-work",
                t.get("due_date") or "",
                t.get("created_date") or "",
                "Yes" if t["task_completed"] else "No",
                t["notes"] or ""))

    # ── Tab 1: Add Tasks ──────────────────────────────────────────────────────
    # No mode toggle here.
    # Left:  project → goal name → Work/Non-work toggle → Add Goal
    # Right: project → goal (cascades) → task name → priority → due date → notes

    def _build_tab1(self):
        self._clear("Add Tasks")
        f = self._tab_frames["Add Tasks"]

        top = tk.Frame(f, bg="white")
        top.pack(fill="x", padx=8, pady=8)

        all_projects = self._all_projects()

        # ── LEFT: Add Goal ─────────────────────────────────────────────────────
        gc = self._make_section(top, "Add Goal")
        gc.pack(side="left", fill="both", expand=True, padx=(0, 6))

        self._lbl(gc, "1. Select or Create Impact Project").grid(
            row=0, column=0, sticky="w", pady=(0, 2))
        proj_row = tk.Frame(gc, bg=LIGHT)
        proj_row.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self._t1g_proj_cb = self._combo(proj_row, all_projects, width=22,
                                         textvariable=self._t1g_project)
        self._t1g_proj_cb.pack(side="left")
        self._btn(proj_row, "+ New", "#888",
                  lambda: self._new_project_dialog(self._t1g_project,
                                                   self._build_tab1),
                  width=6).pack(side="left", padx=(6, 0))

        self._lbl(gc, "2. Goal Name").grid(row=2, column=0, sticky="w", pady=(0, 2))
        self.inp_goal = self._entry(gc)
        self.inp_goal.grid(row=3, column=0, sticky="ew", pady=(0, 8))

        self._lbl(gc, "3. Type").grid(row=4, column=0, sticky="w", pady=(0, 2))
        wt = self._work_toggle(gc, self._t1g_is_work)
        wt.grid(row=5, column=0, sticky="w", pady=(0, 12))

        self._btn(gc, "Add Goal", PURPLE, self._add_goal).grid(
            row=6, column=0, sticky="w")
        gc.columnconfigure(0, weight=1)

        # ── RIGHT: Add Task ────────────────────────────────────────────────────
        tc = self._make_section(top, "Add Task")
        tc.pack(side="left", fill="both", expand=True, padx=(6, 0))

        self._lbl(tc, "1. Select Impact Project").grid(
            row=0, column=0, sticky="w", pady=(0, 2))
        t_proj_row = tk.Frame(tc, bg=LIGHT)
        t_proj_row.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self._t1t_proj_cb = self._combo(t_proj_row, all_projects, width=22,
                                         textvariable=self._t1t_project)
        self._t1t_proj_cb.pack(side="left")
        self._t1t_proj_cb.bind("<<ComboboxSelected>>",
                                lambda _: self._refresh_t1_goal_dropdown())

        self._lbl(tc, "2. Select Goal").grid(
            row=2, column=0, sticky="w", pady=(0, 2))
        t1_goals = (self._goals_for_project(self._t1t_project.get())
                    if self._t1t_project.get() else [])
        self._t1t_goal_cb = self._combo(tc, t1_goals, width=28,
                                         textvariable=self._t1t_goal)
        self._t1t_goal_cb.grid(row=3, column=0, sticky="ew", pady=(0, 8))

        self._lbl(tc, "3. Task Name").grid(
            row=4, column=0, sticky="w", pady=(0, 2))
        self.inp_task = self._entry(tc)
        self.inp_task.grid(row=5, column=0, sticky="ew", pady=(0, 8))

        self._lbl(tc, "4. Priority").grid(
            row=6, column=0, sticky="w", pady=(0, 2))
        self.sel_priority = self._combo(tc, PRIORITIES)
        self.sel_priority.grid(row=7, column=0, sticky="ew", pady=(0, 8))

        self._lbl(tc, "5. Due Date  (YYYY-MM-DD, optional)").grid(
            row=8, column=0, sticky="w", pady=(0, 2))
        self.inp_due_date = self._entry(tc, width=16)
        self.inp_due_date.grid(row=9, column=0, sticky="w", pady=(0, 8))
        # Placeholder hint
        self.inp_due_date.insert(0, "")
        self._lbl(tc, "e.g. 2025-12-31", size=9, color="#aaa").grid(
            row=10, column=0, sticky="w", pady=(0, 6))

        self._lbl(tc, "6. Notes").grid(
            row=11, column=0, sticky="w", pady=(0, 2))
        self.inp_notes = tk.Text(tc, height=3, width=30, relief="flat", bd=1,
                                 highlightthickness=1, bg=LIGHT,
                                 highlightcolor=PURPLE, highlightbackground="#ccc")
        self.inp_notes.grid(row=12, column=0, sticky="ew", pady=(0, 10))

        self._btn(tc, "Add Task", "#28a745", self._add_task).grid(
            row=13, column=0, sticky="w")
        tc.columnconfigure(0, weight=1)

        # ── Bottom row: Rename Project / Edit Goal ─────────────────────────────
        edit_outer = tk.Frame(f, bg="white")
        edit_outer.pack(fill="x", padx=8, pady=(0, 10))

        ep = self._make_section(edit_outer, "Rename Project")
        ep.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self._lbl(ep, "Select Project").grid(row=0, column=0, sticky="w")
        self.sel_edit_project = self._combo(ep, self._all_projects())
        self.sel_edit_project.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        self.sel_edit_project.bind("<<ComboboxSelected>>", self._prefill_project)
        self._lbl(ep, "New Name").grid(row=2, column=0, sticky="w")
        self.inp_edit_project = self._entry(ep)
        self.inp_edit_project.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self._btn(ep, "Rename Project", "#e07b00",
                  self._rename_project).grid(row=4, column=0, sticky="w")
        ep.columnconfigure(0, weight=1)

        eg = self._make_section(edit_outer, "Edit Goal")
        eg.pack(side="left", fill="both", expand=True)
        self._lbl(eg, "Select Goal").grid(row=0, column=0, sticky="w")
        self.sel_edit_goal = self._combo(eg, self._all_goals())
        self.sel_edit_goal.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        self.sel_edit_goal.bind("<<ComboboxSelected>>", self._prefill_goal)
        self._lbl(eg, "New Name").grid(row=2, column=0, sticky="w")
        self.inp_edit_goal = self._entry(eg)
        self.inp_edit_goal.grid(row=3, column=0, sticky="ew", pady=(0, 4))
        self._lbl(eg, "Move to Project").grid(row=4, column=0, sticky="w")
        self.sel_goal_project = self._combo(eg, self._all_projects())
        self.sel_goal_project.grid(row=5, column=0, sticky="ew", pady=(0, 4))
        self._lbl(eg, "Type").grid(row=6, column=0, sticky="w", pady=(4, 2))
        self._eg_is_work = tk.BooleanVar(value=True)
        wt = self._work_toggle(eg, self._eg_is_work)
        wt.grid(row=7, column=0, sticky="w", pady=(0, 8))
        self._btn(eg, "Save Goal", "#e07b00",
                  self._save_goal).grid(row=8, column=0, sticky="w")
        eg.columnconfigure(0, weight=1)

    def _refresh_t1_goal_dropdown(self):
        proj  = self._t1t_project.get()
        goals = self._goals_for_project(proj) if proj else []
        self._t1t_goal_cb["values"] = goals
        if goals:
            self._t1t_goal_cb.current(0)
            self._t1t_goal.set(goals[0])
        else:
            self._t1t_goal.set("")

    def _new_project_dialog(self, target_var, refresh_fn):
        dlg = tk.Toplevel(self)
        dlg.title("New Project")
        dlg.geometry("320x130")
        dlg.grab_set()
        dlg.configure(bg="white")
        tk.Label(dlg, text="New project name:", bg="white").pack(
            anchor="w", padx=20, pady=(15, 4))
        e = tk.Entry(dlg, width=36)
        e.pack(padx=20, fill="x")
        e.focus()
        def ok():
            v = e.get().strip()
            if v:
                target_var.set(v)
                dlg.destroy()
                refresh_fn()
        self._btn(dlg, "OK", PURPLE, ok).pack(pady=10)
        dlg.bind("<Return>", lambda _: ok())

    def _add_goal(self):
        project = self._t1g_project.get().strip()
        goal    = self.inp_goal.get().strip()
        is_work = 1 if self._t1g_is_work.get() else 0
        if not project or not goal:
            messagebox.showwarning("Missing",
                                   "Select a project and enter a goal name."); return
        if any(t["impact_project"] == project and t["goal"] == goal
               for t in load_tasks()):
            messagebox.showwarning("Duplicate", "This goal already exists."); return
        db_exec(
            f"INSERT INTO {TABLE} (impact_project,goal,task_completed,"
            f"selected_today,priority,time_spent,is_work) VALUES(?,?,0,0,'Medium',0,?)",
            (project, goal, is_work))
        self.inp_goal.delete(0, "end")
        self._build_tab1()

    def _add_task(self):
        project = self._t1t_project.get().strip()
        goal    = self._t1t_goal.get().strip()
        task    = self.inp_task.get().strip()
        if not project or not goal or not task:
            messagebox.showwarning("Missing",
                                   "Select a project, goal, and enter a task name."); return

        # Task inherits is_work from its goal
        is_work  = 1 if self._is_work_for_goal(goal) else 0
        notes    = self.inp_notes.get("1.0", "end").strip() or None
        due_raw  = self.inp_due_date.get().strip()
        due_date = due_raw if due_raw else None

        # Basic date validation
        if due_date:
            try:
                date.fromisoformat(due_date)
            except ValueError:
                messagebox.showwarning("Invalid date",
                                       "Date must be YYYY-MM-DD (e.g. 2025-12-31)"); return

        db_exec(
            f"INSERT INTO {TABLE} (impact_project,goal,task,task_completed,"
            f"selected_today,priority,notes,time_spent,is_work,due_date,created_date)"
            f" VALUES(?,?,?,0,0,?,?,0,?,?,?)",
            (project, goal, task, self.sel_priority.get(), notes, is_work,
             due_date, str(date.today())))
        self.inp_task.delete(0, "end")
        self.inp_due_date.delete(0, "end")
        self.inp_notes.delete("1.0", "end")
        self._refresh_tree()

    # ── Tab 2: My Tasks ───────────────────────────────────────────────────────

    def _build_tab2(self):
        self._clear("My Tasks")
        f = self._tab_frames["My Tasks"]
        f.configure(bg="white")

        # ── Mode bar ──────────────────────────────────────────────────────────
        self._mode_bar(f, self._on_t2_mode_change)

        # ── Filter bar ────────────────────────────────────────────────────────
        work_mode = self._work_mode.get()
        fbar = tk.Frame(f, bg="#f8f8ff", bd=1, relief="flat")
        fbar.pack(fill="x", padx=8, pady=(0, 6))

        all_projs = self._all_projects(work_mode if work_mode else None)
        proj_choices = ["All"] + all_projs
        tk.Label(fbar, text="Project:", bg="#f8f8ff",
                 font=("Helvetica", 10)).pack(side="left", padx=(10, 4), pady=6)
        proj_cb = ttk.Combobox(fbar, values=proj_choices, width=16,
                               textvariable=self._t2_proj_filter, state="readonly")
        proj_cb.pack(side="left", padx=(0, 12), pady=6)
        proj_cb.bind("<<ComboboxSelected>>", lambda _: self._on_t2_proj_change())

        sel_proj  = self._t2_proj_filter.get()
        goal_pool = (self._goals_for_project(sel_proj, work_mode if work_mode else None)
                     if sel_proj != "All"
                     else self._all_goals(work_mode if work_mode else None))
        goal_choices = ["All"] + goal_pool
        if self._t2_goal_filter.get() not in goal_choices:
            self._t2_goal_filter.set("All")

        tk.Label(fbar, text="Goal:", bg="#f8f8ff",
                 font=("Helvetica", 10)).pack(side="left", padx=(0, 4), pady=6)
        goal_cb = ttk.Combobox(fbar, values=goal_choices, width=18,
                               textvariable=self._t2_goal_filter, state="readonly")
        goal_cb.pack(side="left", padx=(0, 12), pady=6)
        goal_cb.bind("<<ComboboxSelected>>", lambda _: self._build_tab2())

        tk.Label(fbar, text="Priority:", bg="#f8f8ff",
                 font=("Helvetica", 10)).pack(side="left", padx=(0, 4), pady=6)
        pri_cb = ttk.Combobox(fbar, values=["All"] + PRIORITIES, width=10,
                              textvariable=self._t2_pri_filter, state="readonly")
        pri_cb.pack(side="left", padx=(0, 12), pady=6)
        pri_cb.bind("<<ComboboxSelected>>", lambda _: self._build_tab2())

        tk.Checkbutton(fbar, text="Show Completed", variable=self._t2_show_done,
                       bg="#f8f8ff", command=self._build_tab2).pack(
                       side="left", padx=(0, 10), pady=6)

        # ── Task table (reactive to all filters) ──────────────────────────────
        tree_sec = self._make_section(f, "All Tasks")
        tree_sec.pack(fill="x", padx=8, pady=(0, 0))

        cols = ("ID", "Task", "Goal", "Project", "Priority",
                "Type", "Due Date", "Date Added", "Done", "Notes")
        self.tree = ttk.Treeview(tree_sec, columns=cols, show="headings", height=9)
        widths = {"ID": 30, "Task": 150, "Goal": 100, "Project": 100,
                  "Priority": 65, "Type": 75, "Due Date": 85,
                  "Date Added": 85, "Done": 40, "Notes": 140}
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=widths.get(c, 100),
                             stretch=(c == "Notes"))
        vsb = ttk.Scrollbar(tree_sec, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")
        self._refresh_tree()   # fills table respecting all filters

        # Edit / Delete buttons
        btn_row = tk.Frame(f, bg="white")
        btn_row.pack(fill="x", padx=8, pady=(4, 6))
        self._btn(btn_row, "Delete Selected", "#dc3545",
                  self._delete_task).pack(side="left", padx=(0, 6))
        self._btn(btn_row, "Edit Selected", "#e07b00",
                  self._edit_task).pack(side="left")

        # ── Divider ───────────────────────────────────────────────────────────
        div = tk.Frame(f, bg="white")
        div.pack(fill="x", padx=8, pady=(10, 6))
        tk.Frame(div, height=2, bg=PURPLE).pack(fill="x")
        tk.Label(div, text="Select Tasks for Today",
                 font=("Helvetica", 13, "bold"),
                 fg=PURPLE, bg="white").pack(anchor="w", pady=(4, 0))

        # ── Task checklist (same filters as table) ────────────────────────────
        tasks      = load_tasks()
        df         = self._filtered_tasks()
        COLS_PER_ROW = 4

        if not df:
            tk.Label(f, text="No tasks match the current filters.",
                     bg="white", fg="#888").pack(pady=12)
        else:
            all_tasks = [t for t in tasks if t["task"]]
            projects  = sorted(set(t["impact_project"] for t in df))

            for row_start in range(0, len(projects), COLS_PER_ROW):
                row_projs = projects[row_start:row_start + COLS_PER_ROW]
                row_frame = tk.Frame(f, bg="white")
                row_frame.pack(fill="x", padx=10, pady=(0, 6))

                for proj in row_projs:
                    pt  = [t for t in df        if t["impact_project"] == proj]
                    apt = [t for t in all_tasks if t["impact_project"] == proj]

                    card = tk.LabelFrame(row_frame, text=f"  {proj}  ",
                                         font=("Helvetica", 11, "bold"), fg=PURPLE,
                                         bg=LIGHT, bd=2, relief="groove",
                                         padx=8, pady=6)
                    card.pack(side="left", fill="both", expand=True, padx=4, anchor="n")
                    self._mini_progress(card,
                                        sum(1 for t in apt if t["task_completed"]),
                                        len(apt), "#28a745")

                    for goal in sorted(set(t["goal"] for t in pt)):
                        gt  = [t for t in pt       if t["goal"] == goal]
                        agt = [t for t in all_tasks if t["goal"] == goal]
                        tk.Label(card, text=goal,
                                 font=("Helvetica", 11, "bold"),
                                 bg=LIGHT, fg="#333").pack(anchor="w", pady=(6, 0))
                        self._mini_progress(card,
                                            sum(1 for t in agt if t["task_completed"]),
                                            len(agt))
                        for t in gt:
                            trow = tk.Frame(card, bg=LIGHT)
                            trow.pack(fill="x", padx=6, pady=1)
                            var = tk.BooleanVar(value=(t["id"] in self._today_sel))
                            col = ("#aaa" if t["task_completed"]
                                   else PRI_COLOR.get(t["priority"], "#333"))
                            def _on(tid=t["id"], v=var):
                                if v.get(): self._today_sel.add(tid)
                                else:       self._today_sel.discard(tid)
                            label_parts = f"{t['task']}  [{t['priority']}]"
                            if t.get("due_date"):
                                label_parts += f"  📅 {t['due_date']}"
                            tk.Checkbutton(
                                trow, text=label_parts,
                                variable=var, command=_on,
                                bg=LIGHT, fg=col, activebackground=LIGHT,
                                font=("Helvetica", 10)
                            ).pack(side="left")
                            self._work_badge(trow, bool(t.get("is_work", 1)))

        self._btn(f, "Confirm Selected for Today  \u2192", PURPLE,
                  self._confirm_today).pack(pady=12)

    def _on_t2_mode_change(self):
        # Reset project/goal filters when mode changes
        self._t2_proj_filter.set("All")
        self._t2_goal_filter.set("All")
        self._build_tab2()

    def _on_t2_proj_change(self):
        self._t2_goal_filter.set("All")
        self._build_tab2()

    # ── Tab 2 helpers ─────────────────────────────────────────────────────────

    def _prefill_project(self, _=None):
        v = self.sel_edit_project.get()
        self.inp_edit_project.delete(0, "end")
        self.inp_edit_project.insert(0, v)

    def _prefill_goal(self, _=None):
        v    = self.sel_edit_goal.get()
        proj = next((t["impact_project"] for t in load_tasks()
                     if t["goal"] == v), None)
        is_w = self._is_work_for_goal(v)
        self.inp_edit_goal.delete(0, "end")
        self.inp_edit_goal.insert(0, v)
        if hasattr(self, "sel_goal_project") and proj:
            if proj in self.sel_goal_project["values"]:
                self.sel_goal_project.set(proj)
        if hasattr(self, "_eg_is_work"):
            self._eg_is_work.set(is_w)

    def _delete_task(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("None selected", "Select a row first."); return
        name = self.tree.item(sel[0])["values"][1]
        if messagebox.askyesno("Delete", f"Delete '{name}'? Cannot be undone."):
            db_exec(f"DELETE FROM {TABLE} WHERE id=?", (int(sel[0]),))
            self._refresh_tree()

    def _edit_task(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("None selected", "Select a row first."); return
        task_id = int(sel[0])
        full    = next((t for t in load_tasks() if t["id"] == task_id), {})

        all_projs = self._all_projects()
        all_goals = self._all_goals()

        dlg = tk.Toplevel(self)
        dlg.title("Edit Task")
        dlg.geometry("460x570")
        dlg.grab_set()
        dlg.configure(bg="white")

        # Helper for consistent label+widget rows
        def row_lbl(text, pady_top=8):
            tk.Label(dlg, text=text, bg="white",
                     font=("Helvetica", 10)).pack(anchor="w", padx=20,
                                                   pady=(pady_top, 0))

        row_lbl("Task Name", pady_top=15)
        e_task = tk.Entry(dlg, width=44)
        e_task.insert(0, full.get("task") or "")
        e_task.pack(padx=20, pady=(2, 0), fill="x")

        row_lbl("Impact Project")
        e_proj = ttk.Combobox(dlg, values=all_projs, state="readonly", width=42)
        e_proj.set(full.get("impact_project") or (all_projs[0] if all_projs else ""))
        e_proj.pack(padx=20, pady=(2, 0), fill="x")

        # Goal dropdown cascades from project
        def refresh_goal_cb(*_):
            proj  = e_proj.get()
            goals = self._goals_for_project(proj)
            e_goal["values"] = goals
            if full.get("goal") in goals:
                e_goal.set(full.get("goal"))
            elif goals:
                e_goal.current(0)

        row_lbl("Goal")
        cur_goals = self._goals_for_project(full.get("impact_project", ""))
        e_goal = ttk.Combobox(dlg, values=cur_goals, state="readonly", width=42)
        e_goal.set(full.get("goal") or (cur_goals[0] if cur_goals else ""))
        e_goal.pack(padx=20, pady=(2, 0), fill="x")
        e_proj.bind("<<ComboboxSelected>>", refresh_goal_cb)

        row_lbl("Priority")
        e_pri = ttk.Combobox(dlg, values=PRIORITIES, state="readonly", width=42)
        e_pri.set(full.get("priority") or "Medium")
        e_pri.pack(padx=20, pady=(2, 0), fill="x")

        row_lbl("Due Date  (YYYY-MM-DD, optional)")
        e_due = tk.Entry(dlg, width=20)
        e_due.insert(0, full.get("due_date") or "")
        e_due.pack(padx=20, pady=(2, 0), anchor="w")

        row_lbl("Date Added  (YYYY-MM-DD, optional)")
        e_created = tk.Entry(dlg, width=20)
        e_created.insert(0, full.get("created_date") or "")
        e_created.pack(padx=20, pady=(2, 0), anchor="w")

        row_lbl("Notes")
        e_notes = tk.Text(dlg, height=3, width=44)
        e_notes.insert("1.0", full.get("notes") or "")
        e_notes.pack(padx=20, pady=(2, 8), fill="x")

        def save():
            notes   = e_notes.get("1.0", "end").strip() or None
            due_raw = e_due.get().strip()
            if due_raw:
                try:
                    date.fromisoformat(due_raw)
                except ValueError:
                    messagebox.showwarning("Invalid date",
                                           "Due Date must be YYYY-MM-DD"); return
            created_raw = e_created.get().strip()
            if created_raw:
                try:
                    date.fromisoformat(created_raw)
                except ValueError:
                    messagebox.showwarning("Invalid date",
                                           "Date Added must be YYYY-MM-DD"); return
            due_date     = due_raw     or None
            created_date = created_raw or None
            new_proj = e_proj.get()
            new_goal = e_goal.get()
            is_work  = 1 if self._is_work_for_goal(new_goal) else 0
            db_exec(
                f"UPDATE {TABLE} SET task=?,impact_project=?,goal=?,"
                f"priority=?,notes=?,due_date=?,created_date=?,is_work=? WHERE id=?",
                (e_task.get().strip(), new_proj, new_goal,
                 e_pri.get(), notes, due_date, created_date, is_work, task_id))
            self._refresh_tree()
            dlg.destroy()

        self._btn(dlg, "Save", PURPLE, save).pack(pady=8)

    def _rename_project(self):
        old = self.sel_edit_project.get()
        new = self.inp_edit_project.get().strip()
        if not new or new == old:
            messagebox.showwarning("No change", "Enter a different name."); return
        if messagebox.askyesno("Rename", f"Rename '{old}' to '{new}'?"):
            db_exec(f"UPDATE {TABLE} SET impact_project=? WHERE impact_project=?",
                    (new, old))
            self._build_tab2()

    def _save_goal(self):
        old  = self.sel_edit_goal.get()
        new  = self.inp_edit_goal.get().strip()
        proj = self.sel_goal_project.get()
        is_w = 1 if self._eg_is_work.get() else 0
        if not new:
            messagebox.showwarning("Missing", "Enter a goal name."); return
        if messagebox.askyesno("Save Goal", f"Update goal '{old}'?"):
            # Update all rows with this goal (name, project, is_work)
            db_exec(
                f"UPDATE {TABLE} SET goal=?,impact_project=?,is_work=? WHERE goal=?",
                (new, proj, is_w, old))
            self._build_tab2()

    def _confirm_today(self):
        if not self._today_sel:
            messagebox.showwarning("Nothing selected", "Tick some tasks first."); return
        for tid in self._today_sel:
            db_exec(
                f"UPDATE {TABLE} SET selected_today=1,selected_date=? WHERE id=?",
                (TODAY, tid))
        n = len(self._today_sel)
        self._today_sel.clear()
        messagebox.showinfo("Done", f"{n} task(s) added to today's list!")
        self._build_tab2()

    # ── Tab 3: Tasks for Today ────────────────────────────────────────────────

    def _build_tab3(self):
        self._clear("Tasks for Today")
        f = self._tab_frames["Tasks for Today"]
        f.configure(bg="white")

        self._mode_bar(f, self._build_tab3)

        work_mode = self._work_mode.get()
        all_tasks = [t for t in load_tasks()
                     if t["task"] and t["selected_today"] == 1
                     and t.get("selected_date") == TODAY]
        tasks = ([t for t in all_tasks if t.get("is_work", 1) == 1]
                 if work_mode else all_tasks)

        if not tasks:
            tk.Label(f, text="No tasks selected for today.",
                     font=("Helvetica", 13), bg="white").pack(pady=20)
            tk.Label(f,
                     text="Go to 'My Tasks', check tasks, then click "
                          "'Confirm Selected for Today'.",
                     fg="#888", bg="white").pack()
        else:
            projects   = sorted(set(t["impact_project"] for t in tasks))
            COLS_PER_ROW = 4

            for row_start in range(0, len(projects), COLS_PER_ROW):
                row_projs = projects[row_start:row_start + COLS_PER_ROW]
                row_frame = tk.Frame(f, bg="white")
                row_frame.pack(fill="x", padx=10, pady=(0, 6))

                for proj in row_projs:
                    pt   = [t for t in tasks if t["impact_project"] == proj]
                    card = tk.LabelFrame(row_frame, text=f"  {proj}  ",
                                         font=("Helvetica", 11, "bold"), fg=PURPLE,
                                         bg=LIGHT, bd=2, relief="groove",
                                         padx=8, pady=6)
                    card.pack(side="left", fill="both", expand=True, padx=4, anchor="n")
                    for goal in sorted(set(t["goal"] for t in pt)):
                        tk.Label(card, text=goal, font=("Helvetica", 11, "bold"),
                                 bg=LIGHT).pack(anchor="w", pady=(6, 2))
                        for t in [x for x in pt if x["goal"] == goal]:
                            self._task_row(card, t)

        self._btn(f, "Reset Today's List", "#dc3545",
                  self._reset_today).pack(pady=12)

        if self.timer_task_id is not None and self._after_id is None:
            self._tick()

    def _task_row(self, parent, t):
        is_done = bool(t["task_completed"])
        is_mine = (self.timer_task_id == t["id"])
        saved_s = int((t.get("time_spent") or 0) * 3600)
        col     = "#aaa" if is_done else PRI_COLOR.get(t["priority"], "#333")

        row = tk.Frame(parent, bg=LIGHT)
        row.pack(fill="x", pady=2)

        var = tk.BooleanVar(value=is_done)
        def on_complete(tid=t["id"], v=var):
            val = 1 if v.get() else 0
            if val == 1 and self.timer_task_id == tid:
                self._stop_timer(tid)
            db_exec(f"UPDATE {TABLE} SET task_completed=? WHERE id=?", (val, tid))
            self._build_tab3()

        tk.Checkbutton(row, variable=var, command=on_complete,
                       bg=LIGHT, activebackground=LIGHT).pack(side="left")

        label = f"{t['task']}  [{t['priority']}]"
        if t.get("due_date"):
            label += f"  \U0001f4c5 {t['due_date']}"
        tk.Label(row, text=label, fg=col, bg=LIGHT,
                 font=("Helvetica", 10)).pack(side="left")
        self._work_badge(row, bool(t.get("is_work", 1)))

        if not is_done:
            if is_mine:
                disp_text, disp_color = f"  \u25cf {fmt_secs(saved_s)}", "#dc3545"
            elif saved_s > 0:
                disp_text, disp_color = f"  \u23f8 {fmt_secs(saved_s)}", "#888"
            else:
                disp_text, disp_color = "", "#888"

            lbl = tk.Label(row, text=disp_text, fg=disp_color,
                           font=("Courier", 10), bg=LIGHT, width=14, anchor="w")
            lbl.pack(side="left", padx=(6, 4))
            if is_mine:
                self._timer_label = lbl

            btn_text  = "Pause"   if is_mine else ("Resume" if saved_s > 0 else "Start")
            btn_color = "#dc3545" if is_mine else "#28a745"

            def on_timer(tid=t["id"], base=saved_s, label=lbl, running=is_mine):
                if running:
                    self._stop_timer(tid); self._build_tab3()
                else:
                    if self.timer_task_id is not None:
                        self._stop_timer(self.timer_task_id)
                    self._start_timer(tid, base, label)

            self._btn(row, btn_text, btn_color, on_timer, width=7).pack(side="left")

        if t.get("notes"):
            tk.Label(parent, text=t["notes"], fg="#aaa",
                     font=("Helvetica", 9), bg=LIGHT).pack(anchor="w", padx=20)

    # ── Timer ─────────────────────────────────────────────────────────────────

    def _start_timer(self, task_id, base_secs, label):
        self.timer_task_id = task_id
        self.timer_start_t = time.time()
        self.timer_base_s  = float(base_secs)
        self._timer_label  = label
        self._tick()

    def _tick(self):
        if self.timer_task_id is None:
            return
        elapsed = (time.time() - self.timer_start_t) + self.timer_base_s
        lbl = self._timer_label
        if lbl is not None:
            try:
                if lbl.winfo_exists():
                    lbl.configure(text=f"  \u25cf {fmt_secs(elapsed)}",
                                  fg="#dc3545")
                else:
                    self._after_id = None
                    return
            except tk.TclError:
                self._after_id = None
                return
        self._after_id = self.after(1000, self._tick)

    def _stop_timer(self, task_id):
        if self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None
        if self.timer_start_t is not None and self.timer_task_id == task_id:
            elapsed_h = (time.time() - self.timer_start_t) / 3600.0
            row = next((t for t in load_tasks() if t["id"] == task_id), None)
            prev = float(row.get("time_spent") or 0) if row else 0.0
            db_exec(f"UPDATE {TABLE} SET time_spent=? WHERE id=?",
                    (prev + elapsed_h, task_id))
        self.timer_task_id = None
        self.timer_start_t = None
        self.timer_base_s  = 0.0
        self._timer_label  = None

    def _reset_today(self):
        if self.timer_task_id is not None:
            self._stop_timer(self.timer_task_id)
        if messagebox.askyesno("Reset", "Clear today's list? Tasks won't be deleted."):
            db_exec(f"UPDATE {TABLE} SET selected_today=0 WHERE selected_date=?",
                    (TODAY,))
            self._build_tab3()

    # ── Tab 4: Completed Tasks ────────────────────────────────────────────────

    def _build_tab4(self):
        self._clear("Completed Tasks")
        f = self._tab_frames["Completed Tasks"]
        f.configure(bg="white")

        self._mode_bar(f, self._build_tab4)

        work_mode = self._work_mode.get()
        all_done  = [t for t in load_tasks() if t["task"] and t["task_completed"]]
        tasks     = ([t for t in all_done if t.get("is_work", 1) == 1]
                     if work_mode else all_done)

        cols  = ("Project", "Goal", "Task", "Priority",
                 "Type", "Due Date", "Time (h)", "Notes")
        tree  = ttk.Treeview(f, columns=cols, show="headings", height=20)
        widths = {"Project": 120, "Goal": 120, "Task": 160, "Priority": 70,
                  "Type": 75, "Due Date": 85, "Time (h)": 65, "Notes": 180}
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=widths.get(c, 100))
        for t in tasks:
            tree.insert("", "end", values=(
                t["impact_project"], t["goal"], t["task"], t["priority"],
                "Work" if t.get("is_work", 1) else "Non-work",
                t.get("due_date") or "",
                round(float(t.get("time_spent") or 0), 2),
                t["notes"] or ""))
        sb = ttk.Scrollbar(f, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        sb.pack(side="left", fill="y", pady=10)

    # ── Tab 5: Weekly Summary ─────────────────────────────────────────────────

    def _build_tab5(self):
        self._clear("Weekly Summary")
        f = self._tab_frames["Weekly Summary"]
        f.configure(bg="white")

        self._mode_bar(f, self._build_tab5)

        work_mode  = self._work_mode.get()
        all_tasks  = [t for t in load_tasks() if t["task"]]
        tasks      = ([t for t in all_tasks if t.get("is_work", 1) == 1]
                      if work_mode else all_tasks)

        week_start = str(date.today() - timedelta(days=6))
        done_week  = [t for t in tasks if t["task_completed"]
                      and t.get("selected_date")
                      and t["selected_date"] >= week_start]
        total_done = sum(1 for t in tasks if t["task_completed"])
        total_all  = len(tasks)
        rate       = f"{round(100*total_done/total_all)}%" if total_all else "-"

        stat_row = tk.Frame(f, bg="white")
        stat_row.pack(fill="x", padx=10, pady=10)
        for title, val, col in [
            ("Completed This Week", str(len(done_week)), PURPLE),
            ("Overall Progress",    f"{total_done} / {total_all}", PURPLE),
            ("Completion Rate",     rate, PURPLE),
        ]:
            card = tk.Frame(stat_row, bd=1, relief="solid", bg="white",
                            padx=12, pady=10)
            card.pack(side="left", fill="both", expand=True, padx=4)
            tk.Label(card, text=title, font=("Helvetica", 10, "bold"),
                     fg="#555", bg="white").pack()
            tk.Label(card, text=val, font=("Helvetica", 22, "bold"),
                     fg=col, bg="white").pack()

        tk.Label(f, text="By Impact Project",
                 font=("Helvetica", 13, "bold"), bg="white",
                 fg="#333").pack(anchor="w", padx=10, pady=(10, 4))
        proj_row = tk.Frame(f, bg="white")
        proj_row.pack(fill="x", padx=10)
        for proj in sorted(set(t["impact_project"] for t in tasks)):
            pt    = [t for t in tasks if t["impact_project"] == proj]
            done  = sum(1 for t in pt if t["task_completed"])
            hours = round(sum(float(t.get("time_spent") or 0) for t in pt), 1)
            card  = tk.LabelFrame(proj_row, text=f"  {proj}  ",
                                  font=("Helvetica", 10, "bold"), fg=PURPLE,
                                  bg=LIGHT, bd=1, padx=8, pady=6)
            card.pack(side="left", fill="both", expand=True, padx=4)
            if hours > 0:
                tk.Label(card, text=f"{hours}h tracked",
                         fg="#888", bg=LIGHT,
                         font=("Helvetica", 9)).pack(anchor="w")
            self._mini_progress(card, done, len(pt))

        tk.Label(f, text="By Priority",
                 font=("Helvetica", 13, "bold"), bg="white",
                 fg="#333").pack(anchor="w", padx=10, pady=(14, 4))
        cols = ("Priority", "Completed", "Rate")
        tree = ttk.Treeview(f, columns=cols, show="headings", height=4)
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=150)
        for pri in PRIORITIES:
            pt   = [t for t in tasks if t["priority"] == pri]
            done = sum(1 for t in pt if t["task_completed"])
            pct  = f"{round(100*done/len(pt))}%" if pt else "-"
            tree.insert("", "end", values=(pri, f"{done}/{len(pt)}", pct))
        tree.pack(fill="x", padx=10, pady=(0, 10))


if __name__ == "__main__":
    app = App()
    app.mainloop()


