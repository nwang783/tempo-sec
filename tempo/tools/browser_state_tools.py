"""
Browser state management tools.

Tools for listing, saving, loading, and deleting browser state
to enable persistent sessions across browser agent invocations.
"""

from typing import TYPE_CHECKING

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema

if TYPE_CHECKING:
    from tempo.infra.browser_state import BrowserStateManager
    from tempo.tools.browser_tools import BrowserSession


class BrowserListStatesTool(Tool):
    """List all available saved browser states."""

    name = "browser_list_states"
    description = (
        "List all saved browser states with their metadata "
        "(domain, creation time, expiration, etc.)"
    )
    category = ToolCategory.BROWSING

    def __init__(self, state_manager: "BrowserStateManager"):
        self._state_manager = state_manager

    async def execute(self, purpose: str = "", **kwargs) -> ToolResult:
        """List available browser states."""
        try:
            states = await self._state_manager.list_states()

            if not states:
                return ToolResult(
                    success=True,
                    output="No saved browser states found.",
                    metadata={"count": 0},
                )

            lines = [f"Found {len(states)} saved browser state(s):", ""]
            for state in states:
                lines.append(f"- **{state['name']}**")
                lines.append(f"  Domain: {state.get('target_domain', 'N/A')}")
                lines.append(f"  Created: {state.get('created_at', 'N/A')}")
                lines.append(f"  Updated: {state.get('updated_at', 'N/A')}")
                lines.append(f"  Expires: {state.get('expires_at', 'N/A')}")
                if state.get("metadata", {}).get("description"):
                    lines.append(f"  Description: {state['metadata']['description']}")
                lines.append("")

            return ToolResult(
                success=True,
                output="\n".join(lines),
                metadata={"count": len(states), "states": states},
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={"type": "object", "properties": {}, "required": []},
        )


class BrowserSaveStateTool(Tool):
    """Save current browser state with a name."""

    name = "browser_save_state"
    description = (
        "Save the current browser state (cookies, localStorage, sessionStorage) "
        "with a name for later use"
    )
    category = ToolCategory.BROWSING

    def __init__(self, session: "BrowserSession", state_manager: "BrowserStateManager"):
        self._session = session
        self._state_manager = state_manager

    async def execute(
        self,
        name: str,
        description: str = "",
        ttl_days: int | None = None,
        purpose: str = "",
        **kwargs,
    ) -> ToolResult:
        """Save browser state."""
        try:
            state = await self._session.capture_state()
            state.name = name
            state.metadata["description"] = description
            state.metadata["created_by"] = "browser_agent"

            await self._state_manager.save(state, ttl_days=ttl_days)

            return ToolResult(
                success=True,
                output=(
                    f"Browser state saved as '{name}' for domain {state.target_domain}. "
                    f"Expires: {state.expires_at}"
                ),
                metadata={
                    "state_name": name,
                    "domain": state.target_domain,
                    "expires_at": state.expires_at,
                },
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": (
                            "Name for the saved state "
                            "(e.g., 'admin_session', 'user_session')"
                        ),
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional description of what this state represents",
                        "default": "",
                    },
                    "ttl_days": {
                        "type": "integer",
                        "description": "Optional custom TTL in days (overrides default)",
                    },
                },
                "required": ["name"],
            },
        )


class BrowserLoadStateTool(Tool):
    """Load a saved browser state."""

    name = "browser_load_state"
    description = "Load a previously saved browser state to restore cookies and storage"
    category = ToolCategory.BROWSING

    def __init__(self, session: "BrowserSession", state_manager: "BrowserStateManager"):
        self._session = session
        self._state_manager = state_manager

    async def execute(self, name: str, purpose: str = "", **kwargs) -> ToolResult:
        """Load browser state."""
        try:
            state = await self._state_manager.load(name)
            if not state:
                return ToolResult(
                    success=False,
                    output="",
                    error=(
                        f"No saved state found with name '{name}' "
                        "(may be expired or deleted)"
                    ),
                )

            await self._session.restore_state(state)

            return ToolResult(
                success=True,
                output=(
                    f"Loaded browser state '{name}' (domain: {state.target_domain}). "
                    "Cookies and storage restored. Navigate to the target to use the session."
                ),
                metadata={"state_name": name, "domain": state.target_domain},
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the saved state to load",
                    },
                },
                "required": ["name"],
            },
        )


class BrowserDeleteStateTool(Tool):
    """Delete a saved browser state."""

    name = "browser_delete_state"
    description = "Delete a saved browser state"
    category = ToolCategory.BROWSING

    def __init__(self, state_manager: "BrowserStateManager"):
        self._state_manager = state_manager

    async def execute(self, name: str, purpose: str = "", **kwargs) -> ToolResult:
        """Delete browser state."""
        try:
            deleted = await self._state_manager.delete(name)

            if deleted:
                return ToolResult(
                    success=True,
                    output=f"Deleted browser state '{name}'",
                    metadata={"state_name": name},
                )
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"No saved state found with name '{name}'",
                )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the state to delete",
                    },
                },
                "required": ["name"],
            },
        )


class BrowserCleanupStatesTool(Tool):
    """Clean up expired browser states."""

    name = "browser_cleanup_states"
    description = "Remove all expired browser states to free up storage"
    category = ToolCategory.BROWSING

    def __init__(self, state_manager: "BrowserStateManager"):
        self._state_manager = state_manager

    async def execute(self, purpose: str = "", **kwargs) -> ToolResult:
        """Clean up expired states."""
        try:
            deleted_count = await self._state_manager.cleanup_expired()

            return ToolResult(
                success=True,
                output=f"Cleaned up {deleted_count} expired browser state(s)",
                metadata={"deleted_count": deleted_count},
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={"type": "object", "properties": {}, "required": []},
        )

