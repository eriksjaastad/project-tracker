import json
from pathlib import Path
from collections import defaultdict

GRAPH_PATH = Path(__file__).parent / "data" / "graph.json"

def main():
    if not GRAPH_PATH.exists():
        print(f"Error: {GRAPH_PATH} not found.")
        return

    with open(GRAPH_PATH, "r") as f:
        data = json.load(f)

    orphans_by_project = defaultdict(list)
    total_orphans = 0

    for node in data.get("nodes", []):
        if node.get("is_orphan") or node.get("size") == 0:
            orphans_by_project[node["project"]].append(node["id"])
            total_orphans += 1

    for project in sorted(orphans_by_project.keys()):
        files = sorted(orphans_by_project[project])
        print(f"=== {project} ({len(files)} orphans) ===")
        for f in files:
            print(f)
        print()

    print(f"TOTAL: {total_orphans} orphans across {len(orphans_by_project)} projects")

if __name__ == "__main__":
    main()
