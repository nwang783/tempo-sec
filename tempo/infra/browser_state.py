"""
Browser state persistence manager.

Handles saving and loading browser state (cookies, localStorage, sessionStorage)
for persistent authenticated sessions across browser agent invocations.
"""

import asyncio
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Default state storage directory
DEFAULT_STATE_DIR = Path.home() / ".tempo-sec" / "browser_states"
DEFAULT_TTL_DAYS = 7


@dataclass
class BrowserState:
    """Serializable browser state."""
    name: str
    target_domain: str
    cookies: list[dict[str, Any]] = field(default_factory=list)
    local_storage: dict[str, str] = field(default_factory=dict)
    session_storage: dict[str, str] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    expires_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        now = datetime.utcnow()
        if not self.created_at:
            self.created_at = now.isoformat()
        if not self.updated_at:
            self.updated_at = now.isoformat()
        if not self.expires_at:
            # Default 7 day expiration
            self.expires_at = (now + timedelta(days=DEFAULT_TTL_DAYS)).isoformat()

    def is_expired(self) -> bool:
        """Check if this state has expired."""
        if not self.expires_at:
            return False
        try:
            expires = datetime.fromisoformat(self.expires_at)
            return datetime.utcnow() > expires
        except (ValueError, TypeError):
            return False


class BrowserStateManager:
    """
    Manages persistent browser state storage.

    Provides async-safe operations for saving and loading browser state,
    supporting multiple named states (e.g., "admin_session", "user_session").
    Automatically cleans up expired states.
    """

    def __init__(
        self,
        state_dir: Path | str | None = None,
        ttl_days: int = DEFAULT_TTL_DAYS,
    ):
        self.state_dir = Path(state_dir) if state_dir else DEFAULT_STATE_DIR
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_days = ttl_days
        self._lock = asyncio.Lock()

    def _state_path(self, name: str) -> Path:
        """Get the file path for a named state."""
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        return self.state_dir / f"{safe_name}.json"

    async def cleanup_expired(self) -> int:
        """Remove expired states. Returns count of deleted states."""
        async with self._lock:
            deleted_count = 0
            for path in self.state_dir.glob("*.json"):
                try:
                    data = json.loads(path.read_text())
                    state = BrowserState(**data)
                    if state.is_expired():
                        path.unlink()
                        deleted_count += 1
                except Exception:
                    continue
            return deleted_count

    async def save(
        self,
        state: BrowserState,
        ttl_days: int | None = None,
    ) -> None:
        """Save browser state to disk with optional custom TTL."""
        async with self._lock:
            state.updated_at = datetime.utcnow().isoformat()

            # Update expiration if TTL provided
            if ttl_days is not None:
                expires = datetime.utcnow() + timedelta(days=ttl_days)
                state.expires_at = expires.isoformat()
            elif not state.expires_at:
                # Use default TTL
                expires = datetime.utcnow() + timedelta(days=self.ttl_days)
                state.expires_at = expires.isoformat()

            path = self._state_path(state.name)
            path.write_text(json.dumps(asdict(state), indent=2))

    async def load(self, name: str) -> BrowserState | None:
        """Load browser state from disk. Returns None if not found or expired."""
        async with self._lock:
            path = self._state_path(name)
            if not path.exists():
                return None

            try:
                data = json.loads(path.read_text())
                state = BrowserState(**data)

                # Check expiration
                if state.is_expired():
                    path.unlink()  # Clean up expired state
                    return None

                return state
            except Exception:
                return None

    async def list_states(self, include_expired: bool = False) -> list[dict[str, Any]]:
        """List all available states with metadata."""
        async with self._lock:
            states = []
            for path in self.state_dir.glob("*.json"):
                try:
                    data = json.loads(path.read_text())
                    state = BrowserState(**data)

                    # Skip expired unless requested
                    if not include_expired and state.is_expired():
                        continue

                    states.append({
                        "name": data.get("name", path.stem),
                        "target_domain": data.get("target_domain", ""),
                        "created_at": data.get("created_at", ""),
                        "updated_at": data.get("updated_at", ""),
                        "expires_at": data.get("expires_at", ""),
                        "expired": state.is_expired(),
                        "metadata": data.get("metadata", {}),
                    })
                except Exception:
                    continue
            return states

    async def delete(self, name: str) -> bool:
        """Delete a saved state."""
        async with self._lock:
            path = self._state_path(name)
            if path.exists():
                path.unlink()
                return True
            return False

    async def exists(self, name: str) -> bool:
        """Check if a non-expired state exists."""
        state = await self.load(name)
        return state is not None
