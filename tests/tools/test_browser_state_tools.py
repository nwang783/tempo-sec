"""
Unit tests for browser state management tools.

Tests for BrowserListStatesTool, BrowserSaveStateTool, BrowserLoadStateTool,
BrowserDeleteStateTool, and BrowserCleanupStatesTool.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from tempo.tools.browser_state_tools import (
    BrowserListStatesTool,
    BrowserSaveStateTool,
    BrowserLoadStateTool,
    BrowserDeleteStateTool,
    BrowserCleanupStatesTool,
)
from tempo.tools.base import ToolCategory
from tempo.infra.browser_state import BrowserState


@pytest.fixture
def mock_state_manager():
    """Create a mock BrowserStateManager."""
    return MagicMock()


@pytest.fixture
def mock_browser_session():
    """Create a mock BrowserSession."""
    return MagicMock()


class TestBrowserListStatesTool:
    """Tests for BrowserListStatesTool."""

    def test_tool_metadata(self, mock_state_manager):
        """Tool has correct metadata."""
        tool = BrowserListStatesTool(state_manager=mock_state_manager)
        
        assert tool.name == "browser_list_states"
        assert tool.category == ToolCategory.BROWSING
        assert "List" in tool.description

    def test_schema_no_required_params(self, mock_state_manager):
        """Schema has no required parameters."""
        tool = BrowserListStatesTool(state_manager=mock_state_manager)
        schema = tool.get_schema()
        
        assert schema.name == "browser_list_states"
        assert schema.parameters["required"] == []

    @pytest.mark.asyncio
    async def test_execute_empty_states(self, mock_state_manager):
        """Execute returns message when no states exist."""
        mock_state_manager.list_states = AsyncMock(return_value=[])
        tool = BrowserListStatesTool(state_manager=mock_state_manager)
        
        result = await tool.execute()
        
        assert result.success
        assert "No saved browser states found" in result.output
        assert result.metadata["count"] == 0

    @pytest.mark.asyncio
    async def test_execute_with_states(self, mock_state_manager):
        """Execute returns formatted list of states."""
        states = [
            {
                "name": "admin_session",
                "target_domain": "example.com",
                "created_at": "2024-01-15T10:00:00",
                "updated_at": "2024-01-15T11:00:00",
                "expires_at": "2024-01-22T10:00:00",
                "metadata": {"description": "Admin login"},
            },
            {
                "name": "user_session",
                "target_domain": "test.com",
                "created_at": "2024-01-14T09:00:00",
                "updated_at": "2024-01-14T10:00:00",
                "expires_at": "2024-01-21T09:00:00",
                "metadata": {},
            },
        ]
        mock_state_manager.list_states = AsyncMock(return_value=states)
        tool = BrowserListStatesTool(state_manager=mock_state_manager)
        
        result = await tool.execute()
        
        assert result.success
        assert "Found 2 saved browser state(s)" in result.output
        assert "admin_session" in result.output
        assert "user_session" in result.output
        assert "example.com" in result.output
        assert "Admin login" in result.output
        assert result.metadata["count"] == 2

    @pytest.mark.asyncio
    async def test_execute_handles_error(self, mock_state_manager):
        """Execute handles errors gracefully."""
        mock_state_manager.list_states = AsyncMock(side_effect=Exception("Test error"))
        tool = BrowserListStatesTool(state_manager=mock_state_manager)
        
        result = await tool.execute()
        
        assert not result.success
        assert "Test error" in result.error


class TestBrowserSaveStateTool:
    """Tests for BrowserSaveStateTool."""

    def test_tool_metadata(self, mock_browser_session, mock_state_manager):
        """Tool has correct metadata."""
        tool = BrowserSaveStateTool(
            session=mock_browser_session,
            state_manager=mock_state_manager,
        )
        
        assert tool.name == "browser_save_state"
        assert tool.category == ToolCategory.BROWSING
        assert "Save" in tool.description

    def test_schema_requires_name(self, mock_browser_session, mock_state_manager):
        """Schema requires name parameter."""
        tool = BrowserSaveStateTool(
            session=mock_browser_session,
            state_manager=mock_state_manager,
        )
        schema = tool.get_schema()
        
        assert "name" in schema.parameters["properties"]
        assert "name" in schema.parameters["required"]
        assert "description" in schema.parameters["properties"]
        assert "ttl_days" in schema.parameters["properties"]

    @pytest.mark.asyncio
    async def test_execute_saves_state(self, mock_browser_session, mock_state_manager):
        """Execute saves browser state successfully."""
        # Mock capture_state to return a state
        mock_state = BrowserState(
            name="",
            target_domain="example.com",
            cookies=[{"name": "session", "value": "abc123"}],
        )
        mock_browser_session.capture_state = AsyncMock(return_value=mock_state)
        mock_state_manager.save = AsyncMock()
        
        tool = BrowserSaveStateTool(
            session=mock_browser_session,
            state_manager=mock_state_manager,
        )
        
        result = await tool.execute(
            name="my_session",
            description="Test session",
            ttl_days=14,
        )
        
        assert result.success
        assert "my_session" in result.output
        assert "example.com" in result.output
        assert result.metadata["state_name"] == "my_session"
        assert result.metadata["domain"] == "example.com"
        
        # Verify save was called
        mock_state_manager.save.assert_called_once()
        saved_state = mock_state_manager.save.call_args[0][0]
        assert saved_state.name == "my_session"
        assert saved_state.metadata["description"] == "Test session"

    @pytest.mark.asyncio
    async def test_execute_handles_error(self, mock_browser_session, mock_state_manager):
        """Execute handles errors gracefully."""
        mock_browser_session.capture_state = AsyncMock(
            side_effect=Exception("Browser not initialized")
        )
        
        tool = BrowserSaveStateTool(
            session=mock_browser_session,
            state_manager=mock_state_manager,
        )
        
        result = await tool.execute(name="test")
        
        assert not result.success
        assert "Browser not initialized" in result.error


class TestBrowserLoadStateTool:
    """Tests for BrowserLoadStateTool."""

    def test_tool_metadata(self, mock_browser_session, mock_state_manager):
        """Tool has correct metadata."""
        tool = BrowserLoadStateTool(
            session=mock_browser_session,
            state_manager=mock_state_manager,
        )
        
        assert tool.name == "browser_load_state"
        assert tool.category == ToolCategory.BROWSING
        assert "Load" in tool.description

    def test_schema_requires_name(self, mock_browser_session, mock_state_manager):
        """Schema requires name parameter."""
        tool = BrowserLoadStateTool(
            session=mock_browser_session,
            state_manager=mock_state_manager,
        )
        schema = tool.get_schema()
        
        assert "name" in schema.parameters["properties"]
        assert "name" in schema.parameters["required"]

    @pytest.mark.asyncio
    async def test_execute_loads_state(self, mock_browser_session, mock_state_manager):
        """Execute loads browser state successfully."""
        mock_state = BrowserState(
            name="test_session",
            target_domain="example.com",
            cookies=[{"name": "session", "value": "abc123"}],
        )
        mock_state_manager.load = AsyncMock(return_value=mock_state)
        mock_browser_session.restore_state = AsyncMock()
        
        tool = BrowserLoadStateTool(
            session=mock_browser_session,
            state_manager=mock_state_manager,
        )
        
        result = await tool.execute(name="test_session")
        
        assert result.success
        assert "test_session" in result.output
        assert "example.com" in result.output
        assert result.metadata["state_name"] == "test_session"
        
        # Verify restore_state was called
        mock_browser_session.restore_state.assert_called_once_with(mock_state)

    @pytest.mark.asyncio
    async def test_execute_state_not_found(self, mock_browser_session, mock_state_manager):
        """Execute returns error when state doesn't exist."""
        mock_state_manager.load = AsyncMock(return_value=None)
        
        tool = BrowserLoadStateTool(
            session=mock_browser_session,
            state_manager=mock_state_manager,
        )
        
        result = await tool.execute(name="nonexistent")
        
        assert not result.success
        assert "No saved state found" in result.error
        assert "nonexistent" in result.error

    @pytest.mark.asyncio
    async def test_execute_handles_error(self, mock_browser_session, mock_state_manager):
        """Execute handles errors gracefully."""
        mock_state_manager.load = AsyncMock(side_effect=Exception("IO error"))
        
        tool = BrowserLoadStateTool(
            session=mock_browser_session,
            state_manager=mock_state_manager,
        )
        
        result = await tool.execute(name="test")
        
        assert not result.success
        assert "IO error" in result.error


