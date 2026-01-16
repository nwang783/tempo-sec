"""
Persistence utilities for context tree serialization.

Handles saving and loading context trees to/from JSON files.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tempo.context.frame import ContextFrame


@dataclass
class ContextTreeData:
    """Container for serialized context tree with metadata."""
    session_id: str
    created_at: datetime
    updated_at: datetime
    current_frame_id: str
    frames: dict[str, dict[str, Any]]  # frame_id -> frame data
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "current_frame_id": self.current_frame_id,
            "frames": self.frames,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ContextTreeData":
        """Deserialize from dictionary."""
        return cls(
            session_id=data["session_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            current_frame_id=data["current_frame_id"],
            frames=data["frames"],
            metadata=data.get("metadata", {}),
        )


def save_context_tree(
    session_id: str,
    frames: dict[str, ContextFrame],
    current_frame_id: str,
    persistence_dir: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    """
    Save the context tree to a JSON file.
    
    Args:
        session_id: Unique session identifier
        frames: Dictionary of frame_id -> ContextFrame
        current_frame_id: ID of the currently active frame
        persistence_dir: Directory to save context files
        metadata: Optional additional metadata
        
    Returns:
        Path to the saved file
    """
    # Ensure directory exists
    path = Path(persistence_dir)
    path.mkdir(parents=True, exist_ok=True)
    
    # Serialize frames
    serialized_frames = {
        frame_id: frame.to_dict()
        for frame_id, frame in frames.items()
    }
    
    # Check if file exists to get created_at
    file_path = path / f"{session_id}.json"
    now = datetime.now(timezone.utc)
    
    if file_path.exists():
        with open(file_path, "r") as f:
            existing = json.load(f)
            created_at = datetime.fromisoformat(existing["created_at"])
    else:
        created_at = now
    
    # Create tree data
    tree_data = ContextTreeData(
        session_id=session_id,
        created_at=created_at,
        updated_at=now,
        current_frame_id=current_frame_id,
        frames=serialized_frames,
        metadata=metadata or {},
    )
    
    # Write to file
    with open(file_path, "w") as f:
        json.dump(tree_data.to_dict(), f, indent=2)
    
    return str(file_path)


def load_context_tree(path: str) -> tuple[dict[str, ContextFrame], str, ContextTreeData]:
    """
    Load a context tree from a JSON file.
    
    Args:
        path: Path to the JSON file
        
    Returns:
        Tuple of (frames dict, current_frame_id, tree_data)
        
    Raises:
        FileNotFoundError: If the file doesn't exist
        json.JSONDecodeError: If the file is invalid JSON
    """
    with open(path, "r") as f:
        data = json.load(f)
    
    tree_data = ContextTreeData.from_dict(data)
    
    # Deserialize frames
    frames = {
        frame_id: ContextFrame.from_dict(frame_data)
        for frame_id, frame_data in tree_data.frames.items()
    }
    
    return frames, tree_data.current_frame_id, tree_data


def list_sessions(persistence_dir: str) -> list[tuple[str, datetime, datetime]]:
    """
    List all saved sessions in the persistence directory.
    
    Args:
        persistence_dir: Directory containing context files
        
    Returns:
        List of (session_id, created_at, updated_at) tuples
    """
    path = Path(persistence_dir)
    if not path.exists():
        return []
    
    sessions = []
    for file_path in path.glob("*.json"):
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
            sessions.append((
                data["session_id"],
                datetime.fromisoformat(data["created_at"]),
                datetime.fromisoformat(data["updated_at"]),
            ))
        except (json.JSONDecodeError, KeyError):
            continue  # Skip invalid files
    
    return sorted(sessions, key=lambda x: x[2], reverse=True)  # Most recent first


def delete_session(session_id: str, persistence_dir: str) -> bool:
    """
    Delete a saved session.
    
    Args:
        session_id: Session ID to delete
        persistence_dir: Directory containing context files
        
    Returns:
        True if deleted, False if not found
    """
    file_path = Path(persistence_dir) / f"{session_id}.json"
    if file_path.exists():
        file_path.unlink()
        return True
    return False
