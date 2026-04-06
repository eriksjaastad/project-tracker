// Code Graph Overlay — Open Brain renderer
// Renders the Open Brain graph from brain.db: typed nodes + weighted edges.
// Uses d3-force for layout, Canvas 2D for rendering.

let overlayCanvas, overlayCtx;
let overlayLoaded = false;
let overlayData = { nodes: [], edges: [] };
let overlaySimulation = null;
let overlayTransform = { x: 0, y: 0, k: 1 };
let overlayHovered = null;
let overlayPanning = false;
let overlayPanStart = { x: 0, y: 0 };
let overlayRafId = null;

// Node colors by type
const NODE_COLORS = {
    project:  '#58a6ff',  // blue
    person:   '#f97583',  // pink-red
    artifact: '#3fb950',  // green
    concept:  '#d2a8ff',  // purple
    task:     '#f0883e',  // orange
    decision: '#56d364',  // bright green
    tag:      '#8b949e',  // gray
};

const NODE_LABELS = {
    project: 'Projects',
    person: 'People',
    artifact: 'Files',
    concept: 'Concepts',
    task: 'Tasks',
    decision: 'Decisions',
    tag: 'Tags',
};

function overlayNodeColor(type) {
    return NODE_COLORS[type] || '#8b949e';
}

function overlayNodeRadius(node) {
    const s = node.size || 1;
    if (s > 100) return 12;
    if (s > 20) return 8;
    if (s > 5) return 5;
    return 3;
}

async function loadOverlay() {
    overlayCanvas = document.getElementById('overlay-canvas');
    if (!overlayCanvas) return;

    overlayCtx = overlayCanvas.getContext('2d');

    const container = document.getElementById('overlay-container');
    // Use the visible viewport height minus header
    overlayCanvas.width = container.clientWidth || window.innerWidth;
    overlayCanvas.height = container.clientHeight || (window.innerHeight - 120);

    // Hide the placeholder status text
    const status = document.getElementById('overlay-status');
    if (status) status.style.display = 'none';

    if (overlayLoaded && overlayData.nodes.length > 0) {
        renderOverlay();
        return;
    }

    // Fetch Open Brain graph
    try {
        const resp = await fetch('/api/open-brain');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        overlayData = await resp.json();
    } catch (e) {
        if (status) {
            status.style.display = 'block';
            document.getElementById('overlay-waiting').textContent = `Error loading Open Brain graph: ${e.message}`;
        }
        return;
    }

    if (!overlayData.nodes || overlayData.nodes.length === 0) {
        if (status) {
            status.style.display = 'block';
            document.getElementById('overlay-waiting').textContent = 'Open Brain graph is empty. Run: brain.py graph build';
        }
        return;
    }

    // Build node lookup for edge resolution
    const nodeMap = new Map();
    overlayData.nodes.forEach(n => nodeMap.set(n.id, n));

    // Filter edges to only those with valid source/target
    overlayData.edges = overlayData.edges.filter(e => nodeMap.has(e.source) && nodeMap.has(e.target));

    // Update overlay stats
    updateOverlayStats();

    // Run d3 force layout
    const w = overlayCanvas.width;
    const h = overlayCanvas.height;

    overlaySimulation = d3.forceSimulation(overlayData.nodes)
        .force('link', d3.forceLink(overlayData.edges)
            .id(d => d.id)
            .distance(d => d.weight > 2 ? 30 : 60)
            .strength(d => Math.min(d.weight * 0.1, 0.5))
        )
        .force('charge', d3.forceManyBody()
            .strength(d => -overlayNodeRadius(d) * 8)
            .distanceMax(300)
        )
        .force('center', d3.forceCenter(w / 2, h / 2))
        .force('collision', d3.forceCollide(d => overlayNodeRadius(d) + 2))
        .alphaDecay(0.02)
        .on('tick', renderOverlay);

    setupOverlayInteraction();
    overlayLoaded = true;
}

function updateOverlayStats() {
    // Update the overlay's own status area, NOT the shared sidebar
    const statusEl = document.getElementById('overlay-status');
    if (!statusEl) return;
    const stats = overlayData.stats || {};
    const typeCounts = {};
    overlayData.nodes.forEach(n => {
        typeCounts[n.type] = (typeCounts[n.type] || 0) + 1;
    });

    statusEl.style.display = 'block';
    statusEl.style.position = 'fixed';
    statusEl.style.bottom = '20px';
    statusEl.style.left = '20px';
    statusEl.style.top = 'auto';
    statusEl.style.transform = 'none';
    statusEl.style.textAlign = 'left';
    statusEl.style.fontSize = '12px';
    statusEl.style.maxWidth = '300px';
    statusEl.style.background = 'rgba(0,0,0,0.7)';
    statusEl.style.padding = '12px';
    statusEl.style.borderRadius = '8px';

    statusEl.innerHTML = `
        <div><strong>Open Brain</strong></div>
        <div>Nodes: ${stats.total_nodes || overlayData.nodes.length} | Edges: ${stats.total_edges || overlayData.edges.length}</div>
        <div style="margin-top:6px">${Object.entries(NODE_COLORS)
            .filter(([type]) => typeCounts[type])
            .map(([type, color]) => `<span style="color:${color}">● ${NODE_LABELS[type] || type} (${typeCounts[type]})</span>`)
            .join(' ')}</div>
    `;
}

