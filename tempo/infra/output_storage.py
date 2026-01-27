"""
Truncated output storage manager.

Handles saving tool outputs that exceed the display limit to files,
allowing the AI to access full content via file_read tool.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_DIR = Path.home() / ".tempo-sec" / "truncated_outputs"
FALLBACK_OUTPUT_DIR = Path("/tmp/tempo-sec/truncated_outputs")
DEFAULT_TTL_HOURS = 24


@dataclass
class OutputMetadata:
    """Metadata for a saved output file."""
    tool_call_id: str
    tool_name: str
    session_id: str
    saved_at: str
    expires_at: str
    char_count: int
    file_path: str


class TruncatedOutputStorage:
    """
    Manages storage of truncated tool outputs.

    When tool outputs exceed the display limit, this saves the full
    content to a file so the AI can access it via file_read.
    """

    def __init__(
        self,
        output_dir: Path | str | None = None,
        session_id: str = "",
        ttl_hours: int = DEFAULT_TTL_HOURS,
        enabled: bool = True,
    ):
        self.output_dir = Path(output_dir).expanduser() if output_dir else DEFAULT_OUTPUT_DIR
        self.session_id = session_id
        self.ttl_hours = ttl_hours
        self.enabled = enabled

        # Create session-specific directory
        if self.enabled:
            self.session_dir = self.output_dir / self.session_id if session_id else self.output_dir
            try:
                self.session_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                self.output_dir = FALLBACK_OUTPUT_DIR
                self.session_dir = self.output_dir / self.session_id if session_id else self.output_dir
                self.session_dir.mkdir(parents=True, exist_ok=True)

    def _output_path(self, tool_call_id: str) -> Path:
        """Get the file path for a tool call's output."""
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in tool_call_id)
        return self.session_dir / f"{safe_id}.txt"

    def _metadata_path(self, tool_call_id: str) -> Path:
        """Get the metadata file path."""
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in tool_call_id)
        return self.session_dir / f"{safe_id}.meta.json"

    def save_output(
        self,
        tool_call_id: str,
        content: str,
        tool_name: str = "",
    ) -> str | None:
        """
        Save tool output to a file.

        Args:
            tool_call_id: Unique ID of the tool call
            content: Full output content to save
            tool_name: Name of the tool (for metadata)

        Returns:
            File path where content was saved, or None if disabled/failed
        """
        if not self.enabled:
            return None

        try:
            output_path = self._output_path(tool_call_id)
            metadata_path = self._metadata_path(tool_call_id)

            # Save content
            output_path.write_text(content, encoding="utf-8")

            # Save metadata
            now = datetime.now(timezone.utc)
            metadata = OutputMetadata(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                session_id=self.session_id,
                saved_at=now.isoformat(),
                expires_at=(now + timedelta(hours=self.ttl_hours)).isoformat(),
                char_count=len(content),
                file_path=str(output_path),
            )
            metadata_path.write_text(
                json.dumps(metadata.__dict__, indent=2),
                encoding="utf-8"
            )

            return str(output_path)
        except Exception:
            return None

    def cleanup_expired(self) -> int:
        """Remove expired output files. Returns count of deleted files."""
        if not self.output_dir.exists():
            return 0

        deleted_count = 0
        now = datetime.now(timezone.utc)

        # Walk all session directories
        for session_dir in self.output_dir.iterdir():
            if not session_dir.is_dir():
                continue

            for meta_path in session_dir.glob("*.meta.json"):
                try:
                    data = json.loads(meta_path.read_text())
                    expires_at = datetime.fromisoformat(data["expires_at"])

                    if now > expires_at:
                        # Delete both content and metadata files
                        output_path = Path(data["file_path"])
                        if output_path.exists():
                            output_path.unlink()
                        meta_path.unlink()
                        deleted_count += 1
                except Exception:
                    continue

            # Remove empty session directories
            try:
                if session_dir.exists() and not any(session_dir.iterdir()):
                    session_dir.rmdir()
            except Exception:
                pass

        return deleted_count