class TestBrowserDeleteStateTool:
    """Tests for BrowserDeleteStateTool."""

    def test_tool_metadata(self, mock_state_manager):
        """Tool has correct metadata."""
        tool = BrowserDeleteStateTool(state_manager=mock_state_manager)
        
        assert tool.name == "browser_delete_state"
        assert tool.category == ToolCategory.BROWSING
        assert "Delete" in tool.description

    def test_schema_requires_name(self, mock_state_manager):
        """Schema requires name parameter."""
        tool = BrowserDeleteStateTool(state_manager=mock_state_manager)
        schema = tool.get_schema()
        
        assert "name" in schema.parameters["properties"]
        assert "name" in schema.parameters["required"]

    @pytest.mark.asyncio
    async def test_execute_deletes_state(self, mock_state_manager):
        """Execute deletes state successfully."""
        mock_state_manager.delete = AsyncMock(return_value=True)
        tool = BrowserDeleteStateTool(state_manager=mock_state_manager)
        
        result = await tool.execute(name="old_session")
        
        assert result.success
        assert "Deleted" in result.output
        assert "old_session" in result.output
        assert result.metadata["state_name"] == "old_session"

    @pytest.mark.asyncio
    async def test_execute_state_not_found(self, mock_state_manager):
        """Execute returns error when state doesn't exist."""
        mock_state_manager.delete = AsyncMock(return_value=False)
        tool = BrowserDeleteStateTool(state_manager=mock_state_manager)
        
        result = await tool.execute(name="nonexistent")
        
        assert not result.success
        assert "No saved state found" in result.error
        assert "nonexistent" in result.error

    @pytest.mark.asyncio
    async def test_execute_handles_error(self, mock_state_manager):
        """Execute handles errors gracefully."""
        mock_state_manager.delete = AsyncMock(side_effect=Exception("Permission denied"))
        tool = BrowserDeleteStateTool(state_manager=mock_state_manager)
        
        result = await tool.execute(name="test")
        
        assert not result.success
        assert "Permission denied" in result.error


