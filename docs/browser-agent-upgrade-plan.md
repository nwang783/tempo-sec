# Comprehensive Implementation Plan: Browser Agent Reimplementation and Upgrade

## Executive Summary

This plan details the reimplementation of the browser agent for tempo-sec with enhanced capabilities including Chromium-based automation via Playwright, persistent browser state management, visual capabilities (screenshots), multiple interaction methods, scope parameter support, and configurable display modes. The design honors the codebase's MVC architecture pattern and dependency rules.

### Key Updates (2026-01-06)

Three additional requirements have been integrated into this plan:

1. **UI Event Propagation**: Browser agent activities will be visible in the UI through the visualization collector system. The `BrowserTaskTool` will create child collectors for browser agents, enabling users to see browser operations in real-time.

2. **Agent Prompt Updates**: Recon and test agent prompts will include comprehensive guidance on WHEN and HOW to use the `browser_task` tool, with examples of state management, headless mode configuration, and appropriate use cases.

3. **Headless Mode Configuration**: A single global setting in `config.toml` controls whether the browser window is visible. This simplifies configuration and ensures consistent browser behavior across all browser tasks. The default is headless (no visible window).

---

## 1. Context & Understanding

### 1.1 Current State Analysis

The codebase currently has a basic browser agent implementation at `tempo/agents/browser.py` with the following characteristics:

**Existing Components:**
- `BrowserAgent` class extending `BaseAgentDefinition`
- `BrowserSession` class in `tempo/tools/browser_tools.py` managing Playwright lifecycle
- Browser tools: `BrowserNavigateTool`, `BrowserSnapshotTool`, `BrowserClickTool`, `BrowserTypeTool`, `BrowserFillFormTool`
- `BrowserTaskTool` in `tempo/tools/browser_task_tool.py` for parent agents to dispatch browser tasks
- `CompleteBrowserTaskTool` for signaling browser task completion

**Current Limitations:**
1. No state persistence (cookies, localStorage, sessions)
2. No named state management (e.g., "admin_session", "user_session")
3. No screenshot/visual capture capability
4. No coordinate-based clicking
5. No scope parameter support (unlike other subagents)
6. Always headless, no configurable display mode
7. No integration with findings document for browser-discovered authentication flows

### 1.2 Why This Approach Aligns with Codebase Principles

From `MISSION.md` and `AGENTS.md`:
- **"Context is Sacred"**: Browser state persistence reduces redundant authentication flows, saving context tokens
- **"Tools Should Expand, not Constrict"**: Browser tools remain simple but gain powerful state management
- **"Using Subagents for Tangential Tasks"**: Browser agent as subagent keeps orchestrator context lean
- **Dependency Rules**: Tools in `tools/` must not import from `agents/` or `context/` directly - will use protocols

### 1.3 Key Existing Patterns to Leverage

| Pattern | Location | How We'll Use It |
|---------|----------|------------------|
| Agent registration | `tempo/agents/__init__.py` | `@register_agent` decorator |
| Scope propagation | `tempo/agents/test_subagent.py`, `tempo/agents/recon_subagent.py` | `DEFAULT_SCOPE_PLACEHOLDERS` check pattern |
| Tool factory pattern | `tempo/tools/tool_factory.py` | Register new browser tools |
| Findings integration | `tempo/infra/protocols.py` | `FindingsUpdater` protocol |
| Config management | `tempo/agent/config.py` | Add browser-specific config options |

---

## 2. Architectural Decisions

### 2.1 New File Structure

```
tempo/
├── infra/
│   └── browser_state.py        # NEW: Browser state persistence manager
├── tools/
│   ├── browser_tools.py        # MODIFY: Add screenshot, coordinate click, state tools
│   ├── browser_task_tool.py    # MODIFY: Add state_name, scope, headless params, visualization
│   └── browser_state_tools.py  # NEW: State management tools (list, save, load, delete)
├── agents/
│   └── browser.py              # MODIFY: Add scope support, state configuration
└── prompts/
    └── templates/
        ├── browser_base.txt    # MODIFY: Add state management guidance
        ├── subagent_recon.txt  # MODIFY: Add browser_task usage guidance
        └── subagent_test.txt   # MODIFY: Add browser_task usage guidance
```

### 2.2 State Persistence Architecture

**Design Decision**: Create a `BrowserStateManager` class in `tempo/infra/browser_state.py` that:
- Stores browser state (cookies, localStorage, sessionStorage) as JSON files
- Uses named states (e.g., "admin_session", "user_session")
- Provides async-safe operations for concurrent subagent access
- Lives in `infra/` since it's cross-cutting infrastructure (like `ContainerManager`)
- **NEW**: Supports TTL-based cleanup for old states

**State Storage Location**: `~/.tempo-sec/browser_states/` or configurable via config

