// Tempo Sec Visualization App

const statusEl = document.getElementById('status');
const treeContainer = document.getElementById('tree-container');
const detailsContent = document.getElementById('details-content');
const agentStateContent = document.getElementById('agent-state-content');

// State
let socket = null;
let rootNode = {
    id: "root",
    name: "Start",
    type: "root",
    children: []
};
let frames = new Map(); // id -> node
let currentFrameId = "root";

// Add root to map
frames.set("root", rootNode);

// Tree Layout Config
const margin = { top: 20, right: 90, bottom: 30, left: 90 };
let width = treeContainer.clientWidth - margin.left - margin.right;
let height = treeContainer.clientHeight - margin.top - margin.bottom;

// D3 Setup
const svg = d3.select("#tree-container").append("svg")
    .attr("width", width + margin.left + margin.right)
    .attr("height", height + margin.top + margin.bottom)
    .call(d3.zoom().on("zoom", (event) => {
        g.attr("transform", event.transform);
    }))
    .append("g")
    .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

const g = svg.append("g");

let i = 0;
const duration = 750;
let root = d3.hierarchy(rootNode, d => d.children);
root.x0 = height / 2;
root.y0 = 0;

// Connect via WebSocket
function connect() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    socket = new WebSocket(`${protocol}//${host}/ws`);

    socket.onopen = function () {
        statusEl.textContent = "Connected";
        statusEl.className = "status connected";
        console.log("WebSocket connected");

        // Request initial state if needed
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
        statusEl.textContent = "Disconnected";
        statusEl.className = "status disconnected";
        console.log("WebSocket disconnected. Reconnecting in 3s...");
        setTimeout(connect, 3000);
    };

    socket.onerror = function (err) {
        console.error("WebSocket error:", err);
    };
}

function handleEvent(event) {
    if (!event.type) return;

    const data = event.data;
    const frameId = data.frame_id; // May be undefined for internal events

    // Manage Frame Structure
    // If we see a frame ID we don't know, assume it's a child of the current frame
    // This is a simplification; ideally we'd get parent_id from backend.
    if (frameId && !frames.has(frameId)) {
        const parentFrame = frames.get(currentFrameId) || rootNode;
        const newFrame = {
            id: frameId,
            name: `Frame ${frameId.substring(0, 4)}`,
            type: "frame",
            children: [],
            parent: parentFrame
        };
        frames.set(frameId, newFrame);
        if (!parentFrame.children) parentFrame.children = [];
        parentFrame.children.push(newFrame);

        currentFrameId = frameId;
        update(root);
    }

    if (frameId) {
        currentFrameId = frameId;
    }

    switch (event.type) {
        case "tool_call":
            addToolNode(data);
            break;
        case "step":
            updateState(data);
            break;
        case "phase_transition":
            // Can add specific marker or update state
            break;
        case "start":
            // Reset tree if desired
            break;
    }

    update(root);
}

function addToolNode(toolData) {
    const frame = frames.get(currentFrameId) || rootNode;
    const toolNode = {
        id: toolData.id || `tool-${Date.now()}`,
        name: toolData.tool_name,
        type: "tool",
        data: toolData,
        children: []
    };

    if (!frame.children) frame.children = [];
    frame.children.push(toolNode);

    // Auto-update view
    update(root);

    // If auto-scroll lock is on?
}

function updateState(data) {
    if (data.phase) {
        document.getElementById("state-phase").textContent = data.phase;
    }
    if (data.step_number) {
        document.getElementById("state-step").textContent = data.step_number;
    }
    document.getElementById("state-latest").textContent = new Date().toLocaleTimeString();
}

