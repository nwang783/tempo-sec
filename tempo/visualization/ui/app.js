// Tempo Sec Visualization App - Linear Stack v4

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
let steps = new Map();
let currentFrameId = "root";
let currentStepNumber = 0;
let stepsWithTools = new Set(); // Track which steps have tool calls
let summarizedTools = new Set(); // Track which tool calls have been summarized
let isConnected = false;
let updateTimeout = null;

frames.set("root", rootNode);

// DOM
const container = document.getElementById('tree-container');
let width = container.clientWidth;
let height = container.clientHeight;

// D3 Setup - Vertical pan only (no zoom)
const svg = d3.select("#tree-container").append("svg")
    .attr("width", width)
    .attr("height", height);

// Create a zoom behavior that only allows vertical panning
const zoomBehavior = d3.zoom()
    .scaleExtent([1, 1]) // Disable zoom
    .on("zoom", (event) => {
        // Only allow vertical translation
        const transform = event.transform;
        g.attr("transform", `translate(${width / 2}, ${transform.y})`);
    });

svg.call(zoomBehavior)
    .on("dblclick.zoom", null);

// Enable mouse wheel for vertical scrolling
svg.on("wheel", function (event) {
    event.preventDefault();
    const currentTransform = d3.zoomTransform(this);
    const newY = currentTransform.y - event.deltaY;
    svg.call(zoomBehavior.transform, d3.zoomIdentity.translate(0, newY));
});

const g = svg.append("g")
    .attr("transform", `translate(${width / 2}, 20)`);

const duration = 400;

function connect() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    socket = new WebSocket(`${protocol}//${host}/ws`);

    socket.onopen = function () {
        statusEl.textContent = "CONNECTED";
        statusEl.className = "status connected";
        isConnected = true;
        debouncedUpdate();
    };

    socket.onmessage = function (event) {
        try {
            const msg = JSON.parse(event.data);
            handleEvent(msg);
        } catch (e) {
            console.error(e);
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
    }

    if (frameId) currentFrameId = frameId;
    if (data.step_number !== undefined) currentStepNumber = data.step_number;

    switch (event.type) {
        case "start":
            if (data.model) {
                document.getElementById("state-model").textContent = data.model;
            }
            break;
        case "phase_summary":
            addPhaseSummaryNode(data);
            break;
        case "tool_call":
            addToolNode(data);
            break;
        case "step":
            updateState(data);
            getOrCreateStepNode(currentFrameId, data.step_number);
            debouncedUpdate();
            break;
        case "summarized":
            // Mark a tool as summarized (no longer in full context)
            if (data.tool_call_id) {
                summarizedTools.add(data.tool_call_id);
                debouncedUpdate();
            }
            break;
        case "paused":
            // Agent is paused, waiting for user input
            statusEl.textContent = "PAUSED";
            statusEl.className = "status paused";
            document.getElementById("prompt-status").textContent =
                data.reason || "Agent paused. Send a prompt to continue.";
            break;
        case "resumed":
            // Agent resumed from pause
            statusEl.textContent = "CONNECTED";
            statusEl.className = "status connected";
            document.getElementById("prompt-status").textContent = "";
            break;
        case "user_prompt_injected":
            // User prompt was received and injected - add visual node
            addUserPromptNode(data);
            document.getElementById("prompt-status").textContent =
                "✓ Prompt injected: " + (data.content_preview || "").substring(0, 50) + "...";
            break;
        case "finish":
            statusEl.textContent = data.success ? "FINISHED" : "FAILED";
            statusEl.className = "status " + (data.success ? "connected" : "disconnected");
            break;
        case "cost_update":
            updateCostPanel(data);
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
        data: { step_number: stepNum },
        children: []
    };

    if (!frame.children) frame.children = [];
    frame.children.push(stepNode);
    steps.set(stepKey, stepNode);
    return stepNode;
}

