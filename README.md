# Time Management App

A desktop task and time management application built with Python and Tkinter.

## Features

- **Add Tasks** — Create projects, goals, and tasks with priority levels (Low, Medium, High, Critical) and due dates. Tag each item as Work or Non-work.
- **My Tasks** — Browse all tasks with filters by priority, project, goal, and completion status.
- **Tasks for Today** — Select tasks to focus on for the day and track time spent with a built-in timer.
- **Completed Tasks** — Review finished tasks.
- **Weekly Summary** — Overview of work completed during the week.

## Requirements

- Python 3.7+
- `customtkinter` (optional — falls back to plain `tkinter` if not installed)

```
pip install customtkinter
```

## Usage

```
python app.py
```

The app creates a `task_data.sqlite` file in the same directory to store all data.

## Data Storage

All tasks are persisted locally in a SQLite database (`task_data.sqlite`). The schema is automatically created and migrated on first run.
