"""
Browser tool for web navigation and content extraction.
"""

from typing import TYPE_CHECKING

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema

if TYPE_CHECKING:
    from tempo.infra.container import ContainerManager


class BrowserTool(Tool):
    """Browse web pages and extract content."""
    
    name = "browser"
    description = "Navigate to a URL and extract page content"
    category = ToolCategory.BROWSING
    
    def __init__(self, container_manager: "ContainerManager | None" = None):
        """
        Initialize the browser tool.
        
        Args:
            container_manager: Container for sandboxed execution.
                               If None, uses local playwright (for testing only).
        """
        self.container = container_manager
        self._browser = None
        self._page = None
        self._playwright = None
    
    async def _ensure_browser(self):
        """Ensure browser is initialized."""
        if self._browser is not None:
            return
            
        if self.container is not None:
            # Browser runs in container - we'll use curl/wget for basic fetching
            # and execute playwright commands via container exec
            return  # Container mode uses exec-based approach
        
        # Local mode - use playwright directly
        from playwright.async_api import async_playwright
        
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._page = await self._browser.new_page()
    
    async def _cleanup(self):
        """Clean up browser resources."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._page = None
        self._playwright = None
    
    async def execute(
        self,
        url: str,
        extract_links: bool = False,
        screenshot: bool = False,
        wait_for: str | None = None,
        purpose: str = "",
    ) -> ToolResult:
        """
        Browse to a URL and extract content.
        
        Args:
            url: The URL to navigate to
            extract_links: Whether to extract all links from the page
            screenshot: Whether to capture a screenshot
            wait_for: CSS selector to wait for before extracting
            purpose: Why this tool is being called
            
        Returns:
            ToolResult with page content
        """
        try:
            await self._ensure_browser()
            
            # Container mode - execute playwright script in container
            if self.container is not None:
                return await self._execute_in_container(url, extract_links, screenshot)
            
            # Local mode - use direct playwright
            # Navigate to URL
            response = await self._page.goto(url, wait_until="domcontentloaded")
            
            if response is None or response.status >= 400:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Failed to load page: HTTP {response.status if response else 'unknown'}",
                )
            
            # Wait for selector if specified
            if wait_for:
                try:
                    await self._page.wait_for_selector(wait_for, timeout=10000)
                except Exception:
                    pass  # Continue even if selector not found
            
            # Extract page content
            title = await self._page.title()
            
            # Get visible text content
            text_content = await self._page.evaluate("""
                () => {
                    // Remove script and style elements
                    const scripts = document.querySelectorAll('script, style, noscript');
                    scripts.forEach(el => el.remove());
                    return document.body.innerText;
                }
            """)
            
            result_parts = [
                f"Title: {title}",
                f"URL: {url}",
                "",
                "Content:",
                text_content[:5000] if len(text_content) > 5000 else text_content,
            ]
            
            # Extract links if requested
            if extract_links:
                links = await self._page.evaluate("""
                    () => Array.from(document.querySelectorAll('a[href]'))
                        .map(a => ({text: a.innerText.trim(), href: a.href}))
                        .filter(l => l.text && l.href.startsWith('http'))
                        .slice(0, 50)
                """)
                result_parts.append("")
                result_parts.append(f"Links ({len(links)}):")
                for link in links[:20]:  # Limit to 20 for output
                    result_parts.append(f"  - [{link['text'][:50]}]({link['href']})")
            
            # Screenshot if requested
            screenshot_path = None
            if screenshot:
                import tempfile
                screenshot_path = tempfile.mktemp(suffix=".png")
                await self._page.screenshot(path=screenshot_path)
                result_parts.append(f"\nScreenshot saved to: {screenshot_path}")
            
            return ToolResult(
                success=True,
                output="\n".join(result_parts),
                metadata={
                    "url": url,
                    "title": title,
                    "screenshot_path": screenshot_path,
                },
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )
    
    async def _execute_in_container(
        self,
        url: str,
        extract_links: bool = False,
        screenshot: bool = False,
    ) -> ToolResult:
        """Execute browser commands in the container using playwright."""
        # Build the optional links extraction code
        links_code = ""
        if extract_links:
            links_code = '''
            links = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href]'))
                    .map(a => ({text: a.innerText.trim(), href: a.href}))
                    .filter(l => l.text && l.href.startswith('http'))
                    .slice(0, 20)
            """)
            print()
            print(f"Links ({len(links)}):")
            for link in links:
                print(f"  - [{link['text'][:50]}]({link['href']})")
'''
        
        # Python script to run inside container
        script = f'''
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            response = await page.goto("{url}", wait_until="domcontentloaded")
            
            if response is None or response.status >= 400:
                status = response.status if response else 'unknown'
                print(f"ERROR: HTTP {{status}}")
                return
            
            title = await page.title()
            content = await page.evaluate("""
                () => {{
                    const scripts = document.querySelectorAll('script, style, noscript');
                    scripts.forEach(el => el.remove());
                    return document.body.innerText;
                }}
            """)
            
            print(f"Title: {{title}}")
            print(f"URL: {url}")
            print()
            print("Content:")
            print(content[:5000] if len(content) > 5000 else content)
{links_code}
        finally:
            await browser.close()

asyncio.run(main())
'''
        
        exit_code, stdout, stderr = await self.container.exec(
            f"python3 -c '{script}'",
            timeout=60,
        )
        
        if exit_code != 0 or stdout.startswith("ERROR:"):
            return ToolResult(
                success=False,
                output="",
                error=stderr or stdout,
            )
        
        return ToolResult(
            success=True,
            output=stdout,
            metadata={"url": url},
        )
    
    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
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
                    "extract_links": {
                        "type": "boolean",
                        "description": "Extract all links from the page",
                        "default": False,
                    },
                    "screenshot": {
                        "type": "boolean",
                        "description": "Capture a screenshot",
                        "default": False,
                    },
                    "wait_for": {
                        "type": "string",
                        "description": "CSS selector to wait for",
                    },
                },
                "required": ["url"],
            },
        )
    
    def default_summarizer(self, result: ToolResult) -> str:
        """Summarize browser output."""
        if not result.success:
            return f"Failed to browse: {result.error}"
        
        # Extract just title and key info
        lines = result.output.split("\n")
        summary_parts = []
        
        for line in lines[:3]:  # Title, URL
            if line.strip():
                summary_parts.append(line)
        
        # Truncate content
        content_start = result.output.find("Content:")
        if content_start >= 0:
            content = result.output[content_start:content_start + 500]
            summary_parts.append(content + "...")
        
        return "\n".join(summary_parts)