function addToolNode(toolData) {
    const stepNum = currentStepNumber;
    const stepNode = getOrCreateStepNode(currentFrameId, stepNum);

    const isPhase = toolData.tool_name === 'transition_phase';

    const toolNode = {
        id: toolData.id || `tool-${Date.now()}`,
        name: isPhase ? (toolData.input?.phase?.toUpperCase() || "PHASE CHANGE") : toolData.tool_name,
        type: isPhase ? "phase_marker" : "tool",
        data: toolData, // Store raw tool data directly
        children: []
    };

    stepNode.children.push(toolNode);
    stepsWithTools.add(currentStepNumber); // Mark this step as having a tool

    // Update "Latest" timestamp
    const now = new Date();
    const timeStr = now.toLocaleTimeString();
    document.getElementById("state-latest").textContent = `${toolData.tool_name} @ ${timeStr}`;

    debouncedUpdate();
}

function addUserPromptNode(promptData) {
    const stepNum = currentStepNumber;
    const stepNode = getOrCreateStepNode(currentFrameId, stepNum);

    const promptNode = {
        id: `user-prompt-${Date.now()}`,
        name: "USER PROMPT",
        type: "user_prompt",
        data: {
            content: promptData.content_preview || "User intervention",
            timestamp: new Date().toISOString()
        },
        children: []
    };

    stepNode.children.push(promptNode);
    stepsWithTools.add(currentStepNumber);

    // Update "Latest" timestamp
    const now = new Date();
    const timeStr = now.toLocaleTimeString();
    document.getElementById("state-latest").textContent = `User Prompt @ ${timeStr}`;

    debouncedUpdate();
}

function addPhaseSummaryNode(summaryData) {
    const stepNum = currentStepNumber;
    const stepNode = getOrCreateStepNode(currentFrameId, stepNum);

    const summaryNode = {
        id: `phase-summary-${Date.now()}`,
        name: "PHASE SUMMARY",
        type: "phase_summary",
        data: {
            from_phase: summaryData.from_phase,
            to_phase: summaryData.to_phase,
            summary: summaryData.summary,
            summary_preview: summaryData.summary_preview,
            timestamp: new Date().toISOString()
        },
        children: []
    };

    stepNode.children.push(summaryNode);
    stepsWithTools.add(currentStepNumber);

    // Update "Latest" timestamp
    const now = new Date();
    const timeStr = now.toLocaleTimeString();
    document.getElementById("state-latest").textContent =
        `Phase Summary (${summaryData.from_phase} → ${summaryData.to_phase}) @ ${timeStr}`;

    debouncedUpdate();
}

function updateState(data) {
    if (data.phase) document.getElementById("state-phase").textContent = data.phase;
    if (data.step_number) document.getElementById("state-step").textContent = data.step_number;
}

function debouncedUpdate() {
    if (updateTimeout) clearTimeout(updateTimeout);
    updateTimeout = setTimeout(() => {
        update();
    }, 100);
}

function getIcon(type, name) {
    if (type === 'phase_marker') return '🚀';
    if (type === 'phase_summary') return '📋';
    if (type === 'user_prompt') return '💬';
    if (name.includes('shell')) return '>';
    if (name.includes('read') || name.includes('write') || name.includes('view')) return '📄';
    if (name.includes('browser')) return '🌐';
    return '⚙️';
}

// === Custom Layout Engine ===
function computeLayout(root) {
    const nodes = [];
    let currentY = 20; // Start with some padding

    function traverse(node) {
        // Skip empty steps (steps with no tool children)
        if (node.type === 'step') {
            const hasTools = node.children && node.children.length > 0;
            if (!hasTools) return; // Skip this step entirely

            // Render step header
            node.x = 0;
            node.y = currentY;
            node.height = 25;
            currentY += node.height + 5;
            nodes.push(node);
        } else if (node.type === 'tool') {
            node.x = 0;
            node.y = currentY;
            node.height = 60;
            currentY += node.height + 10;
            nodes.push(node);
        } else if (node.type === 'user_prompt') {
            node.x = 0;
            node.y = currentY;
            node.height = 50;
            currentY += node.height + 15;
            nodes.push(node);
        } else if (node.type === 'phase_marker') {
            node.x = 0;
            node.y = currentY;
            node.height = 45;
            currentY += node.height + 15;
            nodes.push(node);
        } else if (node.type === 'phase_summary') {
            node.x = 0;
            node.y = currentY;
            node.height = 55;
            currentY += node.height + 15;
            nodes.push(node);
        }

        if (node.children) {
            node.children.forEach(traverse);
        }
    }

    traverse(root);
    return { nodes, totalHeight: currentY };
}

