"""
Visualization Collector.

Captures agent execution events and forwards them to the visualization server.

This module implements the VisualizationObserver protocol, allowing the Agent
to emit events without tight coupling to this implementation.
"""

import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from tempo.visualization.server import VisualizationServer

logger = logging.getLogger(__name__)


@dataclass
class VisualizationEvent:
    """Standard event for visualization."""
    type: str
    timestamp: str
    data: Dict[str, Any]
    
    @classmethod
    def create(cls, event_type: str, data: Dict[str, Any]) -> "VisualizationEvent":
        return cls(
            type=event_type,
            timestamp=datetime.utcnow().isoformat(),
            data=data
        )
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))


class VisualizationCollector:
    """
    Collects events from the Agent and forwards them to the VisualizationServer.
    
    Implements the VisualizationObserver protocol from infra/protocols.py,
    allowing agents to depend on the protocol rather than this concrete class.
    
    Methods accept dict data to avoid importing from context/ or agent/,
    following the project's dependency rules.
    """
    
    def __init__(self, server: "VisualizationServer"):
        self.server = server
        # Cost tracking state
        self._total_cost: float = 0.0
        self._total_prompt_tokens: int = 0
        self._total_completion_tokens: int = 0
        self._total_cached_tokens: int = 0
    
    def on_step(self, step_data: dict | Any, frame_id: str) -> None:
        """
        Called when an agent step completes.
        
        Args:
            step_data: Step data dict OR StepResult object (for compatibility).
                       Dict should contain: step_number, phase, error,
                       should_continue, llm_content, usage
            frame_id: ID of the current context frame
        """
        # Support both dict and object input for compatibility
        if isinstance(step_data, dict):
            data = {
                "step_number": step_data.get("step_number", 0),
                "phase": step_data.get("phase"),
                "error": step_data.get("error"),
                "should_continue": step_data.get("should_continue", True),
                "llm_content": step_data.get("llm_content"),
                "usage": step_data.get("usage", {}),
                "frame_id": frame_id
            }
        else:
            # Legacy: object-based input (StepResult)
            data = {
                "step_number": getattr(step_data, "step_number", 0),
                "phase": str(getattr(step_data, "phase_transition", "")) if getattr(step_data, "phase_transition", None) else None,
                "error": getattr(step_data, "error", None),
                "should_continue": getattr(step_data, "should_continue", True),
                "llm_content": step_data.llm_response.content if getattr(step_data, "llm_response", None) else None,
                "usage": self._extract_usage(step_data),
                "frame_id": frame_id
            }
        
        self.emit("step", data)
        
        # Update cumulative cost tracking and emit cost update
        usage = data.get("usage", {})
        
        self._total_cost += usage.get("cost", 0.0)
        self._total_prompt_tokens += usage.get("prompt_tokens", 0)
        self._total_completion_tokens += usage.get("completion_tokens", 0)
        self._total_cached_tokens += usage.get("cached_tokens", 0)
        
        self.emit("cost_update", {
            "total_cost": self._total_cost,
            "total_prompt_tokens": self._total_prompt_tokens,
            "total_completion_tokens": self._total_completion_tokens,
            "total_cached_tokens": self._total_cached_tokens,
            "step_cost": usage.get("cost", 0.0),
        })
        
        # If there was a phase transition, emit that too
        if data["phase"]:
            self.emit("phase_transition", {
                "to_phase": data["phase"],
                "step_number": data["step_number"]
            })
    
    def _extract_usage(self, step_result: Any) -> dict:
        """Extract usage dict from step_result, handling both dict and object forms."""
        if not getattr(step_result, "llm_response", None):
            return {}
        usage = getattr(step_result.llm_response, "usage", None)
        if usage is None:
            return {}
        # Convert dataclass to dict if needed
        if hasattr(usage, "__dict__"):
            return asdict(usage) if hasattr(usage, "__dataclass_fields__") else vars(usage)
        return usage if isinstance(usage, dict) else {}

    def on_tool_call(self, tool_data: dict | Any, frame_id: str) -> None:
        """
        Called when a tool execution completes.
        
        Args:
            tool_data: Tool call data dict OR ToolCall object (for compatibility).
                       Dict should contain: id, tool_name, input, raw_output,
                       summary, success, error, duration_ms, metadata
            frame_id: ID of the current context frame
        """
        # Support both dict and object input for compatibility
        if isinstance(tool_data, dict):
            data = dict(tool_data)  # Copy to avoid mutation
            data["frame_id"] = frame_id
        else:
            # Legacy: object-based input (ToolCall)
            data = tool_data.to_dict() if hasattr(tool_data, "to_dict") else {}
            data["frame_id"] = frame_id
        
        self.emit("tool_call", data)
        
        # Check if this is a summarization tool call
        tool_name = data.get("tool_name", "")
        if tool_name == "summarize_tool_output" and data.get("success", False):
            metadata = data.get("metadata", {})
            summarized_id = metadata.get("summarized_tool_id")
            if summarized_id:
                self.emit("summarized", {"tool_call_id": summarized_id})

    def emit(self, event_type: str, data: Dict[str, Any]) -> None:
        """Send event to server."""
        event = VisualizationEvent.create(event_type, data)
        # Schedule on event loop since this might be called synchronously
        asyncio.create_task(self.server.broadcast(event.to_json()))

    def on_agent_start(self, objective: str, model_name: str = "") -> None:
        """Called when agent starts execution."""
        state = {"objective": objective, "model": model_name}
        # Store state on server so new connections get it
        self.server.set_agent_state(state)
        self.emit("start", state)

    def on_agent_finish(self, success: bool, output: Any = None) -> None:
        """Called when agent finishes."""
        # Clear agent state so stale data isn't sent to new connections
        self.server.clear_agent_state()
        self.emit("finish", {
            "success": success, 
            "output": str(output) if output else None
        })

    def on_agent_paused(self, reason: str = "") -> None:
        """Called when agent enters pause state (e.g., awaiting user input)."""
        self.emit("paused", {"reason": reason})

    def on_agent_resumed(self, prompt_preview: str = "") -> None:
        """Called when agent resumes from pause state."""
        self.emit("resumed", {
            "prompt_preview": prompt_preview[:100] if prompt_preview else ""
        })

    def on_user_prompt_received(self, content: str) -> None:
        """Called when a user prompt is injected into the agent context."""
        self.emit("user_prompt_injected", {
            "content_preview": content[:200] if content else ""
        })

    def on_test_plan_update(self, items: list) -> None:
        """Called when the test plan is created or updated."""
        self.emit("test_plan_update", {"items": items})

    def on_available_tools(self, tool_schemas: list[dict]) -> None:
        """Called when the available tools are determined for a step.
        
        Args:
            tool_schemas: List of tool schemas in OpenAI format
        """
        tool_names = [
            s.get("function", {}).get("name", "unknown")
            for s in tool_schemas
        ]
        self.emit("available_tools", {"tools": tool_names})

