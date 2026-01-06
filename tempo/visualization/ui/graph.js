/**
 * Graph Visualization Module
 * 
 * D3.js-based tree visualization for the agent execution graph.
 * Handles node creation, layout computation, and rendering.
 * 
 * @module graph
 */

import * as state from './state.js';
import { getNodeIcon, getPhaseIcon, escapeHtml } from './utils.js';

// ============================================================================
// Module State
// ============================================================================

/** @type {number} */
let width = 0;

/** @type {number} */
let height = 0;

/** @type {d3.Selection} */
let svg = null;

/** @type {d3.Selection} */
let g = null;

/** @type {d3.ZoomBehavior} */
let zoomBehavior = null;

/** @type {number} */
const duration = 400;

/** @type {NodeJS.Timeout|null} */
let updateTimeout = null;

// ============================================================================
// Initialization
// ============================================================================

/**
 * Initialize the D3 visualization.
 * Must be called after DOM is ready.
 * 
 * @param {HTMLElement} container - Container element for the SVG
 */
export function init(container) {
    width = container.clientWidth;
    height = container.clientHeight;

    // Create SVG
    svg = d3.select(container).append("svg")
        .attr("width", width)
        .attr("height", height);

    // Zoom behavior - vertical pan only
    zoomBehavior = d3.zoom()
        .scaleExtent([1, 1]) // Disable zoom
        .on("zoom", (event) => {
            const transform = event.transform;
            g.attr("transform", `translate(${width / 2}, ${transform.y})`);
        });

    svg.call(zoomBehavior)
        .on("dblclick.zoom", null);

    // Mouse wheel for vertical scrolling
    svg.on("wheel", function (event) {
        event.preventDefault();
        const currentTransform = d3.zoomTransform(this);
        const newY = currentTransform.y - event.deltaY;
        svg.call(zoomBehavior.transform, d3.zoomIdentity.translate(0, newY));
    });

    // Main group
    g = svg.append("g")
        .attr("transform", `translate(${width / 2}, 20)`);

    // Handle window resize
    window.addEventListener('resize', () => {
        width = container.clientWidth;
        height = container.clientHeight;
        svg.attr("width", width).attr("height", height);
        update();
    });
}

// ============================================================================
// Node Management
// ============================================================================

/**
 * Get or create a step node in the tree.
 * 
 * @param {string} frameId - Frame ID
 * @param {number} stepNum - Step number
 * @returns {Object} Step node
 */
export function getOrCreateStepNode(frameId, stepNum) {
    const stepKey = `${frameId}-${stepNum}`;
    if (state.appState.steps.has(stepKey)) return state.appState.steps.get(stepKey);

    const frame = state.appState.frames.get(frameId) || state.appState.rootNode;

    const stepNode = {
        id: `step-${stepKey}`,
        name: `STEP ${stepNum}`,
        type: "step",
        data: { step_number: stepNum },
        children: []
    };

    if (!frame.children) frame.children = [];
    frame.children.push(stepNode);
    state.appState.steps.set(stepKey, stepNode);
    return stepNode;
}

/**
 * Add a tool call node to the current step.
 * 
 * @param {Object} toolData - Tool call data from the server
 */
export function addToolNode(toolData) {
    const stepNum = state.appState.currentStepNumber;
    const stepNode = getOrCreateStepNode(state.appState.currentFrameId, stepNum);

    const isPhase = toolData.tool_name === 'transition_phase';

    const toolNode = {
        id: toolData.id || `tool-${Date.now()}`,
        name: isPhase ? (toolData.input?.phase?.toUpperCase() || "PHASE CHANGE") : toolData.tool_name,
        type: isPhase ? "phase_marker" : "tool",
        data: toolData,
        children: []
    };

    stepNode.children.push(toolNode);
    state.appState.stepsWithTools.add(state.appState.currentStepNumber);

    // Update "Latest" timestamp
    const now = new Date();
    const timeStr = now.toLocaleTimeString();
    const latestEl = document.getElementById("state-latest");
    if (latestEl) {
        latestEl.textContent = `${toolData.tool_name} @ ${timeStr}`;
    }

    debouncedUpdate();
}