function update() {
    const { nodes, totalHeight } = computeLayout(rootNode);

    // --- Nodes ---
    const node = g.selectAll('g.node')
        .data(nodes, d => d.id);

    const nodeEnter = node.enter().append('g')
        .attr('class', d => `node ${d.type}`)
        .attr("transform", d => `translate(0,${d.y + 30})`)
        .style("opacity", 0)
        .on('click', (event, d) => {
            showDetails(d);
            d3.selectAll(".node").classed("selected", false);
            d3.select(event.currentTarget).classed("selected", true);
        });

    // --- STEP Header ---
    nodeEnter.filter(d => d.type === 'step')
        .append('text')
        .attr("class", "step-label")
        .attr("x", -150)
        .attr("text-anchor", "start")
        .attr("dy", "0.5em")
        .style("font-family", "monospace")
        .style("font-size", "11px")
        .style("fill", "#555")
        .text(d => `STEP ${d.data.step_number || '?'}`);

    // --- TOOL Card ---
    const cardWidth = 320;
    const cardHeight = 60;

    const toolGroup = nodeEnter.filter(d => d.type === 'tool');

    toolGroup.append('rect')
        .attr('x', -cardWidth / 2)
        .attr('y', 0)
        .attr('width', cardWidth)
        .attr('height', cardHeight)
        .attr('rx', 6)
        .style("fill", "#0d0d0d")
        .style("stroke", "#2a2a2a")
        .style("stroke-width", "1px");

    toolGroup.append('circle')
        .attr('cx', -cardWidth / 2 + 32)
        .attr('cy', cardHeight / 2)
        .attr('r', 22)
        .style("fill", "#111")
        .style("stroke", "#444");

    toolGroup.append('text')
        .attr('x', -cardWidth / 2 + 32)
        .attr('y', cardHeight / 2)
        .attr("dy", "7px")
        .attr("text-anchor", "middle")
        .style("font-size", "24px")
        .style("fill", "#fff")
        .text(d => getIcon(d.type, d.name));

    toolGroup.append('text')
        .attr('x', -cardWidth / 2 + 70)
        .attr('y', cardHeight / 3 + 3)
        .style("font-size", "13px")
        .style("font-weight", "bold")
        .style("fill", "#eee")
        .text(d => d.name.toUpperCase());

    toolGroup.append('text')
        .attr('x', -cardWidth / 2 + 70)
        .attr('y', cardHeight * 0.72)
        .style("font-size", "10px")
        .style("fill", "#777")
        .text(d => {
            const p = d.data.input?.purpose || "";
            return p.length > 40 ? p.substring(0, 37) + "..." : p;
        });

    // --- PHASE Banner ---
    const phaseGroup = nodeEnter.filter(d => d.type === 'phase_marker');

    phaseGroup.append('rect')
        .attr('x', -cardWidth / 2)
        .attr('y', 0)
        .attr('width', cardWidth)
        .attr('height', 45)
        .attr('rx', 22)
        .style("fill", "#050505")
        .style("stroke", "var(--accent-green)")
        .style("stroke-width", "2px")
        .style("filter", "drop-shadow(0 0 8px var(--accent-green))");

    phaseGroup.append('text')
        .attr('x', 0)
        .attr('y', 28)
        .attr("text-anchor", "middle")
        .style("font-size", "14px")
        .style("font-weight", "bold")
        .style("fill", "var(--accent-green)")
        .style("text-transform", "uppercase")
        .text(d => `>>> ${d.name} <<<`);

    // --- USER PROMPT Banner ---
    const userPromptGroup = nodeEnter.filter(d => d.type === 'user_prompt');

    userPromptGroup.append('rect')
        .attr('x', -cardWidth / 2)
        .attr('y', 0)
        .attr('width', cardWidth)
        .attr('height', 50)
        .attr('rx', 8)
        .style("fill", "rgba(156, 39, 176, 0.1)")
        .style("stroke", "#9c27b0")
        .style("stroke-width", "2px")
        .style("filter", "drop-shadow(0 0 8px rgba(156, 39, 176, 0.5))");

    userPromptGroup.append('circle')
        .attr('cx', -cardWidth / 2 + 30)
        .attr('cy', 25)
        .attr('r', 18)
        .style("fill", "rgba(156, 39, 176, 0.2)")
        .style("stroke", "#9c27b0");

    userPromptGroup.append('text')
        .attr('x', -cardWidth / 2 + 30)
        .attr('y', 25)
        .attr("dy", "6px")
        .attr("text-anchor", "middle")
        .style("font-size", "20px")
        .style("fill", "#fff")
        .text('💬');

    userPromptGroup.append('text')
        .attr('x', -cardWidth / 2 + 60)
        .attr('y', 18)
        .style("font-size", "11px")
        .style("font-weight", "bold")
        .style("fill", "#9c27b0")
        .style("text-transform", "uppercase")
        .text("User Intervention");

    userPromptGroup.append('text')
        .attr('x', -cardWidth / 2 + 60)
        .attr('y', 36)
        .style("font-size", "10px")
        .style("fill", "#ccc")
        .text(d => {
            const content = d.data.content || "";
            return content.length > 45 ? content.substring(0, 42) + "..." : content;
        });

    // --- PHASE SUMMARY Card ---
    const phaseSummaryGroup = nodeEnter.filter(d => d.type === 'phase_summary');

    phaseSummaryGroup.append('rect')
        .attr('x', -cardWidth / 2)
        .attr('y', 0)
        .attr('width', cardWidth)
        .attr('height', 55)
        .attr('rx', 8)
        .style("fill", "rgba(255, 193, 7, 0.05)")
        .style("stroke", "#ffc107")
        .style("stroke-width", "2px")
        .style("filter", "drop-shadow(0 0 8px rgba(255, 193, 7, 0.3))");

    phaseSummaryGroup.append('circle')
        .attr('cx', -cardWidth / 2 + 30)
        .attr('cy', 27)
        .attr('r', 18)
        .style("fill", "rgba(255, 193, 7, 0.15)")
        .style("stroke", "#ffc107");

    phaseSummaryGroup.append('text')
        .attr('x', -cardWidth / 2 + 30)
        .attr('y', 27)
        .attr("dy", "6px")
        .attr("text-anchor", "middle")
        .style("font-size", "18px")
        .style("fill", "#fff")
        .text('📋');

    phaseSummaryGroup.append('text')
        .attr('x', -cardWidth / 2 + 60)
        .attr('y', 18)
        .style("font-size", "11px")
        .style("font-weight", "bold")
        .style("fill", "#ffc107")
        .style("text-transform", "uppercase")
        .text(d => `${d.data.from_phase} → ${d.data.to_phase}`);

    phaseSummaryGroup.append('text')
        .attr('x', -cardWidth / 2 + 60)
        .attr('y', 38)
        .style("font-size", "10px")
        .style("fill", "#ccc")
        .text(d => {
            const preview = d.data.summary_preview || "";
            return preview.length > 45 ? preview.substring(0, 42) + "..." : preview;
        });

    // --- Update Transitions ---
    const nodeUpdate = node.merge(nodeEnter).transition().duration(duration)
        .attr("transform", d => `translate(${d.x},${d.y})`)
        .style("opacity", d => {
            // Dim summarized tools
            if (d.type === 'tool' && summarizedTools.has(d.id)) {
                return 0.5;
            }
            return 1;
        });

    // Update stroke color based on summarization status (for tool cards)
    node.merge(nodeEnter).selectAll('rect')
        .style("stroke", d => {
            if (d.type === 'tool') {
                return summarizedTools.has(d.id) ? "#333" : "var(--accent-blue)";
            }
            return null; // Keep existing for phases
        })
        .style("stroke-width", d => {
            if (d.type === 'tool') {
                return summarizedTools.has(d.id) ? "1px" : "2px";
            }
            return null;
        });

    // Exit
    node.exit().transition().duration(duration)
        .style("opacity", 0)
        .remove();

    // --- Auto-scroll to bottom ---
    if (totalHeight > height - 100) {
        const targetY = -(totalHeight - height + 100);
        svg.transition().duration(duration)
            .call(zoomBehavior.transform, d3.zoomIdentity.translate(0, targetY));
    }
}

