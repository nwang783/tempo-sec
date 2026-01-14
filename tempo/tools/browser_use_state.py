"""
State persistence integration for browser-use.

Provides tools to save/load browser state using browser-use's Browser
instance while storing state via tempo-sec's BrowserStateManager.
"""

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from browser_use.tools.service import Tools

if TYPE_CHECKING:
    from browser_use import Browser

    from tempo.infra.browser_state import BrowserState, BrowserStateManager


class BrowserUseStateTools:
    """Wrapper to integrate browser-use with tempo-sec state management."""

    def __init__(
        self,
        browser: "Browser",
        state_manager: "BrowserStateManager",
        tools_instance: Tools | None = None,
    ):
        """
        Initialize state tools.

        Args:
            browser: browser-use Browser instance
            state_manager: tempo-sec BrowserStateManager
            tools_instance: Optional shared Tools instance (if None, creates new)
        """
        self.browser = browser
        self.state_manager = state_manager
        self.tools = tools_instance if tools_instance is not None else Tools()

        self._register_state_tools()

    def _register_state_tools(self):
        """Register state management tools for browser-use."""

        @self.tools.action("Save current browser state with a name for later use")
        def browser_save_state(
            name: str,
            description: str = "",
        ) -> str:
            """
            Save browser state (cookies, localStorage, sessionStorage).

            Args:
                name: Name for this state (e.g., 'admin_session', 'logged_in_user')
                description: Optional description of what this state contains

            Returns:
                Success confirmation with state name
            """
            result = asyncio.run(self._save_state_async(name, description))
            return result

        @self.tools.action("Load a previously saved browser state to restore a session")
        def browser_load_state(name: str) -> str:
            """
            Load browser state to restore session.

            Args:
                name: Name of the state to load

            Returns:
                Success confirmation or error message
            """
            result = asyncio.run(self._load_state_async(name))
            return result

        @self.tools.action("List all saved browser states")
        def browser_list_states() -> str:
            """
            List available saved states.

            Returns:
                List of saved states with metadata
            """
            result = asyncio.run(self._list_states_async())
            return result

        @self.tools.action("Delete a saved browser state")
        def browser_delete_state(name: str) -> str:
            """
            Delete a saved state.

            Args:
                name: Name of the state to delete

            Returns:
                Success confirmation or error message
            """
            result = asyncio.run(self._delete_state_async(name))
            return result

    async def _save_state_async(self, name: str, description: str = "") -> str:
        """Internal async method to save state."""
        try:
            state = await self.capture_state(name, description)
            await self.state_manager.save(state)
            return f"Saved browser state '{name}' successfully. Use browser_load_state('{name}') to restore this session later."
        except Exception as e:
            return f"Error saving state: {str(e)}"

    async def _load_state_async(self, name: str) -> str:
        """Internal async method to load state."""
        try:
            state = await self.state_manager.load(name)
            if not state:
                return f"Error: State '{name}' not found or has expired."

            await self.restore_state(state)
            return f"Loaded browser state '{name}' successfully. Session restored."
        except Exception as e:
            return f"Error loading state: {str(e)}"

    async def _list_states_async(self) -> str:
        """Internal async method to list states."""
        try:
            states = await self.state_manager.list_states()
            if not states:
                return "No saved browser states found."

            lines = ["Saved browser states:"]
            for state in states:
                lines.append(
                    f"- {state['name']} (domain: {state['target_domain']}, "
                    f"updated: {state['updated_at'][:19]}, expires: {state['expires_at'][:19]})"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Error listing states: {str(e)}"

    async def _delete_state_async(self, name: str) -> str:
        """Internal async method to delete state."""
        try:
            deleted = await self.state_manager.delete(name)
            if deleted:
                return f"Deleted browser state '{name}' successfully."
            return f"Error: State '{name}' not found."
        except Exception as e:
            return f"Error deleting state: {str(e)}"

    async def capture_state(
        self, name: str, description: str = ""
    ) -> "BrowserState":
        """
        Capture current browser state from browser-use's browser.

        Args:
            name: Name for this state
            description: Optional description

        Returns:
            BrowserState object ready for saving
        """
        from tempo.infra.browser_state import BrowserState

        # Get the current page and context from browser-use
        # browser-use exposes the playwright browser through browser.browser
        # and the context through browser.context
        context = self.browser.context
        page = await self.browser.get_current_page()

        # Extract cookies
        cookies = await context.cookies()

        # Get current URL for domain extraction
        current_url = page.url
        parsed_url = urlparse(current_url)
        target_domain = parsed_url.netloc or "unknown"

        # Extract localStorage
        local_storage = {}
        try:
            local_storage_items = await page.evaluate("""() => {
                const items = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    items[key] = localStorage.getItem(key);
                }
                return items;
            }""")
            local_storage = local_storage_items or {}
        except Exception:
            # May fail if page doesn't support localStorage
            pass

        # Extract sessionStorage
        session_storage = {}
        try:
            session_storage_items = await page.evaluate("""() => {
                const items = {};
                for (let i = 0; i < sessionStorage.length; i++) {
                    const key = sessionStorage.key(i);
                    items[key] = sessionStorage.getItem(key);
                }
                return items;
            }""")
            session_storage = session_storage_items or {}
        except Exception:
            # May fail if page doesn't support sessionStorage
            pass

        # Create BrowserState
        state = BrowserState(
            name=name,
            target_domain=target_domain,
            cookies=cookies,
            local_storage=local_storage,
            session_storage=session_storage,
            metadata={"description": description} if description else {},
        )

        return state

    async def restore_state(self, state: "BrowserState"):
        """
        Restore state to browser-use's browser.

        Args:
            state: BrowserState to restore
        """
        context = self.browser.context
        page = await self.browser.get_current_page()

        # Restore cookies
        if state.cookies:
            await context.add_cookies(state.cookies)

        # Navigate to the target domain to set storage
        # (localStorage/sessionStorage can only be set on a page with that origin)
        if state.target_domain and state.target_domain != "unknown":
            # Check if we're already on the right domain
            current_url = page.url
            parsed_url = urlparse(current_url)
            if parsed_url.netloc != state.target_domain:
                # Navigate to the domain
                protocol = "https" if any(c.get("secure", False) for c in state.cookies) else "http"
                await page.goto(f"{protocol}://{state.target_domain}")

        # Restore localStorage
        if state.local_storage:
            for key, value in state.local_storage.items():
                try:
                    await page.evaluate(
                        f"""() => {{ localStorage.setItem({repr(key)}, {repr(value)}); }}"""
                    )
                except Exception:
                    # May fail if page doesn't support localStorage
                    pass

        # Restore sessionStorage
        if state.session_storage:
            for key, value in state.session_storage.items():
                try:
                    await page.evaluate(
                        f"""() => {{ sessionStorage.setItem({repr(key)}, {repr(value)}); }}"""
                    )
                except Exception:
                    # May fail if page doesn't support sessionStorage
                    pass

    def get_tools(self) -> Tools:
        """Return the Tools instance."""
        return self.tools
