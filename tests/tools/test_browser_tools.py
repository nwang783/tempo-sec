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
    
    @pytest.mark.asyncio
    async def test_execute_uses_selector_if_present(self):
        """Execute uses selector if available in ref."""
        session = BrowserSession()
        tool = BrowserTypeTool(session)
        
        # Mock session and page
        session.ensure_browser = AsyncMock()
        session._snapshot_refs = {
            "ref_0": {
                "role": "textbox",
                "name": "Search",
                "selector": "#search-input",
            }
        }
        # page is a property, so we set _page
        session._page = MagicMock()
        mock_locator = AsyncMock()
        session._page.locator.return_value = mock_locator
        
        result = await tool.execute(
            element="Search box",
            ref="ref_0",
            text="test query",
        )
        
        assert result.success
        # Should call page.locator("#search-input"), NOT get_by_role
        session.page.locator.assert_called_with("#search-input")
        session.page.get_by_role.assert_not_called()
        # Should clear and fill (with timeout)
        mock_locator.clear.assert_called_once()
        mock_locator.fill.assert_called_with("test query", timeout=30000)


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


class TestBrowserScreenshotTool:
    """Tests for BrowserScreenshotTool."""
    
    def test_tool_metadata(self):
        """Tool has correct metadata."""
        from tempo.tools.browser_tools import BrowserScreenshotTool
        session = BrowserSession()
        tool = BrowserScreenshotTool(session)
        
        assert tool.name == "browser_screenshot"
        assert tool.category == ToolCategory.BROWSING
        assert "screenshot" in tool.description.lower()
    
    def test_schema_has_optional_params(self):
        """Schema has optional parameters."""
        from tempo.tools.browser_tools import BrowserScreenshotTool
        session = BrowserSession()
        tool = BrowserScreenshotTool(session)
        schema = tool.get_schema()
        
        assert "filename" in schema.parameters["properties"]
        assert "full_page" in schema.parameters["properties"]
        assert "return_base64" in schema.parameters["properties"]
        assert schema.parameters["required"] == []


class TestBrowserClickCoordsTool:
    """Tests for BrowserClickCoordsTool."""
    
    def test_tool_metadata(self):
        """Tool has correct metadata."""
        from tempo.tools.browser_tools import BrowserClickCoordsTool
        session = BrowserSession()
        tool = BrowserClickCoordsTool(session)
        
        assert tool.name == "browser_click_coords"
        assert tool.category == ToolCategory.BROWSING
        assert "coordinate" in tool.description.lower()
    
    def test_schema_requires_x_y(self):
        """Schema requires x and y parameters."""
        from tempo.tools.browser_tools import BrowserClickCoordsTool
        session = BrowserSession()
        tool = BrowserClickCoordsTool(session)
        schema = tool.get_schema()
        
        assert "x" in schema.parameters["properties"]
        assert "y" in schema.parameters["properties"]
        assert "button" in schema.parameters["properties"]
        assert "x" in schema.parameters["required"]
        assert "y" in schema.parameters["required"]


class TestBrowserScrollTool:
    """Tests for BrowserScrollTool."""
    
    def test_tool_metadata(self):
        """Tool has correct metadata."""
        from tempo.tools.browser_tools import BrowserScrollTool
        session = BrowserSession()
        tool = BrowserScrollTool(session)
        
        assert tool.name == "browser_scroll"
        assert tool.category == ToolCategory.BROWSING
        assert "scroll" in tool.description.lower()
    
    def test_schema_has_optional_params(self):
        """Schema has optional direction and amount."""
        from tempo.tools.browser_tools import BrowserScrollTool
        session = BrowserSession()
        tool = BrowserScrollTool(session)
        schema = tool.get_schema()
        
        props = schema.parameters["properties"]
        assert "direction" in props
        assert props["direction"]["enum"] == ["up", "down"]
        assert "amount" in props
        assert schema.parameters["required"] == []