**State File Format**:
```json
{
  "name": "admin_session",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T11:45:00Z",
  "expires_at": "2024-01-22T10:30:00Z",
  "target_domain": "example.com",
  "cookies": [...],
  "local_storage": {...},
  "session_storage": {...},
  "metadata": {
    "created_by": "browser_agent",
    "description": "Admin account session after login"
  }
}
```

**State Cleanup Strategy**:
- Default TTL: 7 days (configurable)
- Cleanup happens automatically on state manager initialization
- Manual cleanup via `browser_cleanup_states` tool
- Expired states are deleted, not archived

### 2.3 Tool-Level Design

**New Tools to Add:**

| Tool Name | Purpose | Category |
|-----------|---------|----------|
| `browser_screenshot` | Capture visual screenshot | BROWSING |
| `browser_click_coords` | Click at x,y coordinates | BROWSING |
| `browser_list_states` | List available saved states | BROWSING |
| `browser_save_state` | Save current browser state | BROWSING |
| `browser_load_state` | Load a saved browser state | BROWSING |
| `browser_delete_state` | Delete a saved state | BROWSING |
| `browser_cleanup_states` | Remove expired states | BROWSING |
| `browser_scroll` | Scroll page (by element or pixels) | BROWSING |
| `browser_wait` | Wait for element or timeout | BROWSING |

**Modifications to Existing Tools:**

1. `BrowserSession` class:
   - Add `headless` parameter (configurable)
   - Add state persistence methods
   - Add screenshot capture method
   - Add coordinate-based click support

2. `BrowserNavigateTool`:
   - Add option to load state before navigation

3. `BrowserTaskTool`:
   - Add `state_name` parameter (optional, use saved state)
   - Add `scope` parameter (propagated to browser agent)
   - Add `headless` parameter (default: True)
   - Add `save_state_as` parameter (optional, save state after task)

### 2.4 Integration Points

**With Orchestrator/Test Agent:**
- Test agent can call `browser_task` with `state_name="user_session"` to reuse authenticated state
- Browser agent reports extracted credentials/tokens back via `complete_browser_task`
- Findings document can record browser-discovered authentication flows

**With Findings Document:**
- Browser state metadata can be stored in findings (which states exist, what they provide)
- Authentication attack surfaces discovered via browser can be documented

### 2.5 UI Event Propagation

**Design Decision**: Browser agent events must be visible in the UI so users can see what the browser is doing.

**Implementation**:
- `BrowserTaskTool` accepts a `visualization_collector` parameter (already part of Agent constructor)
- When creating a browser agent, use `collector.for_subagent("browser_agent_{id}")` to create a child collector
- Pass the child collector to the browser Agent constructor
- All browser agent steps, tool calls, and phase transitions will be emitted to the UI
- UI can display browser agent activity in a nested/hierarchical view

**Event Flow**:
```
Parent Agent (Test/Recon)
  └─> browser_task tool
      └─> Browser Agent (with child collector)
          └─> Events emitted with subagent_id
              └─> UI displays in context
```

### 2.6 Headless Mode Configuration

**Configuration via `config.toml` only**:

```toml
[browser]
headless = true  # Set to false to show browser window
```

**Design Rationale**:
- Simplifies the tool interface by removing per-call configuration
- Ensures consistent browser behavior across all tasks
- Makes debugging easier by changing a single config value
- Avoids complexity of mode-switching during a session

**Use cases**:
- **Headless (default)**: Automated security testing, CI/CD pipelines
- **Non-headless**: Set `headless = false` in config for debugging or demonstrations

**Code Default**: If `[browser].headless` is not set in config, defaults to `true` (headless mode).

---

## 3. Implementation Steps

### Phase 1: Browser State Infrastructure (Foundation)

**Step 1.1: Create BrowserStateManager** (`tempo/infra/browser_state.py`)

```python
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
```

**Step 1.2: Add browser config options** (`tempo/agent/config.py`)

Add to the `AgentConfig` dataclass:
```python
# Browser settings
browser_state_dir: str = "~/.tempo-sec/browser_states"
browser_state_ttl_days: int = 7
browser_headless: bool = True
browser_default_timeout: int = 30000  # milliseconds
browser_viewport_width: int = 1280
browser_viewport_height: int = 720
```

Add to `from_dict()` method:
```python
# [browser] section
if "browser" in data:
    br = data["browser"]
    if "state_dir" in br:
        kwargs["browser_state_dir"] = br["state_dir"]
    if "state_ttl_days" in br:
        kwargs["browser_state_ttl_days"] = br["state_ttl_days"]
    if "headless" in br:
        kwargs["browser_headless"] = br["headless"]
    if "default_timeout" in br:
        kwargs["browser_default_timeout"] = br["default_timeout"]
    if "viewport_width" in br:
        kwargs["browser_viewport_width"] = br["viewport_width"]
    if "viewport_height" in br:
        kwargs["browser_viewport_height"] = br["viewport_height"]
```

