"""
Integration tests for browser state persistence flow.

Tests cover the full lifecycle of browser state management:
- Login flow with state saving
- State persistence across browser agent invocations
- Multiple named states without conflicts
- Expired state handling
- State cleanup operations
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import json

from tempo.infra.browser_state import BrowserState, BrowserStateManager
from tempo.tools.browser_state_tools import (
    BrowserListStatesTool,
    BrowserSaveStateTool,
    BrowserLoadStateTool,
    BrowserDeleteStateTool,
    BrowserCleanupStatesTool,
)


@pytest.fixture
def temp_state_dir(tmp_path):
    """Provide a temporary directory for state storage."""
    state_dir = tmp_path / "browser_states"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


@pytest.fixture
def state_manager(temp_state_dir):
    """Provide a BrowserStateManager with a temporary directory."""
    return BrowserStateManager(state_dir=temp_state_dir)


@pytest.fixture
def mock_browser_session():
    """Create a mock BrowserSession with state capture/restore capabilities."""
    session = MagicMock()
    
    # Track stored state
    session._current_state = {
        "cookies": [],
        "local_storage": {},
        "session_storage": {},
        "url": "about:blank",
    }
    
    async def capture_state():
        from urllib.parse import urlparse
        domain = urlparse(session._current_state["url"]).netloc
        return BrowserState(
            name="",  # Will be set by caller
            target_domain=domain or "example.com",
            cookies=session._current_state["cookies"].copy(),
            local_storage=session._current_state["local_storage"].copy(),
            session_storage=session._current_state["session_storage"].copy(),
        )
    
    async def restore_state(state):
        session._current_state["cookies"] = state.cookies.copy()
        session._current_state["local_storage"] = state.local_storage.copy()
        session._current_state["session_storage"] = state.session_storage.copy()
    
    session.capture_state = capture_state
    session.restore_state = restore_state
    
    return session


class TestFullStateFlow:
    """Integration tests for the complete state management flow."""

    @pytest.mark.asyncio
    async def test_login_save_reload_verify_flow(
        self, mock_browser_session, state_manager
    ):
        """
        Test full flow: login → save state → new session → load state → verify.
        
        This simulates:
        1. Browser agent logs in and saves session
        2. New browser agent instance loads the saved session
        3. Verify the session data is correctly restored
        """
        # Simulate login - set cookies and storage
        mock_browser_session._current_state = {
            "cookies": [
                {"name": "session_id", "value": "abc123", "domain": "example.com"},
                {"name": "csrf_token", "value": "xyz789", "domain": "example.com"},
            ],
            "local_storage": {
                "user_id": "12345",
                "auth_token": "jwt_token_here",
            },
            "session_storage": {
                "cart": '["item1", "item2"]',
            },
            "url": "https://example.com/dashboard",
        }
        
        # Save state using the tool
        save_tool = BrowserSaveStateTool(
            session=mock_browser_session,
            state_manager=state_manager,
        )
        
        save_result = await save_tool.execute(
            name="admin_session",
            description="Admin account logged in",
        )
        
        assert save_result.success
        assert "admin_session" in save_result.output
        
        # Simulate new browser session (clear current state)
        mock_browser_session._current_state = {
            "cookies": [],
            "local_storage": {},
            "session_storage": {},
            "url": "about:blank",
        }
        
        # Load state in new session
        load_tool = BrowserLoadStateTool(
            session=mock_browser_session,
            state_manager=state_manager,
        )
        
        load_result = await load_tool.execute(name="admin_session")
        
        assert load_result.success
        assert "admin_session" in load_result.output
        
        # Verify state was restored
        assert len(mock_browser_session._current_state["cookies"]) == 2
        assert mock_browser_session._current_state["cookies"][0]["name"] == "session_id"
        assert mock_browser_session._current_state["local_storage"]["auth_token"] == "jwt_token_here"
        assert mock_browser_session._current_state["session_storage"]["cart"] == '["item1", "item2"]'

    @pytest.mark.asyncio
    async def test_multiple_named_states_no_conflict(
        self, mock_browser_session, state_manager
    ):
        """Test that multiple named states don't conflict with each other."""
        save_tool = BrowserSaveStateTool(
            session=mock_browser_session,
            state_manager=state_manager,
        )
        list_tool = BrowserListStatesTool(state_manager=state_manager)
        load_tool = BrowserLoadStateTool(
            session=mock_browser_session,
            state_manager=state_manager,
        )
        
        # Create admin session
        mock_browser_session._current_state = {
            "cookies": [{"name": "role", "value": "admin", "domain": "example.com"}],
            "local_storage": {"privileges": "full"},
            "session_storage": {},
            "url": "https://example.com",
        }
        await save_tool.execute(name="admin_session", description="Admin user")
        
        # Create user session
        mock_browser_session._current_state = {
            "cookies": [{"name": "role", "value": "user", "domain": "example.com"}],
            "local_storage": {"privileges": "limited"},
            "session_storage": {},
            "url": "https://example.com",
        }
        await save_tool.execute(name="user_session", description="Regular user")
        
        # Create guest session
        mock_browser_session._current_state = {
            "cookies": [{"name": "role", "value": "guest", "domain": "example.com"}],
            "local_storage": {"privileges": "none"},
            "session_storage": {},
            "url": "https://example.com",
        }
        await save_tool.execute(name="guest_session", description="Guest user")
        
        # List all states
        list_result = await list_tool.execute()
        assert list_result.success
        assert list_result.metadata["count"] == 3
        assert "admin_session" in list_result.output
        assert "user_session" in list_result.output
        assert "guest_session" in list_result.output
        
        # Load admin session and verify
        await load_tool.execute(name="admin_session")
        assert mock_browser_session._current_state["cookies"][0]["value"] == "admin"
        assert mock_browser_session._current_state["local_storage"]["privileges"] == "full"
        
        # Load user session and verify
        await load_tool.execute(name="user_session")
        assert mock_browser_session._current_state["cookies"][0]["value"] == "user"
        assert mock_browser_session._current_state["local_storage"]["privileges"] == "limited"
        
        # Load guest session and verify
        await load_tool.execute(name="guest_session")
        assert mock_browser_session._current_state["cookies"][0]["value"] == "guest"
        assert mock_browser_session._current_state["local_storage"]["privileges"] == "none"

    @pytest.mark.asyncio
    async def test_expired_states_not_loaded(self, mock_browser_session, state_manager):
        """Test that expired states are not loaded and are cleaned up."""
        # Create an expired state directly in the filesystem
        past = datetime.utcnow() - timedelta(days=1)
        expired_path = state_manager._state_path("expired_session")
        expired_path.write_text(json.dumps({
            "name": "expired_session",
            "target_domain": "example.com",
            "cookies": [{"name": "old", "value": "expired"}],
            "local_storage": {},
            "session_storage": {},
            "created_at": past.isoformat(),
            "updated_at": past.isoformat(),
            "expires_at": past.isoformat(),
            "metadata": {"description": "This session has expired"},
        }))
        
        # Try to load expired state
        load_tool = BrowserLoadStateTool(
            session=mock_browser_session,
            state_manager=state_manager,
        )
        
        result = await load_tool.execute(name="expired_session")
        
        assert not result.success
        assert "No saved state found" in result.error
        assert "expired" in result.error.lower() or "deleted" in result.error.lower()
        
        # Verify the expired state file was cleaned up
        assert not expired_path.exists()

    @pytest.mark.asyncio
    async def test_cleanup_only_removes_expired_states(
        self, mock_browser_session, state_manager
    ):
        """Test that cleanup removes only expired states, keeping valid ones."""
        save_tool = BrowserSaveStateTool(
            session=mock_browser_session,
            state_manager=state_manager,
        )
        
        # Create valid states
        mock_browser_session._current_state = {
            "cookies": [{"name": "valid", "value": "1", "domain": "example.com"}],
            "local_storage": {},
            "session_storage": {},
            "url": "https://example.com",
        }
        await save_tool.execute(name="valid_session_1")
        await save_tool.execute(name="valid_session_2")
        
        # Create expired states directly
        past = datetime.utcnow() - timedelta(days=1)
        for i in range(3):
            expired_path = state_manager._state_path(f"expired_{i}")
            expired_path.write_text(json.dumps({
                "name": f"expired_{i}",
                "target_domain": "example.com",
                "cookies": [],
                "local_storage": {},
                "session_storage": {},
                "created_at": past.isoformat(),
                "updated_at": past.isoformat(),
                "expires_at": past.isoformat(),
                "metadata": {},
            }))
        
        # Run cleanup
        cleanup_tool = BrowserCleanupStatesTool(state_manager=state_manager)
        cleanup_result = await cleanup_tool.execute()
        
        assert cleanup_result.success
        assert cleanup_result.metadata["deleted_count"] == 3
        
        # Verify valid states still exist
        list_tool = BrowserListStatesTool(state_manager=state_manager)
        list_result = await list_tool.execute()
        
        assert list_result.metadata["count"] == 2
        assert "valid_session_1" in list_result.output
        assert "valid_session_2" in list_result.output

    @pytest.mark.asyncio
    async def test_state_persistence_across_invocations(
        self, mock_browser_session, temp_state_dir
    ):
        """Test state persists when state manager is recreated (simulating new invocation)."""
        # First invocation: save state
        manager1 = BrowserStateManager(state_dir=temp_state_dir)
        save_tool = BrowserSaveStateTool(
            session=mock_browser_session,
            state_manager=manager1,
        )
        
        mock_browser_session._current_state = {
            "cookies": [{"name": "persistent", "value": "data", "domain": "example.com"}],
            "local_storage": {"key": "value"},
            "session_storage": {},
            "url": "https://example.com",
        }
        await save_tool.execute(name="persistent_session")
        
        # Second invocation: new manager instance, load state
        manager2 = BrowserStateManager(state_dir=temp_state_dir)
        
        # Clear browser state to prove it loads from disk
        mock_browser_session._current_state = {
            "cookies": [],
            "local_storage": {},
            "session_storage": {},
            "url": "about:blank",
        }
        
        load_tool = BrowserLoadStateTool(
            session=mock_browser_session,
            state_manager=manager2,
        )
        
        result = await load_tool.execute(name="persistent_session")
        
        assert result.success
        assert mock_browser_session._current_state["cookies"][0]["value"] == "data"
        assert mock_browser_session._current_state["local_storage"]["key"] == "value"

    @pytest.mark.asyncio
    async def test_state_update_preserves_cookies(
        self, mock_browser_session, state_manager
    ):
        """Test that updating a state preserves the original data structure."""
        save_tool = BrowserSaveStateTool(
            session=mock_browser_session,
            state_manager=state_manager,
        )
        
        # Initial save
        mock_browser_session._current_state = {
            "cookies": [
                {"name": "cookie1", "value": "v1", "domain": "example.com"},
            ],
            "local_storage": {"initial": "data"},
            "session_storage": {},
            "url": "https://example.com",
        }
        await save_tool.execute(name="evolving_session")
        
        # Update state with additional data
        mock_browser_session._current_state = {
            "cookies": [
                {"name": "cookie1", "value": "v1", "domain": "example.com"},
                {"name": "cookie2", "value": "v2", "domain": "example.com"},
            ],
            "local_storage": {"initial": "data", "new": "value"},
            "session_storage": {"temp": "data"},
            "url": "https://example.com",
        }
        await save_tool.execute(name="evolving_session")
        
        # Load and verify updated state
        load_tool = BrowserLoadStateTool(
            session=mock_browser_session,
            state_manager=state_manager,
        )
        
        # Clear and reload
        mock_browser_session._current_state = {
            "cookies": [],
            "local_storage": {},
            "session_storage": {},
            "url": "about:blank",
        }
        await load_tool.execute(name="evolving_session")
        
        assert len(mock_browser_session._current_state["cookies"]) == 2
        assert mock_browser_session._current_state["local_storage"]["new"] == "value"
        assert mock_browser_session._current_state["session_storage"]["temp"] == "data"


