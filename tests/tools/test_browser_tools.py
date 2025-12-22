"""
Tests for Playwright-style browser tools.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tempo.tools.browser_tools import (
    BrowserSession,
    BrowserNavigateTool,
    BrowserSnapshotTool,
    BrowserClickTool,
    BrowserTypeTool,
    BrowserFillFormTool,
)
from tempo.tools.base import ToolCategory


class TestBrowserSession:
    """Tests for BrowserSession manager."""
    
    def test_init_without_container(self):
        """Session initializes correctly without container."""
        session = BrowserSession()
        assert session.container is None
        assert session._browser is None
        assert session._page is None
        assert session._snapshot_refs == {}
    
    def test_init_with_container(self):
        """Session initializes correctly with container."""
        mock_container = MagicMock()
        session = BrowserSession(container_manager=mock_container)
        assert session.container is mock_container
    
    def test_store_and_get_refs(self):
        """Can store and retrieve snapshot refs."""
        session = BrowserSession()
        refs = {
            "ref_0": {"role": "button", "name": "Submit"},
            "ref_1": {"role": "textbox", "name": "Username"},
        }
        session.store_snapshot_refs(refs)
        
        assert session.get_element_by_ref("ref_0") == refs["ref_0"]
        assert session.get_element_by_ref("ref_1") == refs["ref_1"]
        assert session.get_element_by_ref("ref_999") is None


class TestBrowserNavigateTool:
    """Tests for BrowserNavigateTool."""
    
    def test_tool_metadata(self):
        """Tool has correct metadata."""
        session = BrowserSession()
        tool = BrowserNavigateTool(session)
        
        assert tool.name == "browser_navigate"
        assert tool.category == ToolCategory.BROWSING
        assert "Navigate" in tool.description
    
    def test_schema_has_url_required(self):
        """Schema requires url parameter."""
        session = BrowserSession()
        tool = BrowserNavigateTool(session)
        schema = tool.get_schema()
        
        assert schema.name == "browser_navigate"
        assert "url" in schema.parameters["properties"]
        assert "url" in schema.parameters["required"]
    
    @pytest.mark.asyncio
    async def test_execute_with_container_not_implemented(self):
        """Container execution returns not implemented error."""
        mock_container = MagicMock()
        session = BrowserSession(container_manager=mock_container)
        tool = BrowserNavigateTool(session)
        
        # Mock ensure_browser to do nothing
        session.ensure_browser = AsyncMock()
        
        # Mock container.exec to return success
        mock_container.exec = AsyncMock(return_value=(0, "URL: https://example.com\nTitle: Example\nStatus: 200", ""))
        
        result = await tool.execute(url="https://example.com")
        
        # Should work with container implementation
        assert result.success


class TestBrowserSnapshotTool:
    """Tests for BrowserSnapshotTool."""
    
    def test_tool_metadata(self):
        """Tool has correct metadata."""
        session = BrowserSession()
        tool = BrowserSnapshotTool(session)
        
        assert tool.name == "browser_snapshot"
        assert tool.category == ToolCategory.BROWSING
    
    def test_schema_has_optional_filename(self):
        """Schema has optional filename parameter."""
        session = BrowserSession()
        tool = BrowserSnapshotTool(session)
        schema = tool.get_schema()
        
        assert "filename" in schema.parameters["properties"]
        assert schema.parameters["required"] == []


class TestBrowserClickTool:
    """Tests for BrowserClickTool."""
    
    def test_tool_metadata(self):
        """Tool has correct metadata."""
        session = BrowserSession()
        tool = BrowserClickTool(session)
        
        assert tool.name == "browser_click"
        assert tool.category == ToolCategory.BROWSING
    
    def test_schema_requires_element_and_ref(self):
        """Schema requires element and ref parameters."""
        session = BrowserSession()
        tool = BrowserClickTool(session)
        schema = tool.get_schema()
        
        assert "element" in schema.parameters["properties"]
        assert "ref" in schema.parameters["properties"]
        assert "element" in schema.parameters["required"]
        assert "ref" in schema.parameters["required"]
    
    def test_schema_has_optional_click_options(self):
        """Schema has optional click options."""
        session = BrowserSession()
        tool = BrowserClickTool(session)
        schema = tool.get_schema()
        
        props = schema.parameters["properties"]
        assert "doubleClick" in props
        assert "button" in props
        assert "modifiers" in props
    
    @pytest.mark.asyncio
    async def test_execute_missing_ref(self):
        """Execute returns error for missing ref."""
        session = BrowserSession()
        tool = BrowserClickTool(session)
        
        # Mock ensure_browser
        session.ensure_browser = AsyncMock()
        
        result = await tool.execute(
            element="Submit button",
            ref="ref_nonexistent",
        )
        
        assert not result.success
        assert "Ref not found" in result.error


class TestBrowserTypeTool:
    """Tests for BrowserTypeTool."""
    
    def test_tool_metadata(self):
        """Tool has correct metadata."""
        session = BrowserSession()
        tool = BrowserTypeTool(session)
        
        assert tool.name == "browser_type"
        assert tool.category == ToolCategory.BROWSING
    
    def test_schema_requires_element_ref_text(self):
        """Schema requires element, ref, and text parameters."""
        session = BrowserSession()
        tool = BrowserTypeTool(session)
        schema = tool.get_schema()
        
        required = schema.parameters["required"]
        assert "element" in required
        assert "ref" in required
        assert "text" in required


class TestBrowserFillFormTool:
    """Tests for BrowserFillFormTool."""
    
    def test_tool_metadata(self):
        """Tool has correct metadata."""
        session = BrowserSession()
        tool = BrowserFillFormTool(session)
        
        assert tool.name == "browser_fill_form"
        assert tool.category == ToolCategory.BROWSING
    
    def test_schema_requires_fields_array(self):
        """Schema requires fields array parameter."""
        session = BrowserSession()
        tool = BrowserFillFormTool(session)
        schema = tool.get_schema()
        
        assert "fields" in schema.parameters["properties"]
        assert "fields" in schema.parameters["required"]
        assert schema.parameters["properties"]["fields"]["type"] == "array"
    
    @pytest.mark.asyncio
    async def test_execute_empty_fields(self):
        """Execute returns error for empty fields."""
        session = BrowserSession()
        tool = BrowserFillFormTool(session)
        
        session.ensure_browser = AsyncMock()
        
        result = await tool.execute(fields=[])
        
        assert not result.success
        assert "No fields provided" in result.error


class TestToolFactoryIntegration:
    """Integration tests for tool factory."""
    
    def test_local_tools_include_browser_tools(self):
        """create_local_tools registers all browser tools."""
        from unittest.mock import MagicMock
        from tempo.tools.tool_factory import create_local_tools
        
        mock_context = MagicMock()
        
        with pytest.warns(RuntimeWarning):
            registry = create_local_tools(context_store=mock_context)
        
        # Check all browser tools are registered
        assert "browser_navigate" in registry
        assert "browser_snapshot" in registry
        assert "browser_click" in registry
        assert "browser_type" in registry
        assert "browser_fill_form" in registry
