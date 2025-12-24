/**
 * Utility Functions Module
 * 
 * Shared utility functions used across the visualization UI.
 * These are pure functions with no dependencies on application state.
 * 
 * @module utils
 */

// ============================================================================
// HTML Escaping
// ============================================================================

/**
 * Escape HTML special characters to prevent XSS.
 * Uses DOM-based escaping for safety.
 * 
 * @param {string} text - Raw text to escape
 * @returns {string} HTML-safe escaped string
 */
export function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================================================
// Text Utilities
// ============================================================================

/**
 * Get a preview snippet of text, truncated if necessary.
 * 
 * @param {string} text - Full text
 * @param {number} maxLength - Maximum length of preview
 * @returns {string} Truncated preview with ellipsis if needed
 */
export function getPreview(text, maxLength) {
    if (!text) return '';
    const cleaned = text.replace(/\s+/g, ' ').trim();
    if (cleaned.length <= maxLength) return cleaned;
    return cleaned.substring(0, maxLength) + '...';
}

// ============================================================================
// Icon Utilities
// ============================================================================

/**
 * Get an icon for a visualization node based on its type and name.
 * 
 * @param {string} type - Node type (phase_marker, user_prompt, tool, etc.)
 * @param {string} name - Node name (tool name, phase name, etc.)
 * @returns {string} Icon character/emoji
 */
export function getNodeIcon(type, name) {
    if (type === 'phase_marker') return '🚀';
    if (type === 'user_prompt') return '💬';
    if (name.includes('shell')) return '>';
    if (name.includes('read') || name.includes('write') || name.includes('view')) return '📄';
    if (name.includes('browser')) return '🌐';
    return '⚙️';
}

/**
 * Get an icon for a message role in the context window.
 * 
 * @param {string} role - Message role (system, user, assistant, tool_result)
 * @returns {string} Icon emoji
 */
export function getRoleIcon(role) {
    switch (role) {
        case 'system': return '⚙️';
        case 'user': return '👤';
        case 'assistant': return '🤖';
        case 'tool_result': return '📋';
        default: return '💬';
    }
}

/**
 * Get an icon for a tool based on its name.
 * 
 * @param {string} toolName - Name of the tool
 * @returns {string} Icon character/emoji
 */
export function getToolIcon(toolName) {
    if (toolName.includes('shell')) return '>';
    if (toolName.includes('browser')) return '🌐';
    if (toolName.includes('file') || toolName.includes('read') || toolName.includes('write')) return '📄';
    if (toolName.includes('transition')) return '🚀';
    if (toolName.includes('summarize')) return '📝';
    return '⚙️';
}

/**
 * Get a phase-specific icon.
 * 
 * @param {string} phaseName - Phase name (recon, hypothesize, test, reflect)
 * @returns {string} Icon emoji
 */
export function getPhaseIcon(phaseName) {
    const name = phaseName.toLowerCase();
    if (name.includes('recon')) return '🔍';
    if (name.includes('hypo')) return '💡';
    if (name.includes('test')) return '⚡';
    if (name.includes('reflect')) return '📊';
    return '▶';
}

// ============================================================================
// DOM Utilities
// ============================================================================

/**
 * Safely get an element by ID, logging warning if not found.
 * 
 * @param {string} id - Element ID
 * @returns {HTMLElement|null} Element or null
 */
export function getElement(id) {
    const el = document.getElementById(id);
    if (!el) {
        console.warn(`Element not found: ${id}`);
    }
    return el;
}

/**
 * Update text content of an element by ID.
 * 
 * @param {string} id - Element ID
 * @param {string} text - Text to set
 */
export function setText(id, text) {
    const el = document.getElementById(id);
    if (el) {
        el.textContent = text;
    }
}
