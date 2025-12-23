"""
Visualization Collector.

Captures agent execution events and forwards them to the visualization server.
"""

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

from tempo.context.frame import ToolCall
from tempo.infra.llm import LLMResponse
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
    """
    
    def __init__(self, server: VisualizationServer):
        self.server = server
        self._loop = asyncio.get_event_loop()
        # Cost tracking state
        self._total_cost: float = 0.0
        self._total_prompt_tokens: int = 0
        self._total_completion_tokens: int = 0
        self._total_cached_tokens: int = 0
    
    def on_step(self, step_result: Any, frame_id: str) -> None:
        """
        Called when an agent step completes.
        
        Args:
            step_result: StepResult object from Agent.step()
            frame_id: ID of the current context frame
        """
        # Extract relevant data from StepResult
        # Note: We avoid importing StepResult directly to avoid circular imports if possible
        # but type hinting uses Any for flexibility
        
        data = {
            "step_number": getattr(step_result, "step_number", 0),
            "phase": str(getattr(step_result, "phase_transition", "")) if getattr(step_result, "phase_transition") else None,
            "error": getattr(step_result, "error", None),
            "should_continue": getattr(step_result, "should_continue", True),
            "llm_content": step_result.llm_response.content if step_result.llm_response else None,
            "usage": asdict(step_result.llm_response.usage) if step_result.llm_response and step_result.llm_response.usage else {},
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

    def on_tool_call(self, tool_call: ToolCall, frame_id: str) -> None:
        """
        Called when a tool execution completes.
        
        Args:
            tool_call: ToolCall object with results
            frame_id: ID of the current context frame
        """
        data = tool_call.to_dict()
        data["frame_id"] = frame_id
        
        # Add metadata for visualization if not present
        if "purpose" not in data.get("input", {}):
            # Try to extract purpose if it was passed as an argument
            pass
            
        self.emit("tool_call", data)
        
        # Check if this is a summarization tool call
        if tool_call.tool_name == "summarize_tool_output" and tool_call.success:
            summarized_id = tool_call.metadata.get("summarized_tool_id")
            if summarized_id:
                self.emit("summarized", {"tool_call_id": summarized_id})

    def emit(self, event_type: str, data: Dict[str, Any]) -> None:
        """Send event to server."""
        event = VisualizationEvent.create(event_type, data)
        # We need to schedule this on the event loop since this might be called synchronously
        # or from a different context.
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
