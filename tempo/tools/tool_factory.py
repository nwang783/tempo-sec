"""
Tool factory for creating tool registries with proper container injection.

Centralizes tool creation to ensure all network-interacting tools
run in a sandboxed container environment.
"""

from typing import TYPE_CHECKING

from tempo.tools.registry import ToolRegistry
from tempo.tools.shell import ShellTool
from tempo.tools.filesystem import FileReadTool, FileWriteTool
from tempo.tools.meta import (
    SummarizeOutputTool,
    BranchToSubtasksTool,
    FinishSubtaskTool,
)
from tempo.tools.view_output import ViewToolOutputTool

if TYPE_CHECKING:
    from tempo.infra.container import ContainerManager
    from tempo.context.store import ContextStore
    from tempo.agent.branch_coordinator import BranchCoordinator


def create_sandboxed_tools(
    container: "ContainerManager",
    context_store: "ContextStore",
    branch_coordinator: "BranchCoordinator | None" = None,
) -> ToolRegistry:
    """
    Create a tool registry with all tools properly configured for sandboxed execution.

    All network-interacting tools (shell, filesystem) are injected with
    the container manager to ensure they run in a secure, isolated environment.

    Note: Browser tools are now provided via BrowserTaskTool which uses
    the browser-use integration. Agents should register BrowserTaskTool
    separately if browser automation is needed.

    Args:
        container: Container manager for sandboxed execution (required)
        context_store: Context store for summarization tool
        branch_coordinator: Optional branch coordinator for subtasks

    Returns:
        ToolRegistry with all tools configured
    """
    tools = ToolRegistry()

    # Sandboxed tools - these interact with network/filesystem
    tools.register(ShellTool(container_manager=container))
    tools.register(FileReadTool(container_manager=container))
    tools.register(FileWriteTool(container_manager=container))

    # Meta tools
    tools.register(SummarizeOutputTool(context_store=context_store))
    tools.register(ViewToolOutputTool(context_store=context_store))

    if branch_coordinator:
        tools.register(BranchToSubtasksTool(branch_coordinator=branch_coordinator))
        tools.register(FinishSubtaskTool())

    return tools


def create_local_tools(
    context_store: "ContextStore",
) -> ToolRegistry:
    """
    Create a tool registry for local (non-containerized) execution.

    WARNING: This runs tools directly on the host system. Use only for
    development/testing, never in production.

    Note: Browser tools are now provided via BrowserTaskTool which uses
    the browser-use integration. Agents should register BrowserTaskTool
    separately if browser automation is needed.

    Args:
        context_store: Context store for summarization tool

    Returns:
        ToolRegistry with tools configured for local execution
    """
    import warnings
    warnings.warn(
        "Creating local tools without container. Commands will execute on host system.",
        RuntimeWarning,
    )

    tools = ToolRegistry()

    # Local tools (no container injection)
    tools.register(ShellTool())
    tools.register(FileReadTool())
    tools.register(FileWriteTool())

    # Meta tools
    tools.register(SummarizeOutputTool(context_store=context_store))
    tools.register(ViewToolOutputTool(context_store=context_store))

    return tools

