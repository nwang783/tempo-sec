"""
Tool registry for discovering, storing, and retrieving tools.
"""

from typing import TYPE_CHECKING

from tempo.tools.base import Tool, ToolSchema

if TYPE_CHECKING:
    from tempo.infra.container import ContainerManager


class ToolRegistry:
    """
    Registry for discovering, storing, and retrieving tools.
    
    Provides methods for registering tools, looking them up by name,
    and generating schemas for LLM consumption.
    """
    
    def __init__(self):
        """Initialize an empty tool registry."""
        self._tools: dict[str, Tool] = {}
    
    def register(self, tool: Tool) -> None:
        """
        Register a tool instance.
        
        Args:
            tool: Tool instance to register
            
        Raises:
            ValueError: If a tool with the same name already exists
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool
    
    def unregister(self, name: str) -> bool:
        """
        Unregister a tool by name.
        
        Args:
            name: Name of tool to remove
            
        Returns:
            True if removed, False if not found
        """
        if name in self._tools:
            del self._tools[name]
            return True
        return False
    
    def get(self, name: str) -> Tool | None:
        """
        Get a tool by name.
        
        Args:
            name: Tool name
            
        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(name)
    
    def list_tools(self) -> list[str]:
        """
        List all registered tool names.
        
        Returns:
            List of tool names
        """
        return list(self._tools.keys())
    
    def get_schemas(self) -> list[dict]:
        """
        Get all tool schemas in OpenAI format for LLM consumption.
        
        Returns:
            List of tool schemas in OpenAI format
        """
        return [
            tool.get_schema().to_openai_format()
            for tool in self._tools.values()
        ]
    
    def get_schema(self, name: str) -> dict | None:
        """
        Get a specific tool's schema.
        
        Args:
            name: Tool name
            
        Returns:
            Tool schema in OpenAI format or None if not found
        """
        tool = self.get(name)
        if tool:
            return tool.get_schema().to_openai_format()
        return None
    
    def __len__(self) -> int:
        """Return number of registered tools."""
        return len(self._tools)
    
    def __contains__(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools
    
    @classmethod
    def default(cls, container_manager: "ContainerManager | None" = None) -> "ToolRegistry":
        """
        Create a registry with the default tool set.

        Default tools:
            - shell: Execute shell commands
            - file_read: Read file contents
            - file_write: Write file contents

        Note: Browser tools are now provided via BrowserTaskTool which uses
        the browser-use integration. Agents should register BrowserTaskTool
        separately if browser automation is needed.

        Args:
            container_manager: Optional container manager for sandboxed execution

        Returns:
            ToolRegistry with default tools registered
        """
        from tempo.tools.shell import ShellTool
        from tempo.tools.filesystem import FileReadTool, FileWriteTool

        registry = cls()

        # Register built-in tools
        registry.register(ShellTool(container_manager))
        registry.register(FileReadTool(container_manager))
        registry.register(FileWriteTool(container_manager))

        return registry
