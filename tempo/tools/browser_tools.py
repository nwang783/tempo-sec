"""
Playwright-style browser tools for comprehensive web interaction.

This module provides tools that mimic the Playwright MCP server's functionality,
enabling ref-based element targeting via accessibility snapshots.
"""

from collections import deque
from typing import TYPE_CHECKING, Any
import asyncio
import json
import sys

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema

# Default timeout for Playwright operations (30 seconds)
DEFAULT_TIMEOUT_MS = 30000

if TYPE_CHECKING:
    from tempo.infra.container import ContainerManager
    from tempo.infra.browser_state import BrowserStateManager


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
        """
        Initialize the browser session.

        Args:
            container_manager: Optional container for sandboxed execution.
                              If None, runs Playwright locally.
            headless: Whether to run browser in headless mode.
            state_manager: Optional BrowserStateManager for state persistence.
            viewport_width: Browser viewport width in pixels.
            viewport_height: Browser viewport height in pixels.
        """
        self.container = container_manager
        self._headless = headless
        self._state_manager = state_manager
        self._viewport = {"width": viewport_width, "height": viewport_height}
        self._playwright = None
        self._browser = None
        self._page = None
        self._snapshot_refs: dict[str, Any] = {}  # ref -> element info
        # Bounded deques to prevent unbounded memory growth
        self._console_messages: deque[dict] = deque(maxlen=1000)
        self._network_requests: deque[dict] = deque(maxlen=1000)
    
    async def ensure_browser(self) -> None:
        """Ensure browser is initialized with configured headless mode."""
        if self._browser is not None:
            return

        # Always use local Playwright - container mode for browser not yet implemented
        # Container manager can still be used for other sandboxed operations
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)
        self._page = await self._browser.new_page(viewport=self._viewport)

        # Set up console message capture
        self._page.on("console", self._on_console_message)

        # Set up network request capture with response handler
        self._page.on("request", self._on_request)
        self._page.on("response", self._on_response)

        # Auto-clear page data on navigation to keep context relevant
        self._page.on("domcontentloaded", lambda _: self.clear_page_data())
    
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
            "status": None,  # Will be updated by _on_response
        })
    
    def _on_response(self, response) -> None:
        """Capture response status codes and update matching request."""
        url = response.url
        status = response.status
        # Find and update the matching request
        for req in reversed(self._network_requests):
            if req["url"] == url and req["status"] is None:
                req["status"] = status
                break
    
    # Console message level ordering (more severe = higher number)
    _CONSOLE_LEVELS = {
        "debug": 0,
        "log": 1,
        "info": 2,
        "warning": 3,
        "error": 4,
    }
    
    def get_console_messages(self, min_level: str = "info") -> list[dict]:
        """
        Get console messages filtered by minimum level.
        
        Args:
            min_level: Minimum level to return. Each level includes more severe messages.
                       Options: "debug", "log", "info", "warning", "error"
                       
        Returns:
            List of console message dicts with type, text, and location
        """
        min_level_num = self._CONSOLE_LEVELS.get(min_level, 2)
        return [
            msg for msg in self._console_messages
            if self._CONSOLE_LEVELS.get(msg["type"], 2) >= min_level_num
        ]
    
    # Resource types considered static (typically excluded from network analysis)
    _STATIC_RESOURCE_TYPES = {"image", "font", "script", "stylesheet"}
    
    def get_network_requests(self, include_static: bool = False) -> list[dict]:
        """
        Get network requests, optionally filtering out static resources.
        
        Args:
            include_static: If True, include static resources (images, fonts, scripts, stylesheets).
                           Default False excludes them.
                           
        Returns:
            List of request dicts with url, method, resource_type, and status
        """
        if include_static:
            return list(self._network_requests)
        return [
            req for req in self._network_requests
            if req["resource_type"] not in self._STATIC_RESOURCE_TYPES
        ]
    
    def clear_page_data(self) -> None:
        """
        Clear accumulated page data (console messages and network requests).
        
        Called automatically on navigation to keep data relevant to current page.
        """
        self._console_messages.clear()
        self._network_requests.clear()
    
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
                role = element_info.get("role", "")
                name = element_info.get("name", "")
                if role and name:
                    locator = self._page.get_by_role(role, name=name)
                    await locator.scroll_into_view_if_needed()
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