### Phase 2: Enhanced BrowserSession

**Step 2.1: Upgrade BrowserSession class** (`tempo/tools/browser_tools.py`)

Key modifications:
```python
class BrowserSession:
    """
    Shared browser session manager for Playwright-style tools.

    Manages the Playwright browser instance lifecycle, maintains
    state (like element refs from snapshots), and supports:
    - Headless/headed modes
    - State persistence (cookies, localStorage)
    - Screenshot capture
    - Coordinate-based interactions
    """

    def __init__(
        self,
        container_manager: "ContainerManager | None" = None,
        headless: bool = True,
        state_manager: "BrowserStateManager | None" = None,
        viewport_width: int = 1280,
        viewport_height: int = 720,
    ):
        self.container = container_manager
        self._headless = headless
        self._state_manager = state_manager
        self._viewport = {"width": viewport_width, "height": viewport_height}
        # ... existing initialization

    async def ensure_browser(self) -> None:
        """Ensure browser is initialized with configured headless mode."""
        if self._browser is not None:
            return

        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)
        self._page = await self._browser.new_page(viewport=self._viewport)
        # ... console/network capture setup

    async def capture_state(self) -> "BrowserState":
        """Capture current browser state (cookies, storage)."""
        from tempo.infra.browser_state import BrowserState

        await self.ensure_browser()

        # Get cookies
        cookies = await self._page.context.cookies()

        # Get localStorage and sessionStorage
        local_storage = await self._page.evaluate("() => Object.assign({}, localStorage)")
        session_storage = await self._page.evaluate("() => Object.assign({}, sessionStorage)")

        # Get domain from current URL
        from urllib.parse import urlparse
        domain = urlparse(self._page.url).netloc if self._page.url else ""

        return BrowserState(
            name="",  # Will be set by caller
            target_domain=domain,
            cookies=cookies,
            local_storage=local_storage,
            session_storage=session_storage,
        )

    async def restore_state(self, state: "BrowserState") -> None:
        """Restore browser state from saved state."""
        await self.ensure_browser()

        # Restore cookies
        if state.cookies:
            await self._page.context.add_cookies(state.cookies)

        # Restore localStorage
        if state.local_storage:
            for key, value in state.local_storage.items():
                await self._page.evaluate(
                    f"localStorage.setItem({json.dumps(key)}, {json.dumps(value)})"
                )

        # Restore sessionStorage
        if state.session_storage:
            for key, value in state.session_storage.items():
                await self._page.evaluate(
                    f"sessionStorage.setItem({json.dumps(key)}, {json.dumps(value)})"
                )

    async def screenshot(self, path: str | None = None, full_page: bool = False) -> bytes:
        """Capture screenshot of current page."""
        await self.ensure_browser()

        screenshot_bytes = await self._page.screenshot(
            path=path,
            full_page=full_page,
            type="png",
        )
        return screenshot_bytes

    async def click_coordinates(self, x: int, y: int, button: str = "left") -> None:
        """Click at specific coordinates."""
        await self.ensure_browser()
        await self._page.mouse.click(x, y, button=button)

    async def scroll(
        self,
        direction: str = "down",
        amount: int = 500,
        element_ref: str | None = None,
    ) -> None:
        """Scroll the page or a specific element."""
        await self.ensure_browser()

        if element_ref:
            # Scroll element into view
            element_info = self.get_element_by_ref(element_ref)
            if element_info:
                # Use locator to scroll element into view
                # Implementation depends on element location strategy
                pass
        else:
            # Scroll viewport
            delta = amount if direction == "down" else -amount
            await self._page.mouse.wheel(0, delta)

    async def wait_for(
        self,
        selector: str | None = None,
        timeout: int = 30000,
        state: str = "visible",
    ) -> bool:
        """Wait for element or timeout."""
        await self.ensure_browser()

        try:
            if selector:
                await self._page.wait_for_selector(
                    selector,
                    timeout=timeout,
                    state=state,  # "visible", "hidden", "attached", "detached"
                )
            else:
                await self._page.wait_for_timeout(timeout)
            return True
        except Exception:
            return False
```

### Phase 3: New Browser Tools

**Step 3.1: Create browser state tools** (`tempo/tools/browser_state_tools.py`)

