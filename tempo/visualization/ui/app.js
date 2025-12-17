// Tempo Sec Visualization App

const statusEl = document.getElementById('status');
const detailsContent = document.getElementById('details-content');

// State
let socket = null;
let rootNode = {
    id: "root",
    name: "ROOT",
    type: "root",
    children: []
};
let frames = new Map();
let steps = new Map(); // frameId-stepNum -> node
let currentFrameId = "root";
// Track current step number from updates
let currentStepNumber = 0;
let isConnected = false;
let updateTimeout = null;

// Add root to map
frames.set("root", rootNode);

// DOM Elements & Dimensions
const container = document.getElementById('tree-container');
let width = container.clientWidth;
let height = container.clientHeight;

// D3 Setup
const svg = d3.select("#tree-container").append("svg")
    .attr("width", width)
    .attr("height", height)
    .call(d3.zoom()
        .scaleExtent([0.1, 3])
        .on("zoom", (event) => {
            g.attr("transform", event.transform);
        }))
    .on("dblclick.zoom", null);

const g = svg.append("g")
    .attr("transform", `translate(${width / 2}, 50)`);

// Tree Layout
let tree = d3.tree().nodeSize([100, 100]); // Increased spacing
let root = d3.hierarchy(rootNode, d => d.children);

// Animation duration
const duration = 400;
let i = 0;

function connect() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    socket = new WebSocket(`${protocol}//${host}/ws`);

    socket.onopen = function () {
        statusEl.textContent = "CONNECTED";
        statusEl.className = "status connected";
        isConnected = true;
        console.log("WebSocket connected");
        debouncedUpdate();
    };

    socket.onmessage = function (event) {
        try {
            const msg = JSON.parse(event.data);
            handleEvent(msg);
        } catch (e) {
            console.error("Error parsing message:", e);
        }
    };

    socket.onclose = function () {
        statusEl.textContent = "DISCONNECTED";
        statusEl.className = "status disconnected";
        isConnected = false;
        setTimeout(connect, 3000);
    };
}

function handleEvent(event) {
    if (!event.type) return;

    const data = event.data;
    const frameId = data.frame_id;

    // Auto-create frames
    if (frameId && !frames.has(frameId)) {
        const parentFrame = frames.get(currentFrameId) || rootNode;
        const newFrame = {
            id: frameId,
            name: `FRAME`,
            type: "frame",
            children: [],
            parent: parentFrame
        };
        frames.set(frameId, newFrame);
        if (!parentFrame.children) parentFrame.children = [];
        parentFrame.children.push(newFrame);
        currentFrameId = frameId;
        debouncedUpdate();
    }

    if (frameId) currentFrameId = frameId;

    // Update global step number if present
    if (data.step_number !== undefined) {
        currentStepNumber = data.step_number;
    }

    switch (event.type) {
        case "tool_call":
            addToolNode(data);
            break;
        case "step":
            updateState(data);
            // Ensure step node exists even if no tools (e.g. for thinking)
            getOrCreateStepNode(currentFrameId, data.step_number);
            debouncedUpdate();
            break;
    }
}

function getOrCreateStepNode(frameId, stepNum) {
    const stepKey = `${frameId}-${stepNum}`;
    if (steps.has(stepKey)) return steps.get(stepKey);

    const frame = frames.get(frameId) || rootNode;

    const stepNode = {
        id: `step-${stepKey}`,
        name: `STEP ${stepNum}`,
        type: "step",
        data: {},
        children: []
    };

    if (!frame.children) frame.children = [];
    frame.children.push(stepNode);
    steps.set(stepKey, stepNode);
    return stepNode;
}

function addToolNode(toolData) {
    // Determine which step this tool belongs to.
    // If toolData doesn't have step number, use current global step.
    const stepNum = currentStepNumber;

    const stepNode = getOrCreateStepNode(currentFrameId, stepNum);

    const toolNode = {
        id: toolData.id || `tool-${Date.now()}`,
        name: toolData.tool_name,
        type: "tool",
        data: toolData,
        children: []
    };

    stepNode.children.push(toolNode);
    debouncedUpdate();
}

function updateState(data) {
    if (data.phase) document.getElementById("state-phase").textContent = data.phase;
    if (data.step_number) document.getElementById("state-step").textContent = data.step_number;
}

