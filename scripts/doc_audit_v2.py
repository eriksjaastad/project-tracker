#!/usr/bin/env python3
"""
Document Quality Audit System v2 - Semantic Atlas Architecture

A sophisticated multi-pass system for identifying and consolidating redundant documentation.

Architecture:
- Pass 0 (Atlas): Generate standardized summaries + embeddings for ALL docs
- Pass 1 (Auditor): Identify redundancy using Atlas context → Keep/Merge/Delete/Refine
- Pass 2 (Surgeon): Merge related docs into "Golden Versions"
- Pass 3 (QC): Polish and add cross-project links

Key Features:
- Semantic Atlas: Global view of all docs in one context window
- Vector Embeddings: Pre-cluster similar docs before LLM analysis
- Cross-Project Awareness: "Project_B already has a better version"
- Structured Outputs: Machine-parseable decisions

Usage:
    # Build the Semantic Atlas (required first step)
    python doc_audit_v2.py atlas --build

    # Find similar document clusters
    python doc_audit_v2.py atlas --find-similar --threshold 0.85

    # Run the Auditor pass (generates prompts)
    python doc_audit_v2.py audit --project trading-copilot

    # View status
    python doc_audit_v2.py status

    # Clean up
    python doc_audit_v2.py cleanup
"""

import argparse
import json
import os
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Optional
import hashlib

# Optional imports for embeddings
try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

# ============================================================
# Configuration
# ============================================================

PROJECTS_ROOT = Path(__file__).resolve().parents[2]
AUDIT_DIR = Path(__file__).parent.parent / "data" / "doc_audit_v2"

# Subdirectories
ATLAS_DIR = AUDIT_DIR / "atlas"
EMBEDDINGS_DIR = AUDIT_DIR / "embeddings"
CLUSTERS_DIR = AUDIT_DIR / "clusters"
PROMPTS_DIR = AUDIT_DIR / "prompts"
REPORTS_DIR = AUDIT_DIR / "reports"
ACTIONS_DIR = AUDIT_DIR / "actions"

SKIP_DIRS = {
    "node_modules", "venv", ".venv", "__pycache__", ".git",
    "_trash", ".pytest_cache", ".ruff_cache", "data", "logs",
    "archives", ".next", "dist", "build", "doc_audit", "doc_audit_v2"
}

# ============================================================
# PROTECTED PROJECTS - No automated changes allowed!
# These projects contain creative/personal content that should
# never be modified by automated audit processes.
# ============================================================
PROTECTED_PROJECTS = {
    "ai-journal",                # Personal AI conversation journal - creative/personal content
    "writing",                   # Creative writing projects - stories, drafts, etc.
    "plugin-duplicate-detection", # Protected extension - do not touch
    "plugin-find-names-chrome",   # Protected extension - do not touch
}

def is_protected(path: str) -> bool:
    """Check if a path belongs to a protected project."""
    project = path.split('/')[0] if '/' in path else path
    return project in PROTECTED_PROJECTS


# ============================================================
# Data Structures
# ============================================================

@dataclass
class AtlasEntry:
    """Standardized summary for the Semantic Atlas."""
    path: str                    # Relative path from projects root
    project: str                 # Project name
    title: str                   # Document title
    size_bytes: int              # File size
    lines: int                   # Line count
    core_purpose: str            # One-sentence purpose (filled by Gemini)
    key_points: list[str]        # 5 bullet points (filled by Gemini)
    doc_type: str                # readme, guide, reference, config, archive, etc.
    last_modified: str           # ISO timestamp
    content_hash: str            # For change detection
    embedding: list[float] | None = None  # Vector embedding


@dataclass
class AuditDecision:
    """Structured output from the Auditor pass."""
    path: str
    decision: str                # KEEP, MERGE, DELETE, REFINE
    confidence: float            # 0.0 - 1.0
    reasoning: str               # One sentence
    merge_with: list[str] | None # Paths to merge with (if MERGE)
    refine_notes: str | None     # What needs refinement (if REFINE)


# ============================================================
# Utility Functions
# ============================================================

