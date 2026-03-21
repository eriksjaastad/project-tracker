# CRON_JOBS.md — Scheduled Jobs Registry

All scheduled automation across the ecosystem. Every launchd plist is listed here with install instructions and links to the owning project.

> **Last updated:** 2026-03-21
> **Platform:** macOS (launchd + `~/Library/LaunchAgents/`)

---

## Jobs Overview

| Label | Project | Schedule | Status |
|-------|---------|----------|--------|
| `com.erik.journal-personal` | [ai-journal](#ai-journal--personal-journal) | Daily 22:00 | ✅ Installed |
| `com.eriksjaastad.open-brain-antigravity-sync` | [ai-memory](#ai-memory--open-brain-sync) | Always-on daemon | ✅ Installed |
| `com.user.cortana_daily_update` | [cortana-personal-ai](#cortana-personal-ai--daily-data-update) | Daily 13:00 + 22:00 | ⚠️ Template path |
| `com.eriksjaastad.doc-audit` | [project-tracker](#project-tracker--doc-audit) | Daily 03:00 | ⚠️ Not installed |
| `com.user.ecosystem_maintenance` | [project-tracker](#project-tracker--ecosystem-maintenance) | Daily 06:00 | ⚠️ Not installed |
| `com.user.sherlock_watchlist` | [sherlock-holmes](#sherlock-holmes--watchlist-monitor) | Weekly Sun 09:00 | ⚠️ Not installed |

---

## ai-journal — Personal Journal

**Label:** `com.erik.journal-personal`  
**Schedule:** Daily at 22:00  
**Plist:** `~/Library/LaunchAgents/com.erik.journal-personal.plist` *(currently installed)*  
**Script:** `~/bin/journal_personal.sh`  
**Logs:** `/tmp/journal_personal.out` / `/tmp/journal_personal.err`  
**Project:** [ai-journal/README.md](../ai-journal/README.md)

```bash
# Install
launchctl load ~/Library/LaunchAgents/com.erik.journal-personal.plist

# Unload
launchctl unload ~/Library/LaunchAgents/com.erik.journal-personal.plist
```

---

## ai-memory — Open Brain Sync

**Label:** `com.eriksjaastad.open-brain-antigravity-sync`  
**Schedule:** Always-on daemon (KeepAlive=true, restarts on crash, 5s throttle)  
**Plist:** `~/Library/LaunchAgents/com.eriksjaastad.open-brain-antigravity-sync.plist` *(currently installed)*  
**Script:** `~/projects/ai-memory/scripts/open-brain-antigravity-sync.py --poll 60`  
**Secrets:** Doppler project `ai-memory`, config `prd`  
**Logs:** `~/.gemini/tmp/open-brain-antigravity-sync.log` / `open-brain-antigravity-sync.error.log`  
**Project:** [ai-memory/README.md](../ai-memory/README.md)

```bash
# Install
launchctl load ~/Library/LaunchAgents/com.eriksjaastad.open-brain-antigravity-sync.plist

# Check status
launchctl list | grep open-brain

# Unload
launchctl unload ~/Library/LaunchAgents/com.eriksjaastad.open-brain-antigravity-sync.plist
```

---

## cortana-personal-ai — Daily Data Update

**Label:** `com.user.cortana_daily_update`  
**Schedule:** Daily at 13:00 and 22:00  
**Plist:** `~/projects/cortana-personal-ai/config/com.user.cortana_daily_update.plist`  
**Script:** `~/projects/cortana-personal-ai/scripts/automation/run_daily_update.sh`  

> ⚠️ **Note:** Plist uses `[USER_HOME]` placeholder — replace with `/Users/eriksjaastad` before installing.

**Logs:** `~/projects/cortana-personal-ai/data/logs/daily_update.log`  
**Project:** [cortana-personal-ai/README.md](../cortana-personal-ai/README.md)

```bash
# Fix placeholder paths then install
sed 's|\[USER_HOME\]|/Users/eriksjaastad|g' \
  ~/projects/cortana-personal-ai/config/com.user.cortana_daily_update.plist \
  > ~/Library/LaunchAgents/com.user.cortana_daily_update.plist

launchctl load ~/Library/LaunchAgents/com.user.cortana_daily_update.plist
```

---

## project-tracker — Doc Audit

**Label:** `com.eriksjaastad.doc-audit`  
**Schedule:** Daily at 03:00  
**Plist:** `~/projects/project-tracker/scripts/launchd/com.eriksjaastad.doc-audit.plist`  
**Script:** `~/projects/project-tracker/scripts/doc_audit_daily.sh`  
**Logs:** `~/projects/project-tracker/logs/doc_audit.log`  
**Project:** [project-tracker/README.md](../project-tracker/README.md)

```bash
# Install
cp ~/projects/project-tracker/scripts/launchd/com.eriksjaastad.doc-audit.plist \
   ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.eriksjaastad.doc-audit.plist
```

---

## project-tracker — Ecosystem Maintenance

**Label:** `com.user.ecosystem_maintenance`  
**Schedule:** Daily at 06:00  
**Plist:** `~/projects/project-tracker/scripts/com.user.ecosystem_maintenance.plist`  
**Script:** `~/projects/project-tracker/scripts/maintenance.sh`  
**Logs:** `~/projects/project-tracker/logs/maintenance.log`  
**Project:** [project-tracker/README.md](../project-tracker/README.md)

```bash
# Install
cp ~/projects/project-tracker/scripts/com.user.ecosystem_maintenance.plist \
   ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.user.ecosystem_maintenance.plist
```

---

## sherlock-holmes — Watchlist Monitor

**Label:** `com.user.sherlock_watchlist`  
**Schedule:** Weekly — Sunday at 09:00  
**Plist:** `~/projects/sherlock-holmes/scripts/com.user.sherlock_watchlist.plist`  
**Script:** `~/projects/sherlock-holmes/scripts/run_watchlist_monitor.sh`  
**Logs:** `~/projects/sherlock-holmes/logs/watchlist_cron.log`  
**Project:** [sherlock-holmes/README.md](../sherlock-holmes/README.md)

```bash
# Install
cp ~/projects/sherlock-holmes/scripts/com.user.sherlock_watchlist.plist \
   ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.user.sherlock_watchlist.plist
```

---

## Adding a New Job

1. Create a `.plist` in your project's `config/` or `scripts/` dir
2. Add a row to the table above
3. Include install/unload commands
4. Link to your project's `README.md` using a relative path (`../project-name/README.md`)

> **Never** link to `ai-model-scratch-build/README.md` — that was a copy-paste artifact from an old template.