function debouncedUpdate() {
    if (updateTimeout) clearTimeout(updateTimeout);
    updateTimeout = setTimeout(() => {
        update(root);
    }, 100);
}

// Icons
function getIcon(type, name) {
    if (type === 'frame') return '⬡';
    if (type === 'step') return '#';
    if (name.includes('shell')) return '>';
    if (name.includes('read') || name.includes('write')) return '📄';
    if (name.includes('browser')) return '🌐';
    return '⚙️';
}

function update(source) {
    root = d3.hierarchy(rootNode, d => d.children);

    const treeData = tree(root);
    const nodes = treeData.descendants();
    const links = treeData.links();

    // Nodes
    const node = g.selectAll('g.node')
        .data(nodes, d => d.data.id || (d.data.id = ++i));

    const nodeEnter = node.enter().append('g')
        .attr('class', d => `node ${d.data.type}`)
        .attr("transform", d => `translate(${source.x0 || 0},${source.y0 || 0})`)
        .on('click', (event, d) => {
            showDetails(d);
            d3.selectAll(".node").classed("selected", false);
            d3.select(event.currentTarget).classed("selected", true);
        });

    nodeEnter.append('circle')
        .attr('r', 20)
        .style("fill", "#050505");

    // Icon text - adjusted centering
    nodeEnter.append('text')
        .attr("class", "node-icon")
        .attr("dy", "5px") // Adjusted from .3em to pixel value for better alignment
        .style("text-anchor", "middle")
        .style("font-size", "18px")
        .text(d => getIcon(d.data.type, d.data.name));

    // Label
    nodeEnter.append('text')
        .attr("dy", "35px")
        .attr("text-anchor", "middle")
        .style("font-size", "9px")
        .style("opacity", 0.7)
        .text(d => d.data.name.toUpperCase());

    const nodeUpdate = node.merge(nodeEnter).transition().duration(duration)
        .attr("transform", d => `translate(${d.x},${d.y})`);

    const nodeExit = node.exit().transition().duration(duration)
        .attr("transform", d => `translate(${source.x},${source.y})`)
        .remove();

    // Links
    const link = g.selectAll('path.link')
        .data(links, d => d.target.data.id);

    const linkEnter = link.enter().insert('path', "g")
        .attr("class", "link")
        .attr('d', d => {
            const o = { x: source.x0 || 0, y: source.y0 || 0 };
            return diagonal(o, o);
        });

    const linkUpdate = link.merge(linkEnter).transition().duration(duration)
        .attr('d', d => diagonal(d.source, d.target));

    const linkExit = link.exit().transition().duration(duration)
        .attr('d', d => {
            const o = { x: source.x, y: source.y };
            return diagonal(o, o);
        })
        .remove();

    nodes.forEach(d => {
        d.x0 = d.x;
        d.y0 = d.y;
    });
}

function diagonal(s, d) {
    return `M ${s.x} ${s.y}
            C ${s.x} ${(s.y + d.y) / 2},
              ${d.x} ${(s.y + d.y) / 2},
              ${d.x} ${d.y}`;
}

function showDetails(d) {
    const data = d.data.data;
    if (!data) return;

    let html = `<div class="detail-card">`;

    if (d.data.type === 'tool') {
        html += `
            <div class="tool-badge">${d.data.name}</div>
            <div class="field-group">
                <span class="field-label">Purpose</span>
                <div class="field-value">${escapeHtml(data.input?.purpose || "N/A")}</div>
            </div>
            <div class="field-group">
                <span class="field-label">Input</span>
                <div class="field-value highlight">${escapeHtml(JSON.stringify(data.input, null, 2))}</div>
            </div>
            <div class="field-group">
                <span class="field-label">Output</span>
                <div class="field-value">${escapeHtml(data.raw_output || data.output || "")}</div>
            </div>
        `;
    } else {
        html += `<div class="tool-badge" style="border-color:var(--accent-blue)">${d.data.type.toUpperCase()}</div>`;
        html += `<div class="field-value">ID: ${d.data.id || d.data.name}</div>`;
    }

    html += `</div>`;
    detailsContent.innerHTML = html;
}

function escapeHtml(text) {
    if (!text) return "";
    return text.toString()
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

window.addEventListener('resize', () => {
    width = container.clientWidth;
    height = container.clientHeight;
    svg.attr("width", width).attr("height", height);
    update(root);
});

connect();
