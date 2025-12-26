"""
Context processing utilities for visualization.

Transforms context data into UI-friendly format with token estimates.
This module is extracted from server.py to improve cohesion.
"""

import json
from typing import Any, TYPE_CHECKING

from tempo.infra.tokenizer import count_tokens

if TYPE_CHECKING:
    from tempo.context.store import ContextStore


def estimate_tokens(text: str, model: str | None = None) -> int:
    """
    Estimate token count for text using LiteLLM tokenizer.
    
    Uses the appropriate tokenizer for the specified model when available.
    
    Args:
        text: The text to estimate tokens for
        model: Optional model name for accurate counting
        
    Returns:
        Estimated token count
    """
    return count_tokens(text, model)


def build_context_data_from_store(context_store: "ContextStore") -> dict:
    """
    Build context data dict from a live ContextStore.
    
    Produces the same format as saved JSON context files,
    enabling consistent processing regardless of source.
    
    Args:
        context_store: Live context store instance
        
    Returns:
        Dictionary suitable for process_context_for_ui()
    """
    return context_store.export_for_visualization()


def process_context_for_ui(context_data: dict, model: str | None = None) -> dict:
    """
    Process context data for the UI.
    
    Adds token estimates, flattens the frame structure, and computes
    statistics for display. Tool calls show both raw and summarized
    output sizes to visualize token savings.
    
    Args:
        context_data: Raw context data (from JSON file or ContextStore.export_for_visualization())
        model: Optional model name for accurate token counting
        
    Returns:
        Processed data with:
        - session_id, created_at, updated_at
        - messages: list of message/tool_call dicts with token counts
        - total_tokens, total_messages, total_tool_calls
    """
    result = {
        "session_id": context_data.get("session_id"),
        "created_at": context_data.get("created_at"),
        "updated_at": context_data.get("updated_at"),
        "current_frame_id": context_data.get("current_frame_id"),
        "messages": [],
        "total_tokens": 0,
        "total_messages": 0,
        "total_tool_calls": 0,
    }
    
    frames = context_data.get("frames", {})
    current_frame_id = context_data.get("current_frame_id")
    
    # Build frame path from root to current
    frame_path = _build_frame_path(frames, current_frame_id)
    
    # Collect all messages and tool calls in order
    message_index = 0
    for frame in frame_path:
        # Process messages
        for msg in frame.get("messages", []):
            processed_msg = _process_message(msg, message_index, model)
            result["messages"].append(processed_msg)
            result["total_tokens"] += processed_msg["tokens"]
            result["total_messages"] += 1
            message_index += 1
        
        # Process tool calls
        for tc in frame.get("tool_calls", []):
            processed_tc = _process_tool_call(tc, message_index, model)
            result["messages"].append(processed_tc)
            result["total_tokens"] += processed_tc["tokens"]
            result["total_tool_calls"] += 1
            message_index += 1
    
    return result


def _build_frame_path(frames: dict, current_frame_id: str | None) -> list[dict]:
    """
    Build ordered list of frames from root to current.
    
    Traverses parent_id links to reconstruct the path.
    """
    frame_path = []
    frame_id = current_frame_id
    while frame_id and frame_id in frames:
        frame_path.append(frames[frame_id])
        frame_id = frames[frame_id].get("parent_id")
    frame_path.reverse()
    return frame_path


def _process_message(msg: dict, index: int, model: str | None = None) -> dict:
    """Process a single message for UI display."""
    content = msg.get("content", "")
    tokens = estimate_tokens(content, model)
    return {
        "index": index,
        "type": "message",
        "role": msg.get("role"),
        "content": content,
        "timestamp": msg.get("timestamp"),
        "tokens": tokens,
        "is_summarized": False,
        "metadata": msg.get("metadata", {}),
    }


def _process_tool_call(tc: dict, index: int, model: str | None = None) -> dict:
    """
    Process a single tool call for UI display.
    
    Calculates token usage for both input and output,
    and tracks token savings from summarization.
    """
    tool_name = tc.get("tool_name", "unknown")
    raw_output = tc.get("raw_output", "")
    summary = tc.get("summary")
    is_summarized = summary is not None
    
    # For display, use summary if available
    display_output = summary if is_summarized else raw_output
    
    # Calculate tokens for input and output separately
    input_data = tc.get("input", {})
    input_str = json.dumps(input_data) if input_data else ""
    input_tokens = estimate_tokens(input_str, model)
    output_tokens = estimate_tokens(display_output, model)
    raw_output_tokens = estimate_tokens(raw_output, model)
    
    # Tokens saved by summarization
    tokens_saved = raw_output_tokens - output_tokens if is_summarized else 0
    
    return {
        "index": index,
        "type": "tool_call",
        "tool_call_id": tc.get("id"),
        "tool_name": tool_name,
        "input": input_data,
        "raw_output": raw_output,
        "summary": summary,
        "display_output": display_output,
        "timestamp": tc.get("timestamp"),
        "duration_ms": tc.get("duration_ms", 0),
        "success": tc.get("success", True),
        "error": tc.get("error"),
        "is_summarized": is_summarized,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "raw_output_tokens": raw_output_tokens,
        "tokens_saved": tokens_saved,
        "tokens": input_tokens + output_tokens,
    }