def ensure_dirs():
    """Create all audit directories."""
    for d in [ATLAS_DIR, EMBEDDINGS_DIR, CLUSTERS_DIR, PROMPTS_DIR, REPORTS_DIR, ACTIONS_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    # Write timestamp
    (AUDIT_DIR / ".audit_started").write_text(datetime.now().isoformat())


def content_hash(content: str) -> str:
    """Generate hash for change detection."""
    return hashlib.md5(content.encode()).hexdigest()[:12]


def get_all_docs() -> list[dict]:
    """Collect all markdown docs across all projects."""
    docs = []

    for project_dir in PROJECTS_ROOT.iterdir():
        if not project_dir.is_dir():
            continue
        if project_dir.name.startswith(('.', '_')):
            continue
        if project_dir.name in SKIP_DIRS:
            continue

        for md_file in project_dir.rglob("*.md"):
            rel_parts = md_file.relative_to(project_dir).parts
            if any(part in SKIP_DIRS for part in rel_parts):
                continue
            if any(part.startswith(".") for part in rel_parts):
                continue

            try:
                content = md_file.read_text(encoding='utf-8', errors='ignore')
                stat = md_file.stat()

                # Extract title
                title = md_file.stem
                for line in content.split('\n')[:10]:
                    if line.startswith('# '):
                        title = line[2:].strip()
                        break

                # Guess doc type
                name_lower = md_file.name.lower()
                if 'readme' in name_lower:
                    doc_type = 'readme'
                elif 'index' in name_lower:
                    doc_type = 'index'
                elif 'guide' in name_lower or 'how' in name_lower:
                    doc_type = 'guide'
                elif 'arch' in name_lower:
                    doc_type = 'architecture'
                elif 'todo' in name_lower:
                    doc_type = 'todo'
                elif 'changelog' in name_lower or 'history' in name_lower:
                    doc_type = 'changelog'
                elif any(x in name_lower for x in ['old', 'deprecated', 'backup', 'archive']):
                    doc_type = 'archive'
                else:
                    doc_type = 'reference'

                docs.append({
                    "path": str(md_file.relative_to(PROJECTS_ROOT)),
                    "project": project_dir.name,
                    "title": title,
                    "size_bytes": len(content),
                    "lines": content.count('\n') + 1,
                    "doc_type": doc_type,
                    "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "content_hash": content_hash(content),
                    "content_preview": content[:1000],
                    "full_path": str(md_file)
                })
            except Exception as e:
                print(f"  Warning: {md_file}: {e}")

    return sorted(docs, key=lambda x: (x["project"], x["path"]))


# ============================================================
# Pass 0: Semantic Atlas
# ============================================================

def generate_atlas_prompt(docs: list[dict], batch_num: int) -> str:
    """Generate prompt for Gemini to create Atlas entries."""

    prompt = f"""# Semantic Atlas Generation - Batch {batch_num}

You are building a "Semantic Atlas" - a high-level map of all documentation in a software ecosystem.

For EACH document below, provide:
1. **core_purpose**: One sentence describing what this document is for
2. **key_points**: Exactly 5 bullet points of the most important content
3. **doc_type**: Classify as one of: readme, index, guide, architecture, reference, config, todo, changelog, archive, other

## Output Format
Return a JSON array with one object per document:
```json
[
  {{
    "path": "project/path/to/file.md",
    "core_purpose": "Explains how to configure API authentication for the trading system.",
    "key_points": [
      "Uses OAuth 2.0 for authentication",
      "Requires TRADING_API_KEY environment variable",
      "Supports both sandbox and production endpoints",
      "Rate limited to 100 requests/minute",
      "Tokens expire after 24 hours"
    ],
    "doc_type": "guide"
  }},
  ...
]
```

## Documents to Process ({len(docs)} documents)

"""

    for i, doc in enumerate(docs, 1):
        prompt += f"""---
### Document {i}: {doc['title']}
**Path:** `{doc['path']}`
**Project:** {doc['project']}
**Type Guess:** {doc['doc_type']}
**Size:** {doc['lines']} lines

**Content Preview:**
```
{doc['content_preview'][:800]}
```

"""

    prompt += """
---
## Your Task
Generate the Atlas entries for ALL documents above. Be concise but capture the essence of each document.
Return ONLY the JSON array, no other text.
"""

    return prompt


def cmd_atlas_build(auto: bool = False):
    """Build the Semantic Atlas."""
    ensure_dirs()

    print("\n🗺️  Building Semantic Atlas...\n")

    # Collect all docs
    docs = get_all_docs()
    print(f"   Found {len(docs)} documents across {len(set(d['project'] for d in docs))} projects\n")

    # Save raw doc inventory
    inventory_path = ATLAS_DIR / "doc_inventory.json"
    inventory_path.write_text(json.dumps(docs, indent=2, default=str))
    print(f"   📦 Inventory saved: {inventory_path.name}")

    # Generate prompts in batches (to stay under context limits)
    BATCH_SIZE = 25  # ~25 docs per prompt is safe
    batches = [docs[i:i+BATCH_SIZE] for i in range(0, len(docs), BATCH_SIZE)]

    print(f"   📝 Generating {len(batches)} prompt batches...\n")

    for i, batch in enumerate(batches, 1):
        prompt = generate_atlas_prompt(batch, i)
        prompt_path = PROMPTS_DIR / f"atlas_batch_{i:03d}.md"
        prompt_path.write_text(prompt)
        print(f"      Batch {i}: {len(batch)} docs → {prompt_path.name}")

    if auto:
        # Process batches automatically with Gemini API
        print(f"\n🤖 Auto-processing {len(batches)} batches with Gemini...\n")
        _auto_process_batches(batches)
    else:
        print(f"""
✅ Atlas prompts generated!

📂 Prompts location: {PROMPTS_DIR}

💡 Next steps:
   1. Feed each batch prompt to Gemini (in order)
   2. Save Gemini's JSON responses to: {ATLAS_DIR}/atlas_batch_XXX.json
   3. Run: python doc_audit_v2.py atlas --compile

💡 Or run with --auto to process automatically via API:
   python doc_audit_v2.py atlas --build --auto
""")


def _auto_process_batches(batches: list[list[dict]]):
    """Process atlas batches automatically via Gemini API."""
    import time

    if not GENAI_AVAILABLE:
        print("Error: google-generativeai not installed", flush=True)
        print("Run: pip install google-generativeai", flush=True)
        return

    # Get API key
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        import subprocess
        try:
            result = subprocess.run(
                ["doppler", "secrets", "get", "GOOGLE_API_KEY", "--plain",
                 "--project", "trading-copilot", "--config", "dev"],
                capture_output=True, text=True
            )
            api_key = result.stdout.strip()
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            print(f"Could not fetch API key from Doppler: {e}", flush=True)

    if not api_key:
        print("Error: GOOGLE_API_KEY not found in environment or Doppler", flush=True)
        return

    print(f"   🔑 API key loaded ({len(api_key)} chars)", flush=True)
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.0-flash-exp')

    success_count = 0
    for i, batch in enumerate(batches, 1):
        batch_num = f"{i:03d}"
        response_path = ATLAS_DIR / f"atlas_batch_{batch_num}.json"

        # Skip if already processed
        if response_path.exists():
            print(f"      Batch {i}/{len(batches)}: Already processed ✓", flush=True)
            success_count += 1
            continue

        prompt_path = PROMPTS_DIR / f"atlas_batch_{batch_num}.md"
        if not prompt_path.exists():
            print(f"      Batch {i}/{len(batches)}: Prompt not found ⚠️", flush=True)
            continue

        prompt = prompt_path.read_text()
        print(f"      Batch {i}/{len(batches)}: Processing...", end=" ", flush=True)

        try:
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.3
                )
            )

            # Parse and save response
            result_text = response.text
            # Handle potential markdown code blocks
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]

            result = json.loads(result_text)
            response_path.write_text(json.dumps(result, indent=2))
            print(f"{len(result)} entries ✅", flush=True)
            success_count += 1

            # Rate limiting - be gentle with the API
            if i < len(batches):
                time.sleep(2)

        except json.JSONDecodeError as e:
            print(f"JSON parse error ⚠️ ({e})", flush=True)
            # Save raw response for debugging
            error_path = ATLAS_DIR / f"atlas_batch_{batch_num}_raw.txt"
            error_path.write_text(response.text if response else "No response")
        except Exception as e:
            print(f"API error ⚠️ ({e})", flush=True)
            time.sleep(5)  # Longer pause on error

    print(f"\n✅ Auto-processing complete: {success_count}/{len(batches)} batches", flush=True)

    if success_count == len(batches):
        print("\n💡 All batches processed! Now run:", flush=True)
        print("   python doc_audit_v2.py atlas --compile", flush=True)


