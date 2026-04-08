"""
Time Management App — Python/Tkinter version
DB file:   task_data.sqlite in same directory as this script
"""

import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
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

# ── Main App ──────────────────────────────────────────────────────────────────

class App(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("Time Management")
        self.geometry("1350x920")
        self.minsize(950, 680)
        setup_db()

        # Shared work filter: "work" | "all" | "nonwork"
        self._work_filter = tk.StringVar(value="work")

        # My Tasks state
        self._t2_pri_filter = tk.StringVar(value="All")
        self._t2_show_done  = tk.BooleanVar(value=False)
        self._t2_view_mode  = tk.StringVar(value="list")
        self._t2_expand_all = tk.BooleanVar(value=True)   # True = expanded

        # Tasks for Today state
        self._today_pri_filter = tk.StringVar(value="All")
        self._today_show_done  = tk.BooleanVar(value=False)
        self._today_view_mode  = tk.StringVar(value="bubble")
        self._today_expand_all = tk.BooleanVar(value=True)

        # Manage section collapsed by default
        self._manage_collapsed = True

        # Quick-add vars
        self._qa_project = tk.StringVar(value="")
        self._qa_goal    = tk.StringVar(value="")

        # Add-goal form vars
        self._t1g_project = tk.StringVar(value="")
        self._t1g_is_work = tk.BooleanVar(value=True)

        self._build_ui()

    # ── UI scaffold ────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.tabview = ctk.CTkTabview(self, fg_color="transparent",
                                      command=self._on_tab_change)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        self._tab_frames = {}
        for name in ["My Tasks", "Tasks for Today",
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

    def _on_tab_change(self):
        tab = self.tabview.get()
        {
            "My Tasks":        self._build_tab1,
            "Tasks for Today": self._build_tab2,
            "Completed Tasks": self._build_tab3,
            "Weekly Summary":  self._build_tab4,
        }.get(tab, lambda: None)()

    def _clear(self, name):
        for w in self._tab_frames[name].winfo_children():
            w.destroy()

    # ── Widget helpers ─────────────────────────────────────────────────────────

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

    def _icon_btn(self, parent, icon, command, bg="white", fg="#888"):
        """Tiny flat icon button (e.g. ✏ edit)."""
        return tk.Button(parent, text=icon, command=command,
                         bg=bg, fg=fg, relief="flat", bd=0,
                         font=("Helvetica", 10), cursor="hand2",
                         padx=3, pady=1,
                         activebackground="#e8e8ff", activeforeground=PURPLE)

    def _work_toggle(self, parent, var, bg=LIGHT):
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

    def _mini_progress(self, parent, done, total, color=PURPLE, bg=LIGHT):
        pct = done / total if total > 0 else 0
        row = tk.Frame(parent, bg=bg)
        row.pack(fill="x", pady=(2, 4))
        tk.Label(row, text=f"{round(pct * 100)}%", font=("Helvetica", 8),
                 fg="#999", bg=bg).pack(side="right", padx=(4, 0))
        bar_bg = tk.Frame(row, bg="#e4e4e4", height=5)
        bar_bg.pack(side="left", fill="x", expand=True)
        bar_bg.update_idletasks()
        w = max(1, int(bar_bg.winfo_reqwidth() * pct))
        tk.Frame(bar_bg, bg=color, height=5, width=w).pack(side="left")

    def _pri_dot(self, parent, priority, bg="white"):
        col = PRI_COLOR.get(priority, "#ccc")
        tk.Label(parent, text="●", fg=col, bg=bg,
                 font=("Helvetica", 9)).pack(side="left", padx=(0, 2))

    # ── Shared data helpers ────────────────────────────────────────────────────

    def _apply_work_filter(self, tasks):
        wf = self._work_filter.get()
        if wf == "work":
            return [t for t in tasks if t.get("is_work", 1) == 1]
        if wf == "nonwork":
            return [t for t in tasks if t.get("is_work", 1) == 0]
        return tasks  # "all"

    def _all_projects(self):
        return sorted(set(t["impact_project"] for t in load_tasks()
                          if t["impact_project"]))

    def _goals_for_project(self, project):
        return sorted(set(t["goal"] for t in load_tasks()
                          if t["goal"] and t["impact_project"] == project))

    def _all_goals(self):
        return sorted(set(t["goal"] for t in load_tasks() if t["goal"]))

    def _is_work_for_goal(self, goal):
        row = next((t for t in load_tasks() if t["goal"] == goal), None)
        return bool(row.get("is_work", 1)) if row else True

    def _is_work_for_proj(self, proj):
        row = next((t for t in load_tasks() if t["impact_project"] == proj), None)
        return bool(row.get("is_work", 1)) if row else True

    # ── Filter / control bar ───────────────────────────────────────────────────

    def _build_filter_bar(self, parent, view_var, expand_var,
                          pri_var, done_var, rebuild_fn):
        """Global filter + view-mode bar used on My Tasks and Today tabs."""
        bar = tk.Frame(parent, bg="#f0f0f8")
        bar.pack(fill="x", padx=8, pady=(4, 6))

        # Work filter (3-way radio as push-buttons)
        tk.Label(bar, text="Show:", bg="#f0f0f8",
                 font=("Helvetica", 9, "bold"), fg="#555").pack(
                 side="left", padx=(10, 4), pady=8)
        for val, label in [("work", "Work"), ("all", "All"), ("nonwork", "Non-work")]:
            tk.Radiobutton(bar, text=label, variable=self._work_filter,
                           value=val, indicatoron=0,
                           font=("Helvetica", 9),
                           bg="#e0e0ee", fg="#333",
                           activebackground="#d0d0e8", activeforeground="#333",
                           selectcolor="#c8c0ff", relief="flat",
                           padx=8, pady=3,
                           command=rebuild_fn).pack(side="left", padx=(0, 2), pady=8)

        tk.Frame(bar, bg="#ccc", width=1).pack(side="left", fill="y", padx=8, pady=4)

        # Expand / Contract All (only shown in list view)
        if view_var.get() == "list":
            expand_text = "▲ Contract All" if expand_var.get() else "▼ Expand All"
            def toggle_expand():
                expand_var.set(not expand_var.get())
                rebuild_fn()
            tk.Button(bar, text=expand_text, command=toggle_expand,
                      bg="#f0f0f8", fg="#555", relief="flat",
                      font=("Helvetica", 9), padx=8, pady=3,
                      cursor="hand2",
                      activebackground="#e0e0ee").pack(side="left", padx=(0, 8), pady=8)
            tk.Frame(bar, bg="#ccc", width=1).pack(side="left", fill="y", padx=8, pady=4)

        # Priority filter
        tk.Label(bar, text="Priority:", bg="#f0f0f8",
                 font=("Helvetica", 9)).pack(side="left", padx=(0, 4), pady=8)
        pri_cb = ttk.Combobox(bar, values=["All"] + PRIORITIES, width=9,
                               textvariable=pri_var, state="readonly")
        pri_cb.pack(side="left", padx=(0, 10), pady=8)
        pri_cb.bind("<<ComboboxSelected>>", lambda _: rebuild_fn())

        # Show Completed
        tk.Checkbutton(bar, text="Show Completed", variable=done_var,
                       bg="#f0f0f8", command=rebuild_fn).pack(
                       side="left", padx=(0, 10), pady=8)

        tk.Frame(bar, bg="#ccc", width=1).pack(side="left", fill="y", padx=8, pady=4)

        # View mode buttons (right)
        tk.Label(bar, text="View:", bg="#f0f0f8",
                 font=("Helvetica", 9)).pack(side="left", padx=(0, 4), pady=8)
        for mode, label in [("list", "List"), ("bubble", "Bubble"), ("table", "Table")]:
            active = (view_var.get() == mode)
            def set_mode(m=mode):
                view_var.set(m)
                rebuild_fn()
            tk.Button(bar, text=label, command=set_mode,
                      bg=PURPLE if active else "#e0e0ee",
                      fg="white" if active else "#333",
                      relief="flat", font=("Helvetica", 9),
                      padx=8, pady=3, cursor="hand2",
                      activebackground=PURPLE,
                      activeforeground="white").pack(side="left", padx=(0, 2), pady=8)

    # ── Quick-Add banner ───────────────────────────────────────────────────────

    def _build_quick_add(self, parent):
        all_projects = self._all_projects()

        qa_outer = tk.Frame(parent, bg=PURPLE)
        qa_outer.pack(fill="x", padx=8, pady=(10, 6))

        tk.Label(qa_outer, text="⚡  Quick Add Task",
                 fg="white", bg=PURPLE,
                 font=("Helvetica", 12, "bold")).pack(
                     anchor="w", padx=14, pady=(10, 6))

        qa = tk.Frame(qa_outer, bg=PURPLE)
        qa.pack(fill="x", padx=14, pady=(0, 12))

        def _qa_entry(width):
            return tk.Entry(qa, width=width, relief="flat", bd=0,
                            highlightthickness=1,
                            highlightcolor="white",
                            highlightbackground="#9580e8",
                            bg="white", fg="#222",
                            font=("Helvetica", 11))

        for col_idx, label in enumerate(
                ["Project", "Goal", "Task Name", "Priority",
                 "Due (YYYY-MM-DD)", "Notes (optional)"]):
            tk.Label(qa, text=label, fg="#d4c8ff", bg=PURPLE,
                     font=("Helvetica", 9)).grid(row=0, column=col_idx,
                                                  sticky="w", padx=(0, 6))

        self._qa_proj_cb = self._combo(qa, all_projects, width=15,
                                        textvariable=self._qa_project)
        self._qa_proj_cb.grid(row=1, column=0, padx=(0, 6), ipady=2)
        self._qa_proj_cb.bind("<<ComboboxSelected>>",
                               lambda _: self._refresh_qa_goals())

        qa_goals = (self._goals_for_project(self._qa_project.get())
                    if self._qa_project.get() else [])
        self._qa_goal_cb = self._combo(qa, qa_goals, width=15,
                                        textvariable=self._qa_goal)
        self._qa_goal_cb.grid(row=1, column=1, padx=(0, 6), ipady=2)

        self._qa_task_entry = _qa_entry(28)
        self._qa_task_entry.grid(row=1, column=2, padx=(0, 6), ipady=4)
        self._qa_task_entry.bind("<Return>", lambda _: self._qa_add_task())

        self._qa_pri_cb = self._combo(qa, PRIORITIES, width=9)
        self._qa_pri_cb.grid(row=1, column=3, padx=(0, 6), ipady=2)
        self._qa_pri_cb.current(1)

        self._qa_due_entry = _qa_entry(13)
        self._qa_due_entry.grid(row=1, column=4, padx=(0, 6), ipady=4)

        self._qa_notes_entry = _qa_entry(22)
        self._qa_notes_entry.grid(row=1, column=5, padx=(0, 6), ipady=4)

        tk.Label(qa, text="", bg=PURPLE).grid(row=0, column=6)
        tk.Button(qa, text="Add  →", bg="#28a745", fg="white",
                  relief="flat", font=("Helvetica", 11, "bold"),
                  padx=16, pady=6, cursor="hand2",
                  activebackground="#218838", activeforeground="white",
                  command=self._qa_add_task).grid(row=1, column=6)

        qa.columnconfigure(2, weight=1)

    def _refresh_qa_goals(self):
        proj  = self._qa_project.get()
        goals = self._goals_for_project(proj) if proj else []
        self._qa_goal_cb["values"] = goals
        if goals:
            self._qa_goal_cb.current(0)
            self._qa_goal.set(goals[0])
        else:
            self._qa_goal.set("")

    def _qa_add_task(self):
        project  = self._qa_project.get().strip()
        goal     = self._qa_goal.get().strip()
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

        self._qa_task_entry.delete(0, "end")
        self._qa_due_entry.delete(0, "end")
        self._qa_notes_entry.delete(0, "end")
        self._qa_task_entry.focus()
        self._build_tab1()

    # ── Tab 1: My Tasks ────────────────────────────────────────────────────────

    def _build_tab1(self):
        self._clear("My Tasks")
        f = self._tab_frames["My Tasks"]
        f.configure(bg="white")

        self._build_quick_add(f)
        self._build_manage_section(f)
        self._build_filter_bar(
            f,
            view_var   = self._t2_view_mode,
            expand_var = self._t2_expand_all,
            pri_var    = self._t2_pri_filter,
            done_var   = self._t2_show_done,
            rebuild_fn = self._build_tab1,
        )

        top = tk.Frame(f, bg="white")
        top.pack(fill="x", padx=8, pady=(0, 4))
        self._btn(top, "+ New Project", "#28a745",
                  lambda: self._inline_add_project(f)).pack(side="left")

        all_tasks = self._apply_work_filter(load_tasks())
        show_done = self._t2_show_done.get()
        pri_val   = self._t2_pri_filter.get()
        projects  = sorted(set(t["impact_project"] for t in all_tasks
                               if t["impact_project"]))

        if not projects:
            tk.Label(f, text="No projects yet. Click '+ New Project' to get started.",
                     bg="white", fg="#888",
                     font=("Helvetica", 11)).pack(pady=20)
            return

        view = self._t2_view_mode.get()
        if view == "list":
            self._render_list_view(f, all_tasks, projects,
                                   self._t2_expand_all.get(),
                                   show_done, pri_val, self._build_tab1)
        elif view == "bubble":
            self._render_bubble_view(f, all_tasks, projects,
                                     show_done, pri_val, self._build_tab1)
        else:
            self._render_table_view(f, all_tasks, show_done, pri_val,
                                    self._build_tab1)

    # ── Manage section (collapsible) ───────────────────────────────────────────

    def _build_manage_section(self, parent):
        toggle_frame = tk.Frame(parent, bg="white")
        toggle_frame.pack(fill="x", padx=8, pady=(0, 2))

        arrow = "▶" if self._manage_collapsed else "▼"

        def toggle():
            self._manage_collapsed = not self._manage_collapsed
            self._build_tab1()

        tk.Button(toggle_frame, text=f"  {arrow}  Manage Projects & Goals",
                  font=("Helvetica", 10, "bold"), fg="#666",
                  bg="white", relief="flat", anchor="w",
                  cursor="hand2", activebackground="#f8f8ff",
                  command=toggle).pack(fill="x", ipady=3)

        if self._manage_collapsed:
            return

        all_projects = self._all_projects()
        mid = tk.Frame(parent, bg="#fafafa", bd=1, relief="flat")
        mid.pack(fill="x", padx=8, pady=(0, 6))
        inner = tk.Frame(mid, bg="#fafafa")
        inner.pack(fill="x", padx=8, pady=8)

        # Add Goal
        gc = self._make_section(inner, "Add New Goal")
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
        ep = self._make_section(inner, "Rename Project")
        ep.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self._lbl(ep, "Select Project").grid(row=0, column=0, sticky="w")
        self.sel_edit_project = self._combo(ep, all_projects)
        self.sel_edit_project.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        self.sel_edit_project.bind("<<ComboboxSelected>>", self._prefill_project)
        self._lbl(ep, "New Name").grid(row=2, column=0, sticky="w")
        self.inp_edit_project = self._entry(ep)
        self.inp_edit_project.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self._btn(ep, "Rename", "#e07b00",
                  self._rename_project).grid(row=4, column=0, sticky="w")
        ep.columnconfigure(0, weight=1)

        # Edit Goal
        eg = self._make_section(inner, "Edit Goal")
        eg.pack(side="left", fill="both", expand=True)
        self._lbl(eg, "Select Goal").grid(row=0, column=0, sticky="w")
        self.sel_edit_goal = self._combo(eg, self._all_goals())
        self.sel_edit_goal.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        self.sel_edit_goal.bind("<<ComboboxSelected>>", self._prefill_goal)
        self._lbl(eg, "New Name").grid(row=2, column=0, sticky="w")
        self.inp_edit_goal = self._entry(eg)
        self.inp_edit_goal.grid(row=3, column=0, sticky="ew", pady=(0, 4))
        self._lbl(eg, "Move to Project").grid(row=4, column=0, sticky="w")
        self.sel_goal_project = self._combo(eg, all_projects)
        self.sel_goal_project.grid(row=5, column=0, sticky="ew", pady=(0, 4))
        self._lbl(eg, "Type").grid(row=6, column=0, sticky="w", pady=(4, 2))
        self._eg_is_work = tk.BooleanVar(value=True)
        self._work_toggle(eg, self._eg_is_work).grid(
            row=7, column=0, sticky="w", pady=(0, 8))
        self._btn(eg, "Save Goal", "#e07b00",
                  self._save_goal).grid(row=8, column=0, sticky="w")
        eg.columnconfigure(0, weight=1)

    # ── Goal / project management ──────────────────────────────────────────────

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
            self._build_tab1()

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
            self._build_tab1()

    # ── List view ──────────────────────────────────────────────────────────────

    def _render_list_view(self, parent, all_tasks, projects,
                          expand_all, show_done, pri_val, rebuild_fn):
        for proj in projects:
            proj_tasks = [t for t in all_tasks if t["impact_project"] == proj]
            self._render_list_proj(parent, proj, proj_tasks,
                                   expand_all, show_done, pri_val, rebuild_fn)

    def _render_list_proj(self, parent, proj, all_proj_tasks,
                          expand_all, show_done, pri_val, rebuild_fn):
        # expand_all=True → show expanded; False → contracted
        is_collapsed = not expand_all

        real_tasks = [t for t in all_proj_tasks if t["task"]]
        task_count = len(real_tasks)
        done_count = sum(1 for t in real_tasks if t["task_completed"])
        count_str  = f"  ({done_count}/{task_count})" if task_count else ""

        hdr = tk.Frame(parent, bg="white")
        hdr.pack(fill="x", pady=(10, 0), padx=8)
        tk.Frame(hdr, bg=PURPLE, width=4).pack(side="left", fill="y")

        arrow = "▶" if is_collapsed else "▼"
        tk.Label(hdr, text=f"   {arrow}   {proj}{count_str}",
                 font=("Helvetica", 12, "bold"), fg=PURPLE,
                 bg="white", anchor="w").pack(
                 side="left", fill="x", expand=True, ipady=5)

        # Rename icon
        self._icon_btn(
            hdr, "✏",
            lambda p=proj: self._rename_dialog(
                p, "Project",
                lambda old, new: db_exec(
                    f"UPDATE {TABLE} SET impact_project=? WHERE impact_project=?",
                    (new, old)),
                self._build_tab1)
        ).pack(side="right", padx=(0, 8))

        tk.Frame(parent, bg="#e8e0ff", height=1).pack(fill="x", padx=8)

        if is_collapsed:
            return

        content = tk.Frame(parent, bg="white")
        content.pack(fill="x", padx=(28, 8), pady=(0, 4))

        self._btn(hdr, "+ Goal", "#28a745",
                  lambda c=content, p=proj: self._inline_add_goal(c, p),
                  width=6).pack(side="right", padx=(0, 4))

        goals = sorted(set(t["goal"] for t in all_proj_tasks if t["goal"]))
        for goal in goals:
            goal_tasks = [t for t in all_proj_tasks if t["goal"] == goal]
            real_goal_tasks = [t for t in goal_tasks if t["task"]]

            # Hide goal if all tasks are done and show_done is off
            if real_goal_tasks and not show_done:
                if all(t["task_completed"] for t in real_goal_tasks):
                    continue

            self._render_list_goal(content, proj, goal, goal_tasks,
                                   show_done, pri_val, rebuild_fn)

    def _render_list_goal(self, parent, proj, goal, all_goal_tasks,
                          show_done, pri_val, rebuild_fn):
        real_tasks = [t for t in all_goal_tasks if t["task"]]
        task_count = len(real_tasks)
        done_count = sum(1 for t in real_tasks if t["task_completed"])
        count_str  = f"  ({done_count}/{task_count})" if task_count else ""

        hdr = tk.Frame(parent, bg="white")
        hdr.pack(fill="x", pady=(6, 0))
        tk.Frame(hdr, bg="#bbb", width=2).pack(side="left", fill="y")

        tk.Label(hdr, text=f"   {goal}{count_str}",
                 font=("Helvetica", 10, "bold"), fg="#444",
                 bg="white", anchor="w").pack(
                 side="left", fill="x", expand=True, ipady=3)

        content = tk.Frame(parent, bg="white")

        self._icon_btn(
            hdr, "✏",
            lambda p=proj, g=goal: self._rename_dialog(
                g, "Goal",
                lambda old, new: db_exec(
                    f"UPDATE {TABLE} SET goal=? WHERE goal=? AND impact_project=?",
                    (new, old, p)),
                self._build_tab1)
        ).pack(side="right", padx=(0, 4))

        self._btn(hdr, "+ Task", "#28a745",
                  lambda c=content, p=proj, g=goal:
                  self._inline_add_task(c, p, g),
                  width=6).pack(side="right", padx=(0, 4))

        content.pack(fill="x", padx=(16, 0), pady=(2, 0))

        display_tasks = list(real_tasks)
        if not show_done:
            display_tasks = [t for t in display_tasks if not t["task_completed"]]
        if pri_val != "All":
            display_tasks = [t for t in display_tasks if t["priority"] == pri_val]

        for t in display_tasks:
            self._render_task_row(content, t, rebuild_fn, bg="white")

    # ── Bubble view ────────────────────────────────────────────────────────────

    def _render_bubble_view(self, parent, all_tasks, projects,
                            show_done, pri_val, rebuild_fn):
        COLS = 3
        for row_start in range(0, len(projects), COLS):
            row_projs = projects[row_start:row_start + COLS]
            row_frame = tk.Frame(parent, bg="white")
            row_frame.pack(fill="x", padx=8, pady=(0, 6))

            for proj in row_projs:
                proj_tasks = [t for t in all_tasks if t["impact_project"] == proj]
                card = tk.LabelFrame(row_frame, text=f"  {proj}  ",
                                      font=("Helvetica", 11, "bold"), fg=PURPLE,
                                      bg=LIGHT, bd=2, relief="groove",
                                      padx=8, pady=6)
                card.pack(side="left", fill="both", expand=True, padx=4, anchor="n")

                goals = sorted(set(t["goal"] for t in proj_tasks if t["goal"]))
                for goal in goals:
                    goal_tasks  = [t for t in proj_tasks if t["goal"] == goal]
                    real_gtasks = [t for t in goal_tasks if t["task"]]

                    if real_gtasks and not show_done:
                        if all(t["task_completed"] for t in real_gtasks):
                            continue

                    tk.Label(card, text=goal, font=("Helvetica", 10, "bold"),
                             bg=LIGHT, fg="#444").pack(anchor="w", pady=(6, 2))

                    display = list(real_gtasks)
                    if not show_done:
                        display = [t for t in display if not t["task_completed"]]
                    if pri_val != "All":
                        display = [t for t in display if t["priority"] == pri_val]

                    for t in display:
                        self._render_task_row(card, t, rebuild_fn, bg=LIGHT)

    # ── Table view ─────────────────────────────────────────────────────────────

    def _render_table_view(self, parent, all_tasks, show_done, pri_val, rebuild_fn):
        # Columns definition: (db_key, header_label, char_width)
        COLS = [
            ("impact_project", "Project",  14),
            ("goal",           "Goal",     14),
            ("task",           "Task",     24),
            ("due_date",       "Due Date", 10),
            ("priority",       "Priority", 10),
            ("notes",          "Notes",    22),
        ]

        tasks = [t for t in all_tasks if t["task"]]
        if not show_done:
            tasks = [t for t in tasks if not t["task_completed"]]
        if pri_val != "All":
            tasks = [t for t in tasks if t["priority"] == pri_val]
        tasks = sorted(tasks, key=lambda t: (
            t.get("impact_project") or "",
            t.get("goal") or "",
            t.get("task") or "",
        ))

        container = tk.Frame(parent, bg="white")
        container.pack(fill="x", padx=8, pady=4)

        # Header row
        hdr = tk.Frame(container, bg="#e8e0ff")
        hdr.pack(fill="x", pady=(0, 1))
        for key, label, w in COLS:
            tk.Label(hdr, text=label, width=w, anchor="w",
                     font=("Helvetica", 9, "bold"), fg=PURPLE,
                     bg="#e8e0ff", padx=4).pack(side="left")
        tk.Label(hdr, text="Actions", font=("Helvetica", 9, "bold"),
                 fg=PURPLE, bg="#e8e0ff", padx=4).pack(side="left")

        if not tasks:
            tk.Label(container, text="No tasks match the current filters.",
                     bg="white", fg="#888",
                     font=("Helvetica", 10)).pack(pady=10)
            return

        for i, t in enumerate(tasks):
            bg     = "#f8f8ff" if i % 2 == 0 else "white"
            is_done = bool(t["task_completed"])

            outer = tk.Frame(container, bg=bg)
            outer.pack(fill="x")
            tk.Frame(container, bg="#e8e0ff", height=1).pack(fill="x")

            row = tk.Frame(outer, bg=bg)
            row.pack(fill="x")

            for key, label, w in COLS:
                val = t.get(key) or ""
                if key == "notes":
                    val = val[:28]
                if key == "priority":
                    fg = PRI_COLOR.get(val, "#999") if not is_done else "#aaa"
                else:
                    fg = "#aaa" if is_done else "#333"
                font_s = ("Helvetica", 9, "overstrike") if is_done else ("Helvetica", 9)
                tk.Label(row, text=val, width=w, anchor="w",
                         font=font_s, fg=fg, bg=bg,
                         padx=4).pack(side="left")

            # Mark done checkbox
            var = tk.BooleanVar(value=is_done)
            def on_done(tid=t["id"], v=var):
                db_exec(f"UPDATE {TABLE} SET task_completed=? WHERE id=?",
                        (1 if v.get() else 0, tid))
                rebuild_fn()
            tk.Checkbutton(row, variable=var, command=on_done,
                           bg=bg, activebackground=bg,
                           text="Done").pack(side="left", padx=(4, 2))

            # + Today toggle
            is_today   = (t.get("selected_today") == 1 and
                          t.get("selected_date") == TODAY)
            today_bg   = "#28a745" if is_today else "#bbb"
            today_text = "✓ Today" if is_today else "+ Today"
            tk.Button(row, text=today_text, bg=today_bg, fg="white",
                      relief="flat", font=("Helvetica", 8), padx=5, pady=1,
                      cursor="hand2", activeforeground="white",
                      activebackground=today_bg,
                      command=lambda tid=t["id"]: self._toggle_today(
                          tid, rebuild_fn)
                      ).pack(side="left", padx=(2, 0))

            # Edit icon
            self._icon_btn(row, "✏",
                           lambda tid=t["id"], o=outer:
                           self._open_inline_edit(tid, o, rebuild_fn),
                           bg=bg).pack(side="left", padx=(6, 0))

    # ── Shared task row (list + bubble) ────────────────────────────────────────

    def _render_task_row(self, parent, t, rebuild_fn, bg="white"):
        outer = tk.Frame(parent, bg=bg)
        outer.pack(fill="x", pady=1)
        tk.Frame(outer, bg="#ececec", height=1).pack(fill="x")

        row = tk.Frame(outer, bg=bg)
        row.pack(fill="x", padx=4, pady=(3, 1))

        # Mark done
        var = tk.BooleanVar(value=bool(t["task_completed"]))
        def on_done(tid=t["id"], v=var):
            db_exec(f"UPDATE {TABLE} SET task_completed=? WHERE id=?",
                    (1 if v.get() else 0, tid))
            rebuild_fn()
        tk.Checkbutton(row, variable=var, command=on_done,
                       bg=bg, activebackground=bg).pack(side="left")

        self._pri_dot(row, t["priority"], bg=bg)

        col        = "#aaa" if t["task_completed"] else "#222"
        font_style = ("Helvetica", 10, "overstrike") if t["task_completed"] \
                     else ("Helvetica", 10)
        label = t["task"]
        if t.get("due_date"):
            label += f"  📅 {t['due_date']}"
        tk.Label(row, text=label, fg=col, bg=bg,
                 font=font_style, anchor="w").pack(
                 side="left", fill="x", expand=True)

        # + Today toggle
        is_today   = (t.get("selected_today") == 1 and t.get("selected_date") == TODAY)
        today_bg   = "#28a745" if is_today else "#bbb"
        today_text = "✓ Today" if is_today else "+ Today"
        tk.Button(row, text=today_text, bg=today_bg, fg="white",
                  relief="flat", font=("Helvetica", 9), padx=6, pady=2,
                  cursor="hand2", activeforeground="white",
                  activebackground=today_bg,
                  command=lambda tid=t["id"]: self._toggle_today(
                      tid, rebuild_fn)
                  ).pack(side="right", padx=(4, 0))

        # Edit icon
        self._icon_btn(row, "✏",
                       lambda tid=t["id"], o=outer:
                       self._open_inline_edit(tid, o, rebuild_fn),
                       bg=bg).pack(side="right", padx=(4, 0))

        if t.get("notes"):
            tk.Label(outer, text=f"  ↳ {t['notes']}", fg="#999",
                     font=("Helvetica", 9), bg=bg,
                     anchor="w").pack(fill="x", padx=(20, 4), pady=(0, 2))

    # ── Inline edit panel (includes delete) ────────────────────────────────────

    def _open_inline_edit(self, task_id, container, rebuild_fn):
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
        btn_row.pack(fill="x", padx=10, pady=(0, 8))

        def save():
            due_raw = e_due.get().strip()
            if due_raw:
                try:
                    date.fromisoformat(due_raw)
                except ValueError:
                    messagebox.showwarning("Invalid date",
                                           "Due Date must be YYYY-MM-DD"); return
            new_proj = e_proj.get()
            new_goal = e_goal.get()
            is_work  = 1 if self._is_work_for_goal(new_goal) else 0
            notes    = e_notes.get().strip() or None
            db_exec(
                f"UPDATE {TABLE} SET task=?,impact_project=?,goal=?,"
                f"priority=?,notes=?,due_date=?,is_work=? WHERE id=?",
                (e_task.get().strip(), new_proj, new_goal,
                 e_pri.get(), notes, due_raw or None, is_work, task_id))
            rebuild_fn()

        def delete():
            name = full.get("task", "this task")
            if messagebox.askyesno("Delete", f"Delete '{name}'? Cannot be undone."):
                db_exec(f"DELETE FROM {TABLE} WHERE id=?", (task_id,))
                rebuild_fn()

        # Delete on left, Save/Cancel on right
        self._btn(btn_row, "Delete", "#dc3545", delete).pack(side="left")
        self._btn(btn_row, "Cancel", "#888",
                  lambda: panel.destroy()).pack(side="right", padx=(6, 0))
        self._btn(btn_row, "Save", PURPLE, save).pack(side="right")

    # ── Today / Done helpers ───────────────────────────────────────────────────

    def _toggle_today(self, task_id, rebuild_fn):
        t = next((x for x in load_tasks() if x["id"] == task_id), None)
        if t is None:
            return
        if t.get("selected_today") == 1 and t.get("selected_date") == TODAY:
            db_exec(f"UPDATE {TABLE} SET selected_today=0 WHERE id=?", (task_id,))
        else:
            db_exec(
                f"UPDATE {TABLE} SET selected_today=1,selected_date=? WHERE id=?",
                (TODAY, task_id))
        rebuild_fn()

    # ── Rename dialog ──────────────────────────────────────────────────────────

    def _rename_dialog(self, current_name, kind, save_fn, rebuild_fn):
        """Generic rename dialog. save_fn(old, new) is called on confirm."""
        dlg = tk.Toplevel(self)
        dlg.title(f"Rename {kind}")
        dlg.geometry("340x140")
        dlg.grab_set()
        dlg.configure(bg="white")
        tk.Label(dlg, text=f"Rename '{current_name}' to:",
                 bg="white").pack(anchor="w", padx=20, pady=(15, 4))
        e = tk.Entry(dlg, width=38)
        e.insert(0, current_name)
        e.select_range(0, "end")
        e.pack(padx=20, fill="x")
        e.focus()

        def ok():
            new = e.get().strip()
            if new and new != current_name:
                save_fn(current_name, new)
            dlg.destroy()
            rebuild_fn()

        self._btn(dlg, "Rename", PURPLE, ok).pack(pady=10)
        dlg.bind("<Return>", lambda _: ok())

    # ── Inline add project / goal / task ───────────────────────────────────────

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
            self._build_tab1()

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
            self._build_tab1()

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
                                           "Due Date must be YYYY-MM-DD"); return
            notes = e_notes.get().strip() or None
            db_exec(
                f"INSERT INTO {TABLE} (impact_project,goal,task,task_completed,"
                f"selected_today,priority,time_spent,is_work,"
                f"due_date,created_date,notes)"
                f" VALUES(?,?,?,0,0,?,0,?,?,?,?)",
                (proj, goal, task, e_pri.get(), is_work,
                 due_raw or None, str(date.today()), notes))
            panel.destroy()
            self._build_tab1()

        self._btn(btn_row, "Cancel", "#888",
                  lambda: panel.destroy()).pack(side="right", padx=(6, 0))
        self._btn(btn_row, "Add Task", "#28a745", save).pack(side="right")
        e_task.bind("<Return>", save)
        e_task.bind("<Escape>", lambda ev: panel.destroy())

    # ── Tab 2: Tasks for Today ─────────────────────────────────────────────────

    def _build_tab2(self):
        self._clear("Tasks for Today")
        f = self._tab_frames["Tasks for Today"]
        f.configure(bg="white")

        self._build_filter_bar(
            f,
            view_var   = self._today_view_mode,
            expand_var = self._today_expand_all,
            pri_var    = self._today_pri_filter,
            done_var   = self._today_show_done,
            rebuild_fn = self._build_tab2,
        )

        all_tasks = self._apply_work_filter([
            t for t in load_tasks()
            if t["task"]
            and t.get("selected_today") == 1
            and t.get("selected_date") == TODAY
        ])
        show_done = self._today_show_done.get()
        pri_val   = self._today_pri_filter.get()
        projects  = sorted(set(t["impact_project"] for t in all_tasks
                               if t["impact_project"]))

        if not all_tasks:
            tk.Label(f, text="No tasks selected for today.",
                     font=("Helvetica", 13), bg="white").pack(pady=20)
            tk.Label(f,
                     text="Go to 'My Tasks' and click '+ Today' on any task.",
                     fg="#888", bg="white").pack()
        else:
            view = self._today_view_mode.get()
            if view == "list":
                self._render_list_view(f, all_tasks, projects,
                                       self._today_expand_all.get(),
                                       show_done, pri_val, self._build_tab2)
            elif view == "bubble":
                self._render_bubble_view(f, all_tasks, projects,
                                         show_done, pri_val, self._build_tab2)
            else:
                self._render_table_view(f, all_tasks, show_done, pri_val,
                                        self._build_tab2)

        self._btn(f, "Reset Today's List", "#dc3545",
                  self._reset_today).pack(pady=12)

    def _reset_today(self):
        if messagebox.askyesno("Reset", "Clear today's list? Tasks won't be deleted."):
            db_exec(f"UPDATE {TABLE} SET selected_today=0 WHERE selected_date=?",
                    (TODAY,))
            self._build_tab2()

    # ── Tab 3: Completed Tasks ─────────────────────────────────────────────────

    def _build_tab3(self):
        self._clear("Completed Tasks")
        f = self._tab_frames["Completed Tasks"]
        f.configure(bg="white")

        bar = tk.Frame(f, bg="#f0f0f8")
        bar.pack(fill="x", padx=8, pady=(8, 6))
        tk.Label(bar, text="Show:", bg="#f0f0f8",
                 font=("Helvetica", 9, "bold"), fg="#555").pack(
                 side="left", padx=(10, 4), pady=8)
        for val, label in [("work", "Work"), ("all", "All"), ("nonwork", "Non-work")]:
            tk.Radiobutton(bar, text=label, variable=self._work_filter,
                           value=val, indicatoron=0,
                           font=("Helvetica", 9),
                           bg="#e0e0ee", fg="#333",
                           activebackground="#d0d0e8", activeforeground="#333",
                           selectcolor="#c8c0ff", relief="flat",
                           padx=8, pady=3,
                           command=self._build_tab3).pack(
                           side="left", padx=(0, 2), pady=8)

        all_done = self._apply_work_filter(
            [t for t in load_tasks() if t["task"] and t["task_completed"]])

        cols  = ("Project", "Goal", "Task", "Priority",
                 "Type", "Due Date", "Notes")
        tree  = ttk.Treeview(f, columns=cols, show="headings", height=22)
        widths = {"Project": 120, "Goal": 120, "Task": 190, "Priority": 70,
                  "Type": 75, "Due Date": 85, "Notes": 200}
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=widths.get(c, 100))
        for t in all_done:
            tree.insert("", "end", values=(
                t["impact_project"], t["goal"], t["task"], t["priority"],
                "Work" if t.get("is_work", 1) else "Non-work",
                t.get("due_date") or "",
                t["notes"] or ""))
        sb = ttk.Scrollbar(f, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        sb.pack(side="left", fill="y", pady=10)

    # ── Tab 4: Weekly Summary ──────────────────────────────────────────────────

    def _build_tab4(self):
        self._clear("Weekly Summary")
        f = self._tab_frames["Weekly Summary"]
        f.configure(bg="white")

        bar = tk.Frame(f, bg="#f0f0f8")
        bar.pack(fill="x", padx=8, pady=(8, 6))
        tk.Label(bar, text="Show:", bg="#f0f0f8",
                 font=("Helvetica", 9, "bold"), fg="#555").pack(
                 side="left", padx=(10, 4), pady=8)
        for val, label in [("work", "Work"), ("all", "All"), ("nonwork", "Non-work")]:
            tk.Radiobutton(bar, text=label, variable=self._work_filter,
                           value=val, indicatoron=0,
                           font=("Helvetica", 9),
                           bg="#e0e0ee", fg="#333",
                           activebackground="#d0d0e8", activeforeground="#333",
                           selectcolor="#c8c0ff", relief="flat",
                           padx=8, pady=3,
                           command=self._build_tab4).pack(
                           side="left", padx=(0, 2), pady=8)

        all_tasks = self._apply_work_filter(
            [t for t in load_tasks() if t["task"]])

        week_start = str(date.today() - timedelta(days=6))
        done_week  = [t for t in all_tasks if t["task_completed"]
                      and t.get("selected_date")
                      and t["selected_date"] >= week_start]
        total_done = sum(1 for t in all_tasks if t["task_completed"])
        total_all  = len(all_tasks)
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
        for proj in sorted(set(t["impact_project"] for t in all_tasks)):
            pt   = [t for t in all_tasks if t["impact_project"] == proj]
            done = sum(1 for t in pt if t["task_completed"])
            card = tk.LabelFrame(proj_row, text=f"  {proj}  ",
                                  font=("Helvetica", 10, "bold"), fg=PURPLE,
                                  bg=LIGHT, bd=1, padx=8, pady=6)
            card.pack(side="left", fill="both", expand=True, padx=4)
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
            pt   = [t for t in all_tasks if t["priority"] == pri]
            done = sum(1 for t in pt if t["task_completed"])
            pct  = f"{round(100*done/len(pt))}%" if pt else "-"
            tree.insert("", "end", values=(pri, f"{done}/{len(pt)}", pct))
        tree.pack(fill="x", padx=10, pady=(0, 10))

    # ── Shared helpers ─────────────────────────────────────────────────────────

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
