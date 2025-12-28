/**
 * Event Handling Module
 * 
 * Dispatches WebSocket events to appropriate handlers.
 * Acts as the central hub connecting ws.js events to
 * state updates, graph updates, and panel updates.
 * 
 * @module events
 */

import * as state from './state.js';
import * as graph from './graph.js';
import * as panels from './panels.js';
import * as ws from './ws.js';
import * as agentTree from './agentTree.js';

// ============================================================================
// Event Dispatch
// ============================================================================

/**
 * Handle an incoming WebSocket event.
 * Dispatches to appropriate handler based on event type.
 * 
 * @param {Object} event - Event object with type and data
 */
export function handleEvent(event) {
    if (!event.type) return;

    const data = event.data || {};
    const frameId = data.frame_id;

    // Handle new frames
    if (frameId && !state.appState.frames.has(frameId)) {
        const parentFrame = state.appState.frames.get(state.appState.currentFrameId) || state.appState.rootNode;
        const newFrame = {
            id: frameId,
            name: `FRAME`,
            type: "frame",
            children: [],
            parent: parentFrame
        };
        state.appState.frames.set(frameId, newFrame);
        if (!parentFrame.children) parentFrame.children = [];
        parentFrame.children.push(newFrame);
        state.setCurrentFrameId(frameId);
    }

    // Update current context
    if (frameId) state.setCurrentFrameId(frameId);
    if (data.step_number !== undefined) state.setCurrentStepNumber(data.step_number);

    // Dispatch by event type
    switch (event.type) {
        case "start":
            handleStart(data);
            break;

        case "tool_call":
            graph.addToolNode(data);
            break;

        case "step":
            handleStep(data);
            break;

        case "summarized":
            handleSummarized(data);
            break;

        case "paused":
            handlePaused(data);
            break;

        case "resumed":
            handleResumed();
            break;

        case "user_prompt_injected":
            handleUserPromptInjected(data);
            break;

        case "finish":
            handleFinish(data);
            break;

        case "cost_update":
            panels.updateCostPanel(data);
            break;

        case "test_plan_update":
            panels.handleTestPlanUpdate(data.items);
            break;

        case "available_tools":
            panels.updateAvailableToolsPanel(data.tools);
            break;

        case "subagent_start":
            handleSubagentStart(data);
            break;

        case "subagent_finish":
            handleSubagentFinish(data);
            break;

        case "findings_update":
            handleFindingsUpdate(data);
            break;
    }
}

// ============================================================================
// Event Handlers
// ============================================================================

/**
 * Handle agent start event.
 */
function handleStart(data) {
    if (data.model) {
        const modelEl = document.getElementById("state-model");
        if (modelEl) modelEl.textContent = data.model;

        // Update orchestrator state for agent tree
        state.agentHierarchy.orchestrator.model = data.model;
        agentTree.render();
    }
}

/**
 * Handle step completion event.
 */
function handleStep(data) {
    // Update phase display
    if (data.phase) {
        const phaseEl = document.getElementById("state-phase");
        if (phaseEl) phaseEl.textContent = data.phase;
    }

    // Update step number display
    if (data.step_number !== undefined && data.step_number !== null) {
        const stepEl = document.getElementById("state-step");
        if (stepEl) stepEl.textContent = data.step_number;
    }

    // Create step node and update visualization
    graph.getOrCreateStepNode(state.appState.currentFrameId, data.step_number);
    graph.debouncedUpdate();
}

/**
 * Handle tool summarization event.
 */
function handleSummarized(data) {
    if (data.tool_call_id) {
        state.appState.summarizedTools.add(data.tool_call_id);
        graph.debouncedUpdate();
    }
}

/**
 * Handle agent paused event.
 */
function handlePaused(data) {
    const statusEl = document.getElementById('status');
    if (statusEl) {
        statusEl.textContent = "PAUSED";
        statusEl.className = "status paused";
    }

    const promptStatusEl = document.getElementById("prompt-status");
    if (promptStatusEl) {
        promptStatusEl.textContent = data.reason || "Agent paused. Send a prompt to continue.";
    }
}

/**
 * Handle agent resumed event.
 */