/**
 * Add a tool call node to a specific subagent's graph.
 * 
 * @param {Object} toolData - Tool call data from the server
 * @param {string} subagentId - ID of the subagent to add the tool to
 */
export function addToolNodeForSubagent(toolData, subagentId) {
    const subagent = state.agentHierarchy.subagents.find(s => s.id === subagentId);
    if (!subagent) {
        console.warn(`Subagent ${subagentId} not found for tool node`);
        return;
    }

    // Ensure subagent has graph state
    if (!subagent.rootNode) {
        subagent.rootNode = { id: `${subagentId}-root`, name: "ROOT", type: "root", children: [] };
    }
    if (!subagent.stepsMap) {
        subagent.stepsMap = new Map();
    }

    // Get or create step node in subagent's tree
    const stepNum = subagent.currentStepNumber || 1;
    const stepKey = `${subagentId}-${stepNum}`;
    let stepNode = subagent.stepsMap.get(stepKey);
    if (!stepNode) {
        stepNode = {
            id: `step-${stepKey}`,
            name: `STEP ${stepNum}`,
            type: "step",
            data: { step_number: stepNum },
            children: []
        };
        subagent.rootNode.children.push(stepNode);
        subagent.stepsMap.set(stepKey, stepNode);
    }

    const isPhase = toolData.tool_name === 'transition_phase';
    const toolNode = {
        id: toolData.id || `tool-${Date.now()}`,
        name: isPhase ? (toolData.input?.phase?.toUpperCase() || "PHASE CHANGE") : toolData.tool_name,
        type: isPhase ? "phase_marker" : "tool",
        data: toolData,
        children: []
    };

    stepNode.children.push(toolNode);

    // Re-render if viewing this subagent
    if (state.appState.activeAgentView === subagentId) {
        debouncedUpdate();
    }
}

/**
 * Add a user prompt node to the current step.
 * 
 * @param {Object} promptData - Prompt data from the server
 */
export function addUserPromptNode(promptData) {
    const stepNum = state.appState.currentStepNumber;
    const stepNode = getOrCreateStepNode(state.appState.currentFrameId, stepNum);

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
    state.appState.stepsWithTools.add(state.appState.currentStepNumber);

    // Update "Latest" timestamp
    const now = new Date();
    const timeStr = now.toLocaleTimeString();
    const latestEl = document.getElementById("state-latest");
    if (latestEl) {
        latestEl.textContent = `User Prompt @ ${timeStr}`;
    }

    debouncedUpdate();
}

// ============================================================================
// Layout & Rendering
// ============================================================================

/**
 * Compute custom layout for the tree.
 * 
 * @param {Object} root - Root node
 * @returns {{nodes: Array, totalHeight: number}} Layout result
 */
function computeLayout(root) {
    const nodes = [];
    let currentY = 20;

    function traverse(node) {
        if (node.type === 'step') {
            const hasTools = node.children && node.children.length > 0;
            if (!hasTools) return;

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
        }

        if (node.children) {
            node.children.forEach(traverse);
        }
    }

    traverse(root);
    return { nodes, totalHeight: currentY };
}

/**
 * Debounced update - prevents too many rapid re-renders.
 */
export function debouncedUpdate() {
    if (updateTimeout) clearTimeout(updateTimeout);
    updateTimeout = setTimeout(() => {
        update();
    }, 100);
}

/**
 * Update the D3 visualization.
 */