```python
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
    description = "List all saved browser states with their metadata (domain, creation time, expiration, etc.)"
    category = ToolCategory.BROWSING

    def __init__(self, state_manager: "BrowserStateManager"):
        self._state_manager = state_manager

    async def execute(self, purpose: str = "") -> ToolResult:
        """List available browser states."""
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
            if state.get('metadata', {}).get('description'):
                lines.append(f"  Description: {state['metadata']['description']}")
            lines.append("")

        return ToolResult(
            success=True,
            output="\n".join(lines),
            metadata={"count": len(states), "states": states},
        )

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={"type": "object", "properties": {}, "required": []},
        )


class BrowserSaveStateTool(Tool):
    """Save current browser state with a name."""

    name = "browser_save_state"
    description = "Save the current browser state (cookies, localStorage, sessionStorage) with a name for later use"
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
                output=f"Browser state saved as '{name}' for domain {state.target_domain}. "
                       f"Expires: {state.expires_at}",
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
                        "description": "Name for the saved state (e.g., 'admin_session', 'user_session')",
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

    async def execute(self, name: str, purpose: str = "") -> ToolResult:
        """Load browser state."""
        try:
            state = await self._state_manager.load(name)
            if not state:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"No saved state found with name '{name}' (may be expired or deleted)",
                )

            await self._session.restore_state(state)

            return ToolResult(
                success=True,
                output=f"Loaded browser state '{name}' (domain: {state.target_domain}). "
                       f"Cookies and storage restored. Navigate to the target to use the session.",
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

    async def execute(self, name: str, purpose: str = "") -> ToolResult:
        """Delete browser state."""
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

    async def execute(self, purpose: str = "") -> ToolResult:
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
```

**Step 3.2: Add screenshot and coordinate click tools** (add to `tempo/tools/browser_tools.py`)

```python
class BrowserScreenshotTool(Tool):
    """Capture a screenshot of the current page."""

    name = "browser_screenshot"
    description = "Capture a screenshot of the current page. Returns image path and optionally base64 data."
    category = ToolCategory.BROWSING

    def __init__(self, session: BrowserSession):
        self.session = session

    async def execute(
        self,
        filename: str | None = None,
        full_page: bool = False,
        return_base64: bool = False,
        purpose: str = "",
    ) -> ToolResult:
        """Capture screenshot."""
        try:
            await self.session.ensure_browser()

            # Generate filename if not provided
            if not filename:
                import uuid
                filename = f"/tmp/screenshot_{uuid.uuid4().hex[:8]}.png"

            screenshot_bytes = await self.session.screenshot(path=filename, full_page=full_page)

            output = f"Screenshot saved to: {filename}\nSize: {len(screenshot_bytes)} bytes"
            metadata = {
                "path": filename,
                "size_bytes": len(screenshot_bytes),
                "full_page": full_page,
            }

            if return_base64:
                import base64
                b64_data = base64.b64encode(screenshot_bytes).decode("utf-8")
                metadata["base64"] = b64_data
                output += f"\nBase64 data length: {len(b64_data)}"

            return ToolResult(
                success=True,
                output=output,
                metadata=metadata,
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
                    "filename": {
                        "type": "string",
                        "description": "Path to save screenshot (auto-generated if not provided)",
                    },
                    "full_page": {
                        "type": "boolean",
                        "description": "Capture full scrollable page instead of viewport",
                        "default": False,
                    },
                    "return_base64": {
                        "type": "boolean",
                        "description": "Include base64-encoded image data in metadata (for vision models)",
                        "default": False,
                    },
                },
                "required": [],
            },
        )


class BrowserClickCoordsTool(Tool):
    """Click at specific x,y coordinates."""

    name = "browser_click_coords"
    description = "Click at specific x,y coordinates on the page. Useful when element refs don't work."
    category = ToolCategory.BROWSING

    def __init__(self, session: BrowserSession):
        self.session = session

    async def execute(
        self,
        x: int,
        y: int,
        button: str = "left",
        purpose: str = "",
    ) -> ToolResult:
        """Click at coordinates."""
        try:
            await self.session.ensure_browser()
            await self.session.click_coordinates(x, y, button)

            return ToolResult(
                success=True,
                output=f"Clicked at coordinates ({x}, {y}) with {button} button",
                metadata={"x": x, "y": y, "button": button},
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
                    "x": {
                        "type": "integer",
                        "description": "X coordinate (pixels from left)",
                    },
                    "y": {
                        "type": "integer",
                        "description": "Y coordinate (pixels from top)",
                    },
                    "button": {
                        "type": "string",
                        "enum": ["left", "right", "middle"],
                        "description": "Mouse button to click",
                        "default": "left",
                    },
                },
                "required": ["x", "y"],
            },
        )


class BrowserScrollTool(Tool):
    """Scroll the page."""

    name = "browser_scroll"
    description = "Scroll the page up or down by a specified amount"
    category = ToolCategory.BROWSING

    def __init__(self, session: BrowserSession):
        self.session = session

    async def execute(
        self,
        direction: str = "down",
        amount: int = 500,
        purpose: str = "",
    ) -> ToolResult:
        """Scroll the page."""
        try:
            await self.session.ensure_browser()
            await self.session.scroll(direction=direction, amount=amount)

            return ToolResult(
                success=True,
                output=f"Scrolled {direction} by {amount} pixels",
                metadata={"direction": direction, "amount": amount},
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
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down"],
                        "description": "Scroll direction",
                        "default": "down",
                    },
                    "amount": {
                        "type": "integer",
                        "description": "Pixels to scroll",
                        "default": 500,
                    },
                },
                "required": [],
            },
        )


class BrowserWaitTool(Tool):
    """Wait for element or timeout."""

    name = "browser_wait"
    description = "Wait for an element to appear or for a specified timeout"
    category = ToolCategory.BROWSING

    def __init__(self, session: BrowserSession):
        self.session = session

    async def execute(
        self,
        selector: str | None = None,
        timeout_ms: int = 5000,
        state: str = "visible",
        purpose: str = "",
    ) -> ToolResult:
        """Wait for condition."""
        try:
            await self.session.ensure_browser()

            if selector:
                success = await self.session.wait_for(
                    selector=selector,
                    timeout=timeout_ms,
                    state=state,
                )
                if success:
                    return ToolResult(
                        success=True,
                        output=f"Element '{selector}' is now {state}",
                        metadata={"selector": selector, "state": state},
                    )
                else:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Timeout waiting for '{selector}' to be {state}",
                    )
            else:
                await self.session.wait_for(timeout=timeout_ms)
                return ToolResult(
                    success=True,
                    output=f"Waited {timeout_ms}ms",
                    metadata={"timeout_ms": timeout_ms},
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
                    "selector": {
                        "type": "string",
                        "description": "CSS selector to wait for (if omitted, just waits for timeout)",
                    },
                    "timeout_ms": {
                        "type": "integer",
                        "description": "Maximum time to wait in milliseconds",
                        "default": 5000,
                    },
                    "state": {
                        "type": "string",
                        "enum": ["visible", "hidden", "attached", "detached"],
                        "description": "Element state to wait for",
                        "default": "visible",
                    },
                },
                "required": [],
            },
        )
```


