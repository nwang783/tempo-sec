/**
 * Agent Tree Module
 * 
 * Renders the hierarchical agent tree showing orchestrator and subagents.
 * Supports switching between agents to view their context.
 * 
 * @module agentTree
 */

import * as state from './state.js';
import * as graph from './graph.js';
import * as panels from './panels.js';
import { escapeHtml } from './utils.js';

// Status icon mapping
const STATUS_ICONS = {
    'running': '⏳',
    'complete': '✓',
    'failed': '✗',
    'queued': '📋',
};

const TYPE_ICONS = {
    'recon': '📡',
    'test': '🔬',
    'orchestrator': '🎯',
    'browser': '🌐',
};

/**
 * Render the agent tree panel.
 */
export function render() {
    const container = document.getElementById('agent-tree-content');
    if (!container) return;

    const { orchestrator, subagents } = state.agentHierarchy;

    // Only show if we have orchestrator data
    if (!orchestrator.model) {
        container.innerHTML = '<div class="agent-tree-empty">Waiting for agent start...</div>';
        return;
    }

    let html = renderOrchestratorNode(orchestrator);

    // Render first-level subagents (parent is orchestrator)
    const firstLevelSubagents = subagents.filter(s => s.parent_id === 'orchestrator');
    for (const subagent of firstLevelSubagents) {
        html += renderSubagentNode(subagent, 1);

        // Render any child subagents (e.g., browser agents)
        const children = subagents.filter(s => s.parent_id === subagent.id);
        for (const child of children) {
            html += renderSubagentNode(child, 2);
        }
    }

    html += renderFindingsSummary(state.findingsSummary);

    container.innerHTML = html;
    attachEventListeners();
}

/**
 * Render the orchestrator node.
 */
function renderOrchestratorNode(orchestrator) {
    const activeClass = orchestrator.active ? 'active' : '';

    return `
        <div class="agent-node orchestrator ${activeClass}" data-agent-id="orchestrator">
            <div class="agent-header">
                <span class="agent-icon">${TYPE_ICONS.orchestrator}</span>
                <span class="agent-name">Orchestrator</span>
            </div>
            <div class="agent-details">
                <div>Model: ${escapeHtml(orchestrator.model)}</div>
                <div>Steps: ${orchestrator.steps}</div>
            </div>
        </div>
    `;
}

/**
 * Render a subagent node.
 */
function renderSubagentNode(subagent, depth = 1) {
    const statusIcon = STATUS_ICONS[subagent.status] || '?';
    const typeIcon = TYPE_ICONS[subagent.type] || '🔧';
    const activeClass = subagent.active ? 'active' : '';
    const statusClass = subagent.status === 'failed' ? 'status-failed' : '';
    const nestedClass = depth > 1 ? 'nested-subagent' : '';

    return `
        <div class="agent-node subagent ${activeClass} ${statusClass} ${nestedClass}" data-agent-id="${subagent.id}">
            <div class="agent-header">
                <span class="agent-icon">${typeIcon}</span>
                <span class="agent-name">${escapeHtml(subagent.name)}</span>
                <span class="status-icon">${statusIcon}</span>
            </div>
            <div class="agent-details">
                <div>Steps: ${subagent.steps}</div>
                ${subagent.findings > 0 ? `<div>Findings: ${subagent.findings}</div>` : ''}
                ${subagent.surfaces > 0 ? `<div>Surfaces: ${subagent.surfaces}</div>` : ''}
            </div>
        </div>
    `;
}

/**
 * Render the findings summary section.
 */
function renderFindingsSummary(summary) {
    const { critical, high, medium, low, surfaces_total, surfaces_tested } = summary;
    const hasFindings = critical + high + medium + low > 0;

    if (!hasFindings && surfaces_total === 0) {
        return '';
    }

    return `
        <div class="findings-summary">
            <div class="findings-summary-title">📊 Findings Summary</div>
            <div class="findings-counts">
                ${critical > 0 ? `<span class="finding-badge critical">Critical: ${critical}</span>` : ''}
                ${high > 0 ? `<span class="finding-badge high">High: ${high}</span>` : ''}
                ${medium > 0 ? `<span class="finding-badge medium">Medium: ${medium}</span>` : ''}
                ${low > 0 ? `<span class="finding-badge low">Low: ${low}</span>` : ''}
            </div>
            ${surfaces_total > 0 ? `
                <div class="surfaces-count">
                    Attack Surfaces: ${surfaces_tested} / ${surfaces_total} tested
                </div>
            ` : ''}
        </div>
    `;
}

/**
 * Attach click handlers to agent nodes.
 */
function attachEventListeners() {
    document.querySelectorAll('.agent-node').forEach(node => {
        node.addEventListener('click', (e) => {
            e.stopPropagation(); // Prevent bubbling
            const agentId = node.dataset.agentId;
            console.log('[DEBUG] agentTree click: agentId=', agentId, 'node=', node);
            switchToAgentView(agentId);
        });
    });
}

/**
 * Switch the view to show a specific agent's context.
 * @param {string} agentId - The agent ID to switch to
 */
export function switchToAgentView(agentId) {
    state.setActiveAgent(agentId);
    render();

    // Update graph view and context for selected agent
    if (agentId === 'orchestrator') {
        graph.loadOrchestratorData();
        panels.loadContextWindow();  // Load orchestrator's context
    } else {
        graph.loadSubagentData(agentId);
        panels.loadSubagentContext(agentId);  // Load subagent's context
    }
}

/**
 * Initialize the agent tree (called on app start).
 */
export function init() {
    render();
}