class BrowserNavigateTool(Tool):
    """Navigate to a URL and get a summary of the page content."""
    
    name = "browser_navigate"
    description = "Navigate to a URL and return a YAML summary of the page content including links, forms, and key elements"
    category = ToolCategory.BROWSING
    
    def __init__(self, session: BrowserSession):
        self.session = session
    
    async def execute(
        self,
        url: str,
        purpose: str = "",
    ) -> ToolResult:
        """
        Navigate to the specified URL and extract page summary.
        
        Args:
            url: The URL to navigate to
            purpose: Why this navigation is being performed
            
        Returns:
            ToolResult with navigation status and YAML page summary
        """
        try:
            await self.session.ensure_browser()
            
            # Clear previous page data before navigating
            self.session.clear_page_data()
            
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
            
            # Extract page summary
            page_summary = await self._extract_page_summary()
            
            # Format as YAML-like output
            output = f"""url: {current_url}
title: "{title}"
status: {status}

{page_summary}"""
            
            return ToolResult(
                success=True,
                output=output,
                metadata={"url": current_url, "title": title, "status": status},
            )
            
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
    
    async def _extract_page_summary(self) -> str:
        """Extract a concise YAML summary of page content."""
        summary_parts = []
        
        # Extract links (max 15)
        links = await self.session.page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]'))
                .map(a => ({text: a.innerText.trim().substring(0, 50), href: a.href}))
                .filter(l => l.text && l.href.startsWith('http'))
                .slice(0, 15)
        """)
        
        if links:
            summary_parts.append("links:")
            for link in links:
                text = link['text'].replace('"', '\\"')
                summary_parts.append(f'  - text: "{text}"')
                summary_parts.append(f'    href: "{link["href"]}"')
        
        # Extract forms
        forms = await self.session.page.evaluate("""
            () => Array.from(document.querySelectorAll('form')).map(form => ({
                action: form.action || 'none',
                method: form.method || 'get',
                inputs: Array.from(form.querySelectorAll('input, textarea, select'))
                    .map(el => ({
                        type: el.type || el.tagName.toLowerCase(),
                        name: el.name || el.id || 'unnamed',
                        placeholder: el.placeholder || ''
                    }))
                    .slice(0, 10)
            })).slice(0, 5)
        """)
        
        if forms:
            summary_parts.append("forms:")
            for i, form in enumerate(forms):
                summary_parts.append(f"  - id: form_{i}")
                summary_parts.append(f"    action: \"{form['action']}\"")
                summary_parts.append(f"    method: {form['method']}")
                if form['inputs']:
                    summary_parts.append("    fields:")
                    for inp in form['inputs']:
                        summary_parts.append(f"      - name: {inp['name']}")
                        summary_parts.append(f"        type: {inp['type']}")
        
        # Extract buttons
        buttons = await self.session.page.evaluate("""
            () => Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"], [role="button"]'))
                .map(b => b.innerText?.trim() || b.value || b.getAttribute('aria-label') || 'unnamed')
                .filter(t => t && t.length < 50)
                .slice(0, 10)
        """)
        
        if buttons:
            summary_parts.append("buttons:")
            for btn in buttons:
                summary_parts.append(f'  - "{btn}"')
        
        # Extract headings for content structure
        headings = await self.session.page.evaluate("""
            () => Array.from(document.querySelectorAll('h1, h2, h3'))
                .map(h => ({level: h.tagName, text: h.innerText.trim().substring(0, 80)}))
                .filter(h => h.text)
                .slice(0, 10)
        """)
        
        if headings:
            summary_parts.append("headings:")
            for h in headings:
                text = h['text'].replace('"', '\\"')
                summary_parts.append(f'  - {h["level"].lower()}: "{text}"')
        
        # Extract visible text snippet
        text_content = await self.session.page.evaluate("""
            () => {
                const clone = document.body.cloneNode(true);
                clone.querySelectorAll('script, style, noscript').forEach(el => el.remove());
                return clone.innerText.replace(/\\s+/g, ' ').trim().substring(0, 500);
            }
        """)
        
        if text_content:
            # Truncate and escape for YAML
            text_preview = text_content[:300].replace('"', '\\"').replace('\n', ' ')
            summary_parts.append(f'text_preview: "{text_preview}..."')
        
        return "\n".join(summary_parts)
    
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
                title = await page.title()
                print(f"url: {{page.url}}")
                print(f'title: "{{title}}"')
                print(f"status: {{response.status}}")
                
                # Extract links
                links = await page.evaluate("""
                    () => Array.from(document.querySelectorAll('a[href]'))
                        .map(a => ({{text: a.innerText.trim().substring(0, 50), href: a.href}}))
                        .filter(l => l.text && l.href.startsWith('http'))
                        .slice(0, 15)
                """)
                if links:
                    print("links:")
                    for link in links:
                        print(f'  - text: "{{link["text"]}}"')
                        print(f'    href: "{{link["href"]}}"')
                
                # Extract headings
                headings = await page.evaluate("""
                    () => Array.from(document.querySelectorAll('h1, h2, h3'))
                        .map(h => ({{level: h.tagName, text: h.innerText.trim().substring(0, 80)}}))
                        .filter(h => h.text)
                        .slice(0, 10)
                """)
                if headings:
                    print("headings:")
                    for h in headings:
                        print(f'  - {{h["level"].lower()}}: "{{h["text"]}}"')
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
    """Capture snapshot of the current page for element interaction."""
    
    name = "browser_snapshot"
    description = "Capture a snapshot of the current page with element refs for interaction. Returns interactive elements like links, buttons, inputs, and their refs."
    category = ToolCategory.BROWSING
    
    def __init__(self, session: BrowserSession):
        self.session = session
    
    async def execute(
        self,
        filename: str | None = None,
        purpose: str = "",
    ) -> ToolResult:
        """
        Capture page snapshot with element refs.
        
        Args:
            filename: Optional file to save snapshot to
            purpose: Why this snapshot is being taken
            
        Returns:
            ToolResult with element tree and refs for interaction
        """
        try:
            await self.session.ensure_browser()
            
            if self.session.container is not None:
                return await self._execute_in_container(filename)
            
            # Wait for page to be more stable
            try:
                await self.session.page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass  # Continue even if timeout
            
            refs = {}
            output_lines = []
            
            # Use DOM extraction (accessibility API was removed in Playwright 1.45+)
            output_lines.append("# Page Snapshot (DOM extraction)")
            output_lines.append("")
            
            elements = await self._extract_interactive_elements()
            
            for i, elem in enumerate(elements):
                ref = f"ref_{i}"
                refs[ref] = {
                    "role": elem["type"],
                    "name": elem["text"],
                    "selector": elem.get("selector", ""),
                }
                output_lines.append(f"[{ref}] {elem['type']}: \"{elem['text'][:50]}\"")
                if elem.get("href"):
                    output_lines.append(f"        href: {elem['href']}")
            
            if not refs:
                return ToolResult(
                    success=False,
                    output="",
                    error="No interactive elements found on page. The page may still be loading or is empty.",
                )
            
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
    
    async def _extract_interactive_elements(self) -> list[dict]:
        """Extract interactive elements from DOM with robust selectors."""
        return await self.session.page.evaluate("""
            () => {
                const elements = [];
                
                // Helper function to generate robust selectors
                function generateSelector(el) {
                    // Helper to check uniqueness
                    const isUnique = (sel) => {
                        try {
                            return document.querySelectorAll(sel).length === 1;
                        } catch (e) {
                            return false;
                        }
                    };
                
                    // 1. ID is most reliable
                    if (el.id) {
                        const sel = `#${el.id}`;
                        if (isUnique(sel)) return sel;
                    }
                    
                    // 2. Name attribute (for form elements)
                    if (el.name) {
                        const tag = el.tagName.toLowerCase();
                        const sel = `${tag}[name="${el.name}"]`;
                        if (isUnique(sel)) return sel;
                    }
                    
                    // 3. Unique aria-label
                    const ariaLabel = el.getAttribute('aria-label');
                    if (ariaLabel) {
                        const sel = `[aria-label="${ariaLabel}"]`;
                        if (isUnique(sel)) return sel;
                    }
                    
                    // 4. Test ID (common in React/Vue apps)
                    const testId = el.getAttribute('data-testid') || 
                                   el.getAttribute('data-test-id') ||
                                   el.getAttribute('data-cy');
                    if (testId) {
                        const sel = `[data-testid="${testId}"]`;
                        if (isUnique(sel)) return sel;
                    }
                    
                    // 5. Unique class combinations (fallback)
                    if (el.className && typeof el.className === 'string') {
                        const classes = el.className.split(' ').filter(c => c && !c.match(/^(ng-|_|is-|has-)/));
                        if (classes.length > 0) {
                            const tag = el.tagName.toLowerCase();
                            // Try 1, 2, then 3 classes
                            for (let i = 1; i <= Math.min(3, classes.length); i++) {
                                const sel = `${tag}.${classes.slice(0, i).join('.')}`;
                                if (isUnique(sel)) return sel;
                            }
                        }
                    }
                    
                    // 6. Path-based selector (last resort)
                    // Construct a path of tag:nth-child up to 3 levels
                    let path = [];
                    let current = el;
                    let valid = true;
                    
                    for (let i = 0; i < 3 && current && current.tagName !== 'BODY'; i++) {
                        const parent = current.parentElement;
                        if (!parent) break;
                        
                        const tag = current.tagName.toLowerCase();
                        const siblings = Array.from(parent.children).filter(c => c.tagName === current.tagName);
                        
                        if (siblings.length === 1) {
                            path.unshift(tag);
                        } else {
                            const index = siblings.indexOf(current);
                            path.unshift(`${tag}:nth-of-type(${index + 1})`);
                        }
                        
                        current = parent;
                    }
                    
                    if (path.length > 0) {
                        const sel = path.join(' > ');
                        // Only use if unique (it might not be if we stopped traversing too early)
                        if (isUnique(sel)) return sel;
                    }
                    
                    return null;
                }
                
                // Links
                document.querySelectorAll('a[href]').forEach((el, i) => {
                    if (i < 20) {
                        elements.push({
                            type: 'link',
                            text: el.innerText?.trim() || el.getAttribute('aria-label') || 'unnamed',
                            href: el.href,
                            selector: generateSelector(el) || `a[href="${el.getAttribute('href')}"]`
                        });
                    }
                });
                
                // Buttons
                document.querySelectorAll('button, [role="button"], input[type="submit"], input[type="button"]').forEach((el, i) => {
                    if (i < 15) {
                        elements.push({
                            type: 'button',
                            text: el.innerText?.trim() || el.value || el.getAttribute('aria-label') || 'unnamed',
                            selector: generateSelector(el)
                        });
                    }
                });
                
                // Text inputs
                document.querySelectorAll('input[type="text"], input[type="email"], input[type="password"], input[type="search"], input[type="tel"], input[type="url"], input[type="number"], textarea').forEach((el, i) => {
                    if (i < 15) {
                        // Get associated label text
                        let labelText = el.placeholder || '';
                        if (el.id) {
                            const label = document.querySelector(`label[for="${el.id}"]`);
                            if (label) labelText = label.innerText?.trim() || labelText;
                        }
                        if (!labelText && el.labels && el.labels.length > 0) {
                            labelText = el.labels[0].innerText?.trim() || '';
                        }
                        
                        elements.push({
                            type: 'textbox',
                            text: labelText || el.name || el.id || 'input',
                            selector: generateSelector(el)
                        });
                    }
                });
                
                // Checkboxes and radios
                document.querySelectorAll('input[type="checkbox"], input[type="radio"]').forEach((el, i) => {
                    if (i < 10) {
                        const label = el.labels?.[0]?.innerText || el.name || 'option';
                        elements.push({
                            type: el.type,
                            text: label,
                            selector: generateSelector(el)
                        });
                    }
                });
                
                // Select dropdowns with options
                document.querySelectorAll('select').forEach((el, i) => {
                    if (i < 10) {
                        // Get option details
                        const options = Array.from(el.options).slice(0, 10).map(opt => ({
                            text: opt.text,
                            value: opt.value,
                            selected: opt.selected
                        }));
                        
                        // Get label
                        let labelText = '';
                        if (el.id) {
                            const label = document.querySelector(`label[for="${el.id}"]`);
                            if (label) labelText = label.innerText?.trim() || '';
                        }
                        
                        const optionsSummary = options.map(o => o.text).join(', ');
                        const currentSelection = options.find(o => o.selected)?.text || '';
                        
                        elements.push({
                            type: 'combobox',
                            text: labelText || el.name || el.id || 'dropdown',
                            selector: generateSelector(el),
                            options: optionsSummary,
                            selectedOption: currentSelection
                        });
                    }
                });
                
                return elements.filter(e => e.text && e.text.length < 100);
            }
        """)
    
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
            selector = element_info.get("selector", "")
            
            # Locate element
            locator = None
            if selector:
                # Prioritize explicit selector if available
                locator = self.session.page.locator(selector)
            elif role and name:
                locator = self.session.page.get_by_role(role, name=name)
            elif name:
                locator = self.session.page.get_by_text(name)
            
            if locator is None:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Could not locate element with ref {ref}",
                )
            
            # Build click options with timeout
            click_kwargs = {"button": button, "timeout": DEFAULT_TIMEOUT_MS}
            if modifiers:
                click_kwargs["modifiers"] = modifiers
            
            # Perform click
            if doubleClick:
                await locator.dclick(**click_kwargs)
                action = "Double-clicked"
            else:
                await locator.click(**click_kwargs)
                action = "Clicked"
            
            # Verify click action
            verification = await self._verify_click(locator)
            
            return ToolResult(
                success=True,
                output=f"{action} on {element} (ref: {ref}). {verification}",
                metadata={"ref": ref, "element": element, "action": action, "verification": verification},
            )
            
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
    
    async def _verify_click(self, locator) -> str:
        """Verify click had expected effect."""
        try:
            # Wait briefly for any state changes
            await self.session.page.wait_for_timeout(100)
            
            # Check if element is still visible (button might hide after click)
            try:
                is_visible = await locator.is_visible(timeout=500)
                if not is_visible:
                    return "Element no longer visible (may have triggered navigation or modal)"
            except Exception:
                return "Element state unknown after click"
            
            # Check if element has focus (for form elements)
            try:
                is_focused = await locator.evaluate("el => el === document.activeElement")
                if is_focused:
                    return "Element now has focus"
            except Exception:
                pass
            
            return "Click completed, element still visible"
            
        except Exception as e:
            return f"Verification inconclusive: {e}"
    
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
            selector = element_info.get("selector", "")
            
            # Locate element
            locator = None
            if selector:
                # Prioritize explicit selector if available (more reliable than accessible name)
                locator = self.session.page.locator(selector)
            elif role in ("textbox", "searchbox", "combobox"):
                locator = self.session.page.get_by_role(role, name=name) if name else self.session.page.get_by_role(role)
            elif name:
                locator = self.session.page.get_by_label(name)
            
            if locator is None:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Could not locate input element with ref {ref}",
                )
            
            # Clear existing content and type (with timeouts)
            await locator.clear(timeout=DEFAULT_TIMEOUT_MS)
            
            if slowly:
                await locator.type(text, delay=50, timeout=DEFAULT_TIMEOUT_MS)
            else:
                await locator.fill(text, timeout=DEFAULT_TIMEOUT_MS)
            
            # Submit if requested
            if submit:
                await locator.press("Enter", timeout=DEFAULT_TIMEOUT_MS)
            
            # Verify input value matches what we typed
            verification = ""
            try:
                actual_value = await locator.input_value(timeout=1000)
                if actual_value == text:
                    display_text = f"'{text[:20]}...'" if len(text) > 20 else f"'{text}'"
                    verification = f"Verified: input contains {display_text}"
                elif text in actual_value or actual_value in text:
                    verification = f"Partial match: input contains '{actual_value[:30]}'"
                else:
                    verification = f"Warning: input has '{actual_value[:30]}' instead of expected text"
            except Exception:
                verification = "Could not verify input value"
            
            result_text = f"Typed '{text}' into {element}. {verification}"
            if submit:
                result_text = f"Typed '{text}' into {element} and submitted. {verification}"
            
            return ToolResult(
                success=True,
                output=result_text,
                metadata={"ref": ref, "text": text, "submitted": submit, "verification": verification},
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
                selector = element_info.get("selector", "")
                
                try:
                    # Locate and fill
                    locator = None
                    if selector:
                        # Prioritize explicit selector if available
                        locator = self.session.page.locator(selector)
                    elif role in ("textbox", "searchbox", "combobox"):
                        locator = self.session.page.get_by_role(role, name=name) if name else self.session.page.get_by_role(role)
                    elif name:
                        locator = self.session.page.get_by_label(name)
                    
                    if locator:
                        await locator.fill(value, timeout=DEFAULT_TIMEOUT_MS)
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


class BrowserSelectTool(Tool):
    """Select an option from a dropdown element."""
    
    name = "browser_select"
    description = (
        "Select an option from a dropdown (<select> element). "
        "Use after browser_snapshot to get the element ref. "
        "Can select by visible text (default), value attribute, or index."
    )
    category = ToolCategory.BROWSING
    
    def __init__(self, session: BrowserSession):
        self.session = session
    
    async def execute(
        self,
        element: str,
        ref: str,
        option: str,
        by: str = "text",
        purpose: str = "",
    ) -> ToolResult:
        """
        Select a dropdown option.
        
        Args:
            element: Human-readable description of the dropdown
            ref: Element reference from snapshot
            option: The option to select (text, value, or index)
            by: Selection method - "text", "value", or "index"
            purpose: Why this selection is being made
            
        Returns:
            ToolResult with selection status
        """
        try:
            await self.session.ensure_browser()
            
            element_info = self.session.get_element_by_ref(ref)
            if element_info is None:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Ref not found: {ref}. Run browser_snapshot first.",
                )
            
            selector = element_info.get("selector", "")
            role = element_info.get("role", "")
            
            # Verify element is a dropdown
            if role != "combobox" and not selector:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Element {ref} does not appear to be a dropdown (role: {role})",
                )
            
            # Locate the select element
            if selector:
                locator = self.session.page.locator(selector)
            else:
                # Fallback to role-based lookup
                name = element_info.get("name", "")
                if name:
                    locator = self.session.page.get_by_role("combobox", name=name)
                else:
                    return ToolResult(
                        success=False,
                        output="",
                        error="No selector available for dropdown",
                    )
            
            # Perform selection based on method
            if by == "text":
                await locator.select_option(label=option, timeout=DEFAULT_TIMEOUT_MS)
            elif by == "value":
                await locator.select_option(value=option, timeout=DEFAULT_TIMEOUT_MS)
            elif by == "index":
                await locator.select_option(index=int(option), timeout=DEFAULT_TIMEOUT_MS)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Invalid selection method: {by}. Use 'text', 'value', or 'index'",
                )
            
            # Verify selection by getting current value
            try:
                selected_value = await locator.input_value(timeout=1000)
                verification = f"Current value: {selected_value}"
            except Exception:
                verification = "Selection completed"
            
            return ToolResult(
                success=True,
                output=f"Selected '{option}' in {element} (ref: {ref}). {verification}",
                metadata={"ref": ref, "option": option, "by": by},
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
                        "description": "Human-readable dropdown description",
                    },
                    "ref": {
                        "type": "string",
                        "description": "Element reference from browser_snapshot",
                    },
                    "option": {
                        "type": "string",
                        "description": "Option to select (text, value, or index depending on 'by')",
                    },
                    "by": {
                        "type": "string",
                        "enum": ["text", "value", "index"],
                        "description": "How to select: by visible text (default), value attribute, or index",
                        "default": "text",
                    },
                },
                "required": ["element", "ref", "option"],
            },
        )


class BrowserScreenshotTool(Tool):
    """Capture a screenshot of the current page."""

    name = "browser_screenshot"
    description = (
        "Capture a screenshot of the current page. "
        "Returns image path and optionally base64 data."
    )
    category = ToolCategory.BROWSING

    def __init__(self, session: BrowserSession):
        self.session = session

    async def execute(
        self,
        filename: str | None = None,
        full_page: bool = False,
        return_base64: bool = True,
        purpose: str = "",
        **kwargs,
    ) -> ToolResult:
        """Capture screenshot."""
        try:
            # Type coercion for LLM inputs (may come as strings)
            full_page = full_page if isinstance(full_page, bool) else str(full_page).lower() == "true"
            return_base64 = return_base64 if isinstance(return_base64, bool) else str(return_base64).lower() == "true"
            
            await self.session.ensure_browser()

            # Generate filename if not provided
            if not filename:
                import uuid
                filename = f"/tmp/screenshot_{uuid.uuid4().hex[:8]}.png"

            screenshot_bytes = await self.session.screenshot(
                path=filename, full_page=full_page
            )

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
                        "description": (
                            "Include base64-encoded image data in metadata "
                            "(for vision models). Default: true"
                        ),
                        "default": True,
                    },
                },
                "required": [],
            },
        )


class BrowserClickCoordsTool(Tool):
    """Click at specific x,y coordinates."""

    name = "browser_click_coords"
    description = (
        "Click at specific x,y coordinates on the page. "
        "Useful when element refs don't work."
    )
    category = ToolCategory.BROWSING

    def __init__(self, session: BrowserSession):
        self.session = session

    async def execute(
        self,
        x: int,
        y: int,
        button: str = "left",
        purpose: str = "",
        **kwargs,
    ) -> ToolResult:
        """Click at coordinates."""
        try:
            # Type coercion for LLM inputs (may come as strings)
            x = int(x)
            y = int(y)
            
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


class BrowserTypeCoordsTool(Tool):
    """Type text at specific x,y coordinates."""

    name = "browser_type_coords"
    description = (
        "Click at x,y coordinates to focus an input field, then type text. "
        "Use after taking a screenshot to identify input field locations. "
        "Optionally clears existing content and/or submits with Enter."
    )
    category = ToolCategory.BROWSING

    def __init__(self, session: BrowserSession):
        self.session = session

    async def execute(
        self,
        x: int,
        y: int,
        text: str,
        clear_first: bool = True,
        submit: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Click at coordinates, then type text."""
        try:
            # Type coercion for LLM inputs (may come as strings)
            x = int(x)
            y = int(y)
            clear_first = clear_first if isinstance(clear_first, bool) else str(clear_first).lower() == "true"
            submit = submit if isinstance(submit, bool) else str(submit).lower() == "true"
            
            await self.session.ensure_browser()

            # Click to focus the input field
            await self.session.click_coordinates(x, y)

            # Clear existing content if requested
            if clear_first:
                # Use platform-appropriate select-all
                modifier = "Meta" if sys.platform == "darwin" else "Control"
                await self.session.page.keyboard.press(f"{modifier}+a")
                await self.session.page.keyboard.press("Backspace")

            # Type the text
            await self.session.page.keyboard.type(text, delay=20)

            # Submit if requested
            if submit:
                await self.session.page.keyboard.press("Enter")

            result_text = f"Typed '{text}' at coordinates ({x}, {y})"
            if clear_first:
                result_text += " (cleared first)"
            if submit:
                result_text += " and submitted"

            return ToolResult(
                success=True,
                output=result_text,
                metadata={"x": x, "y": y, "text": text, "submitted": submit},
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
                        "description": "X coordinate of the input field (pixels from left)",
                    },
                    "y": {
                        "type": "integer",
                        "description": "Y coordinate of the input field (pixels from top)",
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to type into the field",
                    },
                    "clear_first": {
                        "type": "boolean",
                        "description": "Clear existing content before typing (default: true)",
                        "default": True,
                    },
                    "submit": {
                        "type": "boolean",
                        "description": "Press Enter after typing to submit",
                        "default": False,
                    },
                },
                "required": ["x", "y", "text"],
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
        **kwargs,
    ) -> ToolResult:
        """Scroll the page."""
        try:
            # Type coercion for LLM inputs (may come as strings)
            amount = int(amount)
            
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
        **kwargs,
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
                        "description": (
                            "CSS selector to wait for "
                            "(if omitted, just waits for timeout)"
                        ),
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