### Phase 4: Browser Agent Updates

**Step 4.1: Update BrowserAgent class** (`tempo/agents/browser.py`)

Key changes:
- Add parameters: `state_name`, `save_state_as`, `headless`, `scope`
- Register new tools in `create_tools()`
- Update `build_system_prompt()` to include scope support
- Update `build_objective()` to mention state loading/saving

See full implementation in the detailed plan sections above.

### Phase 5: BrowserTaskTool Updates

**Step 5.1: Update BrowserTaskTool constructor** (`tempo/tools/browser_task_tool.py`)

```python
def __init__(
    self,
    container_manager: "ContainerManager | None" = None,
    llm_client: "LLMClient | None" = None,
    visualization_collector: "VisualizationCollector | None" = None,
):
    """
    Initialize the browser task tool.

    Args:
        container_manager: Container for sandboxed browser execution
        llm_client: LLM client for the browser agent
        visualization_collector: Collector for UI event propagation
    """
    self._container_manager = container_manager
    self._llm_client = llm_client
    self._visualization_collector = visualization_collector
```

**Step 5.2: Update BrowserTaskTool.execute()** (`tempo/tools/browser_task_tool.py`)

```python
async def execute(
    self,
    task: str,
    url: str = "",
    state_name: str = "",
    save_state_as: str = "",
    scope: str = "",
    max_steps: int | str = 10,
    **kwargs,
) -> ToolResult:
    """
    Execute a browser task via the browser agent.

    Args:
        task: Description of what the browser agent should accomplish
        url: Optional starting URL
        state_name: Optional name of saved state to load
        save_state_as: Optional name to save state as after completion
        scope: Optional scope constraints for the browser agent
        max_steps: Maximum steps for the browser agent (default: 10)
        **kwargs: Additional arguments
    """
    # ... existing code ...

    # Create child visualization collector for browser agent
    browser_collector = None
    if self._visualization_collector:
        import uuid
        browser_id = f"browser_{uuid.uuid4().hex[:8]}"
        browser_collector = self._visualization_collector.for_subagent(browser_id)

    # Create browser agent with visualization
    browser_agent = Agent(
        config=config,
        llm=llm,
        tools=browser_tools,
        context=browser_context,
        visualization_collector=browser_collector,  # NEW: Enable UI events
    )

    # ... rest of execution ...
```

