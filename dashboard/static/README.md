# Dashboard Static Assets — Memory Graph Renderers

This directory contains the JavaScript renderers for the Open Brain memory visualization page (`/memory`). There are multiple renderers sharing a single HTML page, which creates global scope collisions if you're not careful.

## Architecture

All scripts load into the same global scope via `<script>` tags in `memory.html`. There is NO module system — every `function` and `const` at the top level is global. **If two files define the same function name, the last one loaded wins.**

### Files and Load Order

```
memory.html          → Page template, tab buttons, view containers
memory.js            → Graph view (Canvas 2D + d3-force) — loads FIRST
memory_svg.js        → Classic view (SVG + d3-force)
memory_list.js       → List view (table) + switchView() + refreshData()
memory_heatmap.js    → Heatmap view
memory_overlay.js    → Overlay view (Open Brain from graph_nodes/graph_edges)
memory.css           → All styles for the memory page
```

### Global Scope Rules

**CRITICAL:** Each renderer MUST namespace its functions to avoid collisions.

| Renderer | Prefix | Example |
|----------|--------|---------|
| memory.js (Graph) | none (legacy, owns the base names) | `nodeColor()`, `nodeRadius()`, `drawFrame()` |
| memory_svg.js | `svg` or scoped in IIFE | `svgNodeColor()`, `SVG_TYPE_COLORS` |
| memory_overlay.js | `overlay` | `overlayNodeColor()`, `overlayNodeRadius()` |
| memory_list.js | `list` or unique names | `switchView()`, `loadThoughts()` |
| memory_heatmap.js | `heatmap` or unique names | `loadHeatmap()` |

**2026-04-05 bug:** `memory_overlay.js` defined `nodeColor()` and `nodeRadius()` which overwrote the Graph view's versions. Every node rendered gray because the overlay's color map uses Open Brain types (project, artifact, concept) not memory types (observation, conversation, decision). Fix: renamed to `overlayNodeColor()` / `overlayNodeRadius()`.

### Shared Elements

These HTML elements are shared across renderers — be careful not to overwrite another renderer's content:

- `#memory-stats` — Stats display in sidebar. Graph view writes here; overlay should NOT.
- `#memory-legend` — Type/machine legend in sidebar. Built by `buildLegend()` in memory.js. Overlay has its own legend in `#overlay-status`.
- `#memory-controls` — Filter sidebar. Only visible for Graph and Classic views.

## Color Systems

### Memory Types (Graph + Classic + List views)

Defined in `memory.js` as `TYPE_COLORS` and in `memory_svg.js` as `SVG_TYPE_COLORS`. These map memory template types from brain.db's `thoughts` table.

```
observation      → #4ECDC4 (teal)
decision         → #FF6B6B (coral red)
idea             → #FFD93D (yellow)
question         → #A8E6CF (mint green)
conversation     → #B39DDB (lavender purple)
meeting_debrief  → #F48FB1 (pink)
fact             → #80CBC4 (soft teal)
project          → #FFB74D (orange)
insight          → #AED581 (lime green)
person_note      → #F97583 (salmon)
loop_state       → #CE93D8 (medium purple)
dream            → #E1BEE7 (light purple)
default          → #8b949e (gray)
```

**When new memory template types are added in ai-memory**, both `TYPE_COLORS` (memory.js) and `SVG_TYPE_COLORS` (memory_svg.js) must be updated, or the new types will render as gray.

### Open Brain Types (Overlay view)

Defined in `memory_overlay.js` as `NODE_COLORS`. These map Open Brain node types from brain.db's `graph_nodes` table.

```
project   → #58a6ff (blue)
person    → #f97583 (pink-red)
artifact  → #3fb950 (green)
concept   → #d2a8ff (purple)
task      → #f0883e (orange)
decision  → #56d364 (bright green)
tag       → #8b949e (gray)
```

These are completely separate from the memory type colors above.

## Canvas Rendering (Graph View)

### Retina / HiDPI

The Canvas renderer must account for `window.devicePixelRatio` (DPR). On retina Macs (DPR=2), failing to scale the canvas buffer causes blurry, washed-out rendering. SVG doesn't have this problem.

The `resizeCanvas()` function should:
1. Set `canvas.width = clientWidth * dpr` and `canvas.height = clientHeight * dpr`
2. Set `canvas.style.width` and `canvas.style.height` to CSS pixels
3. Apply `ctx.scale(dpr, dpr)` in the draw loop

### Edge Opacity

With 4000+ edges, even slightly opaque edges create a dense mesh that drowns node colors. Current baseline: `rgba(120,120,120,0.35)` for non-highlighted edges. Going higher makes the graph look like a gray blob.

### Node Visibility at Small Scales

At zoomed-out scales, nodes are tiny (3-5px radius). Options for making type colors visible:
- Colored `shadowBlur` glow behind each node
- Remove white stroke on non-interactive nodes (only show on hover/select)
- Increase minimum node radius

## API Endpoints

| Endpoint | Source DB | Used By |
|----------|----------|---------|
| `/api/memory-graph` | brain.db `thoughts` table | Graph, Classic, Heatmap, List |
| `/api/memory/types` | brain.db `thoughts` table | Legend builder |
| `/api/open-brain` | brain.db `graph_nodes` + `graph_edges` | Overlay |

## Data Flow

```
brain.db (thoughts)     → /api/memory-graph  → memory.js (Canvas)
                                              → memory_svg.js (SVG)
                                              → memory_list.js (Table)
                                              → memory_heatmap.js (Heatmap)

brain.db (graph_nodes)  → /api/open-brain      → memory_overlay.js (Canvas)
```

## Adding a New View

1. Create `memory_newview.js` with namespaced functions (prefix all globals)
2. Add a `<div id="memory-newview-view" class="view-content hidden">` container in `memory.html`
3. Add a tab button: `<button onclick="switchView('newview')" id="tab-newview" class="tab-btn">Label</button>`
4. Update `switchView()` in `memory_list.js` — add the view div, tab, and show/hide logic
5. Add `<script src="/static/memory_newview.js"></script>` in the scripts block
6. Add CSS in `memory.css`
7. **Test that existing views still work** — check `nodeColor()` in the console to make sure your file didn't overwrite it
