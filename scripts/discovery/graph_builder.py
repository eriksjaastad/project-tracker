"""Graph builder for project-tracker ecosystem."""

import os
import re
import json
import sys
import argparse
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set, Any, Optional
from collections import defaultdict

# Add project root to sys.path for logger
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from logger import get_logger

logger = get_logger(__name__)

# Load config from shared YAML file (lives in project-scaffolding)
PROJECTS_ROOT = Path(os.getenv("PROJECTS_ROOT", Path.home() / "projects"))
CONFIG_PATH = PROJECTS_ROOT / "project-scaffolding" / "config" / "scan_config.yaml"


def load_config() -> dict:
    """Load graph configuration from YAML file."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f)
    else:
        logger.warning(f"Config not found at {CONFIG_PATH}, using defaults")
        return {}


_config = load_config()

SCAN_EXTENSIONS = _config.get('scan_extensions', {
    '.md': 'markdown',
    '.py': 'python',
    '.ts': 'typescript',
    '.tsx': 'typescript',
    '.js': 'javascript',
    '.jsx': 'javascript',
    '.go': 'go',
    '.json': 'config',
    '.yaml': 'config',
    '.yml': 'config',
})

SKIP_DIRS = set(_config.get('skip_dirs', []))
SKIP_FILES = set(_config.get('skip_files', []))
SKIP_PATTERNS = _config.get('skip_patterns', [])
IGNORE_PROJECTS = set(_config.get('ignore_projects', []))
PROTECTED_PROJECTS = set(_config.get('protected_projects', []))

# Regex patterns for relationship detection
MD_LINK_PATTERN = re.compile(r'\[([^\]]+)\]\(([^)]+\.[a-zA-Z0-9]+)\)')

# Python: from x import y OR import x
PYTHON_IMPORT_FROM = re.compile(r'^\s*from\s+([\w.]+)\s+import', re.MULTILINE)
PYTHON_IMPORT = re.compile(r'^\s*import\s+([\w.,\s]+)', re.MULTILINE)

# JS/TS: import x from 'y' OR import {x} from 'y' OR require('y')
JS_IMPORT = re.compile(r'import\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]', re.MULTILINE)
JS_REQUIRE = re.compile(r'require\([\'"]([^\'"]+)[\'"]\)', re.MULTILINE)

# Go: import "x"
GO_IMPORT = re.compile(r'import\s+[\'"]([^\'"]+)[\'"]', re.MULTILINE)
GO_IMPORT_BLOCK = re.compile(r'import\s+\((.*?)\)', re.DOTALL)

# File reference: # See: path OR // See: path
FILE_REFERENCE = re.compile(r'(?:#|//)\s*See:\s*([^\s\n]+)', re.IGNORECASE)


class GraphBuilder:
    """Builds a knowledge graph of files and their relationships."""

    def __init__(self, root_path: Path):
        self.root = root_path
        self.nodes = []
        self.edges = []
        self.node_map = {}  # id -> node index
        self.stats = {
            "total_nodes": 0,
            "total_edges": 0,
            "orphan_count": 0,
            "projects_scanned": 0,
            "density": 0.0
        }
        self.projects = set()

    def _get_project_name(self, path: Path) -> str:
        """Extract project name from file path."""
        try:
            relative = path.relative_to(self.root)
            return relative.parts[0] if relative.parts else "root"
        except ValueError:
            return "external"

    def _get_node_id(self, path: Path) -> str:
        """Generate a unique ID for a file."""
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)

    def scan(self):
        """Scan the ecosystem for files and build nodes."""
        logger.info(f"Scanning ecosystem starting from: {self.root}")
        
        file_list = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            p_dirpath = Path(dirpath)
            project_name = self._get_project_name(p_dirpath)
            
            # 1. Always skip hidden directories and universal junk
            dirnames[:] = [d for d in dirnames if not d.startswith('.') and d not in SKIP_DIRS]

            # 2. Skip entire projects that are completely ignored
            if project_name in IGNORE_PROJECTS:
                dirnames.clear()  # Don't descend into this project
                continue

            if project_name != "root":
                self.projects.add(project_name)

            for filename in filenames:
                # Skip files from config (boilerplate that exists in every project)
                if filename in SKIP_FILES:
                    continue
                # Skip patterns from config (e.g., tsconfig*, *.d.ts)
                skip = False
                for pattern in SKIP_PATTERNS:
                    if pattern.startswith('*') and filename.endswith(pattern[1:]):
                        skip = True
                        break
                    elif pattern.endswith('*') and filename.startswith(pattern[:-1]):
                        skip = True
                        break
                if skip:
                    continue

                ext = Path(filename).suffix.lower()
                if ext in SCAN_EXTENSIONS:
                    file_path = p_dirpath / filename
                    file_list.append(file_path)
                    
                    node_id = self._get_node_id(file_path)
                    node = {
                        "id": node_id,
                        "name": filename,
                        "type": SCAN_EXTENSIONS[ext],
                        "project": project_name,
                        "path": node_id,
                        "size": 0,
                        "is_orphan": True
                    }
                    self.node_map[node_id] = len(self.nodes)
                    self.nodes.append(node)

        self.stats["total_nodes"] = len(self.nodes)
        self.stats["projects_scanned"] = len(self.projects)
        logger.info(f"Found {len(self.nodes)} files across {len(self.projects)} projects")

        # Now process each file for edges
        for file_path in file_list:
            self._process_file(file_path)

        # Update stats and orphan status
        self._finalize_graph()

    def _process_file(self, file_path: Path):
        """Extract relationships from a single file."""
        node_id = self._get_node_id(file_path)
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
        except Exception as e:
            logger.warning(f"Could not read {file_path}: {e}")
            return

        ext = file_path.suffix.lower()
        
        # Markdown relationships
        if ext == '.md':
            self._extract_markdown_relationships(node_id, content, file_path)
        
        # Python relationships
        elif ext == '.py':
            self._extract_python_relationships(node_id, content)
            
        # JS/TS relationships
        elif ext in ['.js', '.jsx', '.ts', '.tsx']:
            self._extract_js_ts_relationships(node_id, content)
            
        # Go relationships
        elif ext == '.go':
            self._extract_go_relationships(node_id, content)

        # Generic file references (# See: path)
        self._extract_file_references(node_id, content, file_path)

    def _add_edge(self, source_id: str, target_id: str, edge_type: str, label: str = ""):
        """Add an edge if the target exists."""
        if target_id in self.node_map and source_id != target_id:
            edge = {
                "source": source_id,
                "target": target_id,
                "type": edge_type,
                "label": label
            }
            # Avoid duplicate edges
            if edge not in self.edges:
                self.edges.append(edge)
                
            # Update sizes and orphan status (always do this if target exists)
            source_idx = self.node_map[source_id]
            target_idx = self.node_map[target_id]
            self.nodes[source_idx]["size"] += 1
            self.nodes[target_idx]["size"] += 1
            self.nodes[source_idx]["is_orphan"] = False
            self.nodes[target_idx]["is_orphan"] = False

    def _extract_markdown_relationships(self, source_id: str, content: str, file_path: Path):
        source_node = self.nodes[self.node_map[source_id]]
        source_project = source_node["project"]
        
        # Markdown links [text](path)
        for text, path in MD_LINK_PATTERN.findall(content):
            if path.startswith(('http', 'mailto', '#')):
                continue
            
            try:
                target_path = (file_path.parent / path).resolve()
                target_id = self._get_node_id(target_path)
                self._add_edge(source_id, target_id, "markdown_link", f"[{text}]({path})")
            except Exception:
                target_name = Path(path).name
                for node in self.nodes:
                    if node["name"] == target_name:
                        self._add_edge(source_id, node["id"], "markdown_link", f"[{text}]({path})")
                        break

    def _extract_python_relationships(self, source_id: str, content: str):
        for match in PYTHON_IMPORT_FROM.findall(content):
            self._resolve_python_module(source_id, match, "python_import")

        for match in PYTHON_IMPORT.findall(content):
            for part in match.split(','):
                parts = part.strip().split()
                if parts:
                    module = parts[0]
                    self._resolve_python_module(source_id, module, "python_import")

    def _resolve_python_module(self, source_id: str, module_path: str, edge_type: str):
        path_parts = module_path.split('.')
        potential_files = [
            os.path.join(*path_parts) + ".py",
            os.path.join(*path_parts, "__init__.py")
        ]
        
        for pf in potential_files:
            for node in self.nodes:
                if node["path"].endswith(pf):
                    self._add_edge(source_id, node["id"], edge_type, f"import {module_path}")
                    return

    def _extract_js_ts_relationships(self, source_id: str, content: str):
        for match in JS_IMPORT.findall(content):
            self._resolve_js_module(source_id, match, "js_import")
        for match in JS_REQUIRE.findall(content):
            self._resolve_js_module(source_id, match, "js_require")

    def _resolve_js_module(self, source_id: str, module_path: str, edge_type: str):
        if module_path.startswith('.'):
            target_name = Path(module_path).name
            for node in self.nodes:
                if node["name"].startswith(target_name):
                    self._add_edge(source_id, node["id"], edge_type, f"import {module_path}")
                    return
        else:
            for node in self.nodes:
                if module_path in node["path"]:
                    self._add_edge(source_id, node["id"], edge_type, f"import {module_path}")
                    return

    def _extract_go_relationships(self, source_id: str, content: str):
        for match in GO_IMPORT.findall(content):
            self._resolve_go_module(source_id, match)
        for match in GO_IMPORT_BLOCK.findall(content):
            for line in match.split('\n'):
                line = line.strip()
                if not line or line.startswith('//'):
                    continue
                inner_match = re.search(r'[\'"]([^\'"]+)[\'"]', line)
                if inner_match:
                    self._resolve_go_module(source_id, inner_match.group(1))

    def _resolve_go_module(self, source_id: str, module_path: str):
        target_name = Path(module_path).name
        for node in self.nodes:
            if node["name"] == target_name + ".go":
                self._add_edge(source_id, node["id"], "go_import", f"import {module_path}")
                return

    def _extract_file_references(self, source_id: str, content: str, file_path: Path):
        """Extract generic 'See: path' references."""
        for match in FILE_REFERENCE.findall(content):
            path_str = match.strip()
            # Try as relative path first
            try:
                target_path = (file_path.parent / path_str).resolve()
                target_id = self._get_node_id(target_path)
                if target_id in self.node_map:
                    self._add_edge(source_id, target_id, "file_reference", f"See: {path_str}")
                    continue
            except (OSError, ValueError) as e:
                logger.debug(f"Could not resolve file reference {path_str} from {source_id}: {e}")
            
            # Try as absolute path from root
            target_id = path_str.lstrip('/')
            if target_id in self.node_map:
                self._add_edge(source_id, target_id, "file_reference", f"See: {path_str}")
                continue
                
            # Try as filename match
            target_name = Path(path_str).name
            for node in self.nodes:
                if node["name"] == target_name:
                    self._add_edge(source_id, node["id"], "file_reference", f"See: {path_str}")
                    break

    def _finalize_graph(self):
        """Calculate final stats and status."""
        self.stats["total_edges"] = len(self.edges)
        orphans = [n for n in self.nodes if n["is_orphan"]]
        self.stats["orphan_count"] = len(orphans)
        
        # Calculate density
        if self.stats["total_nodes"] > 1:
            n = self.stats["total_nodes"]
            self.stats["density"] = self.stats["total_edges"] / (n * (n - 1))
            
        logger.info(f"Final graph: {self.stats['total_nodes']} nodes, {self.stats['total_edges']} edges, {self.stats['orphan_count']} orphans")

    def generate_analysis(self) -> str:
        """Generate a detailed markdown analysis of the graph."""
        logger.info("Generating AI-readable analysis layer...")
        
        lines = []
        lines.append("# Ecosystem Neural Network Analysis")
        lines.append(f"Generated: {datetime.now().isoformat()}")
        lines.append("")
        
        # Vital Signs
        orphan_pct = (self.stats["orphan_count"] / self.stats["total_nodes"] * 100) if self.stats["total_nodes"] else 0
        lines.append("## Vital Signs")
        lines.append(f"- **Total Nodes:** {self.stats['total_nodes']} files")
        lines.append(f"- **Total Edges:** {self.stats['total_edges']} connections")
        lines.append(f"- **Orphan Count:** {self.stats['orphan_count']} ({orphan_pct:.1f}%)")
        lines.append(f"- **Graph Density:** {self.stats['density']:.6f} ({'sparse' if self.stats['density'] < 0.01 else 'dense'})")
        lines.append(f"- **Projects Scanned:** {self.stats['projects_scanned']}")
        lines.append("")
        
        # Hub Nodes (Top 10)
        lines.append("## Hub Nodes (Top 10 Most Connected)")
        lines.append("| Rank | File | Connections | Type | Project |")
        lines.append("|------|------|-------------|------|---------|")
        hubs = sorted(self.nodes, key=lambda x: x["size"], reverse=True)[:10]
        for i, hub in enumerate(hubs):
            lines.append(f"| {i+1} | {hub['id']} | {hub['size']} | {hub['type']} | {hub['project']} |")
        lines.append("")
        
        # Cross-Project Bridges (referenced from 3+ different projects)
        lines.append("## Cross-Project Bridges")
        lines.append("Files referenced from multiple projects:")
        target_projects = defaultdict(set)
        for edge in self.edges:
            source_node = next((n for n in self.nodes if n["id"] == edge["source"]), None)
            if source_node:
                target_projects[edge["target"]].add(source_node["project"])
        
        bridges = []
        for target_id, projects in target_projects.items():
            if len(projects) >= 3:
                bridges.append((target_id, len(projects)))
        
        for b_id, count in sorted(bridges, key=lambda x: x[1], reverse=True):
            lines.append(f"- `{b_id}` → referenced by {count} projects")
        if not bridges:
            lines.append("- *No cross-project bridges found.*")
        lines.append("")
        
        # Project Dependency Matrix
        lines.append("## Project Dependency Matrix")
        lines.append("Which projects are most depended upon:")
        depended_on = defaultdict(int)
        for target_id, projects in target_projects.items():
            target_node = next((n for n in self.nodes if n["id"] == target_id), None)
            if target_node:
                for p in projects:
                    if p != target_node["project"]:
                        depended_on[target_node["project"]] += 1
        
        for project, count in sorted(depended_on.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"- `{project}` ← referenced {count} times from other projects")
        lines.append("")
        
        # Isolated Clusters
        lines.append("## Isolated Clusters (Low External Connectivity)")
        lines.append("Projects with fewest external connections:")
        project_outbound = defaultdict(int)
        for edge in self.edges:
            source_node = next((n for n in self.nodes if n["id"] == edge["source"]), None)
            target_node = next((n for n in self.nodes if n["id"] == edge["target"]), None)
            if source_node and target_node and source_node["project"] != target_node["project"]:
                project_outbound[source_node["project"]] += 1
        
        isolated = []
        for p in self.projects:
            count = project_outbound.get(p, 0)
            isolated.append((p, count))
            
        for p, count in sorted(isolated, key=lambda x: x[1])[:5]:
            lines.append(f"- `{p}` - {count} outbound links")
        lines.append("")
        
        # Orphan Hotspots
        lines.append("## Orphan Hotspots")
        lines.append("Directories with the most unconnected files:")
        lines.append("| Directory | Orphan Count | Total Files | Orphan % |")
        lines.append("|-----------|--------------|-------------|----------|")
        
        dir_stats = defaultdict(lambda: {"total": 0, "orphans": 0})
        for node in self.nodes:
            path_parts = Path(node["id"]).parts
            if len(path_parts) > 1:
                dir_key = os.path.join(*path_parts[:-1])
                dir_stats[dir_key]["total"] += 1
                if node["is_orphan"]:
                    dir_stats[dir_key]["orphans"] += 1
        
        hotspots = []
        for dir_name, s in dir_stats.items():
            pct = (s["orphans"] / s["total"] * 100)
            hotspots.append((dir_name, s["orphans"], s["total"], pct))
            
        for d, o, t, p in sorted(hotspots, key=lambda x: x[1], reverse=True)[:10]:
            lines.append(f"| {d} | {o} | {t} | {p:.1f}% |")
        lines.append("")
        
        # File Type Distribution
        lines.append("## File Type Distribution")
        lines.append("| Type | Count | % of Total | Avg Connections |")
        lines.append("|------|-------|------------|-----------------|")
        
        type_stats = defaultdict(lambda: {"count": 0, "size_sum": 0})
        for node in self.nodes:
            type_stats[node["type"]]["count"] += 1
            type_stats[node["type"]]["size_sum"] += node["size"]
            
        for t, s in sorted(type_stats.items(), key=lambda x: x[1]["count"], reverse=True):
            pct = (s["count"] / self.stats["total_nodes"] * 100)
            avg = s["size_sum"] / s["count"] if s["count"] else 0
            lines.append(f"| {t} | {s['count']} | {pct:.1f}% | {avg:.1f} |")
        lines.append("")
        
        return "\n".join(lines)

    def update_todo(self, todo_path: Path):
        """Update ecosystem TODO.md with neural network status."""
        if not todo_path.exists():
            logger.warning(f"Ecosystem TODO not found: {todo_path}")
            return
            
        logger.info(f"Updating ecosystem TODO: {todo_path}")
        
        content = todo_path.read_text()
        
        # Find hubs and isolated
        hubs = sorted(self.nodes, key=lambda x: x["size"], reverse=True)[:1]
        top_hub = hubs[0]["id"] if hubs else "N/A"
        
        project_outbound = defaultdict(int)
        for edge in self.edges:
            source_node = next((n for n in self.nodes if n["id"] == edge["source"]), None)
            target_node = next((n for n in self.nodes if n["id"] == edge["target"]), None)
            if source_node and target_node and source_node["project"] != target_node["project"]:
                project_outbound[source_node["project"]] += 1
        
        isolated = sorted(self.projects, key=lambda x: project_outbound.get(x, 0))[:1]
        most_isolated = isolated[0] if isolated else "N/A"
        isolated_count = project_outbound.get(most_isolated, 0)
        
        target_projects = defaultdict(set)
        for edge in self.edges:
            source_node = next((n for n in self.nodes if n["id"] == edge["source"]), None)
            if source_node:
                target_projects[edge["target"]].add(source_node["project"])
        
        bridge_count = len([t for t, p in target_projects.items() if len(p) >= 3])
        orphan_pct = (self.stats["orphan_count"] / self.stats["total_nodes"] * 100) if self.stats["total_nodes"] else 0
        health = "GOOD" if orphan_pct < 5 else "STABLE" if orphan_pct < 15 else "CONGESTED"

        new_section = [
            "## Neural Network Status (Auto-Updated)",
            "",
            f"**Last Scan:** {datetime.now().strftime('%b %d, %Y %I:%M %p')}",
            f"**Health:** {health} ({orphan_pct:.1f}% orphan rate)",
            "",
            "**Quick Stats:**",
            f"- {self.stats['total_nodes']} nodes | {self.stats['total_edges']} edges | {self.stats['orphan_count']} orphans",
            f"- Top Hub: `{top_hub}` ({hubs[0]['size'] if hubs else 0} connections)",
            f"- Most Isolated: `{most_isolated}` ({isolated_count} external links)",
            f"- Cross-project bridges: {bridge_count} files link 3+ projects",
            "",
            "**View full analysis:** `project-tracker/data/graph_analysis.md`",
            "**Interactive graph:** `./pt launch` → Graph tab",
            ""
        ]
        
        new_section_text = "\n".join(new_section)
        
        if "## Neural Network Status (Auto-Updated)" in content:
            # Replace existing section
            pattern = re.compile(r'## Neural Network Status \(Auto-Updated\).*?(?=## |$)', re.DOTALL)
            updated_content = pattern.sub(new_section_text, content)
        else:
            # Append to end
            updated_content = content.strip() + "\n\n" + new_section_text
            
        todo_path.write_text(updated_content)
        logger.info("Ecosystem TODO updated.")

    def to_json(self) -> Dict[str, Any]:
        """Convert graph to JSON format."""
        return {
            "generated_at": datetime.now().isoformat(),
            "stats": self.stats,
            "nodes": self.nodes,
            "edges": self.edges
        }

    def save(self, output_path: Path):
        """Save graph to JSON file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_json(), f, indent=2)
        logger.info(f"Graph saved to {output_path}")