class TestStateFlowErrorHandling:
    """Test error handling in state flow scenarios."""

    @pytest.mark.asyncio
    async def test_load_nonexistent_state(self, mock_browser_session, state_manager):
        """Test loading a state that was never saved."""
        load_tool = BrowserLoadStateTool(
            session=mock_browser_session,
            state_manager=state_manager,
        )
        
        result = await load_tool.execute(name="never_existed")
        
        assert not result.success
        assert "No saved state found" in result.error

    @pytest.mark.asyncio
    async def test_delete_then_load_fails(self, mock_browser_session, state_manager):
        """Test that deleting a state prevents it from being loaded."""
        save_tool = BrowserSaveStateTool(
            session=mock_browser_session,
            state_manager=state_manager,
        )
        delete_tool = BrowserDeleteStateTool(state_manager=state_manager)
        load_tool = BrowserLoadStateTool(
            session=mock_browser_session,
            state_manager=state_manager,
        )
        
        # Save a state
        mock_browser_session._current_state = {
            "cookies": [{"name": "temp", "value": "data", "domain": "example.com"}],
            "local_storage": {},
            "session_storage": {},
            "url": "https://example.com",
        }
        await save_tool.execute(name="temp_session")
        
        # Delete it
        delete_result = await delete_tool.execute(name="temp_session")
        assert delete_result.success
        
        # Try to load - should fail
        load_result = await load_tool.execute(name="temp_session")
        assert not load_result.success
        assert "No saved state found" in load_result.error

    @pytest.mark.asyncio
    async def test_list_empty_states(self, state_manager):
        """Test listing states when none exist."""
        list_tool = BrowserListStatesTool(state_manager=state_manager)
        
        result = await list_tool.execute()
        
        assert result.success
        assert "No saved browser states found" in result.output
        assert result.metadata["count"] == 0

