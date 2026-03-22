#!/usr/bin/env -S uv run --script
# /// script
# dependencies = [
#   "playwright",
# ]
# ///
"""
Memory Graph Snapshot Generator

Captures a high-resolution PNG of the entire Open Brain memory graph.
Designed to run daily to track memory growth over time.

Usage:
    uv run scripts/discovery/memory_snapshot.py
    uv run scripts/discovery/memory_snapshot.py --output data/memory-snapshots/2026-03-16.png
"""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from playwright.sync_api import sync_playwright


# Configuration
BRAIN_DB_PATH = Path(__file__).parent.parent.parent.parent / "ai-memory" / "brain.db"
SNAPSHOT_DIR = Path(__file__).parent.parent.parent / "data" / "memory-snapshots"
SIMILARITY_THRESHOLD = 0.3  # Only show edges with similarity > 30%
MAX_EDGES_PER_NODE = 10  # Limit edges to prevent visual clutter


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def load_memory_graph() -> Dict[str, Any]:
    """Load thoughts from brain.db and calculate similarity edges."""
    print(f"📖 Reading memory database: {BRAIN_DB_PATH}")
    
    if not BRAIN_DB_PATH.exists():
        raise FileNotFoundError(f"Brain database not found: {BRAIN_DB_PATH}")
    
    conn = sqlite3.connect(BRAIN_DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Load all thoughts with embeddings
    rows = conn.execute(
        "SELECT id, content, embedding, metadata, created_at FROM thoughts WHERE embedding IS NOT NULL"
    ).fetchall()
    
    conn.close()
    
    print(f"   Found {len(rows)} thoughts with embeddings")
    
    # Build nodes
    nodes = []
    embeddings = []
    
    for row in rows:
        metadata = json.loads(row["metadata"]) if row["metadata"] else {}
        embedding = json.loads(row["embedding"])
        
        nodes.append({
            "id": row["id"],
            "content": row["content"][:80],  # Truncate for display
            "type": metadata.get("type", "observation"),
            "project": metadata.get("project", ""),
            "created_at": row["created_at"],
        })
        embeddings.append(embedding)
    
    # Calculate similarity edges
    print(f"🔗 Calculating similarity edges (threshold: {SIMILARITY_THRESHOLD})...")
    edges = []
    
    for i, node_i in enumerate(nodes):
        similarities = []
        
        for j, node_j in enumerate(nodes):
            if i >= j:  # Skip self and duplicates
                continue
            
            sim = cosine_similarity(embeddings[i], embeddings[j])
            if sim > SIMILARITY_THRESHOLD:
                similarities.append((j, sim))
        
        # Keep only top N most similar
        similarities.sort(key=lambda x: x[1], reverse=True)
        for j, sim in similarities[:MAX_EDGES_PER_NODE]:
            edges.append({
                "source": node_i["id"],
                "target": nodes[j]["id"],
                "similarity": round(sim, 3)
            })
    
    print(f"   Created {len(edges)} edges")
    
    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "total_thoughts": len(nodes),
            "total_edges": len(edges),
            "snapshot_date": datetime.now().isoformat()
        }
    }


