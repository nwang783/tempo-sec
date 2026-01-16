"""Tests for truncated output storage."""

import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest

from tempo.infra.output_storage import TruncatedOutputStorage, OutputMetadata


class TestTruncatedOutputStorage:
    """Tests for TruncatedOutputStorage class."""

    def test_save_output_creates_file(self, tmp_path):
        """Test that save_output creates the expected files."""
        storage = TruncatedOutputStorage(
            output_dir=tmp_path,
            session_id="test-session",
            enabled=True,
        )

        path = storage.save_output(
            tool_call_id="test-123",
            content="Hello, world!",
            tool_name="shell",
        )

        assert path is not None
        assert Path(path).exists()
        assert Path(path).read_text() == "Hello, world!"

    def test_save_output_creates_metadata(self, tmp_path):
        """Test that save_output creates metadata file."""
        storage = TruncatedOutputStorage(
            output_dir=tmp_path,
            session_id="test-session",
            enabled=True,
        )

        path = storage.save_output(
            tool_call_id="test-123",
            content="Hello, world!",
            tool_name="shell",
        )

        # Check metadata file exists (hyphens are kept in filename)
        meta_path = Path(path).parent / "test-123.meta.json"
        assert meta_path.exists(), f"Expected {meta_path} to exist, but it doesn't"

        # Validate metadata content
        metadata = json.loads(meta_path.read_text())
        assert metadata["tool_call_id"] == "test-123"
        assert metadata["tool_name"] == "shell"
        assert metadata["session_id"] == "test-session"
        assert metadata["char_count"] == 13

    def test_save_output_disabled(self, tmp_path):
        """Test that save_output returns None when disabled."""
        storage = TruncatedOutputStorage(
            output_dir=tmp_path,
            enabled=False,
        )

        path = storage.save_output("test-123", "content")
        assert path is None

    def test_save_output_sanitizes_id(self, tmp_path):
        """Test that special characters in tool_call_id are sanitized."""
        storage = TruncatedOutputStorage(
            output_dir=tmp_path,
            session_id="test-session",
            enabled=True,
        )

        path = storage.save_output(
            tool_call_id="test/with:special*chars?",
            content="test content",
        )

        assert path is not None
        # Verify the path doesn't contain special characters
        assert "/" not in Path(path).name
        assert ":" not in Path(path).name
        assert "*" not in Path(path).name
        assert "?" not in Path(path).name

    def test_cleanup_expired(self, tmp_path):
        """Test cleanup removes expired files."""
        storage = TruncatedOutputStorage(
            output_dir=tmp_path,
            session_id="test-session",
            ttl_hours=24,
            enabled=True,
        )

        # Save an output
        path = storage.save_output("test-123", "content")
        assert path is not None

        # Manually update expiration to past (hyphens are kept in filename)
        meta_path = tmp_path / "test-session" / "test-123.meta.json"
        data = json.loads(meta_path.read_text())
        data["expires_at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        meta_path.write_text(json.dumps(data))

        # Cleanup should remove the file
        deleted = storage.cleanup_expired()
        assert deleted == 1
        assert not Path(path).exists()
        assert not meta_path.exists()

    def test_cleanup_preserves_non_expired(self, tmp_path):
        """Test cleanup preserves non-expired files."""
        storage = TruncatedOutputStorage(
            output_dir=tmp_path,
            session_id="test-session",
            ttl_hours=24,
            enabled=True,
        )

        # Save an output
        path = storage.save_output("test-123", "content")
        assert path is not None

        # Cleanup should not remove it (not expired)
        deleted = storage.cleanup_expired()
        assert deleted == 0
        assert Path(path).exists()

    def test_multiple_sessions(self, tmp_path):
        """Test that different sessions use separate directories."""
        storage1 = TruncatedOutputStorage(
            output_dir=tmp_path,
            session_id="session-1",
            enabled=True,
        )
        storage2 = TruncatedOutputStorage(
            output_dir=tmp_path,
            session_id="session-2",
            enabled=True,
        )

        path1 = storage1.save_output("test-123", "content1")
        path2 = storage2.save_output("test-123", "content2")

        assert path1 is not None
        assert path2 is not None
        assert path1 != path2
        assert "session-1" in path1
        assert "session-2" in path2

        # Verify content is separate
        assert Path(path1).read_text() == "content1"
        assert Path(path2).read_text() == "content2"

    def test_error_handling(self, tmp_path):
        """Test that errors during save are handled gracefully."""
        storage = TruncatedOutputStorage(
            output_dir=tmp_path / "nonexistent" / "deep" / "path",
            session_id="test-session",
            enabled=False,  # Disabled, so should return None
        )

        # Should not raise exception
        path = storage.save_output("test-123", "content")
        assert path is None

    def test_cleanup_handles_corrupted_metadata(self, tmp_path):
        """Test cleanup handles corrupted metadata files gracefully."""
        storage = TruncatedOutputStorage(
            output_dir=tmp_path,
            session_id="test-session",
            enabled=True,
        )

        # Create a corrupted metadata file
        session_dir = tmp_path / "test-session"
        session_dir.mkdir(parents=True, exist_ok=True)
        corrupted_meta = session_dir / "corrupted.meta.json"
        corrupted_meta.write_text("{invalid json")

        # Cleanup should handle it without crashing
        deleted = storage.cleanup_expired()
        assert deleted == 0  # Couldn't process corrupted file

    def test_large_output(self, tmp_path):
        """Test saving large outputs."""
        storage = TruncatedOutputStorage(
            output_dir=tmp_path,
            session_id="test-session",
            enabled=True,
        )

        # Create a large output (1MB)
        large_content = "A" * (1024 * 1024)
        path = storage.save_output("test-large", large_content, tool_name="test")

        assert path is not None
        saved_content = Path(path).read_text()
        assert len(saved_content) == len(large_content)
        assert saved_content == large_content