class TestBrowserCleanupStatesTool:
    """Tests for BrowserCleanupStatesTool."""

    def test_tool_metadata(self, mock_state_manager):
        """Tool has correct metadata."""
        tool = BrowserCleanupStatesTool(state_manager=mock_state_manager)
        
        assert tool.name == "browser_cleanup_states"
        assert tool.category == ToolCategory.BROWSING
        assert "expired" in tool.description.lower()

    def test_schema_no_required_params(self, mock_state_manager):
        """Schema has no required parameters."""
        tool = BrowserCleanupStatesTool(state_manager=mock_state_manager)
        schema = tool.get_schema()
        
        assert schema.parameters["required"] == []

    @pytest.mark.asyncio
    async def test_execute_cleans_up_expired(self, mock_state_manager):
        """Execute cleans up expired states."""
        mock_state_manager.cleanup_expired = AsyncMock(return_value=5)
        tool = BrowserCleanupStatesTool(state_manager=mock_state_manager)
        
        result = await tool.execute()
        
        assert result.success
        assert "5" in result.output
        assert "expired" in result.output.lower()
        assert result.metadata["deleted_count"] == 5

    @pytest.mark.asyncio
    async def test_execute_no_expired_states(self, mock_state_manager):
        """Execute works when no expired states exist."""
        mock_state_manager.cleanup_expired = AsyncMock(return_value=0)
        tool = BrowserCleanupStatesTool(state_manager=mock_state_manager)
        
        result = await tool.execute()
        
        assert result.success
        assert "0" in result.output
        assert result.metadata["deleted_count"] == 0

    @pytest.mark.asyncio
    async def test_execute_handles_error(self, mock_state_manager):
        """Execute handles errors gracefully."""
        mock_state_manager.cleanup_expired = AsyncMock(
            side_effect=Exception("Disk full")
        )
        tool = BrowserCleanupStatesTool(state_manager=mock_state_manager)
        
        result = await tool.execute()
        
        assert not result.success
        assert "Disk full" in result.error


class TestToolSchemaFormat:
    """Test that all tools produce valid schemas."""

    def test_all_tools_have_valid_openai_schema(
        self, mock_browser_session, mock_state_manager
    ):
        """All tools produce valid OpenAI-format schemas."""
        tools = [
            BrowserListStatesTool(state_manager=mock_state_manager),
            BrowserSaveStateTool(
                session=mock_browser_session, state_manager=mock_state_manager
            ),
            BrowserLoadStateTool(
                session=mock_browser_session, state_manager=mock_state_manager
            ),
            BrowserDeleteStateTool(state_manager=mock_state_manager),
            BrowserCleanupStatesTool(state_manager=mock_state_manager),
        ]
        
        for tool in tools:
            schema = tool.get_schema()
            openai_schema = schema.to_openai_format()
            
            assert openai_schema["type"] == "function"
            assert "function" in openai_schema
            assert openai_schema["function"]["name"] == tool.name
            assert "description" in openai_schema["function"]
            assert "parameters" in openai_schema["function"]


