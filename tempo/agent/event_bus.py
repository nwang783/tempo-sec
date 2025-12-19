"""
Event bus for decoupled agent notifications.

Provides a simple pub/sub system for agent events, allowing visualization
and other listeners to subscribe without direct coupling to the Agent class.
"""

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class AgentEvent:
    """Represents an event emitted by the agent."""
    
    type: str
    data: dict[str, Any] = field(default_factory=dict)


# Event type constants
EVENT_STEP_COMPLETE = "step_complete"
EVENT_TOOL_CALL = "tool_call"
EVENT_PHASE_TRANSITION = "phase_transition"
EVENT_PHASE_SUMMARY = "phase_summary"
EVENT_USER_PROMPT = "user_prompt"
EVENT_AGENT_PAUSED = "agent_paused"
EVENT_AGENT_RESUMED = "agent_resumed"


EventHandler = Callable[[AgentEvent], None]


class EventBus:
    """
    Simple pub/sub for agent events.
    
    Allows components to subscribe to specific event types and receive
    notifications when those events occur. This decouples the Agent from
    visualization and other listeners.
    
    Example usage:
        bus = EventBus()
        bus.subscribe("step_complete", my_handler)
        bus.emit(AgentEvent(type="step_complete", data={"step": 1}))
    """
    
    def __init__(self):
        """Initialize an empty event bus."""
        self._handlers: dict[str, list[EventHandler]] = {}
        self._global_handlers: list[EventHandler] = []
    
    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """
        Subscribe to a specific event type.
        
        Args:
            event_type: The event type to subscribe to
            handler: Function to call when event is emitted
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
    
    def subscribe_all(self, handler: EventHandler) -> None:
        """
        Subscribe to all events.
        
        Args:
            handler: Function to call for any event
        """
        self._global_handlers.append(handler)
    
    def unsubscribe(self, event_type: str, handler: EventHandler) -> bool:
        """
        Unsubscribe from an event type.
        
        Args:
            event_type: The event type to unsubscribe from
            handler: The handler to remove
            
        Returns:
            True if handler was found and removed
        """
        if event_type not in self._handlers:
            return False
        try:
            self._handlers[event_type].remove(handler)
            return True
        except ValueError:
            return False
    
    def emit(self, event: AgentEvent) -> None:
        """
        Emit an event to all subscribers.
        
        Args:
            event: The event to emit
        """
        # Call type-specific handlers
        if event.type in self._handlers:
            for handler in self._handlers[event.type]:
                try:
                    handler(event)
                except Exception:
                    # Don't let handler errors break the emitter
                    pass
        
        # Call global handlers
        for handler in self._global_handlers:
            try:
                handler(event)
            except Exception:
                pass
    
    def clear(self) -> None:
        """Remove all handlers."""
        self._handlers.clear()
        self._global_handlers.clear()
    
    def handler_count(self, event_type: str | None = None) -> int:
        """
        Get the number of handlers registered.
        
        Args:
            event_type: Specific event type, or None for total count
            
        Returns:
            Number of handlers
        """
        if event_type is None:
            return sum(len(h) for h in self._handlers.values()) + len(self._global_handlers)
        return len(self._handlers.get(event_type, []))