class BrowserVisionSnapshotTool(Tool):
    """
    Capture a screenshot and analyze it with a vision model.
    
    Returns element descriptions WITH COORDINATES for use with browser_click_coords.
    The screenshot is NOT added to main context - used in a separate LLM call.
    """
    
    name = "browser_vision_snapshot"
    description = (
        "Take a screenshot and analyze it with AI vision. "
        "Returns descriptions of visible elements WITH THEIR COORDINATES. "
        "Use the returned coordinates with browser_click_coords to click on elements. "
        "Useful when DOM snapshot doesn't capture what you need (images, canvas, complex UIs)."
    )
    category = ToolCategory.BROWSING
    
    # Hardcoded vision model (same as browser agent)
    VISION_MODEL = "openai/gpt-5-mini"
    
    # Vision prompt template for coordinate extraction
    VISION_PROMPT = """Analyze this webpage screenshot.
Identify all interactive elements (buttons, links, form fields, dropdowns, icons, etc).

For EACH interactive element, provide:
- What it is and what it does
- Center coordinates (x, y) for clicking
- Expected action when clicked

Viewport size: {width}x{height} pixels. All coordinates must be within this range.
{user_query}

Format your response as a list:
ELEMENT: [description] at ({x}, {y}) - [expected action]

Example:
ELEMENT: Blue "Sign Up" button at (640, 450) - submits registration form
ELEMENT: Email input field at (400, 200) - click to enter email address
ELEMENT: Menu hamburger icon at (50, 30) - opens navigation menu
"""

    def __init__(self, session: BrowserSession):
        self.session = session
        self._llm_client = None
    
    async def execute(
        self,
        query: str = "",
        full_page: bool = False,
        purpose: str = "",
        **kwargs,
    ) -> ToolResult:
        """
        Capture screenshot and analyze with vision model.
        
        Args:
            query: Optional specific question to add to the analysis
            full_page: Capture full scrollable page vs viewport only
            
        Returns:
            Text analysis with element descriptions and coordinates
        """
        import base64
        
        try:
            await self.session.ensure_browser()
            
            # Get viewport dimensions
            viewport = self.session._viewport
            width = viewport.get("width", 1280)
            height = viewport.get("height", 720)
            
            # Capture screenshot as bytes
            screenshot_bytes = await self.session.screenshot(full_page=full_page)
            
            # Encode to base64
            b64_screenshot = base64.b64encode(screenshot_bytes).decode("utf-8")
            
            # Build vision prompt
            user_query_section = f"\nAdditional question: {query}" if query else ""
            prompt_text = self.VISION_PROMPT.format(
                width=width,
                height=height,
                user_query=user_query_section,
            )
            
            # Build multimodal message for vision model
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{b64_screenshot}"
                            }
                        }
                    ]
                }
            ]
            
            # Create LLM client for vision call (lazy init)
            if self._llm_client is None:
                from tempo.infra.llm import LiteLLMClient
                self._llm_client = LiteLLMClient(model=self.VISION_MODEL)
            
            # Make vision API call
            response = await self._llm_client.complete(messages=messages)
            
            if not response.content:
                return ToolResult(
                    success=False,
                    output="",
                    error="Vision model returned empty response",
                )
            
            # Format output
            output = f"""## Vision Analysis (viewport: {width}x{height})

{response.content}

---
**Usage**: Use `browser_click_coords(x=X, y=Y)` to click on any element listed above.
"""
            
            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "viewport_width": width,
                    "viewport_height": height,
                    "full_page": full_page,
                    "model": self.VISION_MODEL,
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
                    "query": {
                        "type": "string",
                        "description": (
                            "Optional specific question to ask about the screenshot. "
                            "Default behavior lists all interactive elements with coordinates."
                        ),
                        "default": "",
                    },
                    "full_page": {
                        "type": "boolean",
                        "description": "Capture full scrollable page instead of just viewport",
                        "default": False,
                    },
                },
                "required": [],
            },
        )


