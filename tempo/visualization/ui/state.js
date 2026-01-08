/**
 * State Management Module
 * 
 * Centralized state management for the visualization UI.
 * All modules import state from here to ensure consistency.
 * 
 * Uses a single state object pattern to ensure all modules share
 * the same references, preventing bugs when state is reset.
 * 
 * @module state
 */

// ============================================================================
// Core Application State
// ============================================================================

/**
 * Centralized application state object.
 * All state is accessed through this object to ensure proper mutation semantics.
 * 
 * @type {Object}
 */
export const appState = {
    /**
     * Root node of the tree for the orchestrator view.
     * This is the root of the D3 tree structure containing steps and tool calls.
     * @type {Object}
     */
    rootNode: { id: "root", name: "ROOT", type: "root", children: [] },

    /**
     * Map of frame IDs to frame node objects.
     * Frames represent agent execution contexts (e.g., main or sub-agents).
     * @type {Map<string, Object>}
     */
    frames: new Map(),

    /**
     * ID of the currently viewed agent ('orchestrator' or a subagent ID).
     * Controls which graph data is displayed.
     * @type {string}
     */
    activeAgentView: 'orchestrator',

    /**
     * Map of step key (frameId-stepNum) to step node objects.
     * @type {Map<string, Object>}
     */
    steps: new Map(),

    /**
     * Currently active frame ID.
     * @type {string}
     */
    currentFrameId: "root",

    /**
     * Current step number in the active frame.
     * @type {number}
     */
    currentStepNumber: 0,

    /**
     * Set of step numbers that have tool calls attached.
     * @type {Set<number>}
     */
    stepsWithTools: new Set(),

    /**
     * Set of tool call IDs that have been summarized.
     * Used to visually distinguish condensed tools in the graph.
     * @type {Set<string>}
     */
    summarizedTools: new Set(),

    /**
     * WebSocket connection status.
     * @type {boolean}
     */
    isConnected: false,

    /**
     * Test plan items from the HYPOTHESIZE phase.
     * @type {Array<Object>}
     */
    testPlanItems: [],

    /**
     * Context window data for the context tab.
     * @type {Object|null}
     */
    contextData: null,

    /**
     * Indices of expanded items in the context window.
     * @type {Set<number>}
     */
    expandedItems: new Set(),

    /**
     * List of currently available tool names.
     * @type {Array<string>}
     */
    availableTools: []
};

// Initialize root frame
appState.frames.set("root", appState.rootNode);

// ============================================================================
// Convenience Exports (for backward compatibility)
// ============================================================================

// These getters allow existing code to access state properties directly
// while still using the centralized appState object.

/** @returns {{id: string, name: string, type: string, children: Array}} */
export function getRootNode() { return appState.rootNode; }

/** @returns {Map<string, Object>} */
export function getFrames() { return appState.frames; }

/** @returns {Map<string, Object>} */
export function getSteps() { return appState.steps; }

/** @returns {string} */
export function getCurrentFrameId() { return appState.currentFrameId; }

/** @returns {number} */
export function getCurrentStepNumber() { return appState.currentStepNumber; }

/** @returns {Set<number>} */
export function getStepsWithTools() { return appState.stepsWithTools; }

/** @returns {Set<string>} */
export function getSummarizedTools() { return appState.summarizedTools; }

/** @returns {boolean} */
export function getIsConnected() { return appState.isConnected; }

/** @returns {Array<Object>} */
export function getTestPlanItems() { return appState.testPlanItems; }

/** @returns {Object|null} */
export function getContextData() { return appState.contextData; }

/** @returns {Set<number>} */
export function getExpandedItems() { return appState.expandedItems; }

/** @returns {Array<string>} */
export function getAvailableTools() { return appState.availableTools; }

// ============================================================================
// State Mutation Functions
// ============================================================================

/**
 * Set the root node (replaces current root).
 * @param {{id: string, name: string, type: string, children: Array}} node - New root node
 */
export function setRootNode(node) {
    appState.rootNode = node;
    appState.frames.set("root", node);
}

/**
 * Set the current frame ID.
 * @param {string} frameId - New frame ID
 */
export function setCurrentFrameId(frameId) {
    appState.currentFrameId = frameId;
}

/**
 * Set the current step number.
 * @param {number} stepNum - New step number
 */
export function setCurrentStepNumber(stepNum) {
    appState.currentStepNumber = stepNum;
}

/**
 * Set the WebSocket connection status.
 * @param {boolean} connected - Connection status
 */
export function setConnected(connected) {
    appState.isConnected = connected;
}

/**
 * Set the test plan items.
 * @param {Array<Object>} items - Test plan items
 */
export function setTestPlanItems(items) {
    appState.testPlanItems = items;
}

/**
 * Set the context window data.
 * @param {Object} data - Context data from API
 */
export function setContextData(data) {
    appState.contextData = data;
}