export function update() {
    if (!g) return;

    const activeRootNode = state.getActiveRootNode();
    const { nodes, totalHeight } = computeLayout(activeRootNode);
    const cardWidth = 320;
    const cardHeight = 60;

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
        .text(d => `STEP ${d.data.step_number !== undefined ? d.data.step_number : '?'}`);

    // --- TOOL Card ---
    const toolGroup = nodeEnter.filter(d => d.type === 'tool');
    renderToolCard(toolGroup, cardWidth, cardHeight);

    // --- PHASE Banner ---
    const phaseGroup = nodeEnter.filter(d => d.type === 'phase_marker');
    renderPhaseBanner(phaseGroup, cardWidth);

    // --- USER PROMPT Banner ---
    const userPromptGroup = nodeEnter.filter(d => d.type === 'user_prompt');
    renderUserPromptBanner(userPromptGroup, cardWidth);

    // --- Update Transitions ---
    node.merge(nodeEnter).transition().duration(duration)
        .attr("transform", d => `translate(${d.x},${d.y})`)
        .style("opacity", d => {
            if (d.type === 'tool' && state.appState.summarizedTools.has(d.id)) {
                return 0.5;
            }
            return 1;
        });

    // Update stroke color based on summarization status
    node.merge(nodeEnter).selectAll('rect')
        .style("stroke", d => {
            if (d.type === 'tool') {
                return state.appState.summarizedTools.has(d.id) ? "#333" : "var(--accent-blue)";
            }
            return null;
        })
        .style("stroke-width", d => {
            if (d.type === 'tool') {
                return state.appState.summarizedTools.has(d.id) ? "1px" : "2px";
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

// ============================================================================
// Rendering Helpers
// ============================================================================

/**
 * Render a tool card node.
 */
function renderToolCard(group, cardWidth, cardHeight) {
    group.append('rect')
        .attr('x', -cardWidth / 2)
        .attr('y', 0)
        .attr('width', cardWidth)
        .attr('height', cardHeight)
        .attr('rx', 6)
        .style("fill", "#0d0d0d")
        .style("stroke", "#2a2a2a")
        .style("stroke-width", "1px");

    group.append('circle')
        .attr('cx', -cardWidth / 2 + 32)
        .attr('cy', cardHeight / 2)
        .attr('r', 22)
        .style("fill", "#111")
        .style("stroke", "#444");

    group.append('text')
        .attr('x', -cardWidth / 2 + 32)
        .attr('y', cardHeight / 2)
        .attr("dy", "7px")
        .attr("text-anchor", "middle")
        .style("font-size", "24px")
        .style("fill", "#fff")
        .text(d => getNodeIcon(d.type, d.name));

    group.append('text')
        .attr('x', -cardWidth / 2 + 70)
        .attr('y', cardHeight / 3 + 3)
        .style("font-size", "13px")
        .style("font-weight", "bold")
        .style("fill", "#eee")
        .text(d => d.name.toUpperCase());

    group.append('text')
        .attr('x', -cardWidth / 2 + 70)
        .attr('y', cardHeight * 0.72)
        .style("font-size", "10px")
        .style("fill", "#777")
        .text(d => {
            const p = d.data.input?.purpose || "";
            return p.length > 40 ? p.substring(0, 37) + "..." : p;
        });
}

/**
 * Render a phase transition banner.
 */
function renderPhaseBanner(group, cardWidth) {
    const phaseWidth = cardWidth + 40;
    const phaseHeight = 42;

    group.append('rect')
        .attr('x', -phaseWidth / 2)
        .attr('y', 0)
        .attr('width', phaseWidth)
        .attr('height', phaseHeight)
        .attr('rx', 4)
        .style("fill", "#2d2d30")
        .style("stroke", "#007acc")
        .style("stroke-width", "1px");

    group.append('rect')
        .attr('x', -phaseWidth / 2)
        .attr('y', 0)
        .attr('width', 4)
        .attr('height', phaseHeight)
        .attr('rx', 2)
        .style("fill", "#007acc");

    group.append('circle')
        .attr('cx', -phaseWidth / 2 + 28)
        .attr('cy', phaseHeight / 2)
        .attr('r', 14)
        .style("fill", "#1e1e1e")
        .style("stroke", "#007acc")
        .style("stroke-width", "1.5px");

    group.append('text')
        .attr('x', -phaseWidth / 2 + 28)
        .attr('y', phaseHeight / 2)
        .attr("dy", "5px")
        .attr("text-anchor", "middle")
        .style("font-size", "14px")
        .style("fill", "#007acc")
        .text(d => getPhaseIcon(d.name));

    group.append('text')
        .attr('x', -phaseWidth / 2 + 55)
        .attr('y', phaseHeight / 2 + 1)
        .attr("dy", "4px")
        .attr("text-anchor", "start")
        .style("font-family", "var(--font-code)")
        .style("font-size", "13px")
        .style("font-weight", "600")
        .style("fill", "#cccccc")
        .style("letter-spacing", "0.5px")
        .text(d => `PHASE: ${d.name}`);

    group.append('text')
        .attr('x', phaseWidth / 2 - 15)
        .attr('y', phaseHeight / 2)
        .attr("dy", "4px")
        .attr("text-anchor", "end")
        .style("font-family", "var(--font-code)")
        .style("font-size", "11px")
        .style("fill", "#555")
        .text('>');
}

/**
 * Render a user prompt banner.
 */
function renderUserPromptBanner(group, cardWidth) {
    group.append('rect')
        .attr('x', -cardWidth / 2)
        .attr('y', 0)
        .attr('width', cardWidth)
        .attr('height', 50)
        .attr('rx', 8)
        .style("fill", "rgba(156, 39, 176, 0.1)")
        .style("stroke", "#9c27b0")
        .style("stroke-width", "2px")
        .style("filter", "drop-shadow(0 0 8px rgba(156, 39, 176, 0.5))");

    group.append('circle')
        .attr('cx', -cardWidth / 2 + 30)
        .attr('cy', 25)
        .attr('r', 18)
        .style("fill", "rgba(156, 39, 176, 0.2)")
        .style("stroke", "#9c27b0");

    group.append('text')
        .attr('x', -cardWidth / 2 + 30)
        .attr('y', 25)
        .attr("dy", "6px")
        .attr("text-anchor", "middle")
        .style("font-size", "20px")
        .style("fill", "#fff")
        .text('💬');

    group.append('text')
        .attr('x', -cardWidth / 2 + 60)
        .attr('y', 18)
        .style("font-size", "11px")
        .style("font-weight", "bold")
        .style("fill", "#9c27b0")
        .style("text-transform", "uppercase")
        .text("User Intervention");

    group.append('text')
        .attr('x', -cardWidth / 2 + 60)
        .attr('y', 36)
        .style("font-size", "10px")
        .style("fill", "#ccc")
        .text(d => {
            const content = d.data.content || "";
            return content.length > 45 ? content.substring(0, 42) + "..." : content;
        });
}

// ============================================================================
// Details Panel
// ============================================================================

/**
 * Show details for a selected node in the right panel.
 * 
 * @param {Object} d - Node data
 */
export function showDetails(d) {
    const detailsContent = document.getElementById('details-content');
    if (!detailsContent) return;

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
    } else if (d.type === 'step') {
        html += `<div class="tool-badge" style="background:#222">STEP ${toolData.step_number}</div>`;
        html += `<p style="color:#888">Agent execution step container.</p>`;
    }

    html += `</div>`;
    detailsContent.innerHTML = html;
}

// ============================================================================
// Context Switching (for Orchestrator mode)
// ============================================================================

// ============================================================================
// Context Switching (for Orchestrator mode)
// ============================================================================

/**
 * Reset zoom and pan to initial state (top center).
 */
export function resetZoom() {
    if (!svg || !zoomBehavior) return;
    svg.call(zoomBehavior.transform, d3.zoomIdentity.translate(0, 0));
}

/**
 * Load orchestrator graph data (switch view back to orchestrator).
 */
export function loadOrchestratorData() {
    state.setActiveAgentView('orchestrator');
    resetZoom();
    debouncedUpdate();
}

/**
 * Load subagent graph data (switch view to show subagent's tools).
 * 
 * @param {string} subagentId - The subagent ID to show
 */
export function loadSubagentData(subagentId) {
    state.setActiveAgentView(subagentId);
    resetZoom();
    debouncedUpdate();
}
