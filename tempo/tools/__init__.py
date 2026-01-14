"""
Tools module for Tempo Sec.

Exports:
    - Tool: Abstract base class for tools
    - ToolCategory: Enum for tool categories
    - ToolResult: Result of tool execution
    - ToolSchema: Schema for tool parameters
    - ToolRegistry: Registry for managing tools
    - Built-in tools: ShellTool, FileReadTool, FileWriteTool
    - Browser-use integration: BrowserUseToolsAdapter, BrowserUseStateTools
    - Meta tools: SummarizeOutputTool, BranchToSubtasksTool, FinishSubtaskTool, FinalizeAnalysisTool
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
from tempo.tools.browser_use_adapter import BrowserUseToolsAdapter
from tempo.tools.browser_use_state import BrowserUseStateTools
from tempo.tools.meta import (
    SummarizeOutputTool,
    BranchToSubtasksTool,
    FinishSubtaskTool,
    FinalizeAnalysisTool,
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
    # Browser-use integration
    "BrowserUseToolsAdapter",
    "BrowserUseStateTools",
    # Meta tools
    "SummarizeOutputTool",
    "BranchToSubtasksTool",
    "FinishSubtaskTool",
    "FinalizeAnalysisTool",
    # Test plan tools
    "CreateTestPlanTool",
    "AddTodoTool",
    "CompleteTodoTool",
]

