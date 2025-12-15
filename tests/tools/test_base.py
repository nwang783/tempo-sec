"""Tests for tempo/tools/base.py."""

import pytest

from tempo.tools.base import (
    Tool,
    ToolCategory,
    ToolResult,
    ToolSchema,
)


class TestToolCategory:
    """Tests for ToolCategory enum."""
    
    def test_all_categories_exist(self):
        """Test all expected categories exist."""
        assert ToolCategory.EXECUTION == "execution"
        assert ToolCategory.BROWSING == "browsing"
        assert ToolCategory.FILESYSTEM == "filesystem"
        assert ToolCategory.NETWORK == "network"
        assert ToolCategory.ANALYSIS == "analysis"
        assert ToolCategory.META == "meta"


class TestToolResult:
    """Tests for ToolResult dataclass."""
    
    def test_successful_result(self):
        """Test creating a successful result."""
        result = ToolResult(
            success=True,
            output="Command completed successfully",
        )
        
        assert result.success is True
        assert result.output == "Command completed successfully"
        assert result.error is None
        assert result.metadata == {}
    
    def test_failed_result(self):
        """Test creating a failed result."""
        result = ToolResult(
            success=False,
            output="",
            error="Command not found: xyz",
        )
        
        assert result.success is False
        assert result.error == "Command not found: xyz"
    
    def test_result_with_metadata(self):
        """Test result with metadata."""
        result = ToolResult(
            success=True,
            output="data",
            metadata={"exit_code": 0, "duration": 1.5},
        )
        
        assert result.metadata == {"exit_code": 0, "duration": 1.5}
    
    def test_result_with_structured_data(self):
        """Test result with structured data."""
        result = ToolResult(
            success=True,
            output="JSON parsed",
            structured_data={"key": "value", "items": [1, 2, 3]},
        )
        
        assert result.structured_data == {"key": "value", "items": [1, 2, 3]}


class TestToolSchema:
    """Tests for ToolSchema dataclass."""
    
    def test_basic_schema(self):
        """Test basic schema creation."""
        schema = ToolSchema(
            name="test_tool",
            description="A test tool",
            parameters={
                "type": "object",
                "properties": {
                    "arg1": {"type": "string"},
                },
                "required": ["arg1"],
            },
        )
        
        assert schema.name == "test_tool"
        assert schema.description == "A test tool"
    
    def test_to_openai_format(self):
        """Test conversion to OpenAI format."""
        schema = ToolSchema(
            name="shell",
            description="Execute shell commands",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The command"},
                },
                "required": ["command"],
            },
        )
        
        openai_format = schema.to_openai_format()
        
        assert openai_format["type"] == "function"
        assert openai_format["function"]["name"] == "shell"
        assert openai_format["function"]["description"] == "Execute shell commands"
        assert "parameters" in openai_format["function"]
    
    def test_purpose_field_injected(self):
        """Test that 'purpose' field is automatically added."""
        schema = ToolSchema(
            name="test",
            description="Test tool",
            parameters={
                "type": "object",
                "properties": {
                    "arg": {"type": "string"},
                },
                "required": ["arg"],
            },
        )
        
        openai_format = schema.to_openai_format()
        params = openai_format["function"]["parameters"]
        
        # Purpose should be added to properties
        assert "purpose" in params["properties"]
        assert params["properties"]["purpose"]["type"] == "string"
        
        # Purpose should be in required
        assert "purpose" in params["required"]
    
    def test_purpose_not_duplicated(self):
        """Test that 'purpose' isn't duplicated if already present."""
        schema = ToolSchema(
            name="test",
            description="Test tool",
            parameters={
                "type": "object",
                "properties": {
                    "purpose": {"type": "string", "description": "Custom purpose"},
                },
                "required": ["purpose"],
            },
        )
        
        openai_format = schema.to_openai_format()
        params = openai_format["function"]["parameters"]
        
        # Should still only have one purpose
        assert params["required"].count("purpose") == 1
    
    def test_original_parameters_not_mutated(self):
        """Test that original parameters dict is not mutated."""
        original_params = {
            "type": "object",
            "properties": {
                "arg": {"type": "string"},
            },
            "required": ["arg"],
        }
        original_required = list(original_params["required"])
        
        schema = ToolSchema(
            name="test",
            description="Test",
            parameters=original_params,
        )
        
        schema.to_openai_format()
        
        # Original should not be mutated
        assert original_params["required"] == original_required
        assert "purpose" not in original_params["properties"]


class TestToolABC:
    """Tests for Tool abstract base class."""
    
    def test_cannot_instantiate_directly(self):
        """Test that Tool cannot be instantiated directly."""
        with pytest.raises(TypeError):
            Tool()  # type: ignore
    
    def test_default_summarizer_short_output(self):
        """Test default summarizer passes through short output."""
        class DummyTool(Tool):
            name = "dummy"
            description = "A dummy tool"
            category = ToolCategory.META
            
            async def execute(self, **kwargs):
                return ToolResult(success=True, output="test")
            
            def get_schema(self):
                return ToolSchema(name=self.name, description=self.description, parameters={})
        
        tool = DummyTool()
        result = ToolResult(success=True, output="Short output")
        
        summary = tool.default_summarizer(result)
        assert summary == "Short output"
    
    def test_default_summarizer_long_output(self):
        """Test default summarizer truncates long output."""
        class DummyTool(Tool):
            name = "dummy"
            description = "A dummy tool"
            category = ToolCategory.META
            
            async def execute(self, **kwargs):
                return ToolResult(success=True, output="test")
            
            def get_schema(self):
                return ToolSchema(name=self.name, description=self.description, parameters={})
        
        tool = DummyTool()
        long_output = "A" * 600  # > 500 chars
        result = ToolResult(success=True, output=long_output)
        
        summary = tool.default_summarizer(result)
        
        assert len(summary) < len(long_output)
        assert "[truncated]" in summary
        assert summary.startswith("A" * 250)
        assert summary.endswith("A" * 250)
    
    def test_default_summarizer_error(self):
        """Test default summarizer handles errors."""
        class DummyTool(Tool):
            name = "dummy"
            description = "A dummy tool"
            category = ToolCategory.META
            
            async def execute(self, **kwargs):
                return ToolResult(success=True, output="test")
            
            def get_schema(self):
                return ToolSchema(name=self.name, description=self.description, parameters={})
        
        tool = DummyTool()
        result = ToolResult(success=False, output="", error="Command failed")
        
        summary = tool.default_summarizer(result)
        assert summary == "Error: Command failed"
