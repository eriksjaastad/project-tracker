#!/usr/bin/env python3
"""
Journal Specialist - Knowledge Graph Enrichment for AI Memories.
Specifically scans the ai-journal to establish deep links between logs and projects.
"""

import re
import json
from pathlib import Path
from typing import Set

# Configuration
PROJECTS_ROOT = Path(__file__).resolve().parents[3]
JOURNAL_DIR = PROJECTS_ROOT / "ai-journal" / "entries"
GRAPH_DATA = PROJECTS_ROOT / "project-tracker" / "data" / "graph.json"

class JournalSpecialist:
    def __init__(self):
        self.projects = self._get_project_list()
        self.links = []

    def _get_project_list(self) -> Set[str]:
        """Get list of top-level project directories."""
        skip = {'.git', 'venv', '.venv', 'node_modules', '__pycache__', 'data', 'logs'}
        return {p.name for p in PROJECTS_ROOT.iterdir() if p.is_dir() and p.name not in skip}

    def scan(self):
        """Scan all journal entries for project references."""
        if not JOURNAL_DIR.exists():
            print(f"Journal directory not found: {JOURNAL_DIR}")
            return

        print(f"🕵️ Journal Specialist scanning {JOURNAL_DIR}...")
        
        # Walk through year/month directories
        count = 0
        for entry_path in JOURNAL_DIR.glob("**/*.md"):
            if entry_path.name.endswith("__pretty.md") or entry_path.name == "README.md":
                continue
            
            self._process_entry(entry_path)
            count += 1
        
        print(f"✅ Processed {count} journal entries. Found {len(self.links)} project connections.")
        self._update_graph()

    def _process_entry(self, path: Path):
        """Extract project links from a single entry."""
        filename = path.name.lower()
        content = ""
        try:
            content = path.read_text(errors='ignore')
        except:
            return

        # 1. Match project in filename (slug)
        # Example: 2026-01-11...__project-tracker-phase4.md
        for project in self.projects:
            # Look for project name surrounded by non-alphanumerics or at start/end
            pattern = rf'[\-_]{re.escape(project.lower())}[\-_.]'
            if re.search(pattern, filename) or filename.endswith(f"{project.lower()}.md"):
                self.links.append({
                    "journal": str(path.relative_to(PROJECTS_ROOT)),
                    "project": project,
                    "type": "filename_match",
                    "strength": 0.8
                })

        # 2. Match tags like #p/project-name
        tags = re.findall(r'#p/([a-zA-Z0-9\-_]+)', content)
        for tag in tags:
            if tag in self.projects:
                self.links.append({
                    "journal": str(path.relative_to(PROJECTS_ROOT)),
                    "project": tag,
                    "type": "tag_match",
                    "strength": 1.0
                })
            # Also check if tag is a fuzzy match or a common alias
            elif tag.replace('-', '_') in self.projects or tag.replace('_', '-') in self.projects:
                resolved = tag.replace('-', '_') if tag.replace('-', '_') in self.projects else tag.replace('_', '-')
                self.links.append({
                    "journal": str(path.relative_to(PROJECTS_ROOT)),
                    "project": resolved,
                    "type": "fuzzy_tag_match",
                    "strength": 0.9
                })

        # 3. Match explicit project indices [[00_Index_project-name]]
        indices = re.findall(r'\[\[00_Index_([a-zA-Z0-9\-_]+)\]\]', content)
        for idx in indices:
            if idx in self.projects:
                self.links.append({
                    "journal": str(path.relative_to(PROJECTS_ROOT)),
                    "project": idx,
                    "type": "index_link",
                    "strength": 1.0
                })

    def _update_graph(self):
        """Inject discovered links as edges into graph.json."""
        if not GRAPH_DATA.exists():
            print("Graph data not found. Run graph_builder first.")
            return

        try:
            with open(GRAPH_DATA, 'r') as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error reading graph: {e}")
            return

        # Map project names to their Index node IDs (usually 00_Index_project.md)
        project_to_node = {}
        for node in data.get('nodes', []):
            if node['name'].startswith('00_Index_'):
                p_name = node['name'].replace('00_Index_', '').replace('.md', '')
                project_to_node[p_name] = node['id']
            # Fallback to root README if index missing
            elif node['name'] == 'README.md' and node['project'] != 'root':
                if node['project'] not in project_to_node:
                    project_to_node[node['project']] = node['id']

        # Add new edges
        new_edges_count = 0
        existing_edges = {(e['source'], e['target']) for e in data.get('edges', [])}

        for link in self.links:
            source = link['journal']
            target_project = link['project']
            
            target_node_id = project_to_node.get(target_project)
            if target_node_id and (source, target_node_id) not in existing_edges:
                data['edges'].append({
                    "source": source,
                    "target": target_node_id,
                    "type": "journal_reference",
                    "metadata": {
                        "match_type": link['type'],
                        "strength": link['strength']
                    }
                })
                existing_edges.add((source, target_node_id))
                new_edges_count += 1

        if new_edges_count > 0:
            with open(GRAPH_DATA, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"✨ Injected {new_edges_count} specialized journal edges into the Knowledge Graph.")
        else:
            print("No new journal edges to add.")

if __name__ == "__main__":
    specialist = JournalSpecialist()
    specialist.scan()
