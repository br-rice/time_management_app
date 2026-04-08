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

        self._work_mode = tk.BooleanVar(value=True)

        # Tab 2 filters
        self._t2_pri_filter  = tk.StringVar(value="All")
        self._t2_proj_filter = tk.StringVar(value="All")
        self._t2_goal_filter = tk.StringVar(value="All")
        self._t2_show_done   = tk.BooleanVar(value=False)

        # Tab 2 collapsible state
        # projects: expanded by default (collapsed if in set)
        # goals:    collapsed by default (expanded if in set)
        self._t2_collapsed_proj  = set()
        self._t2_expanded_goal   = set()
        self._t2_pending_add_task = None   # (proj, goal) tuple
        self._t2_pending_add_goal = None   # proj string

        # Tab 1 add-goal form
        self._t1g_project = tk.StringVar(value="")
        self._t1g_is_work = tk.BooleanVar(value=True)

        # Quick-add / task form (shared vars)
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
        """Slim progress bar — shows only the filled bar + a small % pill. No done/total counts."""
        pct = done / total if total > 0 else 0
        row = tk.Frame(parent, bg=bg)
        row.pack(fill="x", pady=(2, 4))
        pct_text = f"{round(pct * 100)}%"
        tk.Label(row, text=pct_text, font=("Helvetica", 8),
                 fg="#999", bg=bg).pack(side="right", padx=(4, 0))
        bar_bg = tk.Frame(row, bg="#e4e4e4", height=5)
        bar_bg.pack(side="left", fill="x", expand=True)
        bar_bg.update_idletasks()
        w = max(1, int(bar_bg.winfo_reqwidth() * pct))
        tk.Frame(bar_bg, bg=color, height=5, width=w).pack(side="left")

    def _work_badge(self, parent, is_work, bg=LIGHT):
        color = WORK_COLOR if is_work else NONW_COLOR
        text  = "Work" if is_work else "Non-work"
        tk.Label(parent, text=text,
                 font=("Helvetica", 8, "bold"), fg="white", bg=color,
                 padx=4, pady=1).pack(side="left", padx=(4, 0))

    def _pri_dot(self, parent, priority, bg=LIGHT):
        """Small colored dot indicating priority — replaces verbose [Priority] bracket text."""
        col = PRI_COLOR.get(priority, "#ccc")
        tk.Label(parent, text="●", fg=col, bg=bg,
                 font=("Helvetica", 9)).pack(side="left", padx=(0, 2))

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

    def _build_tab1(self):
        self._clear("Add Tasks")
        f = self._tab_frames["Add Tasks"]
        f.configure(bg="white")

        all_projects = self._all_projects()

        # ── ⚡ Quick-Add Banner ────────────────────────────────────────────────
        qa_outer = tk.Frame(f, bg=PURPLE)
        qa_outer.pack(fill="x", padx=8, pady=(10, 8))

        tk.Label(qa_outer, text="⚡  Quick Add Task",
                 fg="white", bg=PURPLE,
                 font=("Helvetica", 12, "bold")).pack(
                     anchor="w", padx=14, pady=(10, 6))

        qa = tk.Frame(qa_outer, bg=PURPLE)
        qa.pack(fill="x", padx=14, pady=(0, 12))

        # Helper for white entry inside purple banner
        def _qa_entry(width, hint=""):
            e = tk.Entry(qa, width=width, relief="flat", bd=0,
                         highlightthickness=1,
                         highlightcolor="white",
                         highlightbackground="#9580e8",
                         bg="white", fg="#222",
                         font=("Helvetica", 11))
            if hint:
                e.insert(0, hint)
                e.config(fg="#aaa")
                def _focus_in(ev, widget=e, h=hint):
                    if widget.get() == h:
                        widget.delete(0, "end")
                        widget.config(fg="#222")
                def _focus_out(ev, widget=e, h=hint):
                    if not widget.get():
                        widget.insert(0, h)
                        widget.config(fg="#aaa")
                e.bind("<FocusIn>",  _focus_in)
                e.bind("<FocusOut>", _focus_out)
            return e

        # Column labels
        for col_idx, label in enumerate(
                ["Project", "Goal", "Task Name", "Priority", "Due (YYYY-MM-DD)", "Notes (optional)"]):
            tk.Label(qa, text=label, fg="#d4c8ff", bg=PURPLE,
                     font=("Helvetica", 9)).grid(row=0, column=col_idx,
                                                  sticky="w", padx=(0, 6))

        # Project
        self._qa_proj_cb = self._combo(qa, all_projects, width=15,
                                        textvariable=self._t1t_project)
        self._qa_proj_cb.grid(row=1, column=0, padx=(0, 6), ipady=2)
        self._qa_proj_cb.bind("<<ComboboxSelected>>",
                               lambda _: self._refresh_qa_goals())

        # Goal
        qa_goals = (self._goals_for_project(self._t1t_project.get())
                    if self._t1t_project.get() else [])
        self._qa_goal_cb = self._combo(qa, qa_goals, width=15,
                                        textvariable=self._t1t_goal)
        self._qa_goal_cb.grid(row=1, column=1, padx=(0, 6), ipady=2)

        # Task name (wider)
        self._qa_task_entry = _qa_entry(28)
        self._qa_task_entry.grid(row=1, column=2, padx=(0, 6), ipady=4)
        self._qa_task_entry.bind("<Return>", lambda _: self._qa_add_task())

        # Priority
        self._qa_pri_cb = self._combo(qa, PRIORITIES, width=9)
        self._qa_pri_cb.grid(row=1, column=3, padx=(0, 6), ipady=2)
        self._qa_pri_cb.current(1)   # default Medium

        # Due date
        self._qa_due_entry = _qa_entry(13)
        self._qa_due_entry.grid(row=1, column=4, padx=(0, 6), ipady=4)

        # Notes
        self._qa_notes_entry = _qa_entry(22)
        self._qa_notes_entry.grid(row=1, column=5, padx=(0, 6), ipady=4)

        # Add button
        tk.Label(qa, text="", bg=PURPLE).grid(row=0, column=6)
        tk.Button(qa, text="Add  →", bg="#28a745", fg="white",
                  relief="flat", font=("Helvetica", 11, "bold"),
                  padx=16, pady=6, cursor="hand2",
                  activebackground="#218838", activeforeground="white",
                  command=self._qa_add_task).grid(row=1, column=6)

        qa.columnconfigure(2, weight=1)

        # ── Below: Add Goal + Manage sections ────────────────────────────────
        mid = tk.Frame(f, bg="white")
        mid.pack(fill="x", padx=8, pady=(2, 8))

        # Add Goal (compact horizontal layout)
        gc = self._make_section(mid, "Add New Goal")
        gc.pack(side="left", fill="both", expand=True, padx=(0, 6))

        row_g = tk.Frame(gc, bg=LIGHT)
        row_g.pack(fill="x", pady=(0, 6))
        self._lbl(row_g, "Project:", bg=LIGHT).pack(side="left", padx=(0, 6))
        self._t1g_proj_cb = self._combo(row_g, all_projects, width=18,
                                         textvariable=self._t1g_project)
        self._t1g_proj_cb.pack(side="left")
        self._btn(row_g, "+ New", "#888",
                  lambda: self._new_project_dialog(self._t1g_project,
                                                   self._build_tab1),
                  width=6).pack(side="left", padx=(6, 0))

        row_gn = tk.Frame(gc, bg=LIGHT)
        row_gn.pack(fill="x", pady=(0, 6))
        self._lbl(row_gn, "Goal name:", bg=LIGHT).pack(side="left", padx=(0, 6))
        self.inp_goal = self._entry(row_gn, width=22)
        self.inp_goal.pack(side="left", fill="x", expand=True)

        row_gt = tk.Frame(gc, bg=LIGHT)
        row_gt.pack(fill="x", pady=(0, 8))
        self._lbl(row_gt, "Type:", bg=LIGHT).pack(side="left", padx=(0, 6))
        self._work_toggle(row_gt, self._t1g_is_work).pack(side="left")

        self._btn(gc, "Add Goal", PURPLE, self._add_goal)

        # Rename Project
        ep = self._make_section(mid, "Rename Project")
        ep.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self._lbl(ep, "Select Project").grid(row=0, column=0, sticky="w")
        self.sel_edit_project = self._combo(ep, self._all_projects())
        self.sel_edit_project.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        self.sel_edit_project.bind("<<ComboboxSelected>>", self._prefill_project)
        self._lbl(ep, "New Name").grid(row=2, column=0, sticky="w")
        self.inp_edit_project = self._entry(ep)
        self.inp_edit_project.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self._btn(ep, "Rename", "#e07b00",
                  self._rename_project).grid(row=4, column=0, sticky="w")
        ep.columnconfigure(0, weight=1)

        # Edit Goal
        eg = self._make_section(mid, "Edit Goal")
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

    # ── Quick-Add helpers ─────────────────────────────────────────────────────

    def _refresh_qa_goals(self):
        proj  = self._t1t_project.get()
        goals = self._goals_for_project(proj) if proj else []
        self._qa_goal_cb["values"] = goals
        if goals:
            self._qa_goal_cb.current(0)
            self._t1t_goal.set(goals[0])
        else:
            self._t1t_goal.set("")

    # kept for compatibility
    def _refresh_t1_goal_dropdown(self):
        self._refresh_qa_goals()

    def _qa_add_task(self):
        """Add task from the quick-add bar."""
        project  = self._t1t_project.get().strip()
        goal     = self._t1t_goal.get().strip()
        task     = self._qa_task_entry.get().strip()
        priority = self._qa_pri_cb.get() or "Medium"
        due_raw  = self._qa_due_entry.get().strip()
        notes    = self._qa_notes_entry.get().strip() or None

        if not project or not goal or not task:
            messagebox.showwarning("Missing",
                                   "Select a project, goal, and enter a task name.")
            return
        if due_raw:
            try:
                date.fromisoformat(due_raw)
            except ValueError:
                messagebox.showwarning("Invalid date", "Due Date must be YYYY-MM-DD")
                return

        is_work = 1 if self._is_work_for_goal(goal) else 0
        db_exec(
            f"INSERT INTO {TABLE} (impact_project,goal,task,task_completed,"
            f"selected_today,priority,time_spent,is_work,due_date,created_date,notes)"
            f" VALUES(?,?,?,0,0,?,0,?,?,?,?)",
            (project, goal, task, priority, is_work,
             due_raw or None, str(date.today()), notes))

        # Clear task/due/notes fields; keep project/goal so batch adds are fast
        self._qa_task_entry.delete(0, "end")
        self._qa_due_entry.delete(0, "end")
        self._qa_notes_entry.delete(0, "end")
        self._qa_task_entry.focus()

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

    # ── Tab 2: My Tasks ───────────────────────────────────────────────────────

    def _build_tab2(self):
        self._clear("My Tasks")
        f = self._tab_frames["My Tasks"]
        f.configure(bg="white")

        self._mode_bar(f, self._on_t2_mode_change)

        # ── Filter bar ────────────────────────────────────────────────────────
        fbar = tk.Frame(f, bg="#f8f8ff", bd=1, relief="flat")
        fbar.pack(fill="x", padx=8, pady=(0, 6))

        tk.Label(fbar, text="Priority:", bg="#f8f8ff",
                 font=("Helvetica", 10)).pack(side="left", padx=(10, 4), pady=6)
        pri_cb = ttk.Combobox(fbar, values=["All"] + PRIORITIES, width=10,
                              textvariable=self._t2_pri_filter, state="readonly")
        pri_cb.pack(side="left", padx=(0, 12), pady=6)
        pri_cb.bind("<<ComboboxSelected>>", lambda _: self._build_tab2())

        tk.Checkbutton(fbar, text="Show Completed", variable=self._t2_show_done,
                       bg="#f8f8ff", command=self._build_tab2).pack(
                       side="left", padx=(0, 10), pady=6)

        # ── "+ New Project" button ────────────────────────────────────────────
        top = tk.Frame(f, bg="white")
        top.pack(fill="x", padx=8, pady=(0, 4))
        self._btn(top, "+ New Project", "#28a745",
                  lambda: self._inline_add_project(f)).pack(side="left")

        # ── Tree ──────────────────────────────────────────────────────────────
        work_mode = self._work_mode.get()
        show_done = self._t2_show_done.get()
        pri_val   = self._t2_pri_filter.get()

        all_tasks = load_tasks()
        if work_mode:
            all_tasks = [t for t in all_tasks if t.get("is_work", 1) == 1]

        projects = sorted(set(t["impact_project"] for t in all_tasks
                              if t["impact_project"]))

        if not projects:
            tk.Label(f,
                     text="No projects yet. Click '+ New Project' to get started.",
                     bg="white", fg="#888",
                     font=("Helvetica", 11)).pack(pady=20)
        else:
            for proj in projects:
                proj_tasks = [t for t in all_tasks if t["impact_project"] == proj]
                self._render_proj_group(f, proj, proj_tasks, show_done, pri_val)

    def _toggle_proj(self, proj):
        if proj in self._t2_collapsed_proj:
            self._t2_collapsed_proj.discard(proj)
        else:
            self._t2_collapsed_proj.add(proj)
        self._build_tab2()

    def _toggle_goal(self, key):
        if key in self._t2_expanded_goal:
            self._t2_expanded_goal.discard(key)
        else:
            self._t2_expanded_goal.add(key)
        self._build_tab2()

    def _render_proj_group(self, parent, proj, all_proj_tasks, show_done, pri_val):
        is_collapsed = proj in self._t2_collapsed_proj

        task_count = sum(1 for t in all_proj_tasks if t["task"])
        done_count = sum(1 for t in all_proj_tasks
                         if t["task"] and t["task_completed"])
        count_str  = f"  ({done_count}/{task_count})" if task_count else ""

        hdr = tk.Frame(parent, bg="white")
        hdr.pack(fill="x", pady=(10, 0), padx=8)
        tk.Frame(hdr, bg=PURPLE, width=4).pack(side="left", fill="y")

        arrow    = "▶" if is_collapsed else "▼"
        name_btn = tk.Button(hdr, text=f"   {arrow}   {proj}{count_str}",
                             font=("Helvetica", 12, "bold"), fg=PURPLE,
                             bg="white", relief="flat", anchor="w",
                             cursor="hand2", activebackground="#f0f0ff",
                             command=lambda p=proj: self._toggle_proj(p))
        name_btn.pack(side="left", fill="x", expand=True, ipady=5)
        name_btn.bind("<Double-Button-1>",
                      lambda e, b=name_btn, p=proj: self._start_rename_proj(b, p))

        tk.Frame(parent, bg="#e8e0ff", height=1).pack(fill="x", padx=8)

        if is_collapsed:
            self._btn(hdr, "Rename", "#999",
                      lambda b=name_btn, p=proj: self._start_rename_proj(b, p),
                      width=6).pack(side="right", padx=(0, 8))
            return

        content = tk.Frame(parent, bg="white")
        content.pack(fill="x", padx=(28, 8), pady=(0, 4))

        self._btn(hdr, "+ Goal", "#28a745",
                  lambda c=content, p=proj: self._inline_add_goal(c, p),
                  width=6).pack(side="right", padx=(0, 8))
        self._btn(hdr, "Rename", "#999",
                  lambda b=name_btn, p=proj: self._start_rename_proj(b, p),
                  width=6).pack(side="right", padx=(0, 4))

        goals = sorted(set(t["goal"] for t in all_proj_tasks if t["goal"]))
        for goal in goals:
            goal_tasks = [t for t in all_proj_tasks if t["goal"] == goal]
            self._render_goal_group(content, proj, goal, goal_tasks,
                                    show_done, pri_val)

        if self._t2_pending_add_goal == proj:
            self._t2_pending_add_goal = None
            self._inline_add_goal(content, proj)

    def _render_goal_group(self, parent, proj, goal, all_goal_tasks,
                           show_done, pri_val):
        key         = f"{proj}::{goal}"
        is_expanded = key in self._t2_expanded_goal

        task_count = sum(1 for t in all_goal_tasks if t["task"])
        done_count = sum(1 for t in all_goal_tasks
                         if t["task"] and t["task_completed"])
        count_str  = f"  ({done_count}/{task_count})" if task_count else ""

        hdr = tk.Frame(parent, bg="white")
        hdr.pack(fill="x", pady=(6, 0))
        tk.Frame(hdr, bg="#bbb", width=2).pack(side="left", fill="y")

        arrow    = "▼" if is_expanded else "▶"
        name_btn = tk.Button(hdr, text=f"   {arrow}   {goal}{count_str}",
                             font=("Helvetica", 10, "bold"), fg="#444",
                             bg="white", relief="flat", anchor="w",
                             cursor="hand2", activebackground="#f8f8ff",
                             command=lambda k=key: self._toggle_goal(k))
        name_btn.pack(side="left", fill="x", expand=True, ipady=3)
        name_btn.bind("<Double-Button-1>",
                      lambda e, b=name_btn, p=proj, g=goal:
                      self._start_rename_goal(b, p, g))

        if is_expanded:
            content = tk.Frame(parent, bg="white")
            content.pack(fill="x", padx=(20, 0), pady=(2, 0))

            self._btn(hdr, "+ Task", "#28a745",
                      lambda c=content, p=proj, g=goal:
                      self._inline_add_task(c, p, g),
                      width=6).pack(side="right", padx=(0, 4))
            self._btn(hdr, "Edit", "#999",
                      lambda b=name_btn, p=proj, g=goal:
                      self._start_rename_goal(b, p, g),
                      width=4).pack(side="right", padx=(0, 4))

            display_tasks = [t for t in all_goal_tasks if t["task"]]
            if not show_done:
                display_tasks = [t for t in display_tasks
                                 if not t["task_completed"]]
            if pri_val != "All":
                display_tasks = [t for t in display_tasks
                                 if t["priority"] == pri_val]

            for t in display_tasks:
                self._render_task_row_t2(content, t)

            if self._t2_pending_add_task == (proj, goal):
                self._t2_pending_add_task = None
                self._inline_add_task(content, proj, goal)
        else:
            self._btn(hdr, "+ Task", "#28a745",
                      lambda p=proj, g=goal: self._expand_and_add_task(p, g),
                      width=6).pack(side="right", padx=(0, 4))
            self._btn(hdr, "Edit", "#999",
                      lambda b=name_btn, p=proj, g=goal:
                      self._start_rename_goal(b, p, g),
                      width=4).pack(side="right", padx=(0, 4))

    def _render_task_row_t2(self, parent, t):
        bg = "white"
        outer = tk.Frame(parent, bg=bg)
        outer.pack(fill="x", pady=1)
        tk.Frame(outer, bg="#ececec", height=1).pack(fill="x")

        row = tk.Frame(outer, bg=bg)
        row.pack(fill="x", padx=4, pady=(3, 1))

        self._pri_dot(row, t["priority"], bg=bg)

        col        = "#aaa" if t["task_completed"] else "#222"
        font_style = ("Helvetica", 10, "overstrike") if t["task_completed"] \
                     else ("Helvetica", 10)
        label = t["task"]
        if t.get("due_date"):
            label += f"  📅 {t['due_date']}"
        task_lbl = tk.Label(row, text=label, fg=col, bg=bg,
                            font=font_style, anchor="w", cursor="hand2")
        task_lbl.pack(side="left", fill="x", expand=True)
        task_lbl.bind("<Double-Button-1>",
                      lambda e, tid=t["id"], o=outer:
                      self._open_inline_edit(tid, o))
        self._work_badge(row, bool(t.get("is_work", 1)), bg=bg)

        # Today toggle — green when active, grey when not
        is_today   = (t.get("selected_today") == 1
                      and t.get("selected_date") == TODAY)
        today_bg   = "#28a745" if is_today else "#bbb"
        today_text = "✓ Today" if is_today else "+ Today"
        tk.Button(row, text=today_text, bg=today_bg, fg="white",
                  relief="flat", font=("Helvetica", 9), padx=6, pady=2,
                  cursor="hand2", activeforeground="white",
                  activebackground=today_bg,
                  command=lambda tid=t["id"]: self._toggle_today(tid)).pack(
                  side="right", padx=(4, 0))

        self._btn(row, "Del", "#dc3545",
                  lambda tid=t["id"], n=t["task"]:
                  self._delete_task_inline(tid, n),
                  width=3).pack(side="right", padx=(4, 0))
        self._btn(row, "Edit", "#e07b00",
                  lambda tid=t["id"], o=outer:
                  self._open_inline_edit(tid, o),
                  width=4).pack(side="right", padx=(4, 0))

        if t.get("notes"):
            tk.Label(outer, text=f"  ↳ {t['notes']}", fg="#999",
                     font=("Helvetica", 9), bg=bg,
                     anchor="w").pack(fill="x", padx=(20, 4), pady=(0, 2))

    def _delete_task_inline(self, task_id, name):
        if messagebox.askyesno("Delete", f"Delete '{name}'? Cannot be undone."):
            db_exec(f"DELETE FROM {TABLE} WHERE id=?", (task_id,))
            self._today_sel.discard(task_id)
            self._build_tab2()

    def _open_inline_edit(self, task_id, container):
        for w in container.winfo_children():
            if getattr(w, "_inline_edit", False):
                w.destroy()
                return

        full      = next((t for t in load_tasks() if t["id"] == task_id), {})
        all_projs = self._all_projects()

        panel = tk.Frame(container, bg="#f0f0ff", bd=1, relief="flat")
        panel._inline_edit = True
        panel.pack(fill="x", padx=4, pady=(2, 6))

        grid = tk.Frame(panel, bg="#f0f0ff")
        grid.pack(fill="x", padx=10, pady=8)

        def _lbl(text, r, c):
            tk.Label(grid, text=text, bg="#f0f0ff",
                     font=("Helvetica", 9)).grid(
                     row=r, column=c, sticky="w", padx=(0, 8), pady=(0, 2))

        for ci, h in enumerate(["Task", "Project", "Goal",
                                 "Priority", "Due Date", "Notes"]):
            _lbl(h, 0, ci)

        def _ientry(width):
            return tk.Entry(grid, width=width, relief="flat",
                            highlightthickness=1,
                            highlightbackground="#ccc", highlightcolor=PURPLE,
                            bg="white")

        e_task = _ientry(22)
        e_task.insert(0, full.get("task") or "")
        e_task.grid(row=1, column=0, padx=(0, 8), ipady=3)

        e_proj = ttk.Combobox(grid, values=all_projs, state="readonly", width=16)
        e_proj.set(full.get("impact_project") or (all_projs[0] if all_projs else ""))
        e_proj.grid(row=1, column=1, padx=(0, 8))

        cur_goals = self._goals_for_project(full.get("impact_project", ""))
        e_goal = ttk.Combobox(grid, values=cur_goals, state="readonly", width=16)
        e_goal.set(full.get("goal") or (cur_goals[0] if cur_goals else ""))
        e_goal.grid(row=1, column=2, padx=(0, 8))

        def refresh_goals(*_):
            goals = self._goals_for_project(e_proj.get())
            e_goal["values"] = goals
            if goals:
                e_goal.current(0)
        e_proj.bind("<<ComboboxSelected>>", refresh_goals)

        e_pri = ttk.Combobox(grid, values=PRIORITIES, state="readonly", width=10)
        e_pri.set(full.get("priority") or "Medium")
        e_pri.grid(row=1, column=3, padx=(0, 8))

        e_due = _ientry(12)
        e_due.insert(0, full.get("due_date") or "")
        e_due.grid(row=1, column=4, padx=(0, 8), ipady=3)

        e_notes = _ientry(22)
        e_notes.insert(0, full.get("notes") or "")
        e_notes.grid(row=1, column=5, padx=(0, 8), ipady=3)

        btn_row = tk.Frame(panel, bg="#f0f0ff")
        btn_row.pack(anchor="e", padx=10, pady=(0, 8))

        def save():
            due_raw = e_due.get().strip()
            if due_raw:
                try:
                    date.fromisoformat(due_raw)
                except ValueError:
                    messagebox.showwarning("Invalid date",
                                           "Due Date must be YYYY-MM-DD")
                    return
            new_proj = e_proj.get()
            new_goal = e_goal.get()
            is_work  = 1 if self._is_work_for_goal(new_goal) else 0
            notes    = e_notes.get().strip() or None
            db_exec(
                f"UPDATE {TABLE} SET task=?,impact_project=?,goal=?,"
                f"priority=?,notes=?,due_date=?,is_work=? WHERE id=?",
                (e_task.get().strip(), new_proj, new_goal,
                 e_pri.get(), notes, due_raw or None, is_work, task_id))
            self._build_tab2()

        self._btn(btn_row, "Cancel", "#888",
                  lambda: panel.destroy()).pack(side="right", padx=(6, 0))
        self._btn(btn_row, "Save", PURPLE, save).pack(side="right")

    def _toggle_today(self, task_id):
        t = next((x for x in load_tasks() if x["id"] == task_id), None)
        if t is None:
            return
        if t.get("selected_today") == 1 and t.get("selected_date") == TODAY:
            db_exec(f"UPDATE {TABLE} SET selected_today=0 WHERE id=?", (task_id,))
        else:
            db_exec(
                f"UPDATE {TABLE} SET selected_today=1,selected_date=? WHERE id=?",
                (TODAY, task_id))
        self._build_tab2()

    def _expand_and_add_task(self, proj, goal):
        key = f"{proj}::{goal}"
        self._t2_expanded_goal.add(key)
        self._t2_pending_add_task = (proj, goal)
        self._build_tab2()

    def _start_rename_proj(self, btn, proj):
        parent = btn.master
        btn.pack_forget()
        e = tk.Entry(parent, font=("Helvetica", 12, "bold"),
                     fg=PURPLE, bg="white", relief="flat",
                     highlightthickness=1, highlightcolor=PURPLE,
                     highlightbackground="#aaa")
        e.insert(0, proj)
        e.select_range(0, "end")
        e.pack(side="left", fill="x", expand=True, ipady=5)
        e.focus()

        def save(event=None):
            new = e.get().strip()
            if new and new != proj:
                db_exec(
                    f"UPDATE {TABLE} SET impact_project=? WHERE impact_project=?",
                    (new, proj))
            e.destroy()
            self._build_tab2()

        e.bind("<Return>", save)
        e.bind("<Escape>", lambda ev: (e.destroy(), self._build_tab2()))
        e.bind("<FocusOut>", save)

    def _start_rename_goal(self, btn, proj, goal):
        parent = btn.master
        btn.pack_forget()
        e = tk.Entry(parent, font=("Helvetica", 10, "bold"),
                     fg="#444", bg="white", relief="flat",
                     highlightthickness=1, highlightcolor=PURPLE,
                     highlightbackground="#aaa")
        e.insert(0, goal)
        e.select_range(0, "end")
        e.pack(side="left", fill="x", expand=True, ipady=3)
        e.focus()

        def save(event=None):
            new = e.get().strip()
            if new and new != goal:
                db_exec(
                    f"UPDATE {TABLE} SET goal=? WHERE goal=? AND impact_project=?",
                    (new, goal, proj))
            e.destroy()
            self._build_tab2()

        e.bind("<Return>", save)
        e.bind("<Escape>", lambda ev: (e.destroy(), self._build_tab2()))
        e.bind("<FocusOut>", save)

    def _inline_add_project(self, parent_frame):
        for w in parent_frame.winfo_children():
            if getattr(w, "_inline_add_proj", False):
                w.destroy()
                return

        panel = tk.Frame(parent_frame, bg="#e8ffe8", bd=1, relief="flat")
        panel._inline_add_proj = True
        panel.pack(fill="x", padx=8, pady=(0, 6))

        row = tk.Frame(panel, bg="#e8ffe8")
        row.pack(fill="x", padx=10, pady=8)

        tk.Label(row, text="Project:", bg="#e8ffe8",
                 font=("Helvetica", 10)).pack(side="left", padx=(0, 4))
        e_proj = tk.Entry(row, width=18, relief="flat", highlightthickness=1,
                          highlightbackground="#ccc", highlightcolor=PURPLE,
                          bg="white")
        e_proj.pack(side="left", padx=(0, 10), ipady=3)
        e_proj.focus()

        tk.Label(row, text="First Goal:", bg="#e8ffe8",
                 font=("Helvetica", 10)).pack(side="left", padx=(0, 4))
        e_goal = tk.Entry(row, width=18, relief="flat", highlightthickness=1,
                          highlightbackground="#ccc", highlightcolor=PURPLE,
                          bg="white")
        e_goal.pack(side="left", padx=(0, 10), ipady=3)

        is_work_var = tk.BooleanVar(value=True)
        self._work_toggle(row, is_work_var, bg="#e8ffe8").pack(
            side="left", padx=(0, 10))

        def save(event=None):
            pname = e_proj.get().strip()
            gname = e_goal.get().strip()
            if not pname or not gname:
                messagebox.showwarning("Missing",
                                       "Enter both a project name and a first goal.")
                return
            is_work = 1 if is_work_var.get() else 0
            db_exec(
                f"INSERT INTO {TABLE} (impact_project,goal,task_completed,"
                f"selected_today,priority,time_spent,is_work)"
                f" VALUES(?,?,0,0,'Medium',0,?)",
                (pname, gname, is_work))
            panel.destroy()
            self._build_tab2()

        self._btn(row, "Create", "#28a745", save).pack(side="left", padx=(0, 4))
        self._btn(row, "Cancel", "#888",
                  lambda: panel.destroy()).pack(side="left")
        e_proj.bind("<Return>", lambda ev: e_goal.focus())
        e_goal.bind("<Return>", save)
        e_goal.bind("<Escape>", lambda ev: panel.destroy())

    def _inline_add_goal(self, container, proj):
        for w in container.winfo_children():
            if getattr(w, "_inline_add_goal", False):
                w.destroy()
                return

        panel = tk.Frame(container, bg="#e8ffe8", bd=1, relief="flat")
        panel._inline_add_goal = True
        panel.pack(fill="x", pady=4)

        row = tk.Frame(panel, bg="#e8ffe8")
        row.pack(fill="x", padx=8, pady=6)

        tk.Label(row, text="Goal name:", bg="#e8ffe8",
                 font=("Helvetica", 10)).pack(side="left", padx=(0, 4))
        e = tk.Entry(row, width=28, relief="flat", highlightthickness=1,
                     highlightbackground="#ccc", highlightcolor=PURPLE, bg="white")
        e.pack(side="left", padx=(0, 10), ipady=3)
        e.focus()

        is_work_var = tk.BooleanVar(value=self._is_work_for_proj(proj))
        self._work_toggle(row, is_work_var, bg="#e8ffe8").pack(
            side="left", padx=(0, 10))

        def save(event=None):
            name = e.get().strip()
            if not name:
                panel.destroy(); return
            if any(t["impact_project"] == proj and t["goal"] == name
                   for t in load_tasks()):
                messagebox.showwarning("Duplicate", "This goal already exists.")
                return
            is_work = 1 if is_work_var.get() else 0
            db_exec(
                f"INSERT INTO {TABLE} (impact_project,goal,task_completed,"
                f"selected_today,priority,time_spent,is_work)"
                f" VALUES(?,?,0,0,'Medium',0,?)",
                (proj, name, is_work))
            panel.destroy()
            self._build_tab2()

        self._btn(row, "Add Goal", "#28a745", save).pack(side="left", padx=(0, 4))
        self._btn(row, "Cancel", "#888",
                  lambda: panel.destroy()).pack(side="left")
        e.bind("<Return>", save)
        e.bind("<Escape>", lambda ev: panel.destroy())

    def _inline_add_task(self, container, proj, goal):
        for w in container.winfo_children():
            if getattr(w, "_inline_add_task", False):
                w.destroy()
                return

        is_work = 1 if self._is_work_for_goal(goal) else 0

        panel = tk.Frame(container, bg="#e8ffe8", bd=1, relief="flat")
        panel._inline_add_task = True
        panel.pack(fill="x", pady=4)

        grid = tk.Frame(panel, bg="#e8ffe8")
        grid.pack(fill="x", padx=8, pady=8)

        for ci, h in enumerate(["Task", "Priority", "Due Date", "Notes"]):
            tk.Label(grid, text=h, bg="#e8ffe8",
                     font=("Helvetica", 9)).grid(
                     row=0, column=ci, sticky="w", padx=(0, 8), pady=(0, 2))

        def _ientry(width):
            return tk.Entry(grid, width=width, relief="flat",
                            highlightthickness=1,
                            highlightbackground="#ccc", highlightcolor=PURPLE,
                            bg="white")

        e_task = _ientry(28)
        e_task.grid(row=1, column=0, padx=(0, 8), ipady=3)
        e_task.focus()

        e_pri = ttk.Combobox(grid, values=PRIORITIES, state="readonly", width=10)
        e_pri.current(1)
        e_pri.grid(row=1, column=1, padx=(0, 8))

        e_due = _ientry(13)
        e_due.grid(row=1, column=2, padx=(0, 8), ipady=3)

        e_notes = _ientry(22)
        e_notes.grid(row=1, column=3, padx=(0, 8), ipady=3)

        btn_row = tk.Frame(panel, bg="#e8ffe8")
        btn_row.pack(anchor="e", padx=8, pady=(0, 6))

        def save(event=None):
            task = e_task.get().strip()
            if not task:
                panel.destroy(); return
            due_raw = e_due.get().strip()
            if due_raw:
                try:
                    date.fromisoformat(due_raw)
                except ValueError:
                    messagebox.showwarning("Invalid date",
                                           "Due Date must be YYYY-MM-DD")
                    return
            notes = e_notes.get().strip() or None
            db_exec(
                f"INSERT INTO {TABLE} (impact_project,goal,task,task_completed,"
                f"selected_today,priority,time_spent,is_work,"
                f"due_date,created_date,notes)"
                f" VALUES(?,?,?,0,0,?,0,?,?,?,?)",
                (proj, goal, task, e_pri.get(), is_work,
                 due_raw or None, str(date.today()), notes))
            panel.destroy()
            self._build_tab2()

        self._btn(btn_row, "Cancel", "#888",
                  lambda: panel.destroy()).pack(side="right", padx=(6, 0))
        self._btn(btn_row, "Add Task", "#28a745", save).pack(side="right")
        e_task.bind("<Return>", save)
        e_task.bind("<Escape>", lambda ev: panel.destroy())

    def _is_work_for_proj(self, proj):
        row = next((t for t in load_tasks() if t["impact_project"] == proj), None)
        return bool(row.get("is_work", 1)) if row else True

    def _on_t2_mode_change(self):
        self._build_tab2()

    def _on_t2_proj_change(self):
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

        # Priority dot (replaces [Priority] text in label)
        self._pri_dot(row, t["priority"])

        label = t["task"]
        if t.get("due_date"):
            label += f"  📅 {t['due_date']}"
        tk.Label(row, text=label, fg=col, bg=LIGHT,
                 font=("Helvetica", 10)).pack(side="left")
        self._work_badge(row, bool(t.get("is_work", 1)))

        if not is_done:
            if is_mine:
                disp_text, disp_color = f"  ● {fmt_secs(saved_s)}", "#dc3545"
            elif saved_s > 0:
                disp_text, disp_color = f"  ⏸ {fmt_secs(saved_s)}", "#888"
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
                    lbl.configure(text=f"  ● {fmt_secs(elapsed)}",
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

    # ── Shared helpers ────────────────────────────────────────────────────────

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


if __name__ == "__main__":
    app = App()
    app.mainloop()
