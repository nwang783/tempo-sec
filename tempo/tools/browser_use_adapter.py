"""
Adapter to integrate tempo-sec custom tools with browser-use library.

Wraps tempo-sec tools (findings, shell, filesystem, email) into browser-use's
Tools API using the @tools.action decorator pattern.
"""

import asyncio
import uuid
from typing import TYPE_CHECKING

from browser_use.tools.service import Tools

if TYPE_CHECKING:
    from tempo.infra.container import ContainerManager
    from tempo.infra.protocols import FindingsUpdater


class BrowserUseToolsAdapter:
    """Adapter to register tempo-sec tools with browser-use."""

    def __init__(
        self,
        container_manager: "ContainerManager | None" = None,
        findings_updater: "FindingsUpdater | None" = None,
        imap_config: dict | None = None,
        agent_email: str | None = None,
        tools_instance: Tools | None = None,
    ):
        """
        Initialize the tools adapter.

        Args:
            container_manager: Container for sandboxed shell execution
            findings_updater: Findings document manager
            imap_config: IMAP configuration for email tools
            agent_email: Email address for verification flows
            tools_instance: Optional shared Tools instance (if None, creates new)
        """
        self.container = container_manager
        self.findings = findings_updater
        self.imap_config = imap_config or {}
        self.agent_email = agent_email
        self.tools = tools_instance if tools_instance is not None else Tools()

        # Register all custom tools
        self._register_findings_tools()
        self._register_shell_tools()
        self._register_filesystem_tools()
        self._register_email_tools()

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
            result = asyncio.run(
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

            result = asyncio.run(
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
            result = asyncio.run(
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
            result = asyncio.run(mark_tested_tool.execute(surface_id=surface_id))
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
            result = asyncio.run(
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
        """Register file operations tools."""
        from tempo.tools.filesystem import FileReadTool, FileWriteTool

        file_read_tool = FileReadTool(self.container)
        file_write_tool = FileWriteTool(self.container)

        @self.tools.action("Read the contents of a file")
        def file_read(
            path: str,
            encoding: str = "utf-8",
            max_bytes: int = 0,
        ) -> str:
            """
            Read file contents.

            Args:
                path: Path to the file
                encoding: Text encoding (default: utf-8)
                max_bytes: Maximum bytes to read (0 = unlimited)

            Returns:
                File contents
            """
            max_bytes_param = max_bytes if max_bytes > 0 else None
            result = asyncio.run(
                file_read_tool.execute(
                    path=path,
                    encoding=encoding,
                    max_bytes=max_bytes_param,
                )
            )
            if not result.success:
                return f"Error: {result.error}"
            return result.output

        @self.tools.action("Write content to a file (creates or overwrites)")
        def file_write(
            path: str,
            content: str,
            append: bool = False,
            encoding: str = "utf-8",
        ) -> str:
            """
            Write to a file.

            Args:
                path: Path to the file
                content: Content to write
                append: Append instead of overwrite
                encoding: Text encoding (default: utf-8)

            Returns:
                Success confirmation
            """
            result = asyncio.run(
                file_write_tool.execute(
                    path=path,
                    content=content,
                    append=append,
                    encoding=encoding,
                )
            )
            if not result.success:
                return f"Error: {result.error}"
            return result.output

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
            result = asyncio.run(
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
            result = asyncio.run(get_email_tool.execute(message_id=message_id))
            if not result.success:
                return f"Error: {result.error}"
            return result.output

    def get_tools(self) -> Tools:
        """Return the browser-use Tools instance."""
        return self.tools
