"""
Visualization Collector.

Captures agent execution events and forwards them to the visualization server.
"""

import asyncio
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

from tempo.context.frame import ToolCall
from tempo.infra.llm import LLMResponse
from tempo.visualization.server import VisualizationServer


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

    def emit(self, event_type: str, data: Dict[str, Any]) -> None:
        """Send event to server."""
        event = VisualizationEvent.create(event_type, data)
        # We need to schedule this on the event loop since this might be called synchronously
        # or from a different context.
        asyncio.create_task(self.server.broadcast(event.to_json()))

    def on_agent_start(self, objective: str, model_name: str = "") -> None:
        """Called when agent starts execution."""
        self.emit("start", {"objective": objective, "model": model_name})

    def on_agent_finish(self, success: bool, output: Any = None) -> None:
        """Called when agent finishes."""
        self.emit("finish", {
            "success": success, 
            "output": str(output) if output else None
        })
