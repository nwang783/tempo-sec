"""
Tools module for Tempo Sec.

Exports:
    - Tool: Abstract base class for tools
    - ToolCategory: Enum for tool categories
    - ToolResult: Result of tool execution
    - ToolSchema: Schema for tool parameters
    - ToolRegistry: Registry for managing tools
    - Built-in tools: ShellTool, FileReadTool, FileWriteTool
    - Playwright-style browser tools: BrowserSession, BrowserNavigateTool, etc.
    - Meta tools: TransitionPhaseTool, SummarizeOutputTool, FinishTaskTool,
                  BranchToSubtasksTool, FinishSubtaskTool
"""

from tempo.tools.base import (
    Tool,
    ToolCategory,
    ToolResult,
    ToolSchema,
)
from tempo.tools.registry import ToolRegistry
from tempo.tools.shell import ShellTool
from tempo.tools.filesystem import FileReadTool, FileWriteTool
from tempo.tools.browser_tools import (
    BrowserSession,
    BrowserNavigateTool,
    BrowserSnapshotTool,
    BrowserClickTool,
    BrowserTypeTool,
    BrowserFillFormTool,
)
from tempo.tools.meta import (
    TransitionPhaseTool,
    SummarizeOutputTool,
    FinishTaskTool,
    BranchToSubtasksTool,
    FinishSubtaskTool,
)
from tempo.tools.testplan_tools import (
    CreateTestPlanTool,
    AddTodoTool,
    CompleteTodoTool,
)

__all__ = [
    # Base
    "Tool",
    "ToolCategory",
    "ToolResult",
    "ToolSchema",
    # Registry
    "ToolRegistry",
    # Built-in tools
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
    # Meta tools
    "TransitionPhaseTool",
    "SummarizeOutputTool",
    "FinishTaskTool",
    "BranchToSubtasksTool",
    "FinishSubtaskTool",
    # Test plan tools
    "CreateTestPlanTool",
    "AddTodoTool",
    "CompleteTodoTool",
]
