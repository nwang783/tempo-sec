"""
Browser Session Manager.

Singleton that manages a shared browser session across multiple dispatch_browser calls.
Enables session persistence (auth state, cookies) and provides context from previous agents.
"""

import asyncio
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tempo.infra.playwright_mcp import PlaywrightMCPClient

logger = logging.getLogger(__name__)


class BrowserSessionManager:
    """
    Singleton manager for shared browser sessions.
    
    Maintains a single PlaywrightMCPClient instance across multiple dispatch_browser
    calls, enabling session persistence (cookies, storage) and tracking session history.
    """
    
    _instance: "BrowserSessionManager | None" = None
    _lock = asyncio.Lock()
    
    def __init__(self):
        """Initialize session manager (use get_instance() instead)."""
        self._client: "PlaywrightMCPClient | None" = None
        self._session_history: list[dict[str, Any]] = []
        self._run_id = str(uuid.uuid4())[:8]
        self._user_data_dir = os.path.join(
            tempfile.gettempdir(),
            f"tempo-browser-{self._run_id}"
        )
        self._headless = False
        self._started_at: datetime | None = None
        
    @classmethod
    def get_instance(cls) -> "BrowserSessionManager":
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (for testing)."""
        cls._instance = None
        
    def configure(self, headless: bool = False) -> None:
        """Configure session settings before first use."""
        self._headless = headless
        
    async def get_or_create_client(self) -> "PlaywrightMCPClient":
        """
        Get existing client or create a new one.
        
        Returns:
            PlaywrightMCPClient instance (shared across calls)
        """
        async with self._lock:
            if self._client is not None:
                # Check if client is still healthy
                if await self._is_client_healthy():
                    return self._client
                else:
                    # Client crashed - auto-recover
                    logger.warning("Browser session crashed, recovering...")
                    await self._cleanup_client()
            
            # Create new client
            from tempo.infra.playwright_mcp import PlaywrightMCPClient
            
            self._client = PlaywrightMCPClient(
                headless=self._headless,
                user_data_dir=self._user_data_dir,
            )
            await self._client.start_server()
            self._started_at = datetime.now(timezone.utc)
            
            logger.info(f"Browser session started (run_id={self._run_id})")
            return self._client
    
    async def _is_client_healthy(self) -> bool:
        """Check if the browser client is still responsive."""
        if self._client is None:
            return False
        
        try:
            # Try a simple operation
            result = await asyncio.wait_for(
                self._client.call_tool("browser_snapshot", {}),
                timeout=5.0
            )
            return result.get("success", False)
        except Exception as e:
            logger.debug(f"Client health check failed: {e}")
            return False
    
    async def _cleanup_client(self) -> None:
        """Clean up the current client."""
        if self._client:
            try:
                await self._client.stop_server()
            except Exception as e:
                logger.debug(f"Error stopping client: {e}")
            self._client = None
    
    def add_session_summary(
        self, 
        objective: str, 
        summary: str,
        browser_state: dict | None = None,
    ) -> None:
        """
        Record a completed browser session.
        
        Args:
            objective: What the agent was trying to accomplish
            summary: Agent's completion summary
            browser_state: Optional captured browser state
        """
        self._session_history.append({
            "objective": objective,
            "summary": summary,
            "timestamp": datetime.now(timezone.utc),
            "browser_state": browser_state,
        })
        logger.debug(f"Added session to history (total: {len(self._session_history)})")
    
    def get_session_context(self) -> str:
        """
        Get formatted context from previous sessions for the next agent.
        
        Returns:
            Markdown-formatted session history
        """
        if not self._session_history:
            return ""
        
        lines = ["## Previous Browser Sessions\n"]
        lines.append("The browser session is shared. Previous agents have performed:\n")
        
        now = datetime.now(timezone.utc)
        for i, session in enumerate(self._session_history, 1):
            # Calculate time ago
            delta = now - session["timestamp"]
            if delta.total_seconds() < 60:
                time_ago = "just now"
            elif delta.total_seconds() < 3600:
                mins = int(delta.total_seconds() / 60)
                time_ago = f"{mins} minute{'s' if mins != 1 else ''} ago"
            else:
                hours = int(delta.total_seconds() / 3600)
                time_ago = f"{hours} hour{'s' if hours != 1 else ''} ago"
            
            lines.append(f"### Session {i} ({time_ago})")
            lines.append(f"**Objective**: {session['objective']}")
            lines.append(f"**Summary**: {session['summary']}")
            lines.append("")
        
        lines.append("You are continuing in the same browser. Auth state, cookies, and page context may be preserved.\n")
        
        return "\n".join(lines)
    
    @property
    def session_count(self) -> int:
        """Number of completed sessions."""
        return len(self._session_history)
    
    @property
    def has_active_client(self) -> bool:
        """Whether there's an active browser client."""
        return self._client is not None
    
    async def close(self) -> None:
        """
        Close the browser session and clean up.
        
        Should be called when orchestrator exits.
        """
        async with self._lock:
            await self._cleanup_client()
            
            # Clean up user data dir
            import shutil
            if os.path.exists(self._user_data_dir):
                try:
                    shutil.rmtree(self._user_data_dir)
                    logger.debug(f"Cleaned up browser data: {self._user_data_dir}")
                except Exception as e:
                    logger.debug(f"Failed to clean up browser data: {e}")
            
            self._session_history.clear()
            logger.info("Browser session manager closed")