/**
 * Set the available tools list.
 * @param {Array<string>} tools - Tool names
 */
export function setAvailableTools(tools) {
    appState.availableTools = tools;
}

/**
 * Toggle an expanded item in the context window.
 * @param {number} index - Item index
 * @returns {boolean} New expanded state
 */
export function toggleExpandedItem(index) {
    if (appState.expandedItems.has(index)) {
        appState.expandedItems.delete(index);
        return false;
    } else {
        appState.expandedItems.add(index);
        return true;
    }
}

// ============================================================================
// Agent Hierarchy State (for Orchestrator mode)
// ============================================================================

/**
 * Tracks the orchestrator and all subagent runs.
 */
export const agentHierarchy = {
    orchestrator: {
        id: 'orchestrator',
        model: '',
        steps: 0,
        active: true,
    },
    subagents: [],
};

/**
 * Aggregated findings summary across all agents.
 */
export const findingsSummary = {
    critical: 0,
    high: 0,
    medium: 0,
    low: 0,
    surfaces_total: 0,
    surfaces_tested: 0,
};

// ============================================================================
// Agent Hierarchy Mutation Functions
// ============================================================================

/**
 * Add a new subagent to the hierarchy.
 * @param {Object} subagentData - Subagent data from event
 */
export function addSubagent(subagentData) {
    console.log('[DEBUG] addSubagent called with:', subagentData);
    const count = agentHierarchy.subagents.length + 1;
    const newSubagent = {
        id: subagentData.subagent_id,
        type: subagentData.subagent_type,
        name: `${subagentData.subagent_type}_${count}`,
        objective: subagentData.objective || '',
        parent_id: subagentData.parent_id || 'orchestrator',
        status: 'running',
        steps: 0,
        findings: 0,
        surfaces: 0,
        active: false,
        // Per-subagent graph state for visualization
        rootNode: { id: `${subagentData.subagent_id}-root`, name: "ROOT", type: "root", children: [] },
        frames: new Map(),
        stepsMap: new Map(),
        currentFrameId: `${subagentData.subagent_id}-root`,
        currentStepNumber: 0,
    };
    console.log('[DEBUG] addSubagent storing:', newSubagent.id, 'parent:', newSubagent.parent_id);
    agentHierarchy.subagents.push(newSubagent);
}

/**
 * Update a subagent's properties.
 * @param {string} subagentId - Subagent ID
 * @param {Object} updates - Properties to update
 */
export function updateSubagent(subagentId, updates) {
    const subagent = agentHierarchy.subagents.find(s => s.id === subagentId);
    if (subagent) {
        Object.assign(subagent, updates);
    }
}

/**
 * Set which agent is currently active (selected in UI).
 * @param {string} agentId - Agent ID to activate
 */
export function setActiveAgent(agentId) {
    agentHierarchy.orchestrator.active = (agentId === 'orchestrator');
    agentHierarchy.subagents.forEach(s => {
        s.active = (s.id === agentId);
    });
}

/**
 * Set the active agent view for graph display.
 * @param {string} agentId - Agent ID to view ('orchestrator' or subagent ID)
 */
export function setActiveAgentView(agentId) {
    appState.activeAgentView = agentId;
}

/**
 * Get the root node for the currently active agent view.
 * @returns {Object} Root node for the active view
 */
export function getActiveRootNode() {
    if (appState.activeAgentView === 'orchestrator') {
        return appState.rootNode;
    }

    // Find the subagent and return its rootNode
    const subagent = agentHierarchy.subagents.find(s => s.id === appState.activeAgentView);
    if (subagent && subagent.rootNode) {
        return subagent.rootNode;
    }

    // Fallback to main rootNode
    return appState.rootNode;
}

/**
 * Update findings summary.
 * @param {Object} summary - Findings summary data
 */
export function updateFindingsSummary(summary) {
    Object.assign(findingsSummary, summary);
}

/**
 * Reset agent hierarchy (call on new session).
 */
export function resetAgentHierarchy() {
    agentHierarchy.orchestrator = { id: 'orchestrator', model: '', steps: 0, active: true };
    agentHierarchy.subagents = [];
    Object.assign(findingsSummary, { critical: 0, high: 0, medium: 0, low: 0, surfaces_total: 0, surfaces_tested: 0 });
}

/**
 * Reset all state to initial values.
 * Useful for starting a fresh session.
 */
export function resetState() {
    appState.rootNode = { id: "root", name: "ROOT", type: "root", children: [] };
    appState.frames.clear();
    appState.steps.clear();
    appState.frames.set("root", appState.rootNode);
    appState.currentFrameId = "root";
    appState.currentStepNumber = 0;
    appState.stepsWithTools.clear();
    appState.summarizedTools.clear();
    appState.testPlanItems = [];
    appState.contextData = null;
    appState.expandedItems.clear();
    appState.availableTools = [];
    resetAgentHierarchy();
}
