"""Graph builder for project-tracker ecosystem."""

import gc
import os
import re
import json
import sys
import argparse
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
from collections import defaultdict

# Add project root to sys.path for logger
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.config import PROJECTS_BASE_DIR
from scripts.logger import get_logger

# Max file size for relationship extraction (skip files > 1 MB to prevent OOM)
MAX_FILE_SIZE_BYTES = 1_000_000

logger = get_logger(__name__)

# Load config from shared YAML file (lives in project-scaffolding)
PROJECTS_ROOT = PROJECTS_BASE_DIR
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
    '.swift': 'swift',
    '.json': 'config',
    '.yaml': 'config',
    '.yml': 'config',
})

SKIP_DIRS = set(_config.get('skip_dirs', []))
SKIP_FILES = set(_config.get('skip_files', []))
SKIP_PATTERNS = _config.get('skip_patterns', [])
IGNORE_PROJECTS = set(_config.get('ignore_projects', []))
PROTECTED_PROJECTS = set(_config.get('protected_projects', []))
ORPHAN_EXEMPT_PROJECTS = set(_config.get('orphan_exempt_projects', ['root']))

# Regex patterns for relationship detection
MD_LINK_PATTERN = re.compile(r'\[([^\]]+)\]\(([^)]+\.[a-zA-Z0-9]+)\)')

# Obsidian wikilinks: [[Document Name]] or [[path/to/file]]
WIKILINK_PATTERN = re.compile(r'\[\[([^\]]+)\]\]')

# Python: from x import y OR import x
PYTHON_IMPORT_FROM = re.compile(r'^\s*from\s+([\w.]+)\s+import', re.MULTILINE)
PYTHON_IMPORT = re.compile(r'^\s*import\s+([\w.,\s]+)', re.MULTILINE)

# Python CLI invocations in markdown code blocks: `python scripts/run.py`
MD_PYTHON_CLI = re.compile(r'`(?:python|python3|uv run)\s+([^\s`]+\.py)', re.MULTILINE)

# JS/TS: import x from 'y' OR import {x} from 'y' OR require('y')
JS_IMPORT = re.compile(r'import\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]', re.MULTILINE)
JS_REQUIRE = re.compile(r'require\([\'"]([^\'"]+)[\'"]\)', re.MULTILINE)

# Go: import "x"
GO_IMPORT = re.compile(r'import\s+[\'"]([^\'"]+)[\'"]', re.MULTILINE)
GO_IMPORT_BLOCK = re.compile(r'import\s+\((.*?)\)', re.DOTALL)

# Swift: type definitions (class, struct, protocol, enum)
SWIFT_TYPE_DEF = re.compile(r'^\s*(?:public\s+|private\s+|internal\s+|open\s+|final\s+)*(?:class|struct|protocol|enum)\s+(\w+)', re.MULTILINE)

# Shell: source ./file.sh OR . ./file.sh OR bash scripts/run.sh
SHELL_SOURCE = re.compile(r'(?:source|\.)\s+([^\s;]+\.(?:sh|bash|zsh))', re.MULTILINE)
SHELL_EXEC = re.compile(r'(?:bash|sh|zsh)\s+([^\s;]+\.(?:sh|bash|zsh))', re.MULTILINE)

# Dockerfile: COPY/ADD directives
DOCKERFILE_COPY = re.compile(r'(?:COPY|ADD)\s+([^\s]+)', re.MULTILINE)

# YAML references: $ref: './schema.yaml' OR extends: base.yaml
YAML_REF = re.compile(r'\$ref:\s*[\'"]([^\'"]+)[\'"]', re.MULTILINE)
YAML_EXTENDS = re.compile(r'extends:\s*[\'"]?([^\s\n\'"]+)[\'"]?', re.MULTILINE)

# Makefile: include common.mk
MAKEFILE_INCLUDE = re.compile(r'^\s*include\s+([^\s\n]+)', re.MULTILINE)

# File reference: # See: path OR // See: path
FILE_REFERENCE = re.compile(r'(?:#|//)\s*See:\s*([^\s\n]+)', re.IGNORECASE)


