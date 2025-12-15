"""Tests for tempo/tools/registry.py."""

import pytest

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema
from tempo.tools.registry import ToolRegistry


class DummyTool(Tool):
    """A dummy tool for testing."""
    
    name = "dummy"
    description = "A dummy tool"
    category = ToolCategory.EXECUTION
    
    async def execute(self, purpose: str = "") -> ToolResult:
        return ToolResult(success=True, output="dummy output")
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={"type": "object", "properties": {}},
        )


class AnotherTool(Tool):
    """Another dummy tool."""
    
    name = "another"
    description = "Another tool"
    category = ToolCategory.ANALYSIS
    
    async def execute(self, arg: str, purpose: str = "") -> ToolResult:
        return ToolResult(success=True, output=f"arg: {arg}")
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "arg": {"type": "string"},
                },
                "required": ["arg"],
            },
        )


class TestToolRegistry:
    """Tests for ToolRegistry class."""
    
    def test_create_empty_registry(self):
        """Test creating an empty registry."""
        registry = ToolRegistry()
        assert len(registry) == 0
    
    def test_register_tool(self):
        """Test registering a tool."""
        registry = ToolRegistry()
        tool = DummyTool()
        registry.register(tool)
        
        assert len(registry) == 1
        assert "dummy" in registry
    
    def test_register_duplicate_raises(self):
        """Test that registering duplicate tool raises."""
        registry = ToolRegistry()
        registry.register(DummyTool())
        
        with pytest.raises(ValueError, match="already registered"):
            registry.register(DummyTool())
    
    def test_get_tool(self):
        """Test getting a tool by name."""
        registry = ToolRegistry()
        tool = DummyTool()
        registry.register(tool)
        
        retrieved = registry.get("dummy")
        assert retrieved is tool
    
    def test_get_nonexistent_returns_none(self):
        """Test getting nonexistent tool returns None."""
        registry = ToolRegistry()
        assert registry.get("nonexistent") is None
    
    def test_unregister_tool(self):
        """Test unregistering a tool."""
        registry = ToolRegistry()
        registry.register(DummyTool())
        
        result = registry.unregister("dummy")
        
        assert result is True
        assert "dummy" not in registry
    
    def test_unregister_nonexistent(self):
        """Test unregistering nonexistent tool."""
        registry = ToolRegistry()
        result = registry.unregister("nonexistent")
        assert result is False
    
    def test_list_tools(self):
        """Test listing tool names."""
        registry = ToolRegistry()
        registry.register(DummyTool())
        registry.register(AnotherTool())
        
        names = registry.list_tools()
        
        assert set(names) == {"dummy", "another"}
    
    def test_get_schemas(self):
        """Test getting all tool schemas."""
        registry = ToolRegistry()
        registry.register(DummyTool())
        registry.register(AnotherTool())
        
        schemas = registry.get_schemas()
        
        assert len(schemas) == 2
        assert all(s["type"] == "function" for s in schemas)
    
    def test_get_single_schema(self):
        """Test getting a single tool schema."""
        registry = ToolRegistry()
        registry.register(DummyTool())
        
        schema = registry.get_schema("dummy")
        
        assert schema is not None
        assert schema["function"]["name"] == "dummy"
    
    def test_contains(self):
        """Test __contains__ method."""
        registry = ToolRegistry()
        registry.register(DummyTool())
        
        assert "dummy" in registry
        assert "other" not in registry
