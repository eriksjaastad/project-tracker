// Code Graph Overlay — Open Brain renderer
// Renders the Open Brain graph from brain.db: typed nodes + weighted edges.
// Uses d3-force for layout, Canvas 2D for rendering.

let overlayCanvas, overlayCtx;
let overlayLoaded = false;
let overlayData = { nodes: [], edges: [] };
let overlaySimulation = null;
let overlayTransform = { x: 0, y: 0, k: 1 };
let overlayHovered = null;
let overlaySelected = null;
let overlayPanning = false;
let overlayPanStart = { x: 0, y: 0 };
let overlayPanMoved = false;
let overlayRafId = null;
let overlayShowLabels = false;

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

function getOverlayMinMentions() {
    const slider = document.getElementById('overlay-min-mentions');
    if (!slider) return 1;
    // Restore from localStorage on first call
    const saved = localStorage.getItem('overlay-min-mentions');
    if (saved && !slider.dataset.restored) {
        slider.value = saved;
        slider.dataset.restored = '1';
        const valEl = document.getElementById('overlay-min-mentions-val');
        if (valEl) valEl.textContent = saved;
    }
    return parseInt(slider.value, 10);
}

async function loadOverlay(forceReload = false) {
    overlayCanvas = document.getElementById('overlay-canvas');
    if (!overlayCanvas) return;

    overlayCtx = overlayCanvas.getContext('2d');

    const container = document.getElementById('overlay-container');
    overlayCanvas.width = container.clientWidth || window.innerWidth;
    overlayCanvas.height = container.clientHeight || (window.innerHeight - 120);

    const status = document.getElementById('overlay-status');
    if (status) status.style.display = 'none';

    if (overlayLoaded && overlayData.nodes.length > 0 && !forceReload) {
        renderOverlay();
        return;
    }

    // Set up min-mentions slider listener (once)
    const slider = document.getElementById('overlay-min-mentions');
    if (slider && !slider.dataset.bound) {
        slider.dataset.bound = '1';
        slider.addEventListener('input', e => {
            document.getElementById('overlay-min-mentions-val').textContent = e.target.value;
        });
        slider.addEventListener('change', () => {
            localStorage.setItem('overlay-min-mentions', slider.value);
            overlayLoaded = false;
            if (overlaySimulation) overlaySimulation.stop();
            loadOverlay(true);
        });
    }

    // Fetch Open Brain graph with min_mentions filter
    const minMentions = getOverlayMinMentions();
    try {
        const resp = await fetch(`/api/open-brain?min_mentions=${minMentions}`);
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

    // Labels toggle
    const labelsToggle = document.getElementById('overlay-labels-toggle');
    if (labelsToggle && !labelsToggle.dataset.bound) {
        labelsToggle.dataset.bound = '1';
        labelsToggle.addEventListener('change', () => {
            overlayShowLabels = labelsToggle.checked;
            renderOverlay();
        });
    }

    // Reset view button
    const resetBtn = document.getElementById('overlay-reset-view');
    if (resetBtn && !resetBtn.dataset.bound) {
        resetBtn.dataset.bound = '1';
        resetBtn.addEventListener('click', () => {
            overlayTransform = { x: 0, y: 0, k: 1 };
            renderOverlay();
        });
    }

    overlayLoaded = true;
}

function updateOverlayStats() {
    const stats = overlayData.stats || {};
    const typeCounts = {};
    overlayData.nodes.forEach(n => {
        typeCounts[n.type] = (typeCounts[n.type] || 0) + 1;
    });

    // Populate sidebar legend
    const legendEl = document.getElementById('overlay-legend');
    if (legendEl) {
        legendEl.innerHTML = '<h4>Legend</h4>' + Object.entries(NODE_COLORS)
            .filter(([type]) => typeCounts[type])
            .map(([type, color]) => `<div class="legend-item"><span class="legend-color" style="background:${color}"></span>${NODE_LABELS[type] || type} (${typeCounts[type]})</div>`)
            .join('');
    }

    // Populate sidebar stats
    const statsEl = document.getElementById('overlay-stats');
    if (statsEl) {
        statsEl.innerHTML = `<strong>${stats.total_nodes || overlayData.nodes.length}</strong> nodes · <strong>${stats.total_edges || overlayData.edges.length}</strong> edges`;
    }
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

        if (isHovered || n === overlaySelected) {
            ctx.strokeStyle = n === overlaySelected ? '#007bff' : '#fff';
            ctx.lineWidth = 2;
            ctx.stroke();
        }

        // Draw label
        if (overlayShowLabels && !isDimmed && r >= 5) {
            ctx.font = '10px system-ui';
            ctx.fillStyle = '#ccc';
            ctx.textAlign = 'center';
            ctx.globalAlpha = isDimmed ? 0.15 : 0.9;
            ctx.fillText(n.name, n.x, n.y + r + 12);
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
            const dx = e.clientX - overlayPanStart.x;
            const dy = e.clientY - overlayPanStart.y;
            if (Math.abs(dx) > 3 || Math.abs(dy) > 3) overlayPanMoved = true;
            overlayTransform.x += dx;
            overlayTransform.y += dy;
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
        overlayPanMoved = false;
    });

    overlayCanvas.addEventListener('mouseup', e => {
        const wasPanning = overlayPanMoved;
        overlayPanning = false;
        overlayCanvas.style.cursor = overlayHovered ? 'pointer' : 'default';

        // Click handler — only fire if we didn't drag
        if (!wasPanning && overlayHovered) {
            overlaySelected = overlayHovered;
            showOverlayDetail(overlaySelected);
            renderOverlay();
        } else if (!wasPanning && !overlayHovered) {
            closeOverlayDetail();
        }
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

function showOverlayDetail(node) {
    const panel = document.getElementById('overlay-detail-panel');
    const nameEl = document.getElementById('overlay-detail-name');
    const contentEl = document.getElementById('overlay-detail-content');
    if (!panel || !node) return;

    // Find connected nodes
    const connections = [];
    overlayData.edges.forEach(e => {
        const sid = e.source.id ?? e.source;
        const tid = e.target.id ?? e.target;
        if (sid === node.id) {
            const target = overlayData.nodes.find(n => n.id === tid);
            if (target) connections.push({ node: target, edge_type: e.edge_type || e.type || 'related', weight: e.weight || 1 });
        } else if (tid === node.id) {
            const source = overlayData.nodes.find(n => n.id === sid);
            if (source) connections.push({ node: source, edge_type: e.edge_type || e.type || 'related', weight: e.weight || 1 });
        }
    });

    // Sort by weight descending
    connections.sort((a, b) => b.weight - a.weight);

    // Group connections by type
    const byType = {};
    connections.forEach(c => {
        const type = c.node.type || 'other';
        if (!byType[type]) byType[type] = [];
        byType[type].push(c);
    });

    nameEl.textContent = node.name;
    nameEl.style.color = overlayNodeColor(node.type);

    let html = `<div class="overlay-detail-meta">`;
    html += `<strong>Type:</strong> ${NODE_LABELS[node.type] || node.type}<br>`;
    html += `<strong>References:</strong> ${node.size || 0}<br>`;
    html += `<strong>Connections:</strong> ${connections.length}`;
    html += `</div>`;

    html += `<div class="overlay-detail-connections">`;
    for (const [type, conns] of Object.entries(byType)) {
        const label = NODE_LABELS[type] || type;
        const color = overlayNodeColor(type);
        html += `<h4 style="color:${color}">● ${label} (${conns.length})</h4><ul>`;
        conns.slice(0, 20).forEach(c => {
            html += `<li data-node-id="${c.node.id}">${c.node.name}<span class="conn-type">${c.edge_type} ×${c.weight}</span></li>`;
        });
        if (conns.length > 20) html += `<li style="color:#666">...and ${conns.length - 20} more</li>`;
        html += `</ul>`;
    }
    html += `</div>`;

    contentEl.innerHTML = html;
    panel.classList.remove('hidden');

    // Click on connection to navigate to that node
    contentEl.querySelectorAll('li[data-node-id]').forEach(li => {
        li.addEventListener('click', () => {
            const targetNode = overlayData.nodes.find(n => n.id === li.dataset.nodeId);
            if (targetNode) {
                overlaySelected = targetNode;
                showOverlayDetail(targetNode);
                renderOverlay();
            }
        });
    });
}

function closeOverlayDetail() {
    const panel = document.getElementById('overlay-detail-panel');
    if (panel) panel.classList.add('hidden');
    overlaySelected = null;
    renderOverlay();
}