function showDetails(d) {
    // Access data correctly: d.data holds the raw toolData
    const toolData = d.data;

    let html = `<div class="detail-card">`;

    if (d.type === 'tool' || d.type === 'phase_marker') {
        html += `<div class="tool-badge">${d.name}</div>`;
        html += `
            <div class="field-group">
                <span class="field-label">Purpose</span>
                <div class="field-value">${escapeHtml(toolData.input?.purpose || "N/A")}</div>
            </div>
            <div class="field-group">
                <span class="field-label">Input</span>
                <div class="field-value highlight">${escapeHtml(JSON.stringify(toolData.input, null, 2))}</div>
            </div>
            <div class="field-group">
                <span class="field-label">Output</span>
                <div class="field-value">${escapeHtml(toolData.raw_output || toolData.output || "(no output)")}</div>
            </div>
        `;
    } else if (d.type === 'user_prompt') {
        html += `<div class="tool-badge" style="border-left-color:#9c27b0;background:rgba(156,39,176,0.1)">💬 USER PROMPT</div>`;
        html += `
            <div class="field-group">
                <span class="field-label">Prompt Content</span>
                <div class="field-value" style="color:#9c27b0">${escapeHtml(toolData.content || "User intervention")}</div>
            </div>
            <div class="field-group">
                <span class="field-label">Timestamp</span>
                <div class="field-value">${escapeHtml(toolData.timestamp || "N/A")}</div>
            </div>
            <p style="color:#888;font-size:12px;margin-top:15px">
                This prompt was injected into the agent's context by the user during execution.
            </p>
        `;
    } else if (d.type === 'phase_summary') {
        html += `<div class="tool-badge" style="border-left-color:#ffc107;background:rgba(255,193,7,0.1)">📋 PHASE SUMMARY</div>`;
        html += `
            <div class="field-group">
                <span class="field-label">Transition</span>
                <div class="field-value" style="color:#ffc107">${escapeHtml(toolData.from_phase)} → ${escapeHtml(toolData.to_phase)}</div>
            </div>
            <div class="field-group">
                <span class="field-label">Summary</span>
                <div class="field-value">${escapeHtml(toolData.summary || "No summary available")}</div>
            </div>
            <div class="field-group">
                <span class="field-label">Generated</span>
                <div class="field-value">${escapeHtml(toolData.timestamp || "N/A")}</div>
            </div>
            <p style="color:#888;font-size:12px;margin-top:15px">
                This summary was generated by an LLM when transitioning between phases to capture key context.
            </p>
        `;
    } else if (d.type === 'step') {
        html += `<div class="tool-badge" style="background:#222">STEP ${toolData.step_number}</div>`;
        html += `<p style="color:#888">Agent execution step container.</p>`;
    }

    html += `</div>`;
    detailsContent.innerHTML = html;
}