function showDetails(d) {
    const data = d.data.data; // Access raw data from node
    if (!data) return;

    let html = `<div class="detail-card">`;

    // Header
    html += `
        <div class="field-group">
            <span class="field-label">Type</span>
            <div class="field-value">${d.data.type.toUpperCase()}</div>
        </div>
        <div class="field-group">
            <span class="field-label">Name</span>
            <div class="field-value">${d.data.name}</div>
        </div>
    `;

    if (d.data.type === 'tool') {
        const purpose = data.input?.purpose || "No purpose specified";
        html += `
            <div class="field-group">
                <span class="field-label">Purpose</span>
                <div class="field-value">${purpose}</div>
            </div>
            <div class="field-group">
                <span class="field-label">Duration</span>
                <div class="field-value">${data.duration_ms} ms</div>
            </div>
             <div class="field-group">
                <span class="field-label">Input</span>
                <div class="field-value json">${JSON.stringify(data.input, null, 2)}</div>
            </div>
             <div class="field-group">
                <span class="field-label">Output</span>
                <div class="field-value">${escapeHtml(data.raw_output || data.output || "")}</div>
            </div>
        `;
    } else if (d.data.type === 'frame') {
        html += `
             <div class="field-group">
                <span class="field-label">Frame ID</span>
                <div class="field-value">${d.data.id}</div>
            </div>
        `;
    }

    html += `</div>`;
    detailsContent.innerHTML = html;

    // Highlight selected
    d3.selectAll(".node").classed("selected", false);
    // Note: 'this' reference depends on caller interaction
}

function escapeHtml(text) {
    if (!text) return "";
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Update D3 Tree
function update(source) {
    // Recompute hierarchy
    root = d3.hierarchy(rootNode, d => d.children);
    root.x0 = height / 2;
    root.y0 = 0;

    const treeLayout = d3.tree().size([height, width]);
    const treeData = treeLayout(root);

    // Compute the new tree layout
    const nodes = treeData.descendants();
    const links = treeData.descendants().slice(1);

    // Normalize for fixed-depth
    nodes.forEach(d => { d.y = d.depth * 180; });

    // Update Nodes
    const node = g.selectAll('g.node')
        .data(nodes, d => d.id || (d.id = ++i));

    const nodeEnter = node.enter().append('g')
        .attr('class', d => `node ${d.data.type}`)
        .attr("transform", d => "translate(" + source.y0 + "," + source.x0 + ")")
        .on('click', (event, d) => {
            showDetails(d);
            d3.selectAll(".node").classed("selected", false);
            d3.select(event.currentTarget).classed("selected", true);
        });

    nodeEnter.append('circle')
        .attr('r', 10)
        .style("fill", d => d.data.type === 'tool' ? "#fff" : "#3498db");

    nodeEnter.append('text')
        .attr("dy", ".35em")
        .attr("x", d => d.children || d._children ? -13 : 13)
        .attr("text-anchor", d => d.children || d._children ? "end" : "start")
        .text(d => d.data.name);

    // UPDATE
    const nodeUpdate = node.merge(nodeEnter).transition()
        .duration(duration)
        .attr("transform", d => "translate(" + d.y + "," + d.x + ")");

    // EXIT
    const nodeExit = node.exit().transition()
        .duration(duration)
        .attr("transform", d => "translate(" + source.y + "," + source.x + ")")
        .remove();

    // Update Links
    const link = g.selectAll('path.link')
        .data(links, d => d.id);

    const linkEnter = link.enter().insert('path', "g")
        .attr("class", "link")
        .attr('d', d => {
            const o = { x: source.x0, y: source.y0 };
            return diagonal(o, o);
        });

    const linkUpdate = link.merge(linkEnter).transition()
        .duration(duration)
        .attr('d', d => diagonal(d, d.parent));

    const linkExit = link.exit().transition()
        .duration(duration)
        .attr('d', d => {
            const o = { x: source.x, y: source.y };
            return diagonal(o, o);
        })
        .remove();

    // Stash the old positions for transition.
    nodes.forEach(d => {
        d.x0 = d.x;
        d.y0 = d.y;
    });
}

function diagonal(s, d) {
    return `M ${s.y} ${s.x}
            C ${(s.y + d.y) / 2} ${s.x},
              ${(s.y + d.y) / 2} ${d.x},
              ${d.y} ${d.x}`;
}

// Initial connect
connect();
