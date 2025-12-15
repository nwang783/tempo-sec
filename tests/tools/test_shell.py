"""Tests for tempo/tools/shell.py."""

import pytest

from tempo.tools.shell import ShellTool


class TestShellTool:
    """Tests for ShellTool class."""
    
    def test_name_and_category(self):
        """Test tool name and category are set."""
        tool = ShellTool()
        assert tool.name == "shell"
        assert tool.category.value == "execution"
    
    def test_get_schema(self):
        """Test schema generation."""
        tool = ShellTool()
        schema = tool.get_schema().to_openai_format()
        
        assert schema["function"]["name"] == "shell"
        assert "command" in schema["function"]["parameters"]["properties"]
        assert "command" in schema["function"]["parameters"]["required"]
    
    @pytest.mark.asyncio
    async def test_execute_simple_command(self):
        """Test executing a simple command locally."""
        tool = ShellTool(container_manager=None)  # Local execution
        
        result = await tool.execute(
            command="echo 'hello world'",
            purpose="Test execution",
        )
        
        assert result.success is True
        assert "hello world" in result.output
    
    @pytest.mark.asyncio
    async def test_execute_command_with_error(self):
        """Test executing a command that fails."""
        tool = ShellTool(container_manager=None)
        
        result = await tool.execute(
            command="exit 1",
            purpose="Test error",
        )
        
        assert result.success is False
        assert result.metadata["exit_code"] == 1
    
    @pytest.mark.asyncio
    async def test_execute_with_timeout(self):
        """Test command timeout."""
        tool = ShellTool(container_manager=None)
        
        result = await tool.execute(
            command="sleep 5",
            timeout=1,
            purpose="Test timeout",
        )
        
        assert result.success is False
        assert "timed out" in result.error.lower()
    
    def test_default_summarizer_short(self):
        """Test summarizer with short output."""
        tool = ShellTool()
        from tempo.tools.base import ToolResult
        
        result = ToolResult(success=True, output="line1\nline2\nline3")
        summary = tool.default_summarizer(result)
        
        assert summary == "line1\nline2\nline3"
    
    def test_default_summarizer_long(self):
        """Test summarizer with long output."""
        tool = ShellTool()
        from tempo.tools.base import ToolResult
        
        lines = [f"line{i}" for i in range(50)]
        output = "\n".join(lines)
        result = ToolResult(success=True, output=output)
        summary = tool.default_summarizer(result)
        
        assert "omitted" in summary
        assert "line0" in summary
        assert "line49" in summary