function escapeHtml(t) {
    if (!t) return "";
    return t.toString()
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

window.addEventListener('resize', () => {
    width = container.clientWidth;
    height = container.clientHeight;
    svg.attr("width", width).attr("height", height);
    update();
});

// === Prompt Input Handling ===
const promptInput = document.getElementById('prompt-input');
const sendPromptBtn = document.getElementById('send-prompt-btn');
const promptStatus = document.getElementById('prompt-status');

function sendPrompt() {
    const content = promptInput.value.trim();

    if (!content) {
        promptStatus.textContent = "Please enter a prompt.";
        promptStatus.style.color = "#ff9800";
        setTimeout(() => {
            promptStatus.textContent = "";
            promptStatus.style.color = "";
        }, 3000);
        return;
    }

    if (!socket || socket.readyState !== WebSocket.OPEN) {
        promptStatus.textContent = "Not connected. Please wait...";
        promptStatus.style.color = "#ff3232";
        setTimeout(() => {
            promptStatus.textContent = "";
            promptStatus.style.color = "";
        }, 3000);
        return;
    }

    // Send the prompt via WebSocket
    socket.send(JSON.stringify({
        type: 'user_prompt',
        content: content
    }));

    // Clear input and show confirmation
    promptInput.value = '';
    promptStatus.textContent = "✓ Prompt sent!";
    promptStatus.style.color = "";  // Use default green

    // Clear status after a delay
    setTimeout(() => {
        if (promptStatus.textContent === "✓ Prompt sent!") {
            promptStatus.textContent = "";
        }
    }, 5000);
}

const stopBtn = document.getElementById('stop-btn');

function sendStopSignal() {
    if (!socket || socket.readyState !== WebSocket.OPEN) return;

    // Confirm first
    if (!confirm("Are you sure you want to stop the agent?")) return;

    socket.send(JSON.stringify({
        type: 'stop_agent'
    }));

    stopBtn.textContent = "STOPPING...";
    stopBtn.disabled = true;
    statusEl.textContent = "STOPPING";
}

stopBtn.addEventListener('click', sendStopSignal);

// Button click handler
sendPromptBtn.addEventListener('click', sendPrompt);

// Enter key handler (Ctrl+Enter or Cmd+Enter to send)
promptInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        sendPrompt();
    }
});