def main():
    print("Starting Graph Builder...")
    parser = argparse.ArgumentParser(description="Ecosystem Knowledge Graph Builder")
    default_root = str(Path(__file__).resolve().parents[3])
    parser.add_argument("--root", type=str, default=default_root, help="Root directory to scan")
    parser.add_argument("--output", type=str, default="data/graph.json", help="Output JSON file")
    parser.add_argument("--analysis", type=str, default=None, help="Where to write the analysis markdown (default: same dir as --output)")
    parser.add_argument("--update-todo", type=str, default=None, help="Optionally append a summary snapshot to the ecosystem TODO.md")
    args = parser.parse_args()

    root_path = Path(args.root)
    output_path = Path(args.output)
    
    # If output path is relative, make it relative to the script's project root
    if not output_path.is_absolute():
        project_root = Path(__file__).parent.parent.parent
        output_path = project_root / output_path

    start_time = datetime.now()
    
    builder = GraphBuilder(root_path)
    builder.scan()
    builder.save(output_path)
    
    # Analysis layer
    analysis_text = builder.generate_analysis()
    analysis_path = Path(args.analysis) if args.analysis else output_path.parent / "graph_analysis.md"
    analysis_path.write_text(analysis_text)
    logger.info(f"Analysis saved to {analysis_path}")
    
    # Update TODO if requested
    if args.update_todo:
        builder.update_todo(Path(args.update_todo))
    
    duration = datetime.now() - start_time
    logger.info(f"Graph built and analyzed in {duration.total_seconds():.2f} seconds")


if __name__ == "__main__":
    main()