def cmd_atlas_compile():
    """Compile Atlas batch responses into a single Atlas."""

    print("\n📚 Compiling Semantic Atlas...\n")

    # Load inventory for metadata
    inventory_path = ATLAS_DIR / "doc_inventory.json"
    if not inventory_path.exists():
        print("Error: Run 'atlas --build' first")
        return

    inventory = {d["path"]: d for d in json.loads(inventory_path.read_text())}

    # Load all batch responses
    atlas_entries = []
    batch_files = sorted(ATLAS_DIR.glob("atlas_batch_*.json"))

    if not batch_files:
        print("No atlas batch responses found.")
        print(f"Save Gemini's responses to: {ATLAS_DIR}/atlas_batch_001.json, etc.")
        return

    for batch_file in batch_files:
        try:
            batch_data = json.loads(batch_file.read_text())
            for entry in batch_data:
                # Merge with inventory metadata
                path = entry["path"]
                if path in inventory:
                    inv = inventory[path]
                    atlas_entries.append({
                        **entry,
                        "project": inv["project"],
                        "title": inv["title"],
                        "size_bytes": inv["size_bytes"],
                        "lines": inv["lines"],
                        "last_modified": inv["last_modified"],
                        "content_hash": inv["content_hash"],
                        "embedding": None
                    })
            print(f"   ✅ {batch_file.name}: {len(batch_data)} entries")
        except Exception as e:
            print(f"   ⚠️ {batch_file.name}: {e}")

    # Save compiled atlas
    atlas_path = ATLAS_DIR / "semantic_atlas.json"
    atlas_path.write_text(json.dumps(atlas_entries, indent=2))

    print(f"""
✅ Atlas compiled!

📊 Stats:
   Total entries: {len(atlas_entries)}
   Projects: {len(set(e['project'] for e in atlas_entries))}

📂 Atlas location: {atlas_path}

💡 Next steps:
   1. Generate embeddings: python doc_audit_v2.py embeddings --generate
   2. Find similar docs: python doc_audit_v2.py embeddings --cluster
""")


# ============================================================
# Embeddings & Similarity
# ============================================================