class BrowserConsoleTool(Tool):
    """Get console messages from the current page."""
    
    name = "browser_console_messages"
    description = (
        "Returns all console messages (log, info, warn, error) captured since page load. "
        "Useful for debugging JavaScript errors, identifying security issues, or understanding page behavior."
    )
    category = ToolCategory.BROWSING
    
    def __init__(self, session: BrowserSession):
        self.session = session
    
    async def execute(
        self,
        level: str = "info",
        purpose: str = "",
        **kwargs,
    ) -> ToolResult:
        """
        Get console messages filtered by level.
        
        Args:
            level: Minimum level to return - "debug", "log", "info", "warning", "error".
                   Defaults to "info". Each level includes more severe messages.
            purpose: Why console messages are being retrieved
            
        Returns:
            ToolResult with list of console messages
        """
        try:
            await self.session.ensure_browser()
            
            # Validate level
            valid_levels = ["debug", "log", "info", "warning", "error"]
            if level not in valid_levels:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Invalid level '{level}'. Must be one of: {', '.join(valid_levels)}",
                )
            
            messages = self.session.get_console_messages(min_level=level)
            
            if not messages:
                return ToolResult(
                    success=True,
                    output=f"No console messages at level '{level}' or higher.",
                    metadata={"count": 0, "level": level},
                )
            
            # Format output
            output_lines = [f"## Console Messages (level >= {level})"]
            output_lines.append(f"Total: {len(messages)} message(s)\n")
            
            for msg in messages:
                msg_type = msg["type"].upper()
                text = msg["text"]
                location = msg.get("location", "")
                
                if location:
                    output_lines.append(f"[{msg_type}] {text}")
                    output_lines.append(f"       at {location}")
                else:
                    output_lines.append(f"[{msg_type}] {text}")
            
            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={"count": len(messages), "level": level},
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
                    "level": {
                        "type": "string",
                        "description": (
                            "Minimum level to return. Each level includes more severe messages. "
                            "Options: debug, log, info, warning, error"
                        ),
                        "enum": ["debug", "log", "info", "warning", "error"],
                        "default": "info",
                    },
                },
                "required": [],
            },
        )