Update schema:
```python
def get_schema(self) -> ToolSchema:
    return ToolSchema(
        name=self.name,
        description=self.description,
        parameters={
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Description of the browser task to accomplish",
                },
                "url": {
                    "type": "string",
                    "description": "Optional starting URL to navigate to",
                    "default": "",
                },
                "state_name": {
                    "type": "string",
                    "description": "Optional name of saved browser state to load (e.g., 'admin_session')",
                    "default": "",
                },
                "save_state_as": {
                    "type": "string",
                    "description": "Optional name to save browser state as after task completion",
                    "default": "",
                },

                "scope": {
                    "type": "string",
                    "description": "Optional scope constraints for the browser agent",
                    "default": "",
                },
                "max_steps": {
                    "type": "integer",
                    "description": "Maximum steps for the browser agent",
                    "default": 10,
                },
            },
            "required": ["task"],
        },
    )
```

### Phase 6: Prompt Template Updates

**Step 6.1: Update browser_base.txt** (`tempo/prompts/templates/browser_base.txt`)

```
You are a **Browser Automation Agent** - a specialized agent for web browsing tasks.

## Your Role

You execute specific browser-based tasks delegated by a parent agent. Your job is to:
1. Navigate to the target URL (if provided)
2. Load any saved browser state (if specified)
3. Understand the page structure using snapshots
4. Interact with elements to accomplish the task
5. Save browser state (if requested)
6. Report your findings when complete

## Available Tools

{tools}

{scope_section}

## State Management

Browser state (cookies, localStorage, sessionStorage) can be saved and loaded:
- Use `browser_list_states` to see available saved sessions
- Use `browser_load_state` to restore a previously saved session
- Use `browser_save_state` to preserve the current session for later use
- States expire after {ttl_days} days by default (configurable per state)
- Use `browser_cleanup_states` to remove expired states

{state_instructions}

## Workflow

1. **Load State (if specified)**: Use `browser_load_state` to restore session
2. **Navigate**: Use `browser_navigate` to go to the target URL
3. **Snapshot**: Use `browser_snapshot` to get interactive elements with refs
4. **Interact**: Use browser tools with refs or coordinates
5. **Save State (if requested)**: Use `browser_save_state` before completing
6. **Complete**: Call `complete_browser_task` with your findings

## Visual Capabilities

- `browser_screenshot`: Capture what you see (useful for visual elements, can return base64 for vision models)
- `browser_click_coords`: Click at specific x,y coordinates when refs fail
- `browser_scroll`: Scroll the page to reveal more content
- `browser_wait`: Wait for elements or time delays

## Guidelines

- Stay focused on the assigned task - don't explore unrelated pages
- Take snapshots after navigation or significant page changes
- Use refs from the most recent snapshot for interactions
- Use coordinate clicks as fallback when element refs don't work
- Take screenshots to capture visual information
- Report both successes and failures in your findings
- Call `complete_browser_task` when done (success or failure)
- When saving state, provide a clear description for future reference
```

**Step 6.2: Update PromptBuilder** (`tempo/prompts/builder.py`)

```python
def build_browser_prompt(
    self,
    tool_schemas: list[dict],
    scope_content: str | None = None,
    state_name: str | None = None,
    save_state_as: str | None = None,
    ttl_days: int = 7,
) -> str:
    """
    Build the system prompt for browser agent.
    """
    tool_descriptions = self.format_tool_descriptions(tool_schemas)
    template = self._load_template("browser_base")

    # Build scope section
    scope_section = self._build_scope_section(scope_content)

    # Build state instructions
    state_instructions = ""
    if state_name:
        state_instructions += f"\n**Initial State**: Load saved state '{state_name}' at the start.\n"
    if save_state_as:
        state_instructions += f"\n**Save State**: Save browser state as '{save_state_as}' before completing.\n"
    if not state_name and not save_state_as:
        state_instructions = "\nNo specific state loading or saving required for this task.\n"

    return template.format(
        tools=tool_descriptions,
        scope_section=scope_section,
        state_instructions=state_instructions,
        ttl_days=ttl_days,
    )
```

### Phase 7: Agent Prompt Updates

**Step 7.1: Update Recon Agent Prompt** (`tempo/prompts/templates/subagent_recon.txt`)

Add a new section after "Guidelines" explaining when to use browser_task:

```markdown
## When to Use Browser Agent

Use `browser_task` for tasks that require:
- **Dynamic JavaScript Rendering**: SPAs, React apps, Vue apps where content loads via JS
- **Interactive Exploration**: Clicking through multi-page flows, navigating menus
- **Form Submission**: Testing login forms, search forms, registration flows
- **Session Management**: Tasks requiring cookies or authentication state
- **Visual Analysis**: Capturing screenshots of pages
- **AJAX/Fetch Discovery**: Observing network requests made by the browser

**Examples**:
```
# Good use of browser_task
browser_task(
    task="Navigate to the login page, take a screenshot, and list all form fields",
    url="https://example.com"
)

# Good use for state persistence
browser_task(
    task="Log in with credentials admin/admin123 and save the session",
    url="https://example.com/login",
    save_state_as="admin_session"
)