def cmd_embeddings_generate():
    """Generate embeddings for all Atlas entries."""
    import time

    if not GENAI_AVAILABLE:
        print("Error: google-generativeai not installed", flush=True)
        print("Run: pip install google-generativeai", flush=True)
        return

    atlas_path = ATLAS_DIR / "semantic_atlas.json"
    if not atlas_path.exists():
        print("Error: Compile the Atlas first (atlas --compile)", flush=True)
        return

    print("\n🧬 Generating embeddings...\n", flush=True)

    # Configure API
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        # Try Doppler
        import subprocess
        try:
            result = subprocess.run(
                ["doppler", "secrets", "get", "GOOGLE_API_KEY", "--plain",
                 "--project", "trading-copilot", "--config", "dev"],
                capture_output=True, text=True
            )
            api_key = result.stdout.strip()
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            print(f"Could not fetch API key from Doppler: {e}", flush=True)

    if not api_key:
        print("Error: GOOGLE_API_KEY not found", flush=True)
        return

    print(f"   🔑 API key loaded", flush=True)
    genai.configure(api_key=api_key)

    atlas = json.loads(atlas_path.read_text())

    # Count docs needing embeddings
    needs_embedding = [e for e in atlas if not e.get("embedding")]
    already_done = len(atlas) - len(needs_embedding)

    if already_done > 0:
        print(f"   ✓ {already_done} documents already have embeddings", flush=True)

    if not needs_embedding:
        print(f"\n✅ All {len(atlas)} documents already have embeddings!", flush=True)
        return

    print(f"   📊 Processing {len(needs_embedding)} documents...\n", flush=True)

    # Generate embeddings for each entry
    # We embed: core_purpose + key_points joined
    processed = 0
    for i, entry in enumerate(atlas):
        if entry.get("embedding"):
            continue  # Skip if already has embedding

        # Create text to embed
        text = f"{entry['core_purpose']} " + " ".join(entry.get('key_points', []))

        try:
            result = genai.embed_content(
                model="models/text-embedding-004",
                content=text
            )
            entry["embedding"] = result['embedding']
            processed += 1

            if processed % 50 == 0:
                print(f"   Processed {processed}/{len(needs_embedding)} documents...", flush=True)
                # Save progress
                atlas_path.write_text(json.dumps(atlas, indent=2))

            # Small delay to avoid rate limits
            if processed % 100 == 0:
                time.sleep(1)

        except Exception as e:
            print(f"   ⚠️ {entry['path']}: {e}", flush=True)
            time.sleep(2)

    # Final save
    atlas_path.write_text(json.dumps(atlas, indent=2))

    embedded_count = sum(1 for e in atlas if e.get("embedding"))
    print(f"\n✅ Embeddings complete: {embedded_count}/{len(atlas)} documents")


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    if not NUMPY_AVAILABLE:
        # Manual calculation
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0
    else:
        a, b = np.array(a), np.array(b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def cmd_find_similar(threshold: float = 0.85):
    """Find similar document clusters using embeddings."""

    atlas_path = ATLAS_DIR / "semantic_atlas.json"
    if not atlas_path.exists():
        print("Error: Build and compile Atlas first")
        return

    atlas = json.loads(atlas_path.read_text())

    # Filter to entries with embeddings
    with_embeddings = [e for e in atlas if e.get("embedding")]

    if not with_embeddings:
        print("No embeddings found. Run: embeddings --generate")
        return

    print(f"\n🔍 Finding similar documents (threshold: {threshold})...\n")

    # Calculate pairwise similarities
    clusters = []
    seen = set()

    for i, doc_a in enumerate(with_embeddings):
        if doc_a["path"] in seen:
            continue

        similar = []
        for j, doc_b in enumerate(with_embeddings):
            if i == j:
                continue
            if doc_b["path"] in seen:
                continue

            sim = cosine_similarity(doc_a["embedding"], doc_b["embedding"])
            if sim >= threshold:
                similar.append({
                    "path": doc_b["path"],
                    "project": doc_b["project"],
                    "title": doc_b["title"],
                    "similarity": round(sim, 3)
                })

        if similar:
            cluster = {
                "anchor": {
                    "path": doc_a["path"],
                    "project": doc_a["project"],
                    "title": doc_a["title"],
                    "core_purpose": doc_a.get("core_purpose", "")
                },
                "similar": sorted(similar, key=lambda x: -x["similarity"]),
                "size": len(similar) + 1
            }
            clusters.append(cluster)
            seen.add(doc_a["path"])
            for s in similar:
                seen.add(s["path"])

    # Sort clusters by size
    clusters.sort(key=lambda x: -x["size"])

    # Save clusters
    clusters_path = CLUSTERS_DIR / "similar_docs.json"
    clusters_path.write_text(json.dumps(clusters, indent=2))

    # Generate report
    report_lines = [
        "# Similar Document Clusters",
        f"Generated: {datetime.now().isoformat()}",
        f"Threshold: {threshold}",
        f"Total clusters: {len(clusters)}",
        "",
        "---",
        ""
    ]

    for i, cluster in enumerate(clusters[:30], 1):  # Top 30
        anchor = cluster["anchor"]
        report_lines.append(f"## Cluster {i}: {anchor['title']}")
        report_lines.append(f"**Anchor:** `{anchor['path']}` ({anchor['project']})")
        report_lines.append(f"**Purpose:** {anchor['core_purpose']}")
        report_lines.append(f"**Similar documents ({len(cluster['similar'])}):**")
        for s in cluster["similar"]:
            report_lines.append(f"- `{s['path']}` ({s['project']}) - {s['similarity']*100:.1f}% similar")
        report_lines.append("")

    report_path = REPORTS_DIR / "similarity_report.md"
    report_path.write_text("\n".join(report_lines))

    print(f"   Found {len(clusters)} clusters")
    print(f"\n   📊 Report: {report_path}")
    print(f"   📦 Data: {clusters_path}")

    # Preview top clusters
    if clusters:
        print(f"\n   Top clusters:")
        for c in clusters[:5]:
            print(f"      • {c['anchor']['title']}: {c['size']} similar docs")


# ============================================================
# Pass 1: Auditor
# ============================================================

def generate_auditor_prompt(project: str, atlas: list[dict], clusters: list[dict]) -> str:
    """Generate prompt for the Auditor pass."""

    # Filter atlas to this project
    project_docs = [e for e in atlas if e["project"] == project]

    # Get clusters involving this project
    project_clusters = [c for c in clusters
                       if c["anchor"]["project"] == project
                       or any(s["project"] == project for s in c["similar"])]

    prompt = f"""# Document Auditor - {project}

You are the **Auditor**, responsible for reviewing documentation and making structured decisions.

## Your Context

### This Project's Documents ({len(project_docs)} total)
"""

    for doc in project_docs:
        prompt += f"""
**{doc['title']}** (`{doc['path']}`)
- Type: {doc.get('doc_type', 'unknown')}
- Purpose: {doc.get('core_purpose', 'Not analyzed')}
- Key points: {', '.join(doc.get('key_points', [])[:3])}
"""

    if project_clusters:
        prompt += f"""

### Similar Documents Across Projects
These documents from OTHER projects are semantically similar to docs in {project}:
"""
        for cluster in project_clusters[:10]:
            prompt += f"""
**Cluster: {cluster['anchor']['title']}**
- Anchor: `{cluster['anchor']['path']}`
- Similar: {', '.join(f"`{s['path']}`" for s in cluster['similar'][:3])}
"""

    prompt += f"""

## Your Task

For EACH document in {project}, provide a decision:

| Decision | When to Use |
|----------|-------------|
| **KEEP** | Unique, valuable, no redundancy |
| **MERGE** | Should be combined with another doc (specify which) |
| **DELETE** | Empty, obsolete, or completely redundant |
| **REFINE** | Good content but needs cleanup/updating |

## Output Format

Return a JSON array:
```json
[
  {{
    "path": "project/file.md",
    "decision": "KEEP",
    "confidence": 0.95,
    "reasoning": "Core project documentation, unique content.",
    "merge_with": null,
    "refine_notes": null
  }},
  {{
    "path": "project/old_guide.md",
    "decision": "MERGE",
    "confidence": 0.8,
    "reasoning": "70% overlap with setup_guide.md",
    "merge_with": ["project/setup_guide.md"],
    "refine_notes": null
  }},
  {{
    "path": "project/notes.md",
    "decision": "DELETE",
    "confidence": 0.9,
    "reasoning": "Empty file with only a title.",
    "merge_with": null,
    "refine_notes": null
  }},
  {{
    "path": "project/api.md",
    "decision": "REFINE",
    "confidence": 0.85,
    "reasoning": "Good content but references deprecated endpoints.",
    "merge_with": null,
    "refine_notes": "Update API endpoints to v2, remove OAuth 1.0 section"
  }}
]
```

Analyze ALL {len(project_docs)} documents and return the JSON array.
"""

    return prompt


def cmd_audit(project: Optional[str] = None, projects_list: Optional[str] = None, auto: bool = False):
    """Run the Auditor pass."""
    import time

    atlas_path = ATLAS_DIR / "semantic_atlas.json"
    clusters_path = CLUSTERS_DIR / "similar_docs.json"

    if not atlas_path.exists():
        print("Error: Build the Atlas first", flush=True)
        return

    atlas = json.loads(atlas_path.read_text())
    clusters = json.loads(clusters_path.read_text()) if clusters_path.exists() else []

    if projects_list:
        # Comma-separated list of projects
        projects = [p.strip() for p in projects_list.split(",")]
    elif project:
        projects = [project]
    else:
        projects = sorted(set(e["project"] for e in atlas))

    print(f"\n⚖️  Auditor Pass: {len(projects)} projects\n", flush=True)

    # Get API key if auto mode
    api_key = None
    model = None
    if auto:
        if not GENAI_AVAILABLE:
            print("Error: google-generativeai not installed", flush=True)
            return

        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            import subprocess
            try:
                result = subprocess.run(
                    ["doppler", "secrets", "get", "GOOGLE_API_KEY", "--plain",
                     "--project", "trading-copilot", "--config", "dev"],
                    capture_output=True, text=True
                )
                api_key = result.stdout.strip()
            except (subprocess.SubprocessError, FileNotFoundError) as e:
                print(f"Could not fetch API key from Doppler: {e}", flush=True)

        if not api_key:
            print("Error: GOOGLE_API_KEY not found", flush=True)
            return

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        print(f"   🔑 API key loaded, auto-processing enabled\n", flush=True)

    success_count = 0
    for proj in projects:
        proj_docs = [e for e in atlas if e["project"] == proj]
        if len(proj_docs) < 2:
            print(f"   ⏭️  {proj}: Skipping (only {len(proj_docs)} docs)", flush=True)
            continue

        response_path = ACTIONS_DIR / f"audit_{proj}.json"

        # Skip if already processed
        if response_path.exists():
            print(f"   ✓ {proj}: Already processed ({len(proj_docs)} docs)", flush=True)
            success_count += 1
            continue

        prompt = generate_auditor_prompt(proj, atlas, clusters)
        prompt_path = PROMPTS_DIR / f"audit_{proj}.md"
        prompt_path.write_text(prompt)

        if auto and model:
            print(f"   🔄 {proj}: Processing {len(proj_docs)} docs...", end=" ", flush=True)
            try:
                response = model.generate_content(
                    prompt,
                    generation_config=genai.GenerationConfig(
                        response_mime_type="application/json",
                        temperature=0.3
                    )
                )

                result_text = response.text
                if result_text.startswith("```"):
                    result_text = result_text.split("```")[1]
                    if result_text.startswith("json"):
                        result_text = result_text[4:]

                result = json.loads(result_text)
                response_path.write_text(json.dumps(result, indent=2))
                print(f"✅ ({len(result)} decisions)", flush=True)
                success_count += 1
                time.sleep(1)  # Rate limiting

            except json.JSONDecodeError:
                print(f"JSON error ⚠️", flush=True)
                error_path = ACTIONS_DIR / f"audit_{proj}_raw.txt"
                error_path.write_text(response.text if response else "No response")
            except Exception as e:
                print(f"API error: {e} ⚠️", flush=True)
                time.sleep(3)
        else:
            print(f"   ✅ {proj}: {len(proj_docs)} docs → {prompt_path.name}", flush=True)

    if auto:
        print(f"\n✅ Auditor complete: {success_count}/{len(projects)} projects processed", flush=True)
    else:
        print(f"""
📂 Prompts saved to: {PROMPTS_DIR}

💡 Next steps:
   1. Feed each audit prompt to Gemini
   2. Save responses to: {ACTIONS_DIR}/audit_{{project}}.json
   3. Run: python doc_audit_v2.py report
""", flush=True)


# ============================================================
# Status & Cleanup
# ============================================================

def cmd_status():
    """Show audit status."""
    print(f"\n📊 Document Audit v2 Status\n")
    print(f"Directory: {AUDIT_DIR}")

    if not AUDIT_DIR.exists():
        print("No audit in progress.")
        return

    # Count files in each stage
    inventory = ATLAS_DIR / "doc_inventory.json"
    atlas = ATLAS_DIR / "semantic_atlas.json"

    atlas_prompts = list(PROMPTS_DIR.glob("atlas_batch_*.md"))
    atlas_responses = list(ATLAS_DIR.glob("atlas_batch_*.json"))
    audit_prompts = list(PROMPTS_DIR.glob("audit_*.md"))
    audit_responses = list(ACTIONS_DIR.glob("audit_*.json"))

    print(f"""
Stage 0 - Atlas:
  Inventory: {'✅' if inventory.exists() else '❌'}
  Prompts generated: {len(atlas_prompts)}
  Responses received: {len(atlas_responses)}
  Compiled Atlas: {'✅' if atlas.exists() else '❌'}

Stage 1 - Embeddings:
  Atlas has embeddings: {_count_embeddings(atlas)}

Stage 2 - Clusters:
  Similarity clusters: {_count_clusters()}

Stage 3 - Audit:
  Audit prompts: {len(audit_prompts)}
  Audit responses: {len(audit_responses)}
""")


def _count_embeddings(atlas_path: Path) -> str:
    if not atlas_path.exists():
        return "N/A"
    atlas = json.loads(atlas_path.read_text())
    with_emb = sum(1 for e in atlas if e.get("embedding"))
    return f"{with_emb}/{len(atlas)}"


def _count_clusters() -> str:
    clusters_path = CLUSTERS_DIR / "similar_docs.json"
    if not clusters_path.exists():
        return "Not generated"
    clusters = json.loads(clusters_path.read_text())
    return str(len(clusters))


def cmd_cleanup():
    """Remove all audit data."""
    if not AUDIT_DIR.exists():
        print("No audit data to clean up.")
        return

    # This used to be a hand-rolled recursive delete carrying the comment
    # "Safety: ... to avoid Warden P0 block on dangerous removal function" —
    # i.e. it existed specifically to route around the guardrail that blocks
    # shutil.rmtree, and destroyed the tree permanently with no recovery.
    # Routing around the ban is not a safety measure; send2trash IS the
    # sanctioned removal path and it is recoverable (#6899).
    from send2trash import send2trash

    send2trash(str(AUDIT_DIR))
    print(f"✅ Removed: {AUDIT_DIR}")


# ============================================================
# Content Surgeon Pass
# ============================================================

def normalize_decision(d: dict) -> dict:
    """Normalize different audit response formats."""
    action = d.get('action') or d.get('decision', 'UNKNOWN')
    merge_with = d.get('merge_with')
    if isinstance(merge_with, list):
        merge_with = merge_with[0] if merge_with else None
    return {
        'path': d.get('path', ''),
        'action': action,
        'reason': d.get('reason') or d.get('reasoning', ''),
        'merge_with': merge_with
    }


def load_all_audit_decisions() -> list[dict]:
    """Load and normalize all audit decisions."""
    all_decisions = []
    for f in sorted(ACTIONS_DIR.glob('audit_*.json')):
        if '_raw' in f.stem:
            continue
        try:
            raw = json.loads(f.read_text())
            for d in raw:
                all_decisions.append(normalize_decision(d))
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: Could not load decision file {f}: {e}")
    return all_decisions


def cmd_surgeon(action: str = "list", dry_run: bool = True):
    """Content Surgeon pass - execute merges and deletes."""
    print("🔪 Content Surgeon Pass", flush=True)
    print("=" * 50, flush=True)

    decisions = load_all_audit_decisions()

    # Filter out protected projects
    merges_raw = [d for d in decisions if d['action'] == 'MERGE']
    deletes_raw = [d for d in decisions if d['action'] == 'DELETE']

    merges = [d for d in merges_raw if not is_protected(d['path'])]
    deletes = [d for d in deletes_raw if not is_protected(d['path'])]

    protected_count = len(merges_raw) - len(merges) + len(deletes_raw) - len(deletes)
    if protected_count > 0:
        print(f"\n🛡️  Protected: {protected_count} items in {', '.join(PROTECTED_PROJECTS)} (skipped)", flush=True)

    if action == "list":
        print(f"\n📋 Pending Operations:", flush=True)
        print(f"   MERGE:  {len(merges)} documents", flush=True)
        print(f"   DELETE: {len(deletes)} documents", flush=True)

        if merges:
            print(f"\n🔀 Merge Targets:", flush=True)
            by_target = {}
            for m in merges:
                target = m.get('merge_with') or '(unspecified)'
                by_target.setdefault(target, []).append(m['path'])

            for target, sources in sorted(by_target.items()):
                print(f"\n   → {target}", flush=True)
                for src in sources[:5]:
                    print(f"      ← {src}", flush=True)
                if len(sources) > 5:
                    print(f"      ... and {len(sources) - 5} more", flush=True)

        if deletes:
            print(f"\n🗑️  Delete Candidates:", flush=True)
            for d in deletes[:10]:
                print(f"   - {d['path']}", flush=True)
                print(f"     Reason: {d['reason'][:60]}...", flush=True)
            if len(deletes) > 10:
                print(f"   ... and {len(deletes) - 10} more", flush=True)

    elif action == "delete":
        print(f"\n🗑️  Processing {len(deletes)} deletions...", flush=True)

        if dry_run:
            print(f"   [DRY RUN] Would send to macOS Trash:", flush=True)
            for d in deletes:
                src_path = PROJECTS_ROOT / d['path']
                exists = "✓" if src_path.exists() else "✗ (not found)"
                print(f"   [DRY RUN] {d['path']} {exists}", flush=True)
        else:
            from send2trash import send2trash
            trashed = 0
            not_found = 0
            for d in deletes:
                src_path = PROJECTS_ROOT / d['path']
                if src_path.exists():
                    send2trash(str(src_path))
                    trashed += 1
                    print(f"   🗑️  {d['path']}", flush=True)
                else:
                    not_found += 1
            print(f"\n✅ Sent {trashed} files to Trash", flush=True)
            if not_found:
                print(f"   ({not_found} files not found - already deleted?)", flush=True)

    elif action == "merge":
        print(f"\n🔀 Processing {len(merges)} merges...", flush=True)

        # Group by target
        by_target = {}
        for m in merges:
            target = m.get('merge_with')
            if target:
                by_target.setdefault(target, []).append(m)

        if dry_run:
            print(f"   [DRY RUN] Would merge into {len(by_target)} target documents", flush=True)
            for target, sources in list(by_target.items())[:5]:
                print(f"   [DRY RUN] {target} ← {len(sources)} sources", flush=True)
        else:
            merged_count = 0
            for target, sources in by_target.items():
                target_path = PROJECTS_ROOT / target
                if not target_path.exists():
                    print(f"   ⚠️  Target not found: {target}", flush=True)
                    continue

                # Read target content
                target_content = target_path.read_text()

                # Append merged content
                merged_section = "\n\n---\n\n## Merged Content\n\n"
                merged_section += f"*The following content was merged from {len(sources)} documents:*\n\n"

                for src in sources:
                    src_path = PROJECTS_ROOT / src['path']
                    if src_path.exists():
                        merged_section += f"### From: {src['path']}\n\n"
                        merged_section += src_path.read_text()
                        merged_section += "\n\n"
                        merged_count += 1

                # Write updated target
                target_path.write_text(target_content + merged_section)
                print(f"   ✓ {target} ← {len(sources)} merged", flush=True)

            print(f"\n✅ Merged {merged_count} documents", flush=True)


def cmd_merge_process(task_id: str = None, auto: bool = False, dry_run: bool = True):
    """Process merge tasks via Gemini API."""
    import subprocess
    import time

    MERGE_DIR = AUDIT_DIR / "merge_tasks"
    MERGE_OUTPUT_DIR = AUDIT_DIR / "merge_output"
    MERGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("🔀 Merge Task Processor", flush=True)
    print("=" * 50, flush=True)

    # Load task index
    index_path = MERGE_DIR / "index.json"
    if not index_path.exists():
        print("❌ No merge tasks found. Run surgeon --list first.", flush=True)
        return

    tasks = json.loads(index_path.read_text())

    # Filter to specific task if requested
    if task_id:
        tasks = [t for t in tasks if t['task_id'] == task_id]
        if not tasks:
            print(f"❌ Task {task_id} not found.", flush=True)
            return

    # Skip already processed
    pending = []
    for t in tasks:
        output_path = MERGE_OUTPUT_DIR / f"{t['task_id']}_merged.md"
        if output_path.exists():
            print(f"   ✓ {t['task_id']}: Already processed", flush=True)
        else:
            pending.append(t)

    print(f"\n📋 Pending: {len(pending)} merge tasks", flush=True)

    if not auto:
        print("\nRun with --auto to process via Gemini API", flush=True)
        return

    # Get API key
    result = subprocess.run(
        ['doppler', 'secrets', 'get', 'GOOGLE_API_KEY', '--plain',
         '--project', 'trading-copilot', '--config', 'dev'],
        capture_output=True, text=True
    )
    api_key = result.stdout.strip()

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.0-flash-exp')

    for i, task in enumerate(pending):
        task_file = MERGE_DIR / f"{task['task_id']}.md"
        task_content = task_file.read_text()

        print(f"\n[{i+1}/{len(pending)}] 🔄 {task['task_id']}: {task['target']}...", end=" ", flush=True)

        prompt = f"""You are a documentation merger. Given the following merge task, produce a single unified document.

{task_content}

INSTRUCTIONS:
1. Combine the target and source documents intelligently
2. Remove duplicate information
3. Preserve all unique content from each source
4. Maintain consistent formatting and structure
5. Output ONLY the merged markdown content, no explanations

OUTPUT: The complete merged document in markdown format.
"""

        try:
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=8192,
                )
            )

            merged_content = response.text.strip()

            # Save merged output
            output_path = MERGE_OUTPUT_DIR / f"{task['task_id']}_merged.md"
            output_path.write_text(merged_content)
            print(f"✅ Done", flush=True)

            if not dry_run:
                # Apply to actual file
                target_path = PROJECTS_ROOT / task['target']
                if target_path.exists():
                    target_path.write_text(merged_content)
                    print(f"      → Applied to {task['target']}", flush=True)

        except Exception as e:
            print(f"❌ Error: {e}", flush=True)

        # Rate limit
        if i < len(pending) - 1:
            time.sleep(7)

    print(f"\n✅ Processed {len(pending)} merge tasks", flush=True)
    print(f"   Output: {MERGE_OUTPUT_DIR}/", flush=True)


