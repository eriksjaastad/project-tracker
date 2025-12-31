# 🚀 Project Tracker - Quick Start

## Launch the Dashboard

```bash
cd /Users/eriksjaastad/projects/project-tracker
./pt launch
```

That's it! The dashboard will open at http://localhost:8000

**Note:** The `./pt` script automatically uses the virtual environment, so you don't need to activate it manually to launch.

---

## Activate Virtual Environment (Optional)

If you want to run Python commands directly or install new packages:

```bash
cd /Users/eriksjaastad/projects/project-tracker
source venv/bin/activate

# Now you can run commands directly:
python scripts/pt.py list
pip install <new-package>

# Deactivate when done:
deactivate
```

---

## What You'll See

- **All your projects** sorted by last modified (newest first)
- **Progress bars** showing completion %
- **AI agents** working on each project  
- **Status badges** (Active, Development, Paused, etc.)
- **Cron jobs** indicator (⏰)
- **External services** used

Click **"View TODO"** on any project to see the rendered TODO.md

---

## Other Commands

```bash
./pt list      # List projects in terminal
./pt scan      # Scan for new projects
./pt refresh   # Update all data
```

---

## For AI Assistants

To launch the project tracker:

```bash
cd /Users/eriksjaastad/projects/project-tracker && ./pt launch
```

The dashboard will auto-scan projects and open in the browser.

---

**Full documentation:** See `USAGE.md` or `COMPLETION_SUMMARY.md`