// === Cost Panel Updates ===
function updateCostPanel(data) {
    const totalCostEl = document.getElementById('cost-total');
    const cachedEl = document.getElementById('cost-cached');
    const promptEl = document.getElementById('cost-prompt');
    const completionEl = document.getElementById('cost-completion');

    if (!totalCostEl) return;

    // Format cost with 4 decimal places for precision
    const costFormatted = `$${data.total_cost.toFixed(4)}`;
    totalCostEl.textContent = costFormatted;

    // Add flash animation
    totalCostEl.classList.remove('cost-updated');
    void totalCostEl.offsetWidth; // Force reflow
    totalCostEl.classList.add('cost-updated');

    // Update token counts
    if (cachedEl) {
        const cached = data.total_cached_tokens || 0;
        cachedEl.textContent = `${cached.toLocaleString()} tokens`;
    }

    if (promptEl) {
        promptEl.textContent = (data.total_prompt_tokens || 0).toLocaleString();
    }

    if (completionEl) {
        completionEl.textContent = (data.total_completion_tokens || 0).toLocaleString();
    }
}


// === UI Interactions ===
// Collapsible Tree Sections
document.querySelectorAll('.section-header').forEach(header => {
    header.addEventListener('click', () => {
        const section = header.parentElement;
        const content = section.querySelector('.tree-content');

        // Toggle expanded class
        section.classList.toggle('expanded');
        section.classList.toggle('collapsed');

        // Toggle arrow text
        const text = header.childNodes[0]; // Assuming text node is first or arrow is in text
        if (section.classList.contains('collapsed')) {
            content.style.display = 'none';
            header.innerHTML = header.innerHTML.replace('▼', '▶');
        } else {
            content.style.display = 'block';
            header.innerHTML = header.innerHTML.replace('▶', '▼');
        }
    });
});

connect();