# ============================================================
# Refinement Pass
# ============================================================

def cmd_refine(project: str = None, auto: bool = False):
    """Process refinement tasks via Gemini API."""
    import subprocess
    import time

    REFINE_DIR = AUDIT_DIR / "refine_tasks"
    REFINE_OUTPUT_DIR = AUDIT_DIR / "refine_output"
    REFINE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("✨ Refinement Processor", flush=True)
    print("=" * 50, flush=True)

    # Load batch index
    index_path = REFINE_DIR / "index.json"
    if not index_path.exists():
        print("❌ No refine batches found. Run qc --report first.", flush=True)
        return

    batches = json.loads(index_path.read_text())

    # Filter out protected projects
    protected_batches = [b for b in batches if b['project'] in PROTECTED_PROJECTS]
    batches = [b for b in batches if b['project'] not in PROTECTED_PROJECTS]

    if protected_batches:
        print(f"\n🛡️  Protected projects (skipped):", flush=True)
        for b in protected_batches:
            print(f"      {b['project']}: {b['count']} docs", flush=True)

    # Filter to specific project if requested
    if project:
        if project in PROTECTED_PROJECTS:
            print(f"\n🛡️  ERROR: '{project}' is a PROTECTED PROJECT", flush=True)
            print(f"      Protected projects: {', '.join(PROTECTED_PROJECTS)}", flush=True)
            print(f"      These contain creative/personal content and cannot be auto-modified.", flush=True)
            return
        batches = [b for b in batches if b['project'] == project]
        if not batches:
            print(f"❌ Project {project} not found.", flush=True)
            return

    if not auto:
        print(f"\n📋 Projects to refine: {len(batches)}", flush=True)
        for b in batches:
            output_dir = REFINE_OUTPUT_DIR / b['project']
            done = len(list(output_dir.glob('*.md'))) if output_dir.exists() else 0
            print(f"   {b['project']}: {b['count']} docs ({done} done)", flush=True)
        print("\nRun with --auto to process via Gemini API", flush=True)
        return

    # Get API key
    result = subprocess.run(
        ['doppler', 'secrets', 'get', 'GOOGLE_API_KEY', '--plain',
         '--project', 'trading-copilot', '--config', 'dev'],
        capture_output=True, text=True
    )
    api_key = result.stdout.strip()

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.0-flash-exp')

    total_refined = 0
    for batch in batches:
        proj = batch['project']
        batch_file = REFINE_DIR / batch['batch_file']
        docs = json.loads(batch_file.read_text())

        output_dir = REFINE_OUTPUT_DIR / proj
        output_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n📁 {proj} ({len(docs)} docs)", flush=True)

        for i, doc in enumerate(docs):
            # Create safe filename
            safe_name = doc['path'].replace('/', '_').replace(' ', '_')
            output_path = output_dir / f"{safe_name}.md"

            if output_path.exists():
                print(f"   [{i+1}/{len(docs)}] ✓ Already done", flush=True)
                continue

            print(f"   [{i+1}/{len(docs)}] 🔄 {doc['path'][-50:]}...", end=" ", flush=True)

            prompt = f"""You are a documentation editor. Refine this document to make it more complete and useful.

**Document:** {doc['path']}
**Issue:** {doc['reason']}

**Current Content:**
```markdown
{doc['content']}
```

**Instructions:**
1. If the document is empty or sparse, add appropriate content based on the filename and path
2. If it needs cleanup, improve formatting, fix errors, add structure
3. If it needs context, add explanatory text
4. Preserve any existing valuable content
5. Use proper markdown formatting
6. Keep it concise but complete

**Output:** The complete refined document in markdown format. Output ONLY the markdown, no explanations.
"""

            try:
                response = model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.3,
                        max_output_tokens=4096,
                    )
                )

                refined = response.text.strip()
                if refined.startswith('```'):
                    refined = refined.split('\n', 1)[1].rsplit('```', 1)[0]

                output_path.write_text(refined)
                total_refined += 1
                print(f"✅", flush=True)

            except Exception as e:
                print(f"❌ {e}", flush=True)

            # Rate limit
            time.sleep(7)

    print(f"\n✅ Refined {total_refined} documents", flush=True)
    print(f"   Output: {REFINE_OUTPUT_DIR}/", flush=True)