function handleResumed() {
    const statusEl = document.getElementById('status');
    if (statusEl) {
        statusEl.textContent = "CONNECTED";
        statusEl.className = "status connected";
    }

    const promptStatusEl = document.getElementById("prompt-status");
    if (promptStatusEl) {
        promptStatusEl.textContent = "";
    }
}

/**
 * Handle user prompt injection event.
 */
function handleUserPromptInjected(data) {
    graph.addUserPromptNode(data);

    const promptStatusEl = document.getElementById("prompt-status");
    if (promptStatusEl) {
        promptStatusEl.textContent = "✓ Prompt injected: " + (data.content_preview || "").substring(0, 50) + "...";
    }
}

/**
 * Handle agent finish event.
 */
function handleFinish(data) {
    const statusEl = document.getElementById('status');
    if (statusEl) {
        statusEl.textContent = data.success ? "FINISHED" : "FAILED";
        statusEl.className = "status " + (data.success ? "connected" : "disconnected");
    }
}

/**
 * Handle subagent start event.
 */
function handleSubagentStart(data) {
    state.addSubagent(data);
    agentTree.render();
}

/**
 * Handle subagent finish event.
 */
function handleSubagentFinish(data) {
    state.updateSubagent(data.subagent_id, {
        status: data.success ? 'complete' : 'failed',
        findings: data.findings_count || 0,
        surfaces: data.surfaces_count || 0,
    });
    agentTree.render();
}

/**
 * Handle findings update event.
 */
function handleFindingsUpdate(data) {
    state.updateFindingsSummary(data);
    agentTree.render();
}

// ============================================================================
// Prompt Input Handling
// ============================================================================

/**
 * Initialize prompt input handling.
 */
export function initPromptInput() {
    const promptInput = document.getElementById('prompt-input');
    const sendPromptBtn = document.getElementById('send-prompt-btn');
    const promptStatus = document.getElementById('prompt-status');

    if (!promptInput || !sendPromptBtn) return;

    /**
     * Send the current prompt.
     */
    function sendPrompt() {
        const content = promptInput.value.trim();

        if (!content) {
            showPromptFeedback("Please enter a prompt.", "#ff9800");
            return;
        }

        if (!ws.isConnected()) {
            showPromptFeedback("Not connected. Please wait...", "#ff3232");
            return;
        }

        // Send via WebSocket
        ws.sendUserPrompt(content);

        // Clear input and show success
        promptInput.value = '';
        showPromptFeedback("✓ Prompt sent!", "");
    }

    /**
     * Show temporary feedback message.
     */
    function showPromptFeedback(message, color) {
        if (promptStatus) {
            promptStatus.textContent = message;
            promptStatus.style.color = color;

            // Clear after delay (unless it's a success message)
            if (message !== "✓ Prompt sent!") {
                setTimeout(() => {
                    promptStatus.textContent = "";
                    promptStatus.style.color = "";
                }, 3000);
            } else {
                setTimeout(() => {
                    if (promptStatus.textContent === "✓ Prompt sent!") {
                        promptStatus.textContent = "";
                    }
                }, 5000);
            }
        }
    }

    // Button click
    sendPromptBtn.addEventListener('click', sendPrompt);

    // Keyboard shortcut (Ctrl+Enter or Cmd+Enter)
    promptInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            sendPrompt();
        }
    });
}

// ============================================================================
// Stop Button Handling
// ============================================================================

/**
 * Initialize stop button handling.
 */
export function initStopButton() {
    const stopBtn = document.getElementById('stop-btn');
    const statusEl = document.getElementById('status');

    if (!stopBtn) return;

    stopBtn.addEventListener('click', () => {
        if (!ws.isConnected()) return;

        // Confirm first
        if (!confirm("Are you sure you want to stop the agent?")) return;

        ws.sendStopSignal();

        stopBtn.textContent = "STOPPING...";
        stopBtn.disabled = true;
        if (statusEl) statusEl.textContent = "STOPPING";
    });
}

// ============================================================================
// Context Refresh Button
// ============================================================================

/**
 * Initialize context refresh button.
 */
export function initContextRefresh() {
    const refreshBtn = document.getElementById('context-refresh-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', panels.loadContextWindow);
    }
}