function renderOverlay() {
    if (!overlayCtx) return;
    const w = overlayCanvas.width;
    const h = overlayCanvas.height;
    const ctx = overlayCtx;
    const t = overlayTransform;

    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = '#0d1117';
    ctx.fillRect(0, 0, w, h);

    ctx.save();
    ctx.translate(t.x, t.y);
    ctx.scale(t.k, t.k);

    // Build highlight set on hover
    let highlightedIds = null;
    if (overlayHovered) {
        highlightedIds = new Set([overlayHovered.id]);
        overlayData.edges.forEach(e => {
            const sid = e.source.id ?? e.source;
            const tid = e.target.id ?? e.target;
            if (sid === overlayHovered.id) highlightedIds.add(tid);
            if (tid === overlayHovered.id) highlightedIds.add(sid);
        });
    }

    // Draw edges
    overlayData.edges.forEach(e => {
        const src = e.source;
        const tgt = e.target;
        if (src.x == null || tgt.x == null) return;

        const sid = src.id ?? src;
        const tid = tgt.id ?? tgt;
        const isHighlighted = overlayHovered &&
            (sid === overlayHovered.id || tid === overlayHovered.id);
        const dimmed = highlightedIds && !isHighlighted;

        ctx.beginPath();
        ctx.moveTo(src.x, src.y);
        ctx.lineTo(tgt.x, tgt.y);

        if (isHighlighted) {
            ctx.strokeStyle = 'rgba(78, 205, 196, 0.85)';
            ctx.lineWidth = 2;
        } else {
            ctx.strokeStyle = 'rgba(160, 160, 160, 0.4)';
            ctx.lineWidth = Math.min(e.weight * 0.5, 2);
        }
        ctx.globalAlpha = dimmed ? 0.08 : 1;
        ctx.stroke();
        ctx.globalAlpha = 1;
    });

    // Draw nodes
    overlayData.nodes.forEach(n => {
        if (n.x == null) return;
        const r = overlayNodeRadius(n);
        const color = overlayNodeColor(n.type);
        const isDimmed = highlightedIds && !highlightedIds.has(n.id);
        const isHovered = n === overlayHovered;

        ctx.globalAlpha = isDimmed ? 0.15 : 1;

        ctx.beginPath();
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();

        if (isHovered) {
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = 2;
            ctx.stroke();
        }

        // Labels for large nodes or on hover
        if ((n.size > 20 || isHovered) && t.k > 0.4) {
            ctx.fillStyle = isDimmed ? 'rgba(200,200,200,0.3)' : 'rgba(230,230,230,0.9)';
            ctx.font = isHovered ? 'bold 11px system-ui' : '9px system-ui';
            ctx.textAlign = 'center';
            ctx.fillText(n.name, n.x, n.y - r - 3);
        }

        ctx.globalAlpha = 1;
    });

    ctx.restore();

    // Draw tooltip on hover
    if (overlayHovered) {
        const sx = overlayHovered.x * t.k + t.x;
        const sy = overlayHovered.y * t.k + t.y;
        const label = `${overlayHovered.name} (${overlayHovered.type}, ${overlayHovered.size} refs)`;
        ctx.font = '12px system-ui';
        const tw = ctx.measureText(label).width;
        ctx.fillStyle = 'rgba(0,0,0,0.8)';
        ctx.fillRect(sx - tw/2 - 6, sy - 30, tw + 12, 20);
        ctx.fillStyle = '#eee';
        ctx.textAlign = 'center';
        ctx.fillText(label, sx, sy - 16);
    }
}

function setupOverlayInteraction() {
    if (!overlayCanvas) return;

    overlayCanvas.addEventListener('mousemove', e => {
        const rect = overlayCanvas.getBoundingClientRect();
        const mx = (e.clientX - rect.left - overlayTransform.x) / overlayTransform.k;
        const my = (e.clientY - rect.top - overlayTransform.y) / overlayTransform.k;

        if (overlayPanning) {
            overlayTransform.x += e.clientX - overlayPanStart.x;
            overlayTransform.y += e.clientY - overlayPanStart.y;
            overlayPanStart = { x: e.clientX, y: e.clientY };
            renderOverlay();
            return;
        }

        let found = null;
        for (const n of overlayData.nodes) {
            if (n.x == null) continue;
            const dx = mx - n.x;
            const dy = my - n.y;
            if (dx * dx + dy * dy < (overlayNodeRadius(n) + 4) ** 2) {
                found = n;
                break;
            }
        }
        if (found !== overlayHovered) {
            overlayHovered = found;
            overlayCanvas.style.cursor = found ? 'pointer' : 'default';
            renderOverlay();
        }
    });

    overlayCanvas.addEventListener('mousedown', e => {
        overlayPanning = true;
        overlayPanStart = { x: e.clientX, y: e.clientY };
        overlayCanvas.style.cursor = 'grabbing';
    });

    overlayCanvas.addEventListener('mouseup', () => {
        overlayPanning = false;
        overlayCanvas.style.cursor = overlayHovered ? 'pointer' : 'default';
    });

    overlayCanvas.addEventListener('mouseleave', () => {
        overlayPanning = false;
        overlayHovered = null;
        renderOverlay();
    });

    overlayCanvas.addEventListener('wheel', e => {
        e.preventDefault();
        const rect = overlayCanvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const delta = e.deltaY > 0 ? 0.95 : 1.05;
        const newK = Math.max(0.1, Math.min(5, overlayTransform.k * delta));

        overlayTransform.x = mx - (mx - overlayTransform.x) * (newK / overlayTransform.k);
        overlayTransform.y = my - (my - overlayTransform.y) * (newK / overlayTransform.k);
        overlayTransform.k = newK;
        renderOverlay();
    }, { passive: false });
}
