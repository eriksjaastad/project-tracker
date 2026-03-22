// D3.js Memory Graph Visualization

let width, height;
let svg, container, simulation;
let memoryData = { nodes: [], edges: [] };
let currentFilters = {
    thoughtType: '',
    minSimilarity: 0.3,
    maxEdges: 10
};

const TYPE_COLORS = {
    observation: '#4ECDC4',
    decision: '#FF6B6B',
    idea: '#FFD93D',
    question: '#A8E6CF',
    default: '#999999'
};

document.addEventListener('DOMContentLoaded', () => {
    const svgElement = document.getElementById('memory-svg');
    width = svgElement.clientWidth || window.innerWidth - 280;
    height = svgElement.clientHeight || window.innerHeight - 80;
    
    svg = d3.select('#memory-svg');
    container = svg.append('g');
    
    // Setup zoom
    const zoom = d3.zoom()
        .scaleExtent([0.1, 10])
        .on('zoom', (event) => {
            container.attr('transform', event.transform);
        });
    
    svg.call(zoom);
    
    // Initial load
    loadMemoryGraph();
    
    // Event listeners
    document.getElementById('type-filter').addEventListener('change', applyFilters);
    document.getElementById('min-similarity').addEventListener('input', (e) => {
        const val = parseInt(e.target.value) / 100;
        document.getElementById('min-similarity-val').textContent = val.toFixed(2);
        currentFilters.minSimilarity = val;
        applyFilters();
    });
    document.getElementById('max-edges').addEventListener('input', (e) => {
        document.getElementById('max-edges-val').textContent = e.target.value;
        currentFilters.maxEdges = parseInt(e.target.value);
        applyFilters();
    });
    document.getElementById('labels-toggle').addEventListener('change', () => {
        const showLabels = document.getElementById('labels-toggle').checked;
        container.selectAll('.node text').style('display', showLabels ? 'block' : 'none');
    });
    document.getElementById('reset-view').addEventListener('click', () => {
        fitToScreen();
    });
    
    // Resize listener
    window.addEventListener('resize', () => {
        width = svgElement.clientWidth;
        height = svgElement.clientHeight;
        if (simulation) {
            simulation.force('center', d3.forceCenter(width / 2, height / 2));
            simulation.alpha(0.3).restart();
        }
    });
});

async function loadMemoryGraph() {
    showLoading(true);
    try {
        const params = new URLSearchParams({
            thought_type: currentFilters.thoughtType,
            min_similarity: currentFilters.minSimilarity,
            max_edges_per_node: currentFilters.maxEdges
        });
        
        const response = await fetch(`/api/memory-graph?${params}`);
        memoryData = await response.json();
        
        if (memoryData.error) {
            alert(`Error: ${memoryData.error}`);
            showLoading(false);
            return;
        }
        
        updateStats();
        renderGraph();
        showLoading(false);
    } catch (err) {
        console.error('Error loading memory graph:', err);
        alert('Failed to load memory graph');
        showLoading(false);
    }
}

function applyFilters() {
    currentFilters.thoughtType = document.getElementById('type-filter').value;
    loadMemoryGraph();
}

function updateStats() {
    const stats = memoryData.stats || {};
    const statsHtml = `
        <div><strong>Total Thoughts:</strong> ${stats.total_thoughts || 0}</div>
        <div><strong>Connections:</strong> ${stats.total_connections || 0}</div>
        <div><strong>Avg Connections:</strong> ${stats.avg_connections || 0}</div>
    `;
    document.getElementById('memory-stats').innerHTML = statsHtml;
}

function renderGraph() {
    // Clear existing
    container.selectAll('*').remove();
    
    if (!memoryData.nodes || memoryData.nodes.length === 0) {
        console.warn('No thoughts to display');
        return;
    }
    
    // Create deep copies for D3
    const d3Nodes = memoryData.nodes.map(d => ({...d}));
    const d3Edges = memoryData.edges.map(d => ({...d}));
    
    // Create simulation
    simulation = d3.forceSimulation(d3Nodes)
        .force('link', d3.forceLink(d3Edges).id(d => d.id).distance(200))
        .force('charge', d3.forceManyBody().strength(-500))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide().radius(50));
    
    // Set initial positions
    d3Nodes.forEach(n => {
        n.x = width / 2 + (Math.random() - 0.5) * 200;
        n.y = height / 2 + (Math.random() - 0.5) * 200;
    });
    
    // Draw edges
    const link = container.append('g')
        .selectAll('line')
        .data(d3Edges)
        .enter().append('line')
        .attr('class', 'link')
        .attr('stroke-width', d => d.similarity * 3);
    
    // Draw nodes
    const node = container.append('g')
        .selectAll('g')
        .data(d3Nodes)
        .enter().append('g')
        .attr('class', 'node')
        .call(d3.drag()
            .on('start', dragstarted)
            .on('drag', dragged)
            .on('end', dragended))
        .on('click', (event, d) => showDetails(d))
        .on('mouseover', (event, d) => highlightNode(d, true))
        .on('mouseout', (event, d) => highlightNode(d, false));

    node.append('circle')
        .attr('r', d => Math.max(20, 10 + d.size * 2))
        .attr('fill', d => TYPE_COLORS[d.type] || TYPE_COLORS.default);

    const showLabels = document.getElementById('labels-toggle').checked;
    node.append('text')
        .attr('dx', d => Math.max(20, 10 + d.size * 2) + 5)
        .attr('dy', 4)
        .text(d => d.content.substring(0, 50))
        .style('display', showLabels ? 'block' : 'none');

    // Update positions on tick
    simulation.on('tick', () => {
        link
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);

        node.attr('transform', d => `translate(${d.x},${d.y})`);
    });

    // Auto-fit after simulation stabilizes
    simulation.on('end', () => {
        fitToScreen();
    });
}

