"""
Findings document management tools.

Provides tools for the orchestrator to read and update the findings document:
- ReadFindingsTool: Read findings document summary
- AddAttackSurfaceTool: Add new attack surface
- AddFindingTool: Add new security finding
- MarkSurfaceTestedTool: Mark attack surface as tested
- UpdateReconSummaryTool: Update recon summary
"""

import uuid
from typing import TYPE_CHECKING

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema

if TYPE_CHECKING:
    from tempo.infra.protocols import FindingsUpdater


class ReadFindingsTool(Tool):
    """Read the current findings document and get a summary."""

    name = "read_findings"
    description = """Read the current findings document to see what's been discovered.

    This returns a summary of:
    - Total attack surfaces (tested vs untested)
    - Total findings grouped by severity
    - Agents invoked and steps taken
    - Target information

    Use this to orient yourself and understand what testing has been done."""
    category = ToolCategory.META

    def __init__(self, findings_updater: "FindingsUpdater"):
        """
        Initialize the read findings tool.

        Args:
            findings_updater: Component implementing FindingsUpdater protocol
        """
        self.findings = findings_updater

    async def execute(self, purpose: str = "") -> ToolResult:
        """
        Read the findings document.

        Args:
            purpose: A one-sentence summary of why this tool is being called

        Returns:
            ToolResult with findings summary
        """
        try:
            summary = self.findings.get_summary()

            # Format output
            output_lines = [
                f"Target: {summary['target']}",
                f"Created: {summary['created_at']}",
                f"Last updated: {summary['updated_at']}",
                "",
                "Attack Surfaces:",
                f"  Total: {summary['total_surfaces']}",
                f"  Tested: {summary['tested_surfaces']}",
                f"  Untested: {summary['untested_surfaces']}",
                "",
                "Findings:",
                f"  Total: {summary['total_findings']}",
                f"  Critical: {summary['findings_by_severity']['critical']}",
                f"  High: {summary['findings_by_severity']['high']}",
                f"  Medium: {summary['findings_by_severity']['medium']}",
                f"  Low: {summary['findings_by_severity']['low']}",
                f"  Info: {summary['findings_by_severity']['info']}",
                "",
                f"Agents invoked: {', '.join(summary['agents_invoked']) or 'None'}",
                f"Total steps: {summary['total_steps']}",
            ]

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata=summary,
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to read findings: {str(e)}",
            )

    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
        )


class AddAttackSurfaceTool(Tool):
    """Add a new attack surface to the findings document."""

    name = "add_attack_surface"
    description = """Add a new attack surface to the findings document.

    Use this when you discover a new testable entry point during reconnaissance
    or testing. Attack surfaces represent locations that could contain vulnerabilities.

    Examples:
    - Login endpoints
    - API endpoints with parameters
    - File upload forms
    - Input fields that accept user data"""
    category = ToolCategory.META

    def __init__(self, findings_updater: "FindingsUpdater"):
        """
        Initialize the add attack surface tool.

        Args:
            findings_updater: Component implementing FindingsUpdater protocol
        """
        self.findings = findings_updater

    async def execute(
        self,
        surface_type: str,
        url: str,
        description: str,
        discovered_by: str,
        parameters: list[str] | None = None,
        technology_hints: list[str] | None = None,
        priority: str = "medium",
        purpose: str = "",
    ) -> ToolResult:
        """
        Add a new attack surface.

        Args:
            surface_type: Type of surface (endpoint, form, api, websocket, etc.)
            url: Full URL or location
            description: Detailed description
            discovered_by: Agent or tool that discovered it
            parameters: Optional list of parameters
            technology_hints: Optional technology indicators
            priority: Priority level (high, medium, low)
            purpose: A one-sentence summary of why this tool is being called

        Returns:
            ToolResult with the created surface ID
        """
        try:
            # Validate priority
            valid_priorities = {"high", "medium", "low"}
            if priority.lower() not in valid_priorities:
                priority = "medium"

            # Generate UUID
            surface_id = str(uuid.uuid4())

            # Add to document
            self.findings.add_attack_surface(
                surface_id=surface_id,
                surface_type=surface_type,
                url=url,
                description=description,
                discovered_by=discovered_by,
                parameters=parameters or [],
                technology_hints=technology_hints or [],
                priority=priority.lower(),
            )

            # Persist to disk immediately
            if hasattr(self.findings, 'save') and hasattr(self.findings, 'file_path'):
                if self.findings.file_path:
                    self.findings.save()

            return ToolResult(
                success=True,
                output=f"Added attack surface: {surface_type} at {url} (ID: {surface_id})",
                metadata={"surface_id": surface_id},
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to add attack surface: {str(e)}",
            )

    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "surface_type": {
                        "type": "string",
                        "description": "Type of surface (endpoint, form, api, websocket, etc.)",
                    },
                    "url": {
                        "type": "string",
                        "description": "Full URL or location of the attack surface",
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed description of what this surface is",
                    },
                    "discovered_by": {
                        "type": "string",
                        "description": "Agent or tool that discovered this surface",
                    },
                    "parameters": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Input parameters or fields (optional)",
                    },
                    "technology_hints": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Technology indicators (optional)",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "Testing priority (default: medium)",
                    },
                },
                "required": ["surface_type", "url", "description", "discovered_by"],
            },
        )


