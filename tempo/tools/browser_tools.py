"""
Playwright-style browser tools for comprehensive web interaction.

This module provides tools that mimic the Playwright MCP server's functionality,
enabling ref-based element targeting via accessibility snapshots.
"""

from typing import TYPE_CHECKING, Any
import asyncio
import json

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema

if TYPE_CHECKING:
    from tempo.infra.container import ContainerManager


class BrowserSession:
    """
    Shared browser session manager for Playwright-style tools.
    
    Manages the Playwright browser instance lifecycle and maintains
    state (like element refs from snapshots) across tool calls.
    """
    
    def __init__(self, container_manager: "ContainerManager | None" = None):
        """
        Initialize the browser session.
        
        Args:
            container_manager: Optional container for sandboxed execution.
                              If None, runs Playwright locally.
        """
        self.container = container_manager
        self._playwright = None
        self._browser = None
        self._page = None
        self._snapshot_refs: dict[str, Any] = {}  # ref -> element info
        self._console_messages: list[dict] = []
        self._network_requests: list[dict] = []
    
    async def ensure_browser(self) -> None:
        """Ensure browser is initialized and ready."""
        if self._browser is not None:
            return
        
        if self.container is not None:
            # Container mode - browser runs inside container
            # We'll execute commands via container.exec()
            return
        
        # Local mode - use Playwright directly
        from playwright.async_api import async_playwright
        
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._page = await self._browser.new_page()
        
        # Set up console message capture
        self._page.on("console", self._on_console_message)
        
        # Set up network request capture
        self._page.on("request", self._on_request)
    
    def _on_console_message(self, msg) -> None:
        """Capture console messages."""
        self._console_messages.append({
            "type": msg.type,
            "text": msg.text,
            "location": str(msg.location) if msg.location else None,
        })
    
    def _on_request(self, request) -> None:
        """Capture network requests."""
        self._network_requests.append({
            "url": request.url,
            "method": request.method,
            "resource_type": request.resource_type,
        })
    
    @property
    def page(self):
        """Get the current page instance."""
        return self._page
    
    async def close(self) -> None:
        """Close the browser and clean up resources."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        self._page = None
        self._snapshot_refs.clear()
        self._console_messages.clear()
        self._network_requests.clear()
    
    def get_element_by_ref(self, ref: str) -> dict | None:
        """Look up element info by ref from the last snapshot."""
        return self._snapshot_refs.get(ref)
    
    def store_snapshot_refs(self, refs: dict[str, Any]) -> None:
        """Store element refs from a snapshot."""
        self._snapshot_refs = refs


class BrowserNavigateTool(Tool):
    """Navigate to a URL."""
    
    name = "browser_navigate"
    description = "Navigate to a URL"
    category = ToolCategory.BROWSING
    
    def __init__(self, session: BrowserSession):
        self.session = session
    
    async def execute(
        self,
        url: str,
        purpose: str = "",
    ) -> ToolResult:
        """
        Navigate to the specified URL.
        
        Args:
            url: The URL to navigate to
            purpose: Why this navigation is being performed
            
        Returns:
            ToolResult with navigation status
        """
        try:
            await self.session.ensure_browser()
            
            if self.session.container is not None:
                return await self._execute_in_container(url)
            
            response = await self.session.page.goto(url, wait_until="domcontentloaded")
            
            if response is None:
                return ToolResult(
                    success=False,
                    output="",
                    error="Navigation failed: no response received",
                )
            
            status = response.status
            title = await self.session.page.title()
            current_url = self.session.page.url
            
            if status >= 400:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Navigation failed: HTTP {status}",
                    metadata={"url": current_url, "status": status},
                )
            
            return ToolResult(
                success=True,
                output=f"Navigated to: {current_url}\nTitle: {title}\nStatus: {status}",
                metadata={"url": current_url, "title": title, "status": status},
            )
            
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
    
    async def _execute_in_container(self, url: str) -> ToolResult:
        """Execute navigation in container."""
        import base64
        
        script = f'''
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            response = await page.goto("{url}", wait_until="domcontentloaded")
            if response:
                print(f"URL: {{page.url}}")
                print(f"Title: {{await page.title()}}")
                print(f"Status: {{response.status}}")
            else:
                print("ERROR: No response")
        finally:
            await browser.close()

asyncio.run(main())
'''
        script_b64 = base64.b64encode(script.encode()).decode()
        exit_code, stdout, stderr = await self.session.container.exec(
            f"python3 -c \"import base64; exec(base64.b64decode('{script_b64}').decode())\"",
            timeout=60,
        )
        
        if exit_code != 0 or "ERROR:" in stdout:
            return ToolResult(success=False, output="", error=stderr or stdout)
        
        return ToolResult(success=True, output=stdout, metadata={"url": url})
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to navigate to",
                    },
                },
                "required": ["url"],
            },
        )


class BrowserSnapshotTool(Tool):
    """Capture accessibility snapshot of the current page."""
    
    name = "browser_snapshot"
    description = "Capture accessibility snapshot of the current page. This provides element refs for interaction."
    category = ToolCategory.BROWSING
    
    def __init__(self, session: BrowserSession):
        self.session = session
    
    async def execute(
        self,
        filename: str | None = None,
        purpose: str = "",
    ) -> ToolResult:
        """
        Capture accessibility snapshot.
        
        Args:
            filename: Optional file to save snapshot to
            purpose: Why this snapshot is being taken
            
        Returns:
            ToolResult with accessibility tree and element refs
        """
        try:
            await self.session.ensure_browser()
            
            if self.session.container is not None:
                return await self._execute_in_container(filename)
            
            # Get accessibility tree
            snapshot = await self.session.page.accessibility.snapshot()
            
            if snapshot is None:
                return ToolResult(
                    success=False,
                    output="",
                    error="Failed to capture accessibility snapshot",
                )
            
            # Build ref mapping from snapshot
            refs = {}
            ref_counter = [0]
            
            def process_node(node: dict, depth: int = 0) -> list[str]:
                """Process accessibility node and assign refs."""
                lines = []
                ref = f"ref_{ref_counter[0]}"
                ref_counter[0] += 1
                
                role = node.get("role", "unknown")
                name = node.get("name", "")
                
                # Store ref mapping
                refs[ref] = {
                    "role": role,
                    "name": name,
                    "node": node,
                }
                
                # Format output line
                indent = "  " * depth
                line = f"{indent}[{ref}] {role}"
                if name:
                    line += f': "{name[:50]}"' if len(name) > 50 else f': "{name}"'
                lines.append(line)
                
                # Process children
                for child in node.get("children", []):
                    lines.extend(process_node(child, depth + 1))
                
                return lines
            
            output_lines = process_node(snapshot)
            output = "\n".join(output_lines)
            
            # Store refs for later use
            self.session.store_snapshot_refs(refs)
            
            # Save to file if requested
            if filename:
                with open(filename, "w") as f:
                    f.write(output)
                output = f"Snapshot saved to: {filename}\n\n{output}"
            
            return ToolResult(
                success=True,
                output=output,
                metadata={"ref_count": len(refs)},
            )
            
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
    
    async def _execute_in_container(self, filename: str | None) -> ToolResult:
        """Execute snapshot in container."""
        # Container implementation would go here
        return ToolResult(
            success=False,
            output="",
            error="Container execution not yet implemented for browser_snapshot",
        )
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Optional file path to save the snapshot",
                    },
                },
                "required": [],
            },
        )


class BrowserClickTool(Tool):
    """Click on an element by ref."""
    
    name = "browser_click"
    description = "Click on an element identified by ref from the page snapshot"
    category = ToolCategory.BROWSING
    
    def __init__(self, session: BrowserSession):
        self.session = session
    
    async def execute(
        self,
        element: str,
        ref: str,
        doubleClick: bool = False,
        button: str = "left",
        modifiers: list[str] | None = None,
        purpose: str = "",
    ) -> ToolResult:
        """
        Click on the specified element.
        
        Args:
            element: Human-readable element description
            ref: Element reference from snapshot
            doubleClick: Whether to double-click
            button: Mouse button (left, right, middle)
            modifiers: Modifier keys (Shift, Control, Alt, Meta)
            purpose: Why this click is being performed
            
        Returns:
            ToolResult with click status
        """
        try:
            await self.session.ensure_browser()
            
            if self.session.container is not None:
                return ToolResult(
                    success=False,
                    output="",
                    error="Container execution not yet implemented for browser_click",
                )
            
            # Look up element by ref
            element_info = self.session.get_element_by_ref(ref)
            if element_info is None:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Ref not found: {ref}. Run browser_snapshot first to get element refs.",
                )
            
            # Use role and name to locate element
            role = element_info.get("role", "")
            name = element_info.get("name", "")
            
            # Try to locate element using accessibility info
            locator = None
            if role and name:
                locator = self.session.page.get_by_role(role, name=name)
            elif name:
                locator = self.session.page.get_by_text(name)
            
            if locator is None:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Could not locate element with ref {ref}",
                )
            
            # Build click options
            click_kwargs = {"button": button}
            if modifiers:
                click_kwargs["modifiers"] = modifiers
            
            # Perform click
            if doubleClick:
                await locator.dclick(**click_kwargs)
                action = "Double-clicked"
            else:
                await locator.click(**click_kwargs)
                action = "Clicked"
            
            return ToolResult(
                success=True,
                output=f"{action} on {element} (ref: {ref})",
                metadata={"ref": ref, "element": element, "action": action},
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
                    "element": {
                        "type": "string",
                        "description": "Human-readable element description for permission",
                    },
                    "ref": {
                        "type": "string",
                        "description": "Element reference from browser_snapshot",
                    },
                    "doubleClick": {
                        "type": "boolean",
                        "description": "Whether to double-click instead of single click",
                        "default": False,
                    },
                    "button": {
                        "type": "string",
                        "description": "Mouse button: left, right, or middle",
                        "default": "left",
                    },
                    "modifiers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Modifier keys: Shift, Control, Alt, Meta",
                    },
                },
                "required": ["element", "ref"],
            },
        )


class BrowserTypeTool(Tool):
    """Type text into an element."""
    
    name = "browser_type"
    description = "Type text into an editable element identified by ref"
    category = ToolCategory.BROWSING
    
    def __init__(self, session: BrowserSession):
        self.session = session
    
    async def execute(
        self,
        element: str,
        ref: str,
        text: str,
        submit: bool = False,
        slowly: bool = False,
        purpose: str = "",
    ) -> ToolResult:
        """
        Type text into the specified element.
        
        Args:
            element: Human-readable element description
            ref: Element reference from snapshot
            text: Text to type
            submit: Whether to press Enter after typing
            slowly: Whether to type character by character
            purpose: Why this typing is being performed
            
        Returns:
            ToolResult with typing status
        """
        try:
            await self.session.ensure_browser()
            
            if self.session.container is not None:
                return ToolResult(
                    success=False,
                    output="",
                    error="Container execution not yet implemented for browser_type",
                )
            
            # Look up element by ref
            element_info = self.session.get_element_by_ref(ref)
            if element_info is None:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Ref not found: {ref}. Run browser_snapshot first.",
                )
            
            role = element_info.get("role", "")
            name = element_info.get("name", "")
            
            # Locate element
            locator = None
            if role in ("textbox", "searchbox", "combobox"):
                locator = self.session.page.get_by_role(role, name=name) if name else self.session.page.get_by_role(role)
            elif name:
                locator = self.session.page.get_by_label(name)
            
            if locator is None:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Could not locate input element with ref {ref}",
                )
            
            # Clear existing content and type
            await locator.clear()
            
            if slowly:
                await locator.type(text, delay=50)
            else:
                await locator.fill(text)
            
            # Submit if requested
            if submit:
                await locator.press("Enter")
            
            result_text = f"Typed '{text}' into {element}"
            if submit:
                result_text += " and submitted"
            
            return ToolResult(
                success=True,
                output=result_text,
                metadata={"ref": ref, "text": text, "submitted": submit},
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
                    "element": {
                        "type": "string",
                        "description": "Human-readable element description",
                    },
                    "ref": {
                        "type": "string",
                        "description": "Element reference from browser_snapshot",
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to type into the element",
                    },
                    "submit": {
                        "type": "boolean",
                        "description": "Press Enter after typing",
                        "default": False,
                    },
                    "slowly": {
                        "type": "boolean",
                        "description": "Type character by character (triggers key handlers)",
                        "default": False,
                    },
                },
                "required": ["element", "ref", "text"],
            },
        )


class BrowserFillFormTool(Tool):
    """Fill multiple form fields at once."""
    
    name = "browser_fill_form"
    description = "Fill multiple form fields in one operation"
    category = ToolCategory.BROWSING
    
    def __init__(self, session: BrowserSession):
        self.session = session
    
    async def execute(
        self,
        fields: list[dict[str, str]],
        purpose: str = "",
    ) -> ToolResult:
        """
        Fill multiple form fields.
        
        Args:
            fields: List of {ref, value} or {element, ref, value} dicts
            purpose: Why this form is being filled
            
        Returns:
            ToolResult with fill status
        """
        try:
            await self.session.ensure_browser()
            
            if self.session.container is not None:
                return ToolResult(
                    success=False,
                    output="",
                    error="Container execution not yet implemented for browser_fill_form",
                )
            
            if not fields:
                return ToolResult(
                    success=False,
                    output="",
                    error="No fields provided",
                )
            
            filled = []
            errors = []
            
            for field in fields:
                ref = field.get("ref", "")
                value = field.get("value", "")
                element_desc = field.get("element", ref)
                
                if not ref or not value:
                    errors.append(f"Invalid field: {field}")
                    continue
                
                element_info = self.session.get_element_by_ref(ref)
                if element_info is None:
                    errors.append(f"Ref not found: {ref}")
                    continue
                
                role = element_info.get("role", "")
                name = element_info.get("name", "")
                
                try:
                    # Locate and fill
                    locator = None
                    if role in ("textbox", "searchbox", "combobox"):
                        locator = self.session.page.get_by_role(role, name=name) if name else self.session.page.get_by_role(role)
                    elif name:
                        locator = self.session.page.get_by_label(name)
                    
                    if locator:
                        await locator.fill(value)
                        filled.append(f"{element_desc}: '{value}'")
                    else:
                        errors.append(f"Could not locate: {ref}")
                except Exception as e:
                    errors.append(f"Error filling {ref}: {e}")
            
            output_parts = []
            if filled:
                output_parts.append(f"Filled {len(filled)} field(s):")
                output_parts.extend(f"  - {f}" for f in filled)
            if errors:
                output_parts.append(f"\nErrors ({len(errors)}):")
                output_parts.extend(f"  - {e}" for e in errors)
            
            return ToolResult(
                success=len(errors) == 0,
                output="\n".join(output_parts),
                metadata={"filled": len(filled), "errors": len(errors)},
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
                    "fields": {
                        "type": "array",
                        "description": "List of fields to fill",
                        "items": {
                            "type": "object",
                            "properties": {
                                "element": {
                                    "type": "string",
                                    "description": "Human-readable element description",
                                },
                                "ref": {
                                    "type": "string",
                                    "description": "Element reference from snapshot",
                                },
                                "value": {
                                    "type": "string",
                                    "description": "Value to fill",
                                },
                            },
                            "required": ["ref", "value"],
                        },
                    },
                },
                "required": ["fields"],
            },
        )