function fitToScreen() {
    if (!memoryData.nodes || memoryData.nodes.length === 0) return;

    const bounds = container.node().getBBox();
    const fullWidth = width;
    const fullHeight = height;
    const graphWidth = bounds.width;
    const graphHeight = bounds.height;
    const midX = bounds.x + graphWidth / 2;
    const midY = bounds.y + graphHeight / 2;

    if (graphWidth === 0 || graphHeight === 0) return;

    const scale = 0.85 / Math.max(graphWidth / fullWidth, graphHeight / fullHeight);
    const translate = [fullWidth / 2 - scale * midX, fullHeight / 2 - scale * midY];

    const zoom = d3.zoom().scaleExtent([0.1, 10]);
    svg.transition().duration(750).call(
        zoom.transform,
        d3.zoomIdentity.translate(translate[0], translate[1]).scale(scale)
    );
}

function showDetails(thought) {
    // Show panel
    const panel = document.getElementById('thought-details');
    panel.classList.remove('hidden');

    // Hide placeholder, show info
    document.getElementById('details-placeholder').style.display = 'none';
    document.getElementById('details-info').classList.remove('hidden');

    // Populate details
    document.getElementById('details-type').textContent = thought.type.charAt(0).toUpperCase() + thought.type.slice(1);
    document.getElementById('details-content').textContent = thought.content;

    // DEBUG: Log what we're getting from the database
    console.log('Raw timestamp from DB:', thought.created_at);

    // Parse timestamp - database stores local time, display as-is
    // Format: "2026-03-16 01:06:33" -> "3/16/2026, 1:06:33 AM"
    const parts = thought.created_at.match(/(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})/);
    if (parts) {
        const [_, year, month, day, hour, min, sec] = parts;
        console.log('Parsed parts:', { year, month, day, hour, min, sec });
        const date = new Date(year, month - 1, day, hour, min, sec); // month is 0-indexed
        console.log('Created Date object:', date);
        console.log('Formatted:', date.toLocaleString());
        document.getElementById('details-created').textContent = date.toLocaleString();
    } else {
        console.log('Failed to parse timestamp!');
        document.getElementById('details-created').textContent = thought.created_at;
    }

    document.getElementById('details-project').textContent = thought.project || 'N/A';
    document.getElementById('details-connections').textContent = thought.size;

    // Find related thoughts
    const relatedEdges = memoryData.edges.filter(e =>
        e.source === thought.id || e.target === thought.id ||
        e.source.id === thought.id || e.target.id === thought.id
    );

    const relatedList = document.getElementById('related-list');
    relatedList.innerHTML = '';

    relatedEdges.forEach(edge => {
        const relatedId = (edge.source === thought.id || edge.source.id === thought.id) ?
            (edge.target.id || edge.target) : (edge.source.id || edge.source);
        const relatedNode = memoryData.nodes.find(n => n.id === relatedId);

        if (relatedNode) {
            const li = document.createElement('li');
            li.textContent = `${relatedNode.content.substring(0, 60)}... (${(edge.similarity * 100).toFixed(0)}%)`;
            li.onclick = () => showDetails(relatedNode);
            relatedList.appendChild(li);
        }
    });
}

function closeDetails() {
    document.getElementById('thought-details').classList.add('hidden');
    container.selectAll('.node').classed('dimmed', false);
    container.selectAll('.link').classed('highlighted', false);
}

function highlightNode(thought, active) {
    if (active) {
        // Dim all nodes except this one and its connections
        const connectedIds = new Set([thought.id]);
        memoryData.edges.forEach(e => {
            const sourceId = e.source.id || e.source;
            const targetId = e.target.id || e.target;
            if (sourceId === thought.id) connectedIds.add(targetId);
            if (targetId === thought.id) connectedIds.add(sourceId);
        });

        container.selectAll('.node').classed('dimmed', d => !connectedIds.has(d.id));
        container.selectAll('.link').classed('highlighted', e => {
            const sourceId = e.source.id || e.source;
            const targetId = e.target.id || e.target;
            return sourceId === thought.id || targetId === thought.id;
        });
    } else {
        container.selectAll('.node').classed('dimmed', false);
        container.selectAll('.link').classed('highlighted', false);
    }
}

function dragstarted(event, d) {
    if (!event.active) simulation.alphaTarget(0.3).restart();
    d.fx = d.x;
    d.fy = d.y;
}

function dragged(event, d) {
    d.fx = event.x;
    d.fy = event.y;
}

function dragended(event, d) {
    if (!event.active) simulation.alphaTarget(0);
    d.fx = null;
    d.fy = null;
}

function showLoading(show) {
    document.getElementById('loading-overlay').style.display = show ? 'flex' : 'none';
}

function refreshMemoryGraph() {
    loadMemoryGraph();
}