# Reuse saved state
browser_task(
    task="Navigate to /admin and list all available admin functions",
    state_name="admin_session",
    url="https://example.com/admin"
)
```

**Don't use browser_task for**:
- Simple HTTP requests (use `shell` with curl instead)
- Static HTML analysis (use `shell` with wget + grep)
- API testing (use `shell` with curl/httpie)
```

**Step 7.2: Update Test Agent Prompt** (`tempo/prompts/templates/subagent_test.txt`)

Add a new section after "Guidelines" explaining when to use browser_task:

```markdown
## When to Use Browser Agent

Use `browser_task` for testing that requires:
- **Browser-Based Vulnerabilities**: XSS, CSRF, clickjacking
- **Client-Side Security**: Testing JavaScript security, DOM-based XSS
- **Authentication Testing**: Login bypass, session management flaws
- **Multi-Step Exploitation**: Attacks requiring multiple page interactions
- **Automated Attack Chains**: Login → Navigate → Exploit → Extract data
- **Session State**: Reusing authenticated sessions across multiple tests

**State Management for Testing**:
```
# Step 1: Create authenticated session
browser_task(
    task="Log in as regular user with user/pass123",
    url="https://example.com/login",
    save_state_as="user_session"
)

# Step 2: Test privilege escalation with saved state
browser_task(
    task="Try to access /admin endpoint and check response",
    state_name="user_session",
    url="https://example.com/admin"
)

# Step 3: Test for stored XSS with saved state
browser_task(
    task="Submit XSS payload <script>alert(1)</script> in profile bio field",
    state_name="user_session",
    url="https://example.com/profile/edit"
)
```

**Testing Workflow**:
1. Use `browser_task` with `save_state_as` to establish authenticated sessions
2. Reuse states with `state_name` to test from different privilege levels
3. Set `headless = false` in config.toml when debugging failing tests to watch what's happening
4. Use `browser_list_states` to see available sessions before testing
```

### Phase 8: Configuration Updates

**Step 8.1: Update config.toml** (`config.toml`)

Add:
```toml
[browser]
# Directory for storing browser states
state_dir = "~/.tempo-sec/browser_states"
# Default TTL for browser states in days
state_ttl_days = 7
# Headless mode (set to false to show browser window)
headless = true
# Default navigation timeout (ms)
default_timeout = 30000
# Default viewport dimensions
viewport_width = 1280
viewport_height = 720
```

---

## 4. Testing Strategy

### 4.1 Unit Tests

**File**: `tests/infra/test_browser_state.py`
- Test `BrowserStateManager.save()` and `load()`
- Test `list_states()` returns correct metadata
- Test `delete()` removes state files
- Test `cleanup_expired()` removes expired states
- Test async locking for concurrent access
- Test TTL expiration logic

**File**: `tests/tools/test_browser_state_tools.py`
- Test `BrowserListStatesTool` with empty and populated state dirs
- Test `BrowserSaveStateTool` creates valid state files with correct expiration
- Test `BrowserLoadStateTool` restores state correctly
- Test `BrowserLoadStateTool` rejects expired states
- Test `BrowserDeleteStateTool` removes states
- Test `BrowserCleanupStatesTool` removes only expired states

**File**: `tests/tools/test_browser_tools.py` (extend existing)
- Test `BrowserScreenshotTool` creates PNG files
- Test `BrowserScreenshotTool` with base64 output
- Test `BrowserClickCoordsTool` sends correct mouse events
- Test `BrowserScrollTool` scrolls viewport
- Test `BrowserWaitTool` times out correctly

### 4.2 Integration Tests

**File**: `tests/integration/test_browser_state_flow.py`
- Test full flow: navigate -> login -> save state -> new session -> load state -> verify logged in
- Test state persists across browser agent invocations
- Test multiple named states don't conflict
- Test expired states are not loaded
- Test cleanup removes only expired states

**File**: `tests/integration/test_browser_agent_scope.py`
- Test scope parameter propagates to browser agent prompt
- Test headless/headed mode switching

---

## 5. Implementation Checklist

### Phase 1: Foundation & Infrastructure
*Create browser state management and enhance BrowserSession with new capabilities.*

- [ ] Create `tempo/infra/browser_state.py` with `BrowserState` and `BrowserStateManager`
- [ ] Add browser config options to `tempo/agent/config.py`
- [ ] Add `[browser]` section to `config.toml`
- [ ] Update `BrowserSession.__init__()` with new parameters (headless from config, state_manager, viewport)
- [ ] Add `BrowserSession.capture_state()` method
- [ ] Add `BrowserSession.restore_state()` method
- [ ] Add `BrowserSession.screenshot()` method
- [ ] Add `BrowserSession.click_coordinates()` method
- [ ] Add `BrowserSession.scroll()` method
- [ ] Add `BrowserSession.wait_for()` method
- [ ] Write unit tests for `BrowserStateManager` (save/load/delete/cleanup/expiration)

