"""
Agent definitions package.

Contains modular agent definitions that can be loaded by the unified runner.
Each agent definition specifies:
- Model to use
- Tools to register
- System prompt building
- Objective building
- Starting phase

Usage:
    from tempo.agents import get_agent, list_agents
    
    # List available agents
    agents = list_agents()  # ["recon", "test_cycle"]
    
    # Get a specific agent definition
    agent_def = get_agent("recon", target="example.com", output_path="./manifest.json")
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tempo.agents.base import BaseAgentDefinition

# Registry of available agent definitions
_AGENT_REGISTRY: dict[str, type["BaseAgentDefinition"]] = {}


def register_agent(agent_class: type["BaseAgentDefinition"]) -> type["BaseAgentDefinition"]:
    """
    Decorator to register an agent definition.
    
    Usage:
        @register_agent
        class MyAgent(BaseAgentDefinition):
            name = "my_agent"
            ...
    """
    # Determine agent name
    # Check if 'name' is a property descriptor
    attr = getattr(agent_class, 'name', None)
    
    if isinstance(attr, property):
        # It's a property, so we can't get the value without instantiation
        # Require _name class attribute for registration keys
        if hasattr(agent_class, '_name'):
            name = agent_class._name
        else:
            raise ValueError(
                f"Agent class {agent_class.__name__} must define '_name' class attribute "
                "for registration because 'name' is a property."
            )
    else:
        # It's a static value or missing (default to class name)
        name = attr or agent_class.__name__.lower()
    
    _AGENT_REGISTRY[name] = agent_class
    return agent_class


def list_agents() -> list[str]:
    """
    List all registered agent names.
    
    Returns:
        List of agent names
    """
    # Ensure builtin agents are loaded
    _ensure_builtin_agents_loaded()
    return list(_AGENT_REGISTRY.keys())


def get_agent_class(name: str) -> type["BaseAgentDefinition"]:
    """
    Get an agent definition class by name.
    
    Args:
        name: Agent name (e.g., 'recon', 'test_cycle')
        
    Returns:
        Agent definition class
        
    Raises:
        KeyError: If agent not found
    """
    _ensure_builtin_agents_loaded()
    if name not in _AGENT_REGISTRY:
        available = ", ".join(_AGENT_REGISTRY.keys())
        raise KeyError(f"Agent '{name}' not found. Available: {available}")
    return _AGENT_REGISTRY[name]


def get_agent(name: str, **kwargs) -> "BaseAgentDefinition":
    """
    Get an instantiated agent definition by name.
    
    Args:
        name: Agent name (e.g., 'recon', 'test_cycle')
        **kwargs: Arguments to pass to agent constructor
        
    Returns:
        Instantiated agent definition
        
    Raises:
        KeyError: If agent not found
    """
    agent_class = get_agent_class(name)
    return agent_class(**kwargs)


def _ensure_builtin_agents_loaded() -> None:
    """Ensure builtin agent modules are imported for registration."""
    if not _AGENT_REGISTRY:
        # Import builtin agents to trigger registration
        from tempo.agents import recon  # noqa: F401
        from tempo.agents import test_cycle  # noqa: F401
        from tempo.agents import browser  # noqa: F401
        from tempo.agents import recon_subagent  # noqa: F401
        from tempo.agents import test_subagent  # noqa: F401
