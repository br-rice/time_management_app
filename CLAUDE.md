# Time Management App — Claude Context

## What this is
Single-file Python/Tkinter desktop app. All logic lives in `app.py` (~1700 lines). SQLite DB in `task_data.sqlite`.

## Data model
One flat DB table (`tasks`) with hierarchy encoded in fields:
- **Project** (`impact_project`) → **Goal** (`goal`) → **Task** (`task`)
- A row with no `task` is a goal-only placeholder. A row with no `goal` or `task` would be project-only (rare).
- Key fields: `priority` (Low/Medium/High/Critical), `is_work` (0/1), `task_completed`, `selected_today`, `selected_date`, `due_date`, `notes`

## UI structure
4 tabs, each a canvas+scrollbar with a frame inside:
- **My Tasks** (Tab 1): main editing tab — filter bar, 3 view modes, inline add/edit
- **Tasks for Today** (Tab 2): readonly subset selected via "+Today" button
- **Completed Tasks** (Tab 3): time-window filtered, allows unchecking back to My Tasks
- **Weekly Summary** (Tab 4): stats cards and progress bars

## Three view modes (all tabs except Weekly Summary)
- **List**: Project → Goal → Task hierarchy, expand/collapse tasks
- **Bubble**: 3-column card grid, one card per project, equal-width columns via `columnconfigure(weight=1, uniform="col")`
- **Table**: flat sorted rows, grouped by project header rows

## Key rendering methods
- `_render_list_view` / `_render_list_proj` / `_render_list_goal` — list view
- `_render_bubble_view` — bubble/card view
- `_render_table_view` — table view
- `_render_task_row` — shared task row widget (checkbox, priority dot, edit, +Today)
- `_inline_add_goal_compact(parent, proj, rebuild_fn, padx=(24,8))` — green inline form for adding a goal
- `_inline_add_task_compact(parent, proj, goal, rebuild_fn)` — green inline form for adding a task
- `_inline_add_project(parent_frame)` — green inline form for adding a project + first goal

## Add interactions (My Tasks tab only — readonly on other tabs)
- List view: `(+goal)` button on project headers, `(+task)` on goal headers
- Bubble view: `(+goal)` button at bottom of each project card
- Table view: project group sub-headers have `(+goal)` button; panel appends to table container bottom
- All inline forms: Return to save, Escape to cancel, toggle to dismiss

## Colors / constants
- `PURPLE = "#6A5ACD"` — headers, buttons, accents
- `LIGHT = "#f9f9ff"` — card/form backgrounds
- `PRI_COLOR` — Low=#28a745, Medium=#e07b00, High=#dc3545, Critical=#7b0000
- `WORK_COLOR = "#2563EB"`, `NONW_COLOR = "#7C3AED"`

## Rebuild pattern
Every mutating action calls a `rebuild_fn` (e.g. `self._build_tab1`) to re-render the tab from scratch. No partial updates.

## State variables (instance vars on App)
- `_work_filter` — shared across all tabs ("work"/"all"/"nonwork")
- `_t2_*` — My Tasks (view_mode, pri_filter, show_done, expand_all)
- `_today_*` — Tasks for Today
- `_t3_*` — Completed Tasks

## Design direction (in progress)
Moving toward **visualization-first interaction**: add/edit actions triggered directly from the view (cards, rows, headers) rather than a top-bar quick-add banner. The Quick Add banner is a candidate for removal once inline add is complete in all views and for projects.