# ============================================================
# Quality Control Pass
# ============================================================

def cmd_qc(action: str = "list", project: str = None):
    """Quality Control pass - review REFINE candidates."""
    print("✨ Quality Control Pass", flush=True)
    print("=" * 50, flush=True)

    decisions = load_all_audit_decisions()
    refines = [d for d in decisions if d['action'] == 'REFINE']

    # Filter by project if specified
    if project:
        refines = [d for d in refines if d['path'].startswith(f"{project}/")]
        print(f"\nFiltered to project: {project}", flush=True)

    if action == "list":
        print(f"\n📋 REFINE Candidates: {len(refines)} documents", flush=True)

        # Group by project
        by_project = {}
        for d in refines:
            proj = d['path'].split('/')[0]
            by_project.setdefault(proj, []).append(d)

        print(f"\nBy Project:", flush=True)
        for proj in sorted(by_project.keys()):
            docs = by_project[proj]
            print(f"   {proj}: {len(docs)} docs", flush=True)

        # Show high-priority items (index files, READMEs, etc.)
        priority_patterns = ['README', 'AGENTS', 'CLAUDE', 'TODO']
        high_priority = [d for d in refines if any(p in d['path'] for p in priority_patterns)]

        if high_priority:
            print(f"\n⭐ High Priority ({len(high_priority)}):", flush=True)
            for d in high_priority[:15]:
                print(f"   • {d['path']}", flush=True)
                if d['reason']:
                    print(f"     → {d['reason'][:60]}...", flush=True)
            if len(high_priority) > 15:
                print(f"   ... and {len(high_priority) - 15} more", flush=True)

    elif action == "report":
        # Generate detailed refinement report
        report_path = REPORTS_DIR / "refinement_report.md"
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        report = f"""# Refinement Report

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Summary

- **Total REFINE candidates:** {len(refines)}
- **Projects affected:** {len(set(d['path'].split('/')[0] for d in refines))}

## By Project

"""
        by_project = {}
        for d in refines:
            proj = d['path'].split('/')[0]
            by_project.setdefault(proj, []).append(d)

        for proj in sorted(by_project.keys()):
            docs = by_project[proj]
            report += f"### {proj} ({len(docs)} docs)\n\n"
            for d in docs:
                report += f"- `{d['path']}`\n"
                if d['reason']:
                    report += f"  - {d['reason']}\n"
            report += "\n"

        report_path.write_text(report)
        print(f"\n📄 Report saved: {report_path}", flush=True)


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Document Audit System v2")
    subparsers = parser.add_subparsers(dest="command")

    # Atlas commands
    atlas_parser = subparsers.add_parser("atlas", help="Semantic Atlas operations")
    atlas_parser.add_argument("--build", action="store_true", help="Build Atlas prompts")
    atlas_parser.add_argument("--compile", action="store_true", help="Compile Atlas from responses")
    atlas_parser.add_argument("--auto", action="store_true", help="Auto-process batches via Gemini API")

    # Embeddings commands
    emb_parser = subparsers.add_parser("embeddings", help="Embedding operations")
    emb_parser.add_argument("--generate", action="store_true", help="Generate embeddings")
    emb_parser.add_argument("--cluster", action="store_true", help="Find similar clusters")
    emb_parser.add_argument("--threshold", type=float, default=0.85, help="Similarity threshold")

    # Audit command
    audit_parser = subparsers.add_parser("audit", help="Run Auditor pass")
    audit_parser.add_argument("--project", type=str, help="Target specific project")
    audit_parser.add_argument("--projects", type=str, help="Comma-separated list of projects")
    audit_parser.add_argument("--auto", action="store_true", help="Auto-process via Gemini API")

    # Surgeon command
    surgeon_parser = subparsers.add_parser("surgeon", help="Content Surgeon - execute merges/deletes")
    surgeon_parser.add_argument("--list", action="store_true", help="List pending operations")
    surgeon_parser.add_argument("--delete", action="store_true", help="Execute delete operations")
    surgeon_parser.add_argument("--merge", action="store_true", help="Execute merge operations (simple append)")
    surgeon_parser.add_argument("--merge-export", action="store_true", help="Export merge tasks to files")
    surgeon_parser.add_argument("--merge-process", action="store_true", help="Process merge tasks via Gemini")
    surgeon_parser.add_argument("--task", type=str, help="Specific task ID for merge-process")
    surgeon_parser.add_argument("--auto", action="store_true", help="Auto-process via Gemini API")
    surgeon_parser.add_argument("--execute", action="store_true", help="Actually execute (default is dry-run)")

    # Refine command
    refine_parser = subparsers.add_parser("refine", help="Refine documents via Gemini")
    refine_parser.add_argument("--project", type=str, help="Process specific project")
    refine_parser.add_argument("--auto", action="store_true", help="Auto-process via Gemini API")

    # QC command
    qc_parser = subparsers.add_parser("qc", help="Quality Control - review REFINE candidates")
    qc_parser.add_argument("--list", action="store_true", help="List REFINE candidates")
    qc_parser.add_argument("--report", action="store_true", help="Generate refinement report")
    qc_parser.add_argument("--project", type=str, help="Filter by project")

    # Utility commands
    subparsers.add_parser("status", help="Show audit status")
    subparsers.add_parser("cleanup", help="Remove all audit data")

    args = parser.parse_args()

    if args.command == "atlas":
        if args.build:
            cmd_atlas_build(auto=args.auto)
        elif args.compile:
            cmd_atlas_compile()
        else:
            print("Use --build or --compile")
    elif args.command == "embeddings":
        if args.generate:
            cmd_embeddings_generate()
        elif args.cluster:
            cmd_find_similar(args.threshold)
        else:
            print("Use --generate or --cluster")
    elif args.command == "audit":
        cmd_audit(project=args.project, projects_list=args.projects, auto=args.auto)
    elif args.command == "surgeon":
        dry_run = not args.execute
        if args.delete:
            cmd_surgeon(action="delete", dry_run=dry_run)
        elif args.merge:
            cmd_surgeon(action="merge", dry_run=dry_run)
        elif args.merge_process:
            cmd_merge_process(task_id=args.task, auto=args.auto, dry_run=dry_run)
        else:
            cmd_surgeon(action="list")
    elif args.command == "refine":
        cmd_refine(project=args.project, auto=args.auto)
    elif args.command == "qc":
        if args.report:
            cmd_qc(action="report", project=args.project)
        else:
            cmd_qc(action="list", project=args.project)
    elif args.command == "status":
        cmd_status()
    elif args.command == "cleanup":
        cmd_cleanup()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