class BrowserNetworkTool(Tool):
    """List network requests made by the page."""
    
    name = "browser_network_requests"
    description = (
        "Returns all network requests since loading the page. "
        "Useful for identifying API endpoints, analyzing request patterns, and finding potential security issues."
    )
    category = ToolCategory.BROWSING
    
    def __init__(self, session: BrowserSession):
        self.session = session
    
    async def execute(
        self,
        includeStatic: bool = False,
        purpose: str = "",
        **kwargs,
    ) -> ToolResult:
        """
        Get network requests, optionally including static resources.
        
        Args:
            includeStatic: Include static resources (images, fonts, scripts, stylesheets).
                          Defaults to false.
            purpose: Why network requests are being retrieved
            
        Returns:
            ToolResult with list of network requests
        """
        try:
            await self.session.ensure_browser()
            
            requests = self.session.get_network_requests(include_static=includeStatic)
            
            if not requests:
                filter_note = " (excluding static resources)" if not includeStatic else ""
                return ToolResult(
                    success=True,
                    output=f"No network requests captured{filter_note}.",
                    metadata={"count": 0, "include_static": includeStatic},
                )
            
            # Format output
            filter_note = "all requests" if includeStatic else "excluding static (images, fonts, scripts, stylesheets)"
            output_lines = [f"## Network Requests ({filter_note})"]
            output_lines.append(f"Total: {len(requests)} request(s)\n")
            
            for req in requests:
                method = req["method"]
                url = req["url"]
                resource_type = req["resource_type"]
                status = req.get("status")
                
                status_str = f" -> {status}" if status else " -> (pending)"
                output_lines.append(f"[{method}] {url}")
                output_lines.append(f"       type: {resource_type}{status_str}")
            
            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={"count": len(requests), "include_static": includeStatic},
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
                    "includeStatic": {
                        "type": "boolean",
                        "description": (
                            "Include static resources (images, fonts, scripts, stylesheets). "
                            "Defaults to false to show only dynamic requests."
                        ),
                        "default": False,
                    },
                },
                "required": [],
            },
        )


