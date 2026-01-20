/**
 * WebSocket Connection Module
 * 
 * Handles WebSocket connection to the visualization server,
 * including reconnection logic and message handling.
 * 
 * @module ws
 */

import * as state from './state.js';
import { setText } from './utils.js';

// ============================================================================
// Module State
// ============================================================================

/**
 * WebSocket connection instance.
 * @type {WebSocket|null}
 */
let socket = null;

/**
 * Callback for when a message is received.
 * Set by the events module.
 * @type {Function|null}
 */
let onMessageCallback = null;

/**
 * Callback for when connection is established.
 * @type {Function|null}
 */
let onConnectCallback = null;

// ============================================================================
// Public API
// ============================================================================

/**
 * Set the callback for incoming WebSocket messages.
 * 
 * @param {Function} callback - Function to call with parsed message data
 */
export function setOnMessage(callback) {
    onMessageCallback = callback;
}

/**
 * Set the callback for connection established.
 * 
 * @param {Function} callback - Function to call when connected
 */
export function setOnConnect(callback) {
    onConnectCallback = callback;
}

/**
 * Establish WebSocket connection to the visualization server.
 * Automatically reconnects on disconnect.
 */
export function connect() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    socket = new WebSocket(`${protocol}//${host}/ws`);

    socket.onopen = function () {
        const statusEl = document.getElementById('status');
        if (statusEl) {
            statusEl.textContent = "CONNECTED";
            statusEl.className = "status connected";
        }
        state.setConnected(true);

        if (onConnectCallback) {
            onConnectCallback();
        }
    };

    socket.onmessage = function (event) {
        try {
            const msg = JSON.parse(event.data);
            if (onMessageCallback) {
                onMessageCallback(msg);
            }
        } catch (e) {
            console.error('Failed to parse WebSocket message:', e);
        }
    };

    socket.onclose = function () {
        const statusEl = document.getElementById('status');
        if (statusEl) {
            statusEl.textContent = "DISCONNECTED";
            statusEl.className = "status disconnected";
        }
        state.setConnected(false);

        // Reconnect after delay
        setTimeout(connect, 3000);
    };
}

/**
 * Send a message to the server via WebSocket.
 * 
 * @param {string} type - Message type
 * @param {Object} payload - Message payload (will be merged with type)
 * @returns {boolean} True if sent successfully
 */
export function send(type, payload = {}) {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
        console.warn('WebSocket not connected, cannot send message');
        return false;
    }

    socket.send(JSON.stringify({ type, ...payload }));
    return true;
}

/**
 * Check if WebSocket is currently connected.
 * 
 * @returns {boolean} True if connected
 */
export function isConnected() {
    return socket && socket.readyState === WebSocket.OPEN;
}

/**
 * Send a user prompt to the agent.
 * 
 * @param {string} content - Prompt content
 * @returns {boolean} True if sent successfully
 */
export function sendUserPrompt(content) {
    return send('user_prompt', { content });
}

/**
 * Send a stop signal to the agent.
 * 
 * @returns {boolean} True if sent successfully
 */
export function sendStopSignal() {
    return send('stop_agent');
}

/**
 * Send a pause signal to the agent.
 * 
 * @returns {boolean} True if sent successfully
 */
export function sendPauseSignal() {
    return send('pause_agent');
}