class AddFindingTool(Tool):
    """Add a new security finding to the findings document."""

    name = "add_finding"
    description = """Add a new security finding to the findings document.

    Use this when you discover a potential or confirmed vulnerability during testing.
    Always include detailed evidence and reproduction steps.

    Severity levels:
    - critical: Complete system compromise possible
    - high: Significant security impact
    - medium: Moderate security risk
    - low: Minor security concern
    - info: Informational finding

    Status values:
    - suspected: Potential vulnerability, needs validation
    - confirmed: Verified vulnerability
    - false_positive: Initially suspected but not a real issue
    - needs_manual: Requires manual verification"""
    category = ToolCategory.META

    def __init__(self, findings_updater: "FindingsUpdater"):
        """
        Initialize the add finding tool.

        Args:
            findings_updater: Component implementing FindingsUpdater protocol
        """
        self.findings = findings_updater

    async def execute(
        self,
        title: str,
        severity: str,
        status: str,
        description: str,
        evidence: str,
        discovered_by: str,
        attack_surface_id: str | None = None,
        reproduction_steps: list[str] | None = None,
        remediation: str = "",
        validated_by: str | None = None,
        purpose: str = "",
    ) -> ToolResult:
        """
        Add a new security finding.

        Args:
            title: Short descriptive title
            severity: Severity level (critical, high, medium, low, info)
            status: Confirmation status (suspected, confirmed, false_positive, needs_manual)
            description: Detailed description
            evidence: Supporting evidence
            discovered_by: Agent or tool that discovered it
            attack_surface_id: Optional ID of related attack surface
            reproduction_steps: Optional reproduction steps
            remediation: Optional remediation guidance
            validated_by: Optional validator
            purpose: A one-sentence summary of why this tool is being called

        Returns:
            ToolResult with the created finding ID
        """
        try:
            # Validate severity
            valid_severities = {"critical", "high", "medium", "low", "info"}
            if severity.lower() not in valid_severities:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Invalid severity: {severity}. Must be one of: {', '.join(valid_severities)}",
                )

            # Validate status
            valid_statuses = {"suspected", "confirmed", "false_positive", "needs_manual"}
            if status.lower() not in valid_statuses:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Invalid status: {status}. Must be one of: {', '.join(valid_statuses)}",
                )

            # Generate UUID
            finding_id = str(uuid.uuid4())

            # Add to document
            self.findings.add_finding(
                finding_id=finding_id,
                title=title,
                severity=severity.lower(),
                status=status.lower(),
                description=description,
                evidence=evidence,
                discovered_by=discovered_by,
                attack_surface_id=attack_surface_id,
                reproduction_steps=reproduction_steps or [],
                remediation=remediation,
                validated_by=validated_by,
            )

            # Persist to disk immediately
            if hasattr(self.findings, 'save') and hasattr(self.findings, 'file_path'):
                if self.findings.file_path:
                    self.findings.save()

            return ToolResult(
                success=True,
                output=f"Added {severity} finding: {title} (ID: {finding_id})",
                metadata={"finding_id": finding_id},
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to add finding: {str(e)}",
            )

    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Short descriptive title",
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low", "info"],
                        "description": "Severity level",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["suspected", "confirmed", "false_positive", "needs_manual"],
                        "description": "Confirmation status",
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed description of the vulnerability",
                    },
                    "evidence": {
                        "type": "string",
                        "description": "Evidence supporting this finding",
                    },
                    "discovered_by": {
                        "type": "string",
                        "description": "Agent or tool that discovered this finding",
                    },
                    "attack_surface_id": {
                        "type": "string",
                        "description": "ID of related attack surface (optional)",
                    },
                    "reproduction_steps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Steps to reproduce the vulnerability (optional)",
                    },
                    "remediation": {
                        "type": "string",
                        "description": "Recommended remediation (optional)",
                    },
                    "validated_by": {
                        "type": "string",
                        "description": "Agent or tool that validated this finding (optional)",
                    },
                },
                "required": ["title", "severity", "status", "description", "evidence", "discovered_by"],
            },
        )