class BrowserEvaluateTool(Tool):
    """Evaluate JavaScript in the browser.
    
    WARNING: This is a write tool that can execute arbitrary JavaScript.
    Intentional for security testing (XSS detection, DOM manipulation, etc.)
    """
    
    name = "browser_evaluate"
    description = (
        "Evaluate JavaScript expression on the page and return the result. "
        "Useful for XSS testing, DOM inspection, extracting data, or manipulating page state. "
        "Expression should be a function body like '() => { return document.title; }'"
    )
    category = ToolCategory.BROWSING
    
    def __init__(self, session: BrowserSession):
        self.session = session
    
    async def execute(
        self,
        expression: str,
        purpose: str = "",
        **kwargs,
    ) -> ToolResult:
        """
        Evaluate JavaScript expression on the page.
        
        Args:
            expression: JavaScript code to evaluate. Should be a function body
                       like '() => { return document.title; }'
            purpose: Why this JavaScript is being evaluated
            
        Returns:
            ToolResult with the serialized result
        """
        try:
            await self.session.ensure_browser()
            
            if not expression or not expression.strip():
                return ToolResult(
                    success=False,
                    output="",
                    error="Expression is required",
                )
            
            # Execute JavaScript
            result = await self.session.page.evaluate(expression)
            
            # Serialize result for output
            if result is None:
                output = "Result: null"
            elif isinstance(result, (dict, list)):
                output = f"Result:\n{json.dumps(result, indent=2, default=str)}"
            else:
                output = f"Result: {result}"
            
            return ToolResult(
                success=True,
                output=output,
                metadata={"expression": expression[:100]},
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"JavaScript evaluation failed: {str(e)}",
            )
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": (
                            "JavaScript code to evaluate. Should be a function body "
                            "like '() => { return document.title; }' or '() => document.cookie'"
                        ),
                    },
                },
                "required": ["expression"],
            },
        )
