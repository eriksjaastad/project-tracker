# CRON_JOBS.md — Scheduled Jobs Registry

All scheduled automation across the ecosystem. Covers launchd plists and crontab entries.

> **Last updated:** 2026-03-31
> **Platform:** macOS (launchd + crontab + `~/Library/LaunchAgents/`)

---

## Peak-Hour Audit (2026-03-31, card #5354)

Peak hours to avoid: **5-11 AM GMT** and **1-7 PM GMT** (= 1-7 AM EDT and 9 AM-3 PM EDT).
Off-peak windows: 7 PM-1 AM GMT (3-9 PM EDT) and 11 AM-1 PM GMT (7-9 AM EDT).

| Job | Current (EDT) | GMT | Peak? | Action |
|-----|--------------|-----|-------|--------|
| ai-memory daily-backup (launchd) | 03:00 | 07:00 | YES | Reschedule to 23:00 EDT (03:00 GMT) |
| trading-copilot briefing (cron) | 07:55 M-F | 11:55 | YES | Intentional — runs before market open, keep as-is |
| pt maintenance (cron) | 05:00 Sun | 09:00 | YES | Reschedule to 20:00 EDT (00:00 GMT) |
| calendar poller (cron) | */10 min | 24/7 | partial | Lightweight polling, acceptable as-is |
| ai-memory sync-pending (launchd) | */5 min | 24/7 | partial | Lightweight polling, acceptable as-is |
| open-brain-sync (launchd) | always-on | 24/7 | partial | Daemon, must stay running |
| journal-personal (launchd) | 22:00 | 02:00 | no | Safe |
| cortana daily (launchd) | 13:00+22:00 | 17:00+02:00 | no | Safe |
| model-updater (cron) | 12:00 Sun | 16:00 | no | Safe |
| muffinpanrecipes (cron) | 12:00 daily | 16:00 | no | Safe |

Launchd plist and crontab changes are out of scope for this repo — tracked separately.

---

## Jobs Overview

### Launchd (~/Library/LaunchAgents/)

| Label | Project | Schedule | Status |
|-------|---------|----------|--------|
| `com.erik.journal-personal` | [ai-journal](#ai-journal--personal-journal) | Daily 22:00 | Installed |
| `com.eriksjaastad.open-brain-antigravity-sync` | [ai-memory](#ai-memory--open-brain-sync) | Always-on daemon | Installed |
| `com.ai-memory.daily-backup` | [ai-memory](#ai-memory--daily-backup) | Daily 03:00 | Installed |
| `com.ai-memory.sync-pending` | [ai-memory](#ai-memory--sync-pending) | Every 5 min | Installed |
| `com.user.cortana_daily_update` | [cortana-personal-ai](#cortana-personal-ai--daily-data-update) | Daily 13:00 + 22:00 | Template path |
| `com.eriksjaastad.doc-audit` | [project-tracker](#project-tracker--doc-audit) | Daily 03:00 | Not installed |
| `com.user.ecosystem_maintenance` | [project-tracker](#project-tracker--ecosystem-maintenance) | Daily 06:00 | Not installed |
| `com.user.sherlock_watchlist` | [sherlock-holmes](#sherlock-holmes--watchlist-monitor) | Weekly Sun 09:00 | Not installed |
| `com.eriksjaastad.complexity-scan` | [project-tracker](#project-tracker--complexity-scan) | Monthly 1st at 22:00 | Not installed |
| `com.eriksjaastad.project-tracker` | [project-tracker](#project-tracker--dashboard) | Always-on daemon | Installed |
| `com.eriksjaastad.slack-listener` | slack-listener | Always-on daemon | Installed |

### Crontab

| Schedule | Project | Command |
|----------|---------|---------|
| `55 7 * * 1-5` (7:55 AM M-F) | trading-copilot | `morning_briefing_discord.py` |
| `0 5 * * 0` (5:00 AM Sun) | project-tracker | `maintenance.sh` |
| `0 12 * * 0` (noon Sun) | model-updater | `mu check` |
| `0 12 * * *` (noon daily) | muffinpanrecipes | `run_compressed_week.py` |
| `*/10 * * * *` (every 10 min) | project-tracker | `calendar_poller.py` |

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

## project-tracker — Complexity Scan

**Label:** `com.eriksjaastad.complexity-scan`  
**Schedule:** Monthly — 1st of month at 22:00 EDT (off-peak)  
**Plist:** `~/projects/project-tracker/scripts/launchd/com.eriksjaastad.complexity-scan.plist`  
**Script:** `uv run scripts/complexity_scan.py --trend`  
**Logs:** `~/projects/project-tracker/logs/complexity_scan.log`  
**Project:** [project-tracker/README.md](../project-tracker/README.md)  
**Card:** #5528

Tracks cognitive complexity (radon), duplication density, and refactoring ratio
across all active projects. Appends results to `data/complexity_trends.jsonl`.

```bash
# Install radon first (optional — script degrades gracefully without it)
uv pip install radon

# Install plist
cp ~/projects/project-tracker/scripts/launchd/com.eriksjaastad.complexity-scan.plist \
   ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.eriksjaastad.complexity-scan.plist

# Manual run
uv run scripts/complexity_scan.py --project project-tracker
```

---

## Adding a New Job

1. Create a `.plist` in your project's `config/` or `scripts/` dir
2. Add a row to the table above
3. Include install/unload commands
4. Link to your project's `README.md` using a relative path (`../project-name/README.md`)

> **Never** link to `ai-model-scratch-build/README.md` — that was a copy-paste artifact from an old template.