class TestBrowserWaitTool:
    """Tests for BrowserWaitTool."""
    
    def test_tool_metadata(self):
        """Tool has correct metadata."""
        from tempo.tools.browser_tools import BrowserWaitTool
        session = BrowserSession()
        tool = BrowserWaitTool(session)
        
        assert tool.name == "browser_wait"
        assert tool.category == ToolCategory.BROWSING
        assert "wait" in tool.description.lower()
    
    def test_schema_has_optional_params(self):
        """Schema has optional parameters."""
        from tempo.tools.browser_tools import BrowserWaitTool
        session = BrowserSession()
        tool = BrowserWaitTool(session)
        schema = tool.get_schema()
        
        props = schema.parameters["properties"]
        assert "selector" in props
        assert "timeout_ms" in props
        assert "state" in props
        assert props["state"]["enum"] == ["visible", "hidden", "attached", "detached"]
        assert schema.parameters["required"] == []


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


class TestBrowserSmartFillTool:
    """Tests for BrowserSmartFillTool."""
    
    def test_tool_metadata(self):
        """Tool has correct metadata."""
        from tempo.tools.browser_tools import BrowserSmartFillTool
        session = BrowserSession()
        tool = BrowserSmartFillTool(session)
        
        assert tool.name == "browser_smart_fill"
        assert tool.category == ToolCategory.BROWSING
        assert "intelligent" in tool.description.lower() or "fill" in tool.description.lower()
    
    def test_schema_requires_fields(self):
        """Schema requires fields parameter."""
        from tempo.tools.browser_tools import BrowserSmartFillTool
        session = BrowserSession()
        tool = BrowserSmartFillTool(session)
        schema = tool.get_schema()
        
        assert "fields" in schema.parameters["properties"]
        assert "fields" in schema.parameters["required"]
        assert "submit" in schema.parameters["properties"]
    
    @pytest.mark.asyncio
    async def test_execute_empty_fields(self):
        """Execute returns error for empty fields."""
        from tempo.tools.browser_tools import BrowserSmartFillTool
        session = BrowserSession()
        tool = BrowserSmartFillTool(session)
        
        session.ensure_browser = AsyncMock()
        
        result = await tool.execute(fields={})
        
        assert not result.success
        assert "No fields provided" in result.error


class TestBrowserVisionSnapshotTool:
    """Tests for BrowserVisionSnapshotTool."""
    
    def test_tool_metadata(self):
        """Tool has correct metadata."""
        from tempo.tools.browser_tools import BrowserVisionSnapshotTool
        session = BrowserSession()
        tool = BrowserVisionSnapshotTool(session)
        
        assert tool.name == "browser_vision_snapshot"
        assert tool.category == ToolCategory.BROWSING
        assert "vision" in tool.description.lower()
        assert "coordinates" in tool.description.lower()
    
    def test_schema_has_optional_params(self):
        """Schema has optional query and full_page parameters."""
        from tempo.tools.browser_tools import BrowserVisionSnapshotTool
        session = BrowserSession()
        tool = BrowserVisionSnapshotTool(session)
        schema = tool.get_schema()
        
        assert "query" in schema.parameters["properties"]
        assert "full_page" in schema.parameters["properties"]
        assert schema.parameters["required"] == []
    
    def test_vision_model_is_gpt5_mini(self):
        """Vision model is hardcoded to gpt-5-mini."""
        from tempo.tools.browser_tools import BrowserVisionSnapshotTool
        session = BrowserSession()
        tool = BrowserVisionSnapshotTool(session)
        
        assert tool.VISION_MODEL == "openai/gpt-5-mini"
    
    def test_vision_prompt_includes_coordinates(self):
        """Vision prompt template asks for coordinates."""
        from tempo.tools.browser_tools import BrowserVisionSnapshotTool
        session = BrowserSession()
        tool = BrowserVisionSnapshotTool(session)
        
        assert "coordinates" in tool.VISION_PROMPT.lower()
        assert "{width}" in tool.VISION_PROMPT
        assert "{height}" in tool.VISION_PROMPT
