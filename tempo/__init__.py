"""
Tempo Sec - Context-aware cybersecurity agent.

Main package exports for convenient imports.
"""

from tempo.agent import (
    Agent,
    AgentConfig,
    AgentResult,
    StepResult,
    WorkflowManager,
    OutputSummarizer,
    BranchCoordinator,
)
from tempo.context import (
    ContextStore,
    ContextFrame,
    Message,
    MessageRole,
    ToolCall,
)
from tempo.infra import (
    LLMClient,
    LiteLLMClient,
    ContainerManager,
)
from tempo.prompts import (
    Phase,
    PhaseConfig,
    PromptBuilder,
)
from tempo.tools import (
    Tool,
    ToolRegistry,
    ToolResult,
    ToolSchema,
    ShellTool,
    FileReadTool,
    FileWriteTool,
    BrowserSession,
    BrowserNavigateTool,
    BrowserSnapshotTool,
    BrowserClickTool,
    BrowserTypeTool,
    BrowserFillFormTool,
)

__version__ = "0.1.0"

__all__ = [
    # Agent
    "Agent",
    "AgentConfig",
    "AgentResult",
    "StepResult",
    "WorkflowManager",
    "OutputSummarizer",
    "BranchCoordinator",
    # Context
    "ContextStore",
    "ContextFrame",
    "Message",
    "MessageRole",
    "ToolCall",
    # Infrastructure
    "LLMClient",
    "LiteLLMClient",
    "ContainerManager",
    # Prompts
    "Phase",
    "PhaseConfig",
    "PromptBuilder",
    # Tools
    "Tool",
    "ToolRegistry",
    "ToolResult",
    "ToolSchema",
    "ShellTool",
    "FileReadTool",
    "FileWriteTool",
    # Playwright-style browser tools
    "BrowserSession",
    "BrowserNavigateTool",
    "BrowserSnapshotTool",
    "BrowserClickTool",
    "BrowserTypeTool",
    "BrowserFillFormTool",
]