def generate_html(graph_data: Dict[str, Any]) -> str:
    """Generate standalone HTML page with D3.js visualization."""
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Open Brain Memory Graph</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        body {{ margin: 0; padding: 20px; background: #0a0a0a; font-family: monospace; }}
        #graph {{ width: 100vw; height: 100vh; background: #0a0a0a; }}
        .node {{ cursor: pointer; }}
        .node circle {{ stroke: #fff; stroke-width: 1.5px; }}
        .link {{ stroke: #666; stroke-opacity: 0.6; }}
        .node text {{ fill: #fff; font-size: 10px; pointer-events: none; }}
        #stats {{ position: absolute; top: 20px; left: 20px; color: #fff; background: rgba(0,0,0,0.7); padding: 10px; border-radius: 5px; }}
    </style>
</head>
<body>
    <div id="stats">
        <div>Thoughts: {graph_data['stats']['total_thoughts']}</div>
        <div>Connections: {graph_data['stats']['total_edges']}</div>
        <div>Date: {graph_data['stats']['snapshot_date'][:10]}</div>
    </div>
    <svg id="graph"></svg>
    <script>
        const data = {json.dumps(graph_data)};
        
        const width = window.innerWidth;
        const height = window.innerHeight;
        
        const svg = d3.select('#graph')
            .attr('width', width)
            .attr('height', height);
        
        const container = svg.append('g');
        
        // Type colors
        const typeColors = {{
            'observation': '#4ECDC4',
            'decision': '#FF6B6B',
            'idea': '#FFD93D',
            'question': '#A8E6CF',
            'default': '#999999'
        }};
        
        // Create simulation with stronger forces for better visibility
        const simulation = d3.forceSimulation(data.nodes)
            .force('link', d3.forceLink(data.edges).id(d => d.id).distance(300))
            .force('charge', d3.forceManyBody().strength(-1000))
            .force('center', d3.forceCenter(width / 2, height / 2))
            .force('collision', d3.forceCollide().radius(80));

        // Draw edges (thicker and more visible)
        const link = container.append('g')
            .selectAll('line')
            .data(data.edges)
            .join('line')
            .attr('class', 'link')
            .attr('stroke', '#999')
            .attr('stroke-width', d => Math.max(2, d.similarity * 8));

        // Draw nodes (MUCH bigger)
        const node = container.append('g')
            .selectAll('g')
            .data(data.nodes)
            .join('g')
            .attr('class', 'node');

        node.append('circle')
            .attr('r', 40)
            .attr('fill', d => typeColors[d.type] || typeColors.default);

        node.append('text')
            .attr('dx', 50)
            .attr('dy', 8)
            .attr('font-size', '24px')
            .text(d => d.content.substring(0, 60));
        
        // Setup zoom behavior
        const zoom = d3.zoom()
            .scaleExtent([0.01, 20])
            .on('zoom', (event) => {{
                container.attr('transform', event.transform);
            }});

        svg.call(zoom);

        // Update positions on tick
        simulation.on('tick', () => {{
            link
                .attr('x1', d => d.source.x)
                .attr('y1', d => d.source.y)
                .attr('x2', d => d.target.x)
                .attr('y2', d => d.target.y);

            node.attr('transform', d => `translate(${{d.x}},${{d.y}})`);
        }});

        // Auto-fit to screen after simulation stabilizes
        simulation.on('end', () => {{
            console.log('Simulation stabilized, fitting to screen...');
            fitToScreen();
        }});

        function fitToScreen() {{
            if (data.nodes.length === 0) return;

            const bounds = container.node().getBBox();
            const fullWidth = width;
            const fullHeight = height;
            const graphWidth = bounds.width;
            const graphHeight = bounds.height;
            const midX = bounds.x + graphWidth / 2;
            const midY = bounds.y + graphHeight / 2;

            if (graphWidth === 0 || graphHeight === 0) return;

            // Scale to 90% of viewport (leave 10% padding)
            const scale = 0.9 / Math.max(graphWidth / fullWidth, graphHeight / fullHeight);
            const translate = [fullWidth / 2 - scale * midX, fullHeight / 2 - scale * midY];

            svg.call(
                zoom.transform,
                d3.zoomIdentity.translate(translate[0], translate[1]).scale(scale)
            );
        }}
    </script>
</body>
</html>"""


def capture_snapshot(html_content: str, output_path: Path):
    """Use Playwright to capture high-res PNG of the graph."""
    print(f"📸 Capturing snapshot...")
    
    # Create temporary HTML file
    temp_html = output_path.parent / "temp_memory_graph.html"
    temp_html.write_text(html_content)
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 3840, "height": 2160})  # 4K resolution
        
        page.goto(f"file://{temp_html.absolute()}")
        
        # Wait for D3 to finish rendering
        page.wait_for_timeout(5000)  # 5 seconds for simulation to settle
        
        # Take screenshot
        page.screenshot(path=str(output_path), full_page=True)
        
        browser.close()
    
    # Clean up temp file
    temp_html.unlink()
    
    print(f"✅ Snapshot saved: {output_path}")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Capture Open Brain memory graph snapshot")
    parser.add_argument("--output", type=Path, help="Output PNG path (default: data/memory-snapshots/YYYY-MM-DD.png)")
    args = parser.parse_args()
    
    # Determine output path
    if args.output:
        output_path = args.output
    else:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        output_path = SNAPSHOT_DIR / f"{today}.png"
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"\n🧠 Open Brain Memory Graph Snapshot")
    print(f"{'=' * 50}\n")
    
    # Load graph data
    graph_data = load_memory_graph()
    
    # Generate HTML
    html_content = generate_html(graph_data)
    
    # Capture snapshot
    capture_snapshot(html_content, output_path)
    
    print(f"\n{'=' * 50}")
    print(f"📊 Stats: {graph_data['stats']['total_thoughts']} thoughts, {graph_data['stats']['total_edges']} connections")
    print(f"📁 Saved to: {output_path}")
    print(f"{'=' * 50}\n")


if __name__ == "__main__":
    main()

