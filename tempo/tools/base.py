"""
Base classes and data models for tools.

Provides the abstract Tool class that all tools must implement,
along with ToolResult and ToolSchema for structured tool responses.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ToolCategory(str, Enum):
    """Categories for organizing tools."""
    EXECUTION = "execution"     # Shell, code execution
    BROWSING = "browsing"       # Web access
    FILESYSTEM = "filesystem"   # File operations
    NETWORK = "network"         # Network operations
    ANALYSIS = "analysis"       # Code analysis, RE tools
    META = "meta"               # Tool installation, agent control


@dataclass
class ToolResult:
    """Result of a tool execution."""
    success: bool
    output: str
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    # For structured results
    structured_data: Any = None


@dataclass  
class ToolSchema:
    """JSON Schema representation of a tool for LLM consumption."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema format
    
    def to_openai_format(self) -> dict:
        """Convert to OpenAI/Anthropic tool format."""
        import copy
        
        # Deep copy to avoid mutating original parameters
        params = copy.deepcopy(self.parameters)
        
        if "properties" not in params:
            params["properties"] = {}
            
        if "purpose" not in params["properties"]:
            params["properties"]["purpose"] = {
                "type": "string",
                "description": "A one-sentence summary of why this tool is being called."
            }
            
        if "required" not in params:
            params["required"] = []
        if "purpose" not in params["required"]:
            params["required"] = list(params["required"]) + ["purpose"]

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": params,
            }
        }


class Tool(ABC):
    """Abstract base class for all tools."""
    
    name: str
    description: str
    category: ToolCategory
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given parameters."""
        pass
    
    @abstractmethod
    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        pass
    
    def default_summarizer(self, result: ToolResult) -> str:
        """
        Default strategy for summarizing this tool's output.
        Override in subclasses for tool-specific summarization.
        """
        if not result.success:
            return f"Error: {result.error}"
        # Default: truncate long outputs
        if len(result.output) > 500:
            return result.output[:250] + "\n...[truncated]...\n" + result.output[-250:]
        return result.output
