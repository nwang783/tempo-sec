"""
Tool factory module.

NOTE: The create_sandboxed_tools() and create_local_tools() functions were
removed as they were unused. Agents now create their own tool registries
via their create_tools() methods in tempo/agents/.

This module is kept for potential future centralized tool creation patterns.
"""

# Re-export commonly used tool creation components for convenience
from tempo.tools.registry import ToolRegistry
from tempo.tools.shell import ShellTool
from tempo.tools.filesystem import FileReadTool, FileWriteTool
from tempo.tools.view_output import ViewToolOutputTool

__all__ = [
    "ToolRegistry",
    "ShellTool",
    "FileReadTool",
    "FileWriteTool",
    "ViewToolOutputTool",
]
