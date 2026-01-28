/**
 * Tempo Sec Visualization App
 * 
 * Entry point for the visualization UI.
 * Initializes all modules and establishes WebSocket connection.
 * 
 * Architecture:
 * - state.js    : Centralized state management
 * - utils.js    : Pure utility functions
 * - ws.js       : WebSocket connection handling
 * - graph.js    : D3.js tree visualization
 * - panels.js   : UI panel components (cost, test plan, context)
 * - events.js   : Event dispatch and handling
 * 
 * @module app
 */

import * as graph from './graph.js';
import * as panels from './panels.js';
import * as events from './events.js';
import * as ws from './ws.js';
import * as agentTree from './agentTree.js';

// ============================================================================
// Initialization
// ============================================================================

/**
 * Initialize the application.
 * Called when DOM is ready.
 */
function init() {
    console.log('Tempo Sec Visualization initializing...');

    // Initialize graph visualization
    const treeContainer = document.getElementById('tree-container');
    if (treeContainer) {
        graph.init(treeContainer);
    }

    // Initialize UI panels
    panels.initTabs();
    panels.initCollapsibleSections();

    // Initialize event handlers
    events.initPromptInput();
    events.initStopButton();
    events.initPauseButton();
    events.initContextRefresh();

    // Initialize agent tree
    agentTree.init();

    // Wire up WebSocket to event handler
    ws.setOnMessage(events.handleEvent);
    ws.setOnConnect(() => {
        graph.debouncedUpdate();
    });

    // Connect to server
    ws.connect();

    console.log('Tempo Sec Visualization ready');
}

// Start when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
