"""
Adapter to integrate tempo-sec custom tools with browser-use library.

Wraps tempo-sec tools (findings, shell, filesystem, email) into browser-use's
Tools API using the @tools.action decorator pattern.
"""

import asyncio
from typing import TYPE_CHECKING, Coroutine, TypeVar

from browser_use.tools.service import Tools

T = TypeVar("T")


def _run_async(coro: Coroutine[None, None, T]) -> T:
    """
    Run an async coroutine from sync context, handling nested event loops.

    If already inside an event loop (common with browser-use), schedules the
    coroutine on the running loop. Otherwise, uses asyncio.run().
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop - safe to use asyncio.run()
        return asyncio.run(coro)

    # Already in an event loop - run in a thread with its own loop
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()

if TYPE_CHECKING:
    from tempo.infra.container import ContainerManager
    from tempo.infra.protocols import FindingsUpdater
    from tempo.tools.network_capture import NetworkRequestCapture


class BrowserUseToolsAdapter:
    """Adapter to register tempo-sec tools with browser-use."""

    def __init__(
        self,
        container_manager: "ContainerManager | None" = None,
        findings_updater: "FindingsUpdater | None" = None,
        imap_config: dict | None = None,
        agent_email: str | None = None,
        tools_instance: Tools | None = None,
        network_capture: "NetworkRequestCapture | None" = None,
    ):
        """
        Initialize the tools adapter.

        Args:
            container_manager: Container for sandboxed shell execution
            findings_updater: Findings document manager
            imap_config: IMAP configuration for email tools
            agent_email: Email address for verification flows
            tools_instance: Optional shared Tools instance (if None, creates new)
            network_capture: Optional NetworkRequestCapture for network requests
        """
        self.container = container_manager
        self.findings = findings_updater
        self.imap_config = imap_config or {}
        self.agent_email = agent_email
        self.tools = tools_instance if tools_instance is not None else Tools()
        self.network_capture = network_capture

        # Register all custom tools
        self._register_findings_tools()
        self._register_shell_tools()
        self._register_filesystem_tools()
        self._register_email_tools()
        self._register_network_tools()

    def _register_findings_tools(self):
        """Register findings management tools."""
        if not self.findings:
            return

        # Import tools here to avoid circular dependencies
        from tempo.tools.findings_tools import (
            AddAttackSurfaceTool,
            AddFindingTool,
            MarkSurfaceTestedTool,
            ReadFindingsTool,
        )

        # Create tool instances
        read_findings_tool = ReadFindingsTool(self.findings)
        add_finding_tool = AddFindingTool(self.findings)
        add_surface_tool = AddAttackSurfaceTool(self.findings)
        mark_tested_tool = MarkSurfaceTestedTool(self.findings)

        @self.tools.action("Read current findings document summary")
        def read_findings(
            include_findings: bool = False,
            include_surfaces: bool = False,
        ) -> str:
            """
            Read the findings document to see what's been discovered.

            Args:
                include_findings: Include full list of findings
                include_surfaces: Include full list of attack surfaces

            Returns:
                Findings summary as formatted string
            """
            result = _run_async(
                read_findings_tool.execute(
                    include_findings=include_findings,
                    include_surfaces=include_surfaces,
                )
            )
            if not result.success:
                return f"Error: {result.error}"
            return result.output

        @self.tools.action("Add a new security finding to the findings document")
        def add_finding(
            title: str,
            severity: str,
            status: str,
            description: str,
            evidence: str,
            discovered_by: str,
            attack_surface_id: str = "",
            remediation: str = "",
        ) -> str:
            """
            Add a security finding.

            Args:
                title: Short descriptive title
                severity: Severity level (critical, high, medium, low, info)
                status: Confirmation status (suspected, confirmed, false_positive, needs_manual)
                description: Detailed description
                evidence: Supporting evidence
                discovered_by: Agent or tool that discovered it
                attack_surface_id: Optional ID of related attack surface
                remediation: Optional remediation guidance

            Returns:
                Success message with finding ID
            """
            # Convert empty string to None for optional params
            surface_id = attack_surface_id if attack_surface_id else None

            result = _run_async(
                add_finding_tool.execute(
                    title=title,
                    severity=severity,
                    status=status,
                    description=description,
                    evidence=evidence,
                    discovered_by=discovered_by,
                    attack_surface_id=surface_id,
                    remediation=remediation,
                )
            )
            if not result.success:
                return f"Error: {result.error}"
            return result.output

        @self.tools.action("Add a new attack surface to track")
        def add_attack_surface(
            surface_type: str,
            url: str,
            description: str,
            discovered_by: str,
            priority: str = "medium",
        ) -> str:
            """
            Add an attack surface.

            Args:
                surface_type: Type of surface (e.g., web, api, login, form)
                url: URL or endpoint
                description: Description of the surface
                discovered_by: Agent or tool that discovered it
                priority: Priority level (critical, high, medium, low)

            Returns:
                Success message with surface ID
            """
            result = _run_async(
                add_surface_tool.execute(
                    surface_type=surface_type,
                    url=url,
                    description=description,
                    discovered_by=discovered_by,
                    priority=priority,
                )
            )
            if not result.success:
                return f"Error: {result.error}"
            return result.output

        @self.tools.action("Mark an attack surface as tested")
        def mark_surface_tested(surface_id: str) -> str:
            """
            Mark a surface as tested.

            Args:
                surface_id: ID of the surface to mark as tested

            Returns:
                Success confirmation
            """
            result = _run_async(mark_tested_tool.execute(surface_id=surface_id))
            if not result.success:
                return f"Error: {result.error}"
            return result.output

    def _register_shell_tools(self):
        """Register shell execution tool."""
        from tempo.tools.shell import ShellTool

        shell_tool = ShellTool(self.container)

        @self.tools.action("Execute a shell command in the sandbox environment")
        def shell(
            command: str,
            timeout: int = 60,
            working_dir: str = "/workspace",
        ) -> str:
            """
            Execute a shell command.

            Args:
                command: The command to execute
                timeout: Maximum execution time in seconds
                working_dir: Working directory for the command

            Returns:
                Command output
            """
            result = _run_async(
                shell_tool.execute(
                    command=command,
                    timeout=timeout,
                    working_dir=working_dir,
                )
            )
            if not result.success:
                return f"Error (exit {result.metadata.get('exit_code', '?')}): {result.error}"
            return result.output

    def _register_filesystem_tools(self):
        """Register file operations tools.
        
        NOTE: Removed - browser-use already provides built-in file system tools:
        - write_file: Write to files in browser-use's temp filesystem
        - read_file: Read files from browser-use's temp filesystem  
        - replace_file: Replace strings in files
        
        The tempo-sec file_read/file_write tools were duplicates that operated
        on the Docker container filesystem, but the browser agent should use
        browser-use's built-in tools for consistency with its todo.md and
        other file-based workflows.
        
        For Docker container file operations, the shell tool can be used:
        - shell(command="cat /path/to/file") for reading
        - shell(command="echo 'content' > /path/to/file") for writing
        """
        pass  # No custom filesystem tools - use browser-use built-ins

    def _register_email_tools(self):
        """Register email verification tools."""
        if not self.imap_config:
            return

        from tempo.tools.email_tools import CheckInboxTool, GetEmailContentTool

        check_inbox_tool = CheckInboxTool(
            imap_host=self.imap_config.get("host", "imap.gmail.com"),
            imap_port=self.imap_config.get("port", 993),
            imap_password=self.imap_config.get("password"),
            agent_email=self.agent_email,
        )

        get_email_tool = GetEmailContentTool(
            imap_host=self.imap_config.get("host", "imap.gmail.com"),
            imap_port=self.imap_config.get("port", 993),
            imap_password=self.imap_config.get("password"),
            agent_email=self.agent_email,
        )

        @self.tools.action("Check email inbox for verification emails")
        def check_inbox(
            subject_pattern: str = "",
            from_address: str = "",
            timeout_seconds: int = 60,
        ) -> str:
            """
            Check inbox for emails matching criteria.

            Args:
                subject_pattern: Regex pattern to match in subject
                from_address: Sender address to filter by
                timeout_seconds: Max time to wait for matching email

            Returns:
                List of matching emails with IDs
            """
            result = _run_async(
                check_inbox_tool.execute(
                    subject_pattern=subject_pattern,
                    from_address=from_address,
                    timeout_seconds=timeout_seconds,
                )
            )
            if not result.success:
                return f"Error: {result.error}"
            return result.output

        @self.tools.action("Get email content and extract verification links or codes")
        def get_email_content(message_id: str) -> str:
            """
            Get email body and verification data.

            Args:
                message_id: Email message ID from check_inbox

            Returns:
                Email content with extracted verification links/codes
            """
            result = _run_async(get_email_tool.execute(message_id=message_id))
            if not result.success:
                return f"Error: {result.error}"
            return result.output

    def _register_network_tools(self):
        """Register network request capture tools."""
        if not self.network_capture:
            return

        network_capture = self.network_capture

        @self.tools.action(
            "Get captured network requests (XHR/fetch) from the current page"
        )
        def get_network_requests(
            include_bodies: bool = False,
            max_requests: int = 30,
        ) -> str:
            """
            Get captured XHR/fetch network requests from the current page.

            Use this to analyze API calls made by the web application:
            - View API endpoints and request/response patterns
            - Capture authentication tokens and headers for security testing
            - Understand client-side API interactions

            Note: Requests are saved on page navigation. Use file_read on the
            saved file path to access complete request history if output is truncated.

            Args:
                include_bodies: Include request/response bodies (use for API analysis)
                max_requests: Maximum requests to return (default: 30)

            Returns:
                Formatted list of network requests with headers and optional bodies
            """
            # Use async version if bodies requested (to fetch via CDP)
            if include_bodies:
                output, saved_file = _run_async(
                    network_capture.get_requests_async(
                        include_bodies=include_bodies,
                        max_requests=max_requests,
                    )
                )
            else:
                output, saved_file = network_capture.get_requests(
                    include_bodies=include_bodies,
                    max_requests=max_requests,
                )

            if saved_file:
                return f"{output}\n\nFull data saved to: {saved_file}"
            return output

    def get_tools(self) -> Tools:
        """Return the browser-use Tools instance."""
        return self.tools