def _load_gitignore_dirs(project_path: Path) -> set:
    """Load directory-level ignores from a project's .gitignore."""
    gitignore = project_path / ".gitignore"
    dirs = set()
    if not gitignore.exists():
        return dirs
    try:
        for line in gitignore.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # Match simple directory patterns: "tools/", "output/", "/build"
            clean = line.strip('/')
            if clean and '/' not in clean and '*' not in clean:
                dirs.add(clean)
    except Exception:
        pass
    return dirs


class GraphBuilder:
    """Builds a project graph of files and their relationships."""

    def __init__(self, root_path: Path):
        self.root = root_path
        self.nodes = []
        self.edges = []
        self.edge_set = set()  # (source, target, type) for O(1) dedup
        self.node_map = {}  # id -> node index
        self.stats = {
            "total_nodes": 0,
            "total_edges": 0,
            "orphan_count": 0,
            "projects_scanned": 0,
            "density": 0.0
        }
        self.projects = set()
        self._gitignore_cache = {}  # project_name -> set of ignored dirs
        self._swift_types = {}  # type_name -> node_id (for cross-file type references)

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

    def _build_indexes(self):
        """Build lookup indexes for O(1) node resolution."""
        from collections import defaultdict
        self.node_by_id = {node["id"]: node for node in self.nodes}
        self.node_by_name = defaultdict(list)
        for node in self.nodes:
            self.node_by_name[node["name"]].append(node)

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

            # 3. Respect per-project .gitignore directory patterns
            if project_name != "root" and project_name not in self._gitignore_cache:
                self._gitignore_cache[project_name] = _load_gitignore_dirs(self.root / project_name)
            gi_dirs = self._gitignore_cache.get(project_name, set())
            if gi_dirs:
                dirnames[:] = [d for d in dirnames if d not in gi_dirs]

            if project_name != "root":
                self.projects.add(project_name)

            for filename in filenames:
                # Skip dotfiles (consumed by external tools, not project code)
                if filename.startswith('.'):
                    continue
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

        # Build lookup indexes for O(1) node resolution (replaces O(n) linear scans)
        self._build_indexes()

        # Pre-pass: collect Swift type definitions for cross-file resolution
        for file_path in file_list:
            if file_path.suffix.lower() == '.swift':
                try:
                    content = file_path.read_text(encoding='utf-8', errors='ignore')
                    node_id = self._get_node_id(file_path)
                    for type_name in SWIFT_TYPE_DEF.findall(content):
                        self._swift_types[type_name] = node_id
                except Exception:
                    pass

        # Now process each file for edges
        for file_path in file_list:
            self._process_file(file_path)

        # Create synthetic project hub nodes and connect all files to them.
        # This recreates the cluster-per-project visual structure that
        # 00_Index files used to provide, without any files on disk.
        self._add_project_hubs()

        # Free temporary data and collect garbage between phases
        gc.collect()

        # Update stats and orphan status
        self._finalize_graph()

    def _add_project_hubs(self):
        """Create a synthetic hub node per project and connect all files to it.

        Produces the same tight cluster-per-project visual that 00_Index files
        provided, without any files on disk.  Each hub appears as a large
        central node with every file in that project radiating out from it.
        """
        from collections import defaultdict

        # Group node IDs by project
        project_files = defaultdict(list)
        for node in self.nodes:
            project = node.get("project", "root")
            if project != "root":
                project_files[project].append(node["id"])

        for project_name, file_ids in project_files.items():
            if len(file_ids) < 2:
                continue

            # Create a synthetic hub node for this project
            hub_id = f"__hub__{project_name}"
            hub_node = {
                "id": hub_id,
                "name": project_name,
                "type": "project_hub",
                "project": project_name,
                "path": hub_id,
                "size": len(file_ids),
                "is_orphan": False,
            }
            self.node_map[hub_id] = len(self.nodes)
            self.nodes.append(hub_node)

            # Connect every file in this project to the hub
            for file_id in file_ids:
                self._add_edge(file_id, hub_id, "project_member", project_name)

    # Skip reading file contents for files larger than 1 MB to prevent OOM.
    # Node metadata (name, path, type, project) is still collected from the
    # filesystem walk in scan(); only relationship extraction is skipped.

    def _process_file(self, file_path: Path):
        """Extract relationships from a single file."""
        node_id = self._get_node_id(file_path)
        try:
            if file_path.stat().st_size > MAX_FILE_SIZE_BYTES:
                logger.debug(f"Skipping oversized file for relationship scan: {file_path}")
                return
            content = file_path.read_text(encoding='utf-8', errors='ignore')
        except Exception as e:
            logger.warning(f"Could not read {file_path}: {e}")
            return

        ext = file_path.suffix.lower()
        filename = file_path.name

        # Markdown relationships
        if ext == '.md':
            self._extract_markdown_relationships(node_id, content, file_path)
            self._extract_wikilinks(node_id, content, file_path)
            self._extract_python_cli_from_markdown(node_id, content, file_path)

        # Python relationships
        elif ext == '.py':
            self._extract_python_relationships(node_id, content)

        # JS/TS relationships
        elif ext in ['.js', '.jsx', '.ts', '.tsx']:
            self._extract_js_ts_relationships(node_id, content)

        # Swift relationships
        elif ext == '.swift':
            self._extract_swift_relationships(node_id, content)

        # Go relationships
        elif ext == '.go':
            self._extract_go_relationships(node_id, content)

        # Shell script relationships
        elif ext in ['.sh', '.bash', '.zsh']:
            self._extract_shell_relationships(node_id, content, file_path)

        # Dockerfile relationships
        elif filename == 'Dockerfile':
            self._extract_dockerfile_relationships(node_id, content, file_path)

        # Makefile relationships
        elif filename == 'Makefile':
            self._extract_makefile_relationships(node_id, content, file_path)

        # YAML relationships
        elif ext in ['.yaml', '.yml']:
            self._extract_yaml_relationships(node_id, content, file_path)

        # Generic file references (# See: path)
        self._extract_file_references(node_id, content, file_path)

    def _add_edge(self, source_id: str, target_id: str, edge_type: str, label: str = ""):
        """Add an edge if the target exists."""
        if target_id in self.node_map and source_id != target_id:
            # O(1) dedup via set instead of O(n) linear search
            key = (source_id, target_id, edge_type)
            if key not in self.edge_set:
                self.edge_set.add(key)
                self.edges.append({
                    "source": source_id,
                    "target": target_id,
                    "type": edge_type,
                    "label": label
                })

            # Update sizes and orphan status (always do this if target exists)
            source_idx = self.node_map[source_id]
            target_idx = self.node_map[target_id]
            self.nodes[source_idx]["size"] += 1
            self.nodes[target_idx]["size"] += 1
            self.nodes[source_idx]["is_orphan"] = False
            self.nodes[target_idx]["is_orphan"] = False

    def _extract_markdown_relationships(self, source_id: str, content: str, file_path: Path):
        # Markdown links [text](path)
        for text, path in MD_LINK_PATTERN.findall(content):
            if path.startswith(('http', 'mailto', '#')):
                continue
            
            try:
                # Use absolute() not resolve() to avoid following symlinks
                target_path = (file_path.parent / path).absolute()
                target_id = self._get_node_id(target_path)
                self._add_edge(source_id, target_id, "markdown_link", f"[{text}]({path})")
            except Exception:
                target_name = Path(path).name
                for node in self.node_by_name.get(target_name, []):
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
        potential_suffixes = [
            os.path.join(*path_parts) + ".py",
            os.path.join(*path_parts, "__init__.py")
        ]
        # Check node_map keys (which are paths) for suffix matches
        for suffix in potential_suffixes:
            for node_id in self.node_map:
                if node_id.endswith(suffix):
                    self._add_edge(source_id, node_id, edge_type, f"import {module_path}")
                    return

    def _extract_js_ts_relationships(self, source_id: str, content: str):
        for match in JS_IMPORT.findall(content):
            self._resolve_js_module(source_id, match, "js_import")
        for match in JS_REQUIRE.findall(content):
            self._resolve_js_module(source_id, match, "js_require")

    def _resolve_js_module(self, source_id: str, module_path: str, edge_type: str):
        if module_path.startswith('.'):
            target_name = Path(module_path).name
            # Check exact name match first, then prefix match
            for node in self.node_by_name.get(target_name, []):
                self._add_edge(source_id, node["id"], edge_type, f"import {module_path}")
                return
            # Prefix match — check names starting with target_name
            for name, nodes in self.node_by_name.items():
                if name.startswith(target_name):
                    self._add_edge(source_id, nodes[0]["id"], edge_type, f"import {module_path}")
                    return
        else:
            # Path contains — must scan node_map keys
            for node_id in self.node_map:
                if module_path in node_id:
                    self._add_edge(source_id, node_id, edge_type, f"import {module_path}")
                    return

    def _extract_swift_relationships(self, source_id: str, content: str):
        """Extract Swift cross-file type references.

        Swift doesn't use file-level imports for local code — all files in a
        module see each other.  Instead, we connect files by detecting when
        file A references a type (class/struct/protocol/enum) defined in file B.
        """
        for type_name, target_id in self._swift_types.items():
            if target_id == source_id:
                continue  # skip self-references
            # Look for the type name as a whole word in the content
            if re.search(r'\b' + re.escape(type_name) + r'\b', content):
                self._add_edge(source_id, target_id, "swift_type_ref", type_name)

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
        target_name = Path(module_path).name + ".go"
        for node in self.node_by_name.get(target_name, []):
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
            for node in self.node_by_name.get(target_name, []):
                self._add_edge(source_id, node["id"], "file_reference", f"See: {path_str}")
                break

    def _extract_wikilinks(self, source_id: str, content: str, file_path: Path):
        """Extract Obsidian wikilinks [[Document Name]]."""
        for match in WIKILINK_PATTERN.findall(content):
            link_text = match.strip()
            # Wikilinks can be [[path/to/file]] or [[Document Name]]
            # Try as relative path first
            if '/' in link_text:
                try:
                    target_path = (file_path.parent / link_text).resolve()
                    if not target_path.suffix:
                        target_path = target_path.with_suffix('.md')
                    target_id = self._get_node_id(target_path)
                    if target_id in self.node_map:
                        self._add_edge(source_id, target_id, "wikilink", f"[[{link_text}]]")
                        continue
                except (OSError, ValueError):
                    pass

            # Try as filename match (with or without .md extension)
            candidates = (
                self.node_by_name.get(link_text, [])
                or self.node_by_name.get(f"{link_text}.md", [])
            )
            if candidates:
                self._add_edge(source_id, candidates[0]["id"], "wikilink", f"[[{link_text}]]")
            else:
                # Fallback: match by stem (filename without extension)
                for name, nodes in self.node_by_name.items():
                    if Path(name).stem == link_text:
                        self._add_edge(source_id, nodes[0]["id"], "wikilink", f"[[{link_text}]]")
                        break

    def _extract_python_cli_from_markdown(self, source_id: str, content: str, file_path: Path):
        """Extract Python CLI invocations from markdown code blocks."""
        for match in MD_PYTHON_CLI.findall(content):
            script_path = match.strip()
            # Try as relative path
            try:
                target_path = (file_path.parent / script_path).resolve()
                target_id = self._get_node_id(target_path)
                if target_id in self.node_map:
                    self._add_edge(source_id, target_id, "python_cli", f"`python {script_path}`")
                    continue
            except (OSError, ValueError):
                pass

            # Try as filename match
            target_name = Path(script_path).name
            for node in self.node_by_name.get(target_name, []):
                self._add_edge(source_id, node["id"], "python_cli", f"`python {script_path}`")
                break

    def _extract_shell_relationships(self, source_id: str, content: str, file_path: Path):
        """Extract shell script sourcing and execution."""
        # Source patterns: source ./file.sh OR . ./file.sh
        for match in SHELL_SOURCE.findall(content):
            script_path = match.strip()
            self._resolve_shell_path(source_id, script_path, file_path, "shell_source")

        # Execution patterns: bash scripts/run.sh
        for match in SHELL_EXEC.findall(content):
            script_path = match.strip()
            self._resolve_shell_path(source_id, script_path, file_path, "shell_exec")

    def _resolve_shell_path(self, source_id: str, script_path: str, file_path: Path, edge_type: str):
        """Resolve shell script path to a node."""
        # Try as relative path
        try:
            target_path = (file_path.parent / script_path).resolve()
            target_id = self._get_node_id(target_path)
            if target_id in self.node_map:
                self._add_edge(source_id, target_id, edge_type, script_path)
                return
        except (OSError, ValueError):
            pass

        # Try as filename match
        target_name = Path(script_path).name
        for node in self.node_by_name.get(target_name, []):
            self._add_edge(source_id, node["id"], edge_type, script_path)
            return

    def _extract_dockerfile_relationships(self, source_id: str, content: str, file_path: Path):
        """Extract COPY/ADD directives from Dockerfile."""
        for match in DOCKERFILE_COPY.findall(content):
            copy_path = match.strip()
            # Skip URLs and wildcards
            if copy_path.startswith(('http', 'https', '--')) or '*' in copy_path:
                continue

            # Try as relative path
            try:
                target_path = (file_path.parent / copy_path).resolve()
                target_id = self._get_node_id(target_path)
                if target_id in self.node_map:
                    self._add_edge(source_id, target_id, "dockerfile_copy", f"COPY {copy_path}")
                    continue
            except (OSError, ValueError):
                pass

            # Try as filename match
            target_name = Path(copy_path).name
            for node in self.node_by_name.get(target_name, []):
                self._add_edge(source_id, node["id"], "dockerfile_copy", f"COPY {copy_path}")
                break

    def _extract_yaml_relationships(self, source_id: str, content: str, file_path: Path):
        """Extract YAML $ref and extends references."""
        # $ref: './schema.yaml'
        for match in YAML_REF.findall(content):
            ref_path = match.strip()
            self._resolve_yaml_path(source_id, ref_path, file_path, "yaml_ref")

        # extends: base.yaml
        for match in YAML_EXTENDS.findall(content):
            extends_path = match.strip()
            self._resolve_yaml_path(source_id, extends_path, file_path, "yaml_extends")

    def _resolve_yaml_path(self, source_id: str, yaml_path: str, file_path: Path, edge_type: str):
        """Resolve YAML reference path to a node."""
        # Try as relative path
        try:
            target_path = (file_path.parent / yaml_path).resolve()
            target_id = self._get_node_id(target_path)
            if target_id in self.node_map:
                self._add_edge(source_id, target_id, edge_type, yaml_path)
                return
        except (OSError, ValueError):
            pass

        # Try as filename match
        target_name = Path(yaml_path).name
        for node in self.node_by_name.get(target_name, []):
            self._add_edge(source_id, node["id"], edge_type, yaml_path)
            return

    def _extract_makefile_relationships(self, source_id: str, content: str, file_path: Path):
        """Extract Makefile include statements."""
        for match in MAKEFILE_INCLUDE.findall(content):
            include_path = match.strip()
            # Try as relative path
            try:
                target_path = (file_path.parent / include_path).resolve()
                target_id = self._get_node_id(target_path)
                if target_id in self.node_map:
                    self._add_edge(source_id, target_id, "makefile_include", f"include {include_path}")
                    continue
            except (OSError, ValueError):
                pass

            # Try as filename match
            target_name = Path(include_path).name
            for node in self.node_by_name.get(target_name, []):
                self._add_edge(source_id, node["id"], "makefile_include", f"include {include_path}")
                break

    def _finalize_graph(self):
        """Calculate final stats and status."""
        self.stats["total_edges"] = len(self.edges)
        # Exempt root-level files (and other configured projects) from orphan detection
        for node in self.nodes:
            if node["is_orphan"] and node.get("project") in ORPHAN_EXEMPT_PROJECTS:
                node["is_orphan"] = False
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
            source_node = self.node_by_id.get(edge["source"])
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
            target_node = self.node_by_id.get(target_id)
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
            source_node = self.node_by_id.get(edge["source"])
            target_node = self.node_by_id.get(edge["target"])
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
    parser = argparse.ArgumentParser(description="Ecosystem Project Graph Builder")
    default_root = str(Path(__file__).resolve().parents[3])
    parser.add_argument("--root", type=str, default=default_root, help="Root directory to scan")
    parser.add_argument("--output", type=str, default="data/graph.json", help="Output JSON file")
    parser.add_argument("--analysis", type=str, default=None, help="Where to write the analysis markdown (default: same dir as --output)")
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

    duration = datetime.now() - start_time
    logger.info(f"Graph built and analyzed in {duration.total_seconds():.2f} seconds")


if __name__ == "__main__":
    main()
