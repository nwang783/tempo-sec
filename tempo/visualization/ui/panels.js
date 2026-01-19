/**
 * UI Panels Module
 * 
 * Handles rendering and updates for the various UI panels:
 * - Cost tracking panel
 * - Test plan panel
 * - Context window panel
 * - Tab switching
 * 
 * @module panels
 */

import * as state from './state.js';
import { escapeHtml, getPreview, getRoleIcon, getToolIcon } from './utils.js';

// ============================================================================
// Cost Panel
// ============================================================================

/**
 * Update the cost tracking panel with new data.
 * 
 * @param {Object} data - Cost update data
 * @param {number} data.total_cost - Total cost so far
 * @param {number} data.total_cached_tokens - Total cached tokens
 * @param {number} data.total_prompt_tokens - Total prompt tokens
 * @param {number} data.total_completion_tokens - Total completion tokens
 */
export function updateCostPanel(data) {
    const totalCostEl = document.getElementById('cost-total');
    const cachedEl = document.getElementById('cost-cached');
    const promptEl = document.getElementById('cost-prompt');
    const completionEl = document.getElementById('cost-completion');

    if (!totalCostEl) return;

    // Format cost with 4 decimal places
    const costFormatted = `$${data.total_cost.toFixed(4)}`;
    totalCostEl.textContent = costFormatted;

    // Flash animation
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

// ============================================================================
// Test Plan Panel
// ============================================================================

/**
 * Handle a test plan update from the server.
 * 
 * @param {Array<Object>} items - Test plan items
 */
export function handleTestPlanUpdate(items) {
    state.setTestPlanItems(items || []);
    renderTestPlan();
}

/**
 * Render the test plan panel.
 */
export function renderTestPlan() {
    const container = document.getElementById('testplan-items');
    const progressEl = document.getElementById('testplan-progress');

    if (!container || !progressEl) return;

    const items = state.appState.testPlanItems;

    if (!items || items.length === 0) {
        container.innerHTML = '<div class="testplan-empty">No test plan created yet. Waiting for HYPOTHESIZE phase...</div>';
        progressEl.textContent = '0 / 0 completed';
        return;
    }

    // Calculate progress
    const completed = items.filter(item =>
        item.status === 'completed' || item.status === 'skipped'
    ).length;
    progressEl.textContent = `${completed} / ${items.length} completed`;

    // Sort by priority (high first), then by status (pending first)
    const priorityOrder = { high: 0, medium: 1, low: 2 };
    const statusOrder = { pending: 0, in_progress: 1, completed: 2, skipped: 3 };

    const sortedItems = [...items].sort((a, b) => {
        const statusDiff = (statusOrder[a.status] || 0) - (statusOrder[b.status] || 0);
        if (statusDiff !== 0) return statusDiff;
        return (priorityOrder[a.priority] || 1) - (priorityOrder[b.priority] || 1);
    });

    // Render items
    container.innerHTML = sortedItems.map(item => {
        const isComplete = item.status === 'completed' || item.status === 'skipped';
        const checkmark = isComplete ? '✓' : '';

        let reasonHtml = '';
        if (item.reason) {
            reasonHtml = `<div class="testplan-item-reason">${escapeHtml(item.reason)}</div>`;
        }

        return `
            <div class="testplan-item priority-${item.priority || 'medium'} status-${item.status || 'pending'}">
                <div class="testplan-checkbox">${checkmark}</div>
                <div class="testplan-item-content">
                    <div class="testplan-item-description">${escapeHtml(item.description)}</div>
                    <div class="testplan-item-meta">
                        <span class="testplan-item-priority">${item.priority || 'medium'}</span>
                        <span class="testplan-item-status">${item.status || 'pending'}</span>
                    </div>
                    ${reasonHtml}
                </div>
            </div>
        `;
    }).join('');
}

// ============================================================================
// Available Tools Panel
// ============================================================================

/**
 * Update the available tools panel with current tools.
 * 
 * @param {Array<string>} tools - List of available tool names
 */
export function updateAvailableToolsPanel(tools) {
    state.setAvailableTools(tools);
    const container = document.getElementById('available-tools-list');
    if (!container) return;

    if (!tools || tools.length === 0) {
        container.innerHTML = '<div class="tools-empty">No tools available</div>';
        return;
    }

    container.innerHTML = tools.map(name =>
        `<div class="tool-item"><span class="tool-icon">⚙</span> ${escapeHtml(name)}</div>`
    ).join('');
}

// ============================================================================
// Context Window Panel
// ============================================================================

/**
 * Load and display the context window.
 */
export async function loadContextWindow() {
    const container = document.getElementById('context-items');
    const totalTokensEl = document.getElementById('context-total-tokens');
    const messageCountEl = document.getElementById('context-message-count');

    if (!container) return;

    container.innerHTML = '<div class="context-empty">Loading context window...</div>';

    try {
        const response = await fetch('/api/context');
        if (!response.ok) {
            if (response.status === 404) {
                container.innerHTML = '<div class="context-empty">No active session. Start an agent run to see context.</div>';
                return;
            }
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        state.setContextData(data);
        renderContextWindow();

        // Update stats
        if (totalTokensEl) {
            totalTokensEl.textContent = `${data.total_tokens.toLocaleString()} tokens`;
        }
        if (messageCountEl) {
            const msgCount = data.messages.length;
            messageCountEl.textContent = `${msgCount} items`;
        }
    } catch (error) {
        console.error('Failed to load context:', error);
        container.innerHTML = `<div class="context-empty">Failed to load context: ${error.message}</div>`;
    }
}

/**
 * Load and display context for a specific subagent.
 * 
 * @param {string} subagentId - The subagent ID to load context for
 */
export async function loadSubagentContext(subagentId) {
    const container = document.getElementById('context-items');
    const totalTokensEl = document.getElementById('context-total-tokens');
    const messageCountEl = document.getElementById('context-message-count');

    if (!container) return;

    container.innerHTML = '<div class="context-empty">Loading subagent context...</div>';

    try {
        const response = await fetch(`/api/subagent/${subagentId}/context`);
        if (!response.ok) {
            if (response.status === 404) {
                container.innerHTML = '<div class="context-empty">Subagent context not available yet.</div>';
                return;
            }
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        state.setContextData(data);
        renderContextWindow();

        // Update stats
        if (totalTokensEl) {
            totalTokensEl.textContent = `${data.total_tokens.toLocaleString()} tokens`;
        }
        if (messageCountEl) {
            const msgCount = data.messages.length;
            messageCountEl.textContent = `${msgCount} items`;
        }
    } catch (error) {
        console.error('Failed to load subagent context:', error);
        container.innerHTML = `<div class="context-empty">Failed to load subagent context: ${error.message}</div>`;
    }
}

/**
 * Render the context window panel.
 */
export function renderContextWindow() {
    const container = document.getElementById('context-items');
    if (!container) return;

    const data = state.appState.contextData;
    if (!data || !data.messages || data.messages.length === 0) {
        container.innerHTML = '<div class="context-empty">No messages in context window.</div>';
        return;
    }

    const html = data.messages.map((item, index) => {
        const isExpanded = state.appState.expandedItems.has(index);
        const expandedClass = isExpanded ? 'expanded' : '';
        const summarizedClass = item.is_summarized ? 'summarized' : '';

        if (item.type === 'message') {
            return renderMessageItem(item, index, expandedClass, summarizedClass);
        } else if (item.type === 'tool_call') {
            return renderToolCallItem(item, index, expandedClass, summarizedClass);
        }
        return '';
    }).join('');

    container.innerHTML = html;

    // Add click handlers
    container.querySelectorAll('.context-item-header').forEach(header => {
        header.addEventListener('click', () => {
            const index = parseInt(header.dataset.index, 10);
            toggleContextItem(index);
        });
    });
}

/**
 * Render a message item in the context window.
 */
function renderMessageItem(item, index, expandedClass, summarizedClass) {
    const roleIcon = getRoleIcon(item.role);
    const roleClass = `role-${item.role}`;
    const preview = getPreview(item.content, 100);

    return `
        <div class="context-item ${expandedClass} ${summarizedClass} ${roleClass}">
            <div class="context-item-header" data-index="${index}">
                <span class="context-item-icon">${roleIcon}</span>
                <span class="context-item-type">${item.role.toUpperCase()}</span>
                <span class="context-item-preview">${escapeHtml(preview)}</span>
                <span class="context-item-tokens">${item.tokens.toLocaleString()} tokens</span>
                <span class="context-item-expand">${expandedClass ? '▼' : '▶'}</span>
            </div>
            <div class="context-item-body">
                <pre class="context-item-content">${escapeHtml(item.content)}</pre>
            </div>
        </div>
    `;
}

/**
 * Render a tool call item in the context window.
 */
function renderToolCallItem(item, index, expandedClass, summarizedClass) {
    const toolIcon = getToolIcon(item.tool_name);
    const statusClass = item.success ? '' : 'error';
    const preview = getPreview(item.display_output || '', 80);
    const savedBadge = item.tokens_saved > 0
        ? `<span class="context-tokens-saved">-${item.tokens_saved.toLocaleString()}</span>`
        : '';

    return `
        <div class="context-item tool-call ${expandedClass} ${summarizedClass} ${statusClass}">
            <div class="context-item-header" data-index="${index}">
                <span class="context-item-icon">${toolIcon}</span>
                <span class="context-item-type">${item.tool_name}</span>
                <span class="context-item-preview">${escapeHtml(preview)}</span>
                <span class="context-item-tokens">
                    ${item.tokens.toLocaleString()} tokens
                    ${savedBadge}
                </span>
                <span class="context-item-expand">${expandedClass ? '▼' : '▶'}</span>
            </div>
            <div class="context-item-body">
                <div class="context-tool-section">
                    <div class="context-tool-label">Input:</div>
                    <pre class="context-tool-input">${escapeHtml(JSON.stringify(item.input, null, 2))}</pre>
                </div>
                <div class="context-tool-section">
                    <div class="context-tool-label">Output: <span class="context-output-tokens">(${item.output_tokens.toLocaleString()} tokens)</span></div>
                    <pre class="context-tool-output">${escapeHtml(item.display_output || '(no output)')}</pre>
                </div>
                ${item.is_summarized ? `
                <div class="context-tool-section raw-output-section">
                    <div class="context-tool-label">Raw Output (summarized): <span class="context-output-tokens">(${item.raw_output_tokens.toLocaleString()} tokens)</span></div>
                    <pre class="context-tool-output raw">${escapeHtml(item.raw_output || '(no output)')}</pre>
                </div>
                ` : ''}
            </div>
        </div>
    `;
}

/**
 * Toggle expansion of a context item.
 * 
 * @param {number} index - Item index
 */
function toggleContextItem(index) {
    state.toggleExpandedItem(index);
    renderContextWindow();
}

// ============================================================================
// Tab Switching
// ============================================================================

/**
 * Initialize tab switching behavior.
 */
export function initTabs() {
    document.querySelectorAll('.pane-tabs .tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const tabName = tab.dataset.tab;

            // Update tab active state
            document.querySelectorAll('.pane-tabs .tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            // Update content visibility
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });

            if (tabName === 'graph') {
                document.getElementById('tree-container')?.classList.add('active');
            } else if (tabName === 'context') {
                document.getElementById('context-container')?.classList.add('active');
                // Load context for the currently active agent
                const activeAgent = state.appState.activeAgentView;
                if (activeAgent && activeAgent !== 'orchestrator') {
                    loadSubagentContext(activeAgent);
                } else {
                    loadContextWindow();
                }
            }
        });
    });
}

// ============================================================================
// Collapsible Sections
// ============================================================================

/**
 * Initialize collapsible tree sections in the left panel.
 */
export function initCollapsibleSections() {
    document.querySelectorAll('.section-header').forEach(header => {
        header.addEventListener('click', () => {
            const section = header.parentElement;
            const content = section.querySelector('.tree-content');

            section.classList.toggle('expanded');
            section.classList.toggle('collapsed');

            if (section.classList.contains('collapsed')) {
                content.style.display = 'none';
                header.innerHTML = header.innerHTML.replace('▼', '▶');
            } else {
                content.style.display = 'block';
                header.innerHTML = header.innerHTML.replace('▶', '▼');
            }
        });
    });
}