---

### Phase 2: Tools & Agent Integration
*Create new browser tools and wire them into the browser agent and task tool.*

- [ ] Create `tempo/tools/browser_state_tools.py` with:
  - [ ] `BrowserListStatesTool`
  - [ ] `BrowserSaveStateTool`
  - [ ] `BrowserLoadStateTool`
  - [ ] `BrowserDeleteStateTool`
  - [ ] `BrowserCleanupStatesTool`
- [ ] Add to `tempo/tools/browser_tools.py`:
  - [ ] `BrowserScreenshotTool`
  - [ ] `BrowserClickCoordsTool`
  - [ ] `BrowserScrollTool`
  - [ ] `BrowserWaitTool`
- [ ] Update `BrowserAgent` (`tempo/agents/browser.py`):
  - [ ] Add `state_name`, `save_state_as`, `scope` parameters
  - [ ] Register new tools in `create_tools()`
  - [ ] Update `build_system_prompt()` for scope support
  - [ ] Update `build_objective()` with state instructions
- [ ] Update `BrowserTaskTool` (`tempo/tools/browser_task_tool.py`):
  - [ ] Accept `visualization_collector` in constructor
  - [ ] Update `execute()` with `state_name`, `save_state_as`, `scope` parameters
  - [ ] Create child collector for browser agent visualization
  - [ ] Update `get_schema()` with new parameters
- [ ] Update Recon/Test agent tool instantiation to pass `visualization_collector`
- [ ] Write unit tests for new browser tools

---

### Phase 3: Prompts, Testing & Documentation
*Update prompts with usage guidance and write integration tests.*

- [ ] Update `tempo/prompts/templates/browser_base.txt` with state management guidance
- [ ] Update `PromptBuilder.build_browser_prompt()` method
- [ ] Update `subagent_recon.txt` with `browser_task` usage guidance
- [ ] Update `subagent_test.txt` with `browser_task` usage and state examples
- [ ] Write integration tests for full state flow (login → save → reload → verify)
- [ ] Write integration tests for scope propagation
- [ ] Update documentation (TOOLS.md, AGENTS.md)


---

## 6. Deployment & Rollback

### Deployment Steps
1. Create new files (`browser_state.py`, `browser_state_tools.py`)
2. Update existing files in dependency order
3. Run test suite
4. Update documentation (TOOLS.md, AGENTS.md)

### Rollback Plan
- All changes are additive (new tools, new parameters with defaults)
- Existing browser functionality preserved
- No data migration needed
- Simple git revert if issues arise

---

## 7. Open Questions

1. **Screenshot base64** - Should screenshots always include base64 data for vision models, or only when requested?
   - **Decision**: Only when `return_base64=True` to avoid bloating context

2. **State cleanup automation** - Should cleanup happen automatically on state manager init, or only when explicitly called?
   - **Decision**: Run automatic cleanup on init (lightweight operation)

3. **Container mode** - How should state persistence work in container mode?
   - **Future work**: Mount state directory as volume

4. **State sharing** - Should there be a way to export/import states between machines?
   - **Future work**: Add export/import tools if needed

---

## 8. Quick Reference Guide

### How to Configure Headless/Non-Headless Mode

Headless mode is configured **exclusively** via `config.toml`. There is no per-call override.

**Edit `config.toml`:**
```toml
[browser]
headless = true   # Default: run browser without visible window
# headless = false  # Uncomment to show browser window for debugging
```

**Default Behavior**: If `[browser].headless` is not specified in config, the code default is `true` (headless mode).

### Common Scenarios

| Scenario | Configuration | How to Set |
|----------|--------------|------------|
| Automated testing | `headless = true` | Default behavior, no config needed |
| CI/CD Pipeline | `headless = true` | Default behavior, no config needed |
| Debugging failing tests | `headless = false` | Edit config.toml, then run tests |
| Demonstration | `headless = false` | Edit config.toml before presentation |
| Recording attack video | `headless = false` | Edit config.toml to show browser |
| Production scanning | `headless = true` | Default behavior, no config needed |


## 9. Success Criteria

Implementation is complete when:
- [ ] All 9 new browser tools are implemented and registered
- [ ] Browser states persist across agent invocations
- [ ] States expire after TTL and are cleaned up
- [ ] Scope parameter propagates correctly
- [ ] Headless mode is configurable via config.toml
- [ ] Browser agent events appear in UI via visualization collector
- [ ] Recon and Test agent prompts include browser_task usage guidance
- [ ] All tests pass
- [ ] Documentation is updated
- [ ] Example workflows work (login -> save -> reuse)
- [ ] UI displays browser agent activity in nested view
