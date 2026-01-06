"""
Filesystem tools for reading and writing files.
"""

from typing import TYPE_CHECKING

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema

if TYPE_CHECKING:
    from tempo.infra.container import ContainerManager


class FileReadTool(Tool):
    """Read contents of a file."""
    
    name = "file_read"
    description = "Read the contents of a file"
    category = ToolCategory.FILESYSTEM
    
    def __init__(self, container_manager: "ContainerManager | None" = None):
        """
        Initialize the file read tool.
        
        Args:
            container_manager: Container for sandboxed execution.
                               If None, reads from local filesystem.
        """
        self.container = container_manager
    
    async def execute(
        self,
        path: str,
        encoding: str = "utf-8",
        max_bytes: int | str | None = None,
        purpose: str = "",
    ) -> ToolResult:
        """
        Read a file's contents.
        
        Args:
            path: Path to the file to read
            encoding: File encoding (default: utf-8)
            max_bytes: Maximum bytes to read (optional)
            purpose: Why this tool is being called
            
        Returns:
            ToolResult with file contents
        """
        # Coerce max_bytes to int if provided (LLM may pass as string)
        if max_bytes is not None:
            max_bytes = int(max_bytes)
        
        try:
            if self.container is None:
                # Local filesystem
                with open(path, "r", encoding=encoding) as f:
                    if max_bytes:
                        content = f.read(max_bytes)
                    else:
                        content = f.read()
            else:
                # Container filesystem
                content = await self.container.read_file(path)
                if max_bytes and len(content) > max_bytes:
                    content = content[:max_bytes]
            
            return ToolResult(
                success=True,
                output=content,
                metadata={"path": path, "bytes": len(content)},
            )
        except FileNotFoundError:
            return ToolResult(
                success=False,
                output="",
                error=f"File not found: {path}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )
    
    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read",
                    },
                    "encoding": {
                        "type": "string",
                        "description": "File encoding (default: utf-8)",
                        "default": "utf-8",
                    },
                    "max_bytes": {
                        "type": "integer",
                        "description": "Maximum bytes to read (optional)",
                    },
                },
                "required": ["path"],
            },
        )


class FileWriteTool(Tool):
    """Write contents to a file."""
    
    name = "file_write"
    description = "Write content to a file (creates or overwrites)"
    category = ToolCategory.FILESYSTEM
    
    def __init__(self, container_manager: "ContainerManager | None" = None):
        """
        Initialize the file write tool.
        
        Args:
            container_manager: Container for sandboxed execution.
                               If None, writes to local filesystem.
        """
        self.container = container_manager
    
    async def execute(
        self,
        path: str,
        content: str,
        append: bool = False,
        encoding: str = "utf-8",
        purpose: str = "",
    ) -> ToolResult:
        """
        Write content to a file.
        
        Args:
            path: Path to the file to write
            content: Content to write
            append: Append instead of overwrite
            encoding: File encoding (default: utf-8)
            purpose: Why this tool is being called
            
        Returns:
            ToolResult indicating success/failure
        """
        try:
            if self.container is None:
                # Local filesystem
                mode = "a" if append else "w"
                with open(path, mode, encoding=encoding) as f:
                    f.write(content)
            else:
                # Container filesystem
                if append:
                    existing = ""
                    try:
                        existing = await self.container.read_file(path)
                    except FileNotFoundError:
                        pass
                    content = existing + content
                await self.container.write_file(path, content)
            
            return ToolResult(
                success=True,
                output=f"Successfully wrote {len(content)} bytes to {path}",
                metadata={"path": path, "bytes": len(content), "append": append},
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )
    
    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to write",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write",
                    },
                    "append": {
                        "type": "boolean",
                        "description": "Append instead of overwrite",
                        "default": False,
                    },
                },
                "required": ["path", "content"],
            },
        )