class MarkSurfaceTestedTool(Tool):
    """Mark an attack surface as tested."""

    name = "mark_surface_tested"
    description = """Mark an attack surface as tested.

    Use this after you've finished testing an attack surface, whether or not
    you found vulnerabilities. This helps track testing progress."""
    category = ToolCategory.META

    def __init__(self, findings_updater: "FindingsUpdater"):
        """
        Initialize the mark surface tested tool.

        Args:
            findings_updater: Component implementing FindingsUpdater protocol
        """
        self.findings = findings_updater

    async def execute(
        self,
        surface_id: str,
        purpose: str = "",
    ) -> ToolResult:
        """
        Mark an attack surface as tested.

        Args:
            surface_id: ID of the surface to mark
            purpose: A one-sentence summary of why this tool is being called

        Returns:
            ToolResult indicating success/failure
        """
        try:
            success = self.findings.mark_surface_tested(surface_id)

            if not success:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Attack surface not found: {surface_id}",
                )

            # Persist to disk immediately
            if hasattr(self.findings, 'save') and hasattr(self.findings, 'file_path'):
                if self.findings.file_path:
                    self.findings.save()

            return ToolResult(
                success=True,
                output=f"Marked attack surface {surface_id} as tested",
                metadata={"surface_id": surface_id},
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to mark surface as tested: {str(e)}",
            )

    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "surface_id": {
                        "type": "string",
                        "description": "ID of the attack surface to mark as tested",
                    },
                },
                "required": ["surface_id"],
            },
        )


class UpdateReconSummaryTool(Tool):
    """Update the reconnaissance summary in the findings document."""

    name = "update_recon_summary"
    description = """Update the reconnaissance summary with high-level statistics.

    Use this to record overall reconnaissance findings like:
    - Total endpoints, forms, APIs discovered
    - Technologies detected
    - Authentication mechanisms observed
    - General observations

    This provides context for the testing phase."""
    category = ToolCategory.META

    def __init__(self, findings_updater: "FindingsUpdater"):
        """
        Initialize the update recon summary tool.

        Args:
            findings_updater: Component implementing FindingsUpdater protocol
        """
        self.findings = findings_updater

    async def execute(
        self,
        total_endpoints: int | None = None,
        total_forms: int | None = None,
        total_apis: int | None = None,
        technologies_detected: list[str] | None = None,
        authentication_mechanisms: list[str] | None = None,
        notes: str | None = None,
        purpose: str = "",
    ) -> ToolResult:
        """
        Update the recon summary.

        Args:
            total_endpoints: Number of endpoints discovered
            total_forms: Number of forms found
            total_apis: Number of API endpoints
            technologies_detected: List of detected technologies
            authentication_mechanisms: List of auth mechanisms
            notes: General observations
            purpose: A one-sentence summary of why this tool is being called

        Returns:
            ToolResult indicating success
        """
        try:
            self.findings.update_recon_summary(
                total_endpoints=total_endpoints,
                total_forms=total_forms,
                total_apis=total_apis,
                technologies_detected=technologies_detected,
                authentication_mechanisms=authentication_mechanisms,
                notes=notes,
            )

            # Build summary message
            updates = []
            if total_endpoints is not None:
                updates.append(f"endpoints: {total_endpoints}")
            if total_forms is not None:
                updates.append(f"forms: {total_forms}")
            if total_apis is not None:
                updates.append(f"APIs: {total_apis}")
            if technologies_detected:
                updates.append(f"technologies: {len(technologies_detected)}")
            if authentication_mechanisms:
                updates.append(f"auth mechanisms: {len(authentication_mechanisms)}")
            if notes:
                updates.append("notes updated")

            # Persist to disk immediately
            if hasattr(self.findings, 'save') and hasattr(self.findings, 'file_path'):
                if self.findings.file_path:
                    self.findings.save()

            return ToolResult(
                success=True,
                output=f"Updated recon summary: {', '.join(updates)}",
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to update recon summary: {str(e)}",
            )

    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "total_endpoints": {
                        "type": "number",
                        "description": "Number of endpoints discovered (optional)",
                    },
                    "total_forms": {
                        "type": "number",
                        "description": "Number of forms found (optional)",
                    },
                    "total_apis": {
                        "type": "number",
                        "description": "Number of API endpoints (optional)",
                    },
                    "technologies_detected": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of detected technologies (optional)",
                    },
                    "authentication_mechanisms": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of authentication mechanisms (optional)",
                    },
                    "notes": {
                        "type": "string",
                        "description": "General observations from recon (optional)",
                    },
                },
                "required": [],
            },
        )
