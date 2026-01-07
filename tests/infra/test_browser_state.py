"""
Unit tests for BrowserStateManager.

Tests cover state persistence, expiration, TTL handling, and async operations.
"""

import asyncio
import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from tempo.infra.browser_state import (
    BrowserState,
    BrowserStateManager,
    DEFAULT_STATE_DIR,
    DEFAULT_TTL_DAYS,
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


class TestBrowserState:
    """Test BrowserState dataclass."""

    def test_browser_state_creation(self):
        """Test creating a BrowserState with default values."""
        state = BrowserState(
            name="test_session",
            target_domain="example.com",
        )

        assert state.name == "test_session"
        assert state.target_domain == "example.com"
        assert state.cookies == []
        assert state.local_storage == {}
        assert state.session_storage == {}
        assert state.created_at
        assert state.updated_at
        assert state.expires_at
        assert state.metadata == {}

    def test_browser_state_with_data(self):
        """Test creating a BrowserState with full data."""
        cookies = [{"name": "session_id", "value": "abc123", "domain": "example.com"}]
        local_storage = {"token": "xyz789"}
        session_storage = {"cart": "[]"}
        metadata = {"user": "admin"}

        state = BrowserState(
            name="admin_session",
            target_domain="example.com",
            cookies=cookies,
            local_storage=local_storage,
            session_storage=session_storage,
            metadata=metadata,
        )

        assert state.name == "admin_session"
        assert state.cookies == cookies
        assert state.local_storage == local_storage
        assert state.session_storage == session_storage
        assert state.metadata == metadata

    def test_browser_state_timestamps(self):
        """Test that timestamps are automatically set."""
        state = BrowserState(name="test", target_domain="example.com")

        # Parse timestamps
        created = datetime.fromisoformat(state.created_at)
        updated = datetime.fromisoformat(state.updated_at)
        expires = datetime.fromisoformat(state.expires_at)

        # Check they're recent
        now = datetime.utcnow()
        assert (now - created).total_seconds() < 1
        assert (now - updated).total_seconds() < 1

        # Check expiration is in the future (default 7 days)
        expected_expires = now + timedelta(days=DEFAULT_TTL_DAYS)
        assert abs((expires - expected_expires).total_seconds()) < 1

    def test_browser_state_is_expired_false(self):
        """Test is_expired returns False for non-expired states."""
        state = BrowserState(name="test", target_domain="example.com")
        assert not state.is_expired()

    def test_browser_state_is_expired_true(self):
        """Test is_expired returns True for expired states."""
        # Create a state that expired 1 day ago
        past = datetime.utcnow() - timedelta(days=1)
        state = BrowserState(
            name="test",
            target_domain="example.com",
            expires_at=past.isoformat(),
        )
        assert state.is_expired()

    def test_browser_state_is_expired_no_expiration(self):
        """Test is_expired returns False when no expiration is set."""
        state = BrowserState(
            name="test",
            target_domain="example.com",
            expires_at="",
        )
        assert not state.is_expired()


class TestBrowserStateManager:
    """Test BrowserStateManager class."""

    def test_manager_initialization_default(self):
        """Test manager initializes with default directory."""
        manager = BrowserStateManager()
        assert manager.state_dir == DEFAULT_STATE_DIR
        assert manager.ttl_days == DEFAULT_TTL_DAYS
        assert manager.state_dir.exists()

    def test_manager_initialization_custom(self, temp_state_dir):
        """Test manager initializes with custom directory."""
        manager = BrowserStateManager(state_dir=temp_state_dir, ttl_days=14)
        assert manager.state_dir == temp_state_dir
        assert manager.ttl_days == 14

    def test_state_path_sanitization(self, state_manager):
        """Test that state names are sanitized for file paths."""
        path = state_manager._state_path("test@session#123")
        assert path.name == "test_session_123.json"

        path = state_manager._state_path("admin/session")
        assert path.name == "admin_session.json"

    @pytest.mark.asyncio
    async def test_save_and_load_state(self, state_manager):
        """Test saving and loading a state."""
        state = BrowserState(
            name="test_session",
            target_domain="example.com",
            cookies=[{"name": "token", "value": "abc123"}],
            local_storage={"key": "value"},
        )

        # Save state
        await state_manager.save(state)

        # Load state
        loaded = await state_manager.load("test_session")

        assert loaded is not None
        assert loaded.name == state.name
        assert loaded.target_domain == state.target_domain
        assert loaded.cookies == state.cookies
        assert loaded.local_storage == state.local_storage

    @pytest.mark.asyncio
    async def test_load_nonexistent_state(self, state_manager):
        """Test loading a state that doesn't exist."""
        loaded = await state_manager.load("nonexistent")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_save_updates_timestamp(self, state_manager):
        """Test that saving updates the updated_at timestamp."""
        state = BrowserState(name="test", target_domain="example.com")
        original_updated = state.updated_at

        # Wait a bit to ensure timestamp differs
        await asyncio.sleep(0.01)

        # Save state
        await state_manager.save(state)

        # Load and check updated_at changed
        loaded = await state_manager.load("test")
        assert loaded.updated_at != original_updated

    @pytest.mark.asyncio
    async def test_save_with_custom_ttl(self, state_manager):
        """Test saving a state with custom TTL."""
        state = BrowserState(name="test", target_domain="example.com")

        # Save with 30 day TTL
        await state_manager.save(state, ttl_days=30)

        # Load and check expiration
        loaded = await state_manager.load("test")
        expires = datetime.fromisoformat(loaded.expires_at)
        expected = datetime.utcnow() + timedelta(days=30)

        # Should be close to 30 days from now
        assert abs((expires - expected).total_seconds()) < 1

    @pytest.mark.asyncio
    async def test_load_expired_state_returns_none(self, state_manager):
        """Test that loading an expired state returns None and deletes the file."""
        # Create an expired state
        past = datetime.utcnow() - timedelta(days=1)
        state = BrowserState(
            name="expired_session",
            target_domain="example.com",
            expires_at=past.isoformat(),
        )

        # Save it manually
        path = state_manager._state_path(state.name)
        path.write_text(json.dumps({
            "name": state.name,
            "target_domain": state.target_domain,
            "cookies": [],
            "local_storage": {},
            "session_storage": {},
            "created_at": state.created_at,
            "updated_at": state.updated_at,
            "expires_at": state.expires_at,
            "metadata": {},
        }))

        # Try to load
        loaded = await state_manager.load("expired_session")

        # Should be None and file should be deleted
        assert loaded is None
        assert not path.exists()

    @pytest.mark.asyncio
    async def test_delete_state(self, state_manager):
        """Test deleting a state."""
        state = BrowserState(name="test", target_domain="example.com")
        await state_manager.save(state)

        # Verify it exists
        assert await state_manager.exists("test")

        # Delete it
        result = await state_manager.delete("test")
        assert result is True

        # Verify it's gone
        assert not await state_manager.exists("test")

    @pytest.mark.asyncio
    async def test_delete_nonexistent_state(self, state_manager):
        """Test deleting a state that doesn't exist."""
        result = await state_manager.delete("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_exists_true(self, state_manager):
        """Test exists returns True for non-expired state."""
        state = BrowserState(name="test", target_domain="example.com")
        await state_manager.save(state)

        assert await state_manager.exists("test")

    @pytest.mark.asyncio
    async def test_exists_false_nonexistent(self, state_manager):
        """Test exists returns False for nonexistent state."""
        assert not await state_manager.exists("nonexistent")

    @pytest.mark.asyncio
    async def test_exists_false_expired(self, state_manager):
        """Test exists returns False for expired state."""
        # Create an expired state
        past = datetime.utcnow() - timedelta(days=1)
        state = BrowserState(
            name="expired",
            target_domain="example.com",
            expires_at=past.isoformat(),
        )

        # Save it manually
        path = state_manager._state_path(state.name)
        path.write_text(json.dumps({
            "name": state.name,
            "target_domain": state.target_domain,
            "cookies": [],
            "local_storage": {},
            "session_storage": {},
            "created_at": state.created_at,
            "updated_at": state.updated_at,
            "expires_at": state.expires_at,
            "metadata": {},
        }))

        assert not await state_manager.exists("expired")

    @pytest.mark.asyncio
    async def test_list_states(self, state_manager):
        """Test listing all states."""
        # Create multiple states
        states = [
            BrowserState(name="session1", target_domain="example.com"),
            BrowserState(name="session2", target_domain="test.com"),
            BrowserState(name="session3", target_domain="demo.com"),
        ]

        for state in states:
            await state_manager.save(state)

        # List states
        listed = await state_manager.list_states()

        assert len(listed) == 3
        names = {s["name"] for s in listed}
        assert names == {"session1", "session2", "session3"}

    @pytest.mark.asyncio
    async def test_list_states_excludes_expired(self, state_manager):
        """Test that list_states excludes expired states by default."""
        # Create a normal state
        normal = BrowserState(name="normal", target_domain="example.com")
        await state_manager.save(normal)

        # Create an expired state manually
        past = datetime.utcnow() - timedelta(days=1)
        expired_path = state_manager._state_path("expired")
        expired_path.write_text(json.dumps({
            "name": "expired",
            "target_domain": "example.com",
            "cookies": [],
            "local_storage": {},
            "session_storage": {},
            "created_at": past.isoformat(),
            "updated_at": past.isoformat(),
            "expires_at": past.isoformat(),
            "metadata": {},
        }))

        # List without expired
        listed = await state_manager.list_states(include_expired=False)
        assert len(listed) == 1
        assert listed[0]["name"] == "normal"

        # List with expired
        listed_all = await state_manager.list_states(include_expired=True)
        assert len(listed_all) == 2

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, state_manager):
        """Test cleaning up expired states."""
        # Create normal states
        normal1 = BrowserState(name="normal1", target_domain="example.com")
        normal2 = BrowserState(name="normal2", target_domain="example.com")
        await state_manager.save(normal1)
        await state_manager.save(normal2)

        # Create expired states manually
        past = datetime.utcnow() - timedelta(days=1)
        for i in range(3):
            expired_path = state_manager._state_path(f"expired{i}")
            expired_path.write_text(json.dumps({
                "name": f"expired{i}",
                "target_domain": "example.com",
                "cookies": [],
                "local_storage": {},
                "session_storage": {},
                "created_at": past.isoformat(),
                "updated_at": past.isoformat(),
                "expires_at": past.isoformat(),
                "metadata": {},
            }))

        # Cleanup
        deleted_count = await state_manager.cleanup_expired()

        assert deleted_count == 3

        # Verify only normal states remain
        listed = await state_manager.list_states()
        assert len(listed) == 2
        names = {s["name"] for s in listed}
        assert names == {"normal1", "normal2"}

    @pytest.mark.asyncio
    async def test_concurrent_save_operations(self, state_manager):
        """Test that concurrent save operations are thread-safe."""
        async def save_state(name: str):
            state = BrowserState(name=name, target_domain="example.com")
            await state_manager.save(state)

        # Save 10 states concurrently
        await asyncio.gather(*[save_state(f"concurrent{i}") for i in range(10)])

        # All should be saved
        listed = await state_manager.list_states()
        assert len(listed) == 10

    @pytest.mark.asyncio
    async def test_state_metadata_preserved(self, state_manager):
        """Test that state metadata is preserved."""
        metadata = {
            "user": "admin",
            "login_time": "2024-01-01T10:00:00",
            "custom_field": "value",
        }

        state = BrowserState(
            name="test",
            target_domain="example.com",
            metadata=metadata,
        )

        await state_manager.save(state)
        loaded = await state_manager.load("test")

        assert loaded.metadata == metadata

    @pytest.mark.asyncio
    async def test_invalid_state_file_ignored(self, state_manager, temp_state_dir):
        """Test that invalid state files are ignored during operations."""
        # Create an invalid JSON file
        invalid_path = temp_state_dir / "invalid.json"
        invalid_path.write_text("not valid json{{{")

        # Create a valid state
        state = BrowserState(name="valid", target_domain="example.com")
        await state_manager.save(state)

        # List should only return valid state
        listed = await state_manager.list_states()
        assert len(listed) == 1
        assert listed[0]["name"] == "valid"

        # Cleanup should not fail
        deleted = await state_manager.cleanup_expired()
        assert deleted >= 0
