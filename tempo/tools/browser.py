"""
Browser tool for web navigation and content extraction.
"""

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema


class BrowserTool(Tool):
    """Browse web pages and extract content."""
    
    name = "browser"
    description = "Navigate to a URL and extract page content"
    category = ToolCategory.BROWSING
    
    def __init__(self):
        """Initialize the browser tool."""
        self._browser = None
        self._page = None
    
    async def _ensure_browser(self):
        """Ensure browser is initialized."""
        if self._browser is None:
            from playwright.async_api import async_playwright
            
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            self._page = await self._browser.new_page()
    
    async def _cleanup(self):
        """Clean up browser resources."""
        if self._browser:
            await self._browser.close()
            await self._playwright.stop()
            self._browser = None
            self._page = None
    
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
