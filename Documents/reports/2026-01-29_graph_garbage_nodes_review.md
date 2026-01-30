---
tags:
 - p/project-tracker
 - type/report
 - domain/graph
status: #status/active
created: 2026-01-29
---

# Graph Garbage Nodes Review (2026-01-29)

## Summary
Reviewed `data/graph.json` for self-references, small cycles, orphan nodes, and documentation-about-documentation hotspots. No self-referential edges were detected. There are multiple bidirectional cycles and a set of orphan nodes that appear to be reports or operational artifacts.

## Potential Garbage Nodes

### Bidirectional Cycles (sample)
These pairs have A ↔ B links, which can inflate graph density and create circular references.
- `cortana-personal-ai/docs/safety/SAFETY_ARCHITECTURE_IMPLEMENTATION.md` ↔ `cortana-personal-ai/docs/vision/PERSONAL_AI_ARCHITECTURE_VISION.md`
- `cortana-personal-ai/docs/reference/Personal_AI_Philosophy_System_v1.md` ↔ `cortana-personal-ai/docs/README.md`
- `project-scaffolding/Documents/reference/DOCUMENTATION_HYGIENE.md` ↔ `project-scaffolding/Documents/PROJECT_STRUCTURE_STANDARDS.md`
- `project-scaffolding/Documents/PROJECT_INDEXING_SYSTEM.md` ↔ `project-scaffolding/Documents/PROJECT_KICKOFF_GUIDE.md`
- `project-scaffolding/REVIEWS_AND_GOVERNANCE_PROTOCOL.md` ↔ `Project-workflow.md`
- `image-workflow/Documents/video_creation/image-to-video-blueprint.md` ↔ `image-workflow/Documents/video_creation/setup-local-ai.md`
- `image-workflow/Documents/safety/FILE_SAFETY_SYSTEM.md` ↔ `image-workflow/Documents/core/ARCHITECTURE_OVERVIEW.md`
- `agent-skills-library/README.md` ↔ `project-scaffolding/AGENTS.md`
- `agent-skills-library/FIRST_SKILL_COMPLETE.md` ↔ `agent-skills-library/README.md`
- `trading-copilot/PROJECT_PHILOSOPHY.md` ↔ `trading-copilot/PROJECTS.md`

### Orphan Nodes (sample)
These nodes have no inbound or outbound links.
- `BACKUP_FILES_CLEANUP_REPORT.md`
- `BACKUP_PATTERN_ANALYSIS_AND_PROPOSAL.md`
- `AUDIT_TASK_DOCUMENTATION_LANDSCAPE.md`
- `AGENTSYNC_DRIFT_REPORT.md`
- `CLAWDBOT-suggestions.md`
- `TASK_ANTIGRAVITY_FIX_WORKFLOW_REFS.md`
- `WARDEN_LOG.yaml`
- `PROJECT_WORKFLOW_LINK_FIXES.md`
- `DOCUMENTATION_CLEANUP_SUMMARY.md`

### Meta-Documentation Hotspots (high degree)
These are heavily-connected docs that can dominate the graph and are likely "docs about docs."
- `ai-model-scratch-build/README.md`
- `ai-journal/entries/2025/README.md`
- `project-scaffolding/00_Index_project-scaffolding.md`
- `image-workflow/Documents/README.md`
- `project-scaffolding/Documents/PROJECT_KICKOFF_GUIDE.md`
- `project-scaffolding/README.md`

## Recommendations
- Consider pruning bidirectional links to a single directional reference where appropriate.
- Exclude operational reports and audit artifacts from graph indexing (`*_REPORT.md`, drift summaries, backups).
- Add a filter to de-emphasize or collapse documentation hubs (e.g., README/Index files).
- Optionally exclude `ai-journal` index nodes from cross-project graph unless explicitly referenced.
