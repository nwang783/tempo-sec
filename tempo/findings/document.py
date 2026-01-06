"""
FindingsDocument class for managing security testing findings.

Provides a high-level interface for querying and updating findings documents,
with automatic persistence to YAML files.

Supports both synchronous and asynchronous operations. Async methods use
asyncio.Lock for thread-safe concurrent access during parallel subagent execution.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from tempo.findings.schema import (
    AttackSurface,
    Finding,
    FindingsDocumentSchema,
    ReconSummary,
    Severity,
)
from tempo.findings.persistence import load_from_yaml, save_to_yaml

if TYPE_CHECKING:
    from tempo.findings.schema import FindingStatus


class FindingsDocument:
    """
    Manages a findings document with query and update operations.

    This class provides a clean interface for tools and agents to interact
    with the findings document without dealing with YAML serialization directly.
    """

    def __init__(self, target: str, file_path: str | None = None):
        """
        Initialize a new findings document.

        Args:
            target: The target being tested (URL, domain, etc.)
            file_path: Optional path to save/load from. If None, must call save() with path.
        """
        self.file_path = file_path
        self._data = FindingsDocumentSchema(
            target=target,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        # Lock for async-safe operations during parallel subagent execution
        self._lock = asyncio.Lock()

    @classmethod
    def load(cls, file_path: str) -> "FindingsDocument":
        """
        Load an existing findings document from YAML.

        Args:
            file_path: Path to the YAML file

        Returns:
            FindingsDocument instance

        Raises:
            FileNotFoundError: If file doesn't exist
            pydantic.ValidationError: If document is invalid
        """
        doc = cls(target="", file_path=file_path)
        doc._data = load_from_yaml(file_path)
        return doc

    def save(self, file_path: str | None = None) -> None:
        """
        Save the findings document to YAML.

        Args:
            file_path: Path to save to. If None, uses self.file_path.

        Raises:
            ValueError: If no file path is available
            IOError: If file cannot be written
        """
        path = file_path or self.file_path
        if not path:
            raise ValueError("No file path specified for save operation")

        # Update timestamp
        self._data.updated_at = datetime.utcnow()

        save_to_yaml(self._data, path)

        # Update stored path if a new one was provided
        if file_path:
            self.file_path = file_path

    # Query methods

    def get_untested_surfaces(self) -> list[AttackSurface]:
        """
        Get all attack surfaces that haven't been tested yet.

        Returns:
            List of untested attack surfaces
        """
        return [surface for surface in self._data.attack_surfaces if not surface.tested]

    def get_all_findings(self) -> list[Finding]:
        """
        Get all findings.

        Returns:
            List of all finding objects
        """
        return self._data.findings

    def get_all_surfaces(self) -> list[AttackSurface]:
        """
        Get all attack surfaces.

        Returns:
            List of all attack surface objects
        """
        return self._data.attack_surfaces

    def get_findings_by_severity(self, severity: Severity) -> list[Finding]:
        """
        Get all findings of a specific severity level.

        Args:
            severity: The severity level to filter by

        Returns:
            List of findings matching the severity
        """
        return [finding for finding in self._data.findings if finding.severity == severity]

    def get_summary(self) -> dict:
        """
        Get a summary of the findings document.

        Returns:
            Dictionary with summary statistics
        """
        total_surfaces = len(self._data.attack_surfaces)
        tested_surfaces = sum(1 for s in self._data.attack_surfaces if s.tested)

        severity_counts = {
            "critical": len(self.get_findings_by_severity(Severity.CRITICAL)),
            "high": len(self.get_findings_by_severity(Severity.HIGH)),
            "medium": len(self.get_findings_by_severity(Severity.MEDIUM)),
            "low": len(self.get_findings_by_severity(Severity.LOW)),
            "info": len(self.get_findings_by_severity(Severity.INFO)),
        }

        return {
            "target": self._data.target,
            "total_surfaces": total_surfaces,
            "tested_surfaces": tested_surfaces,
            "untested_surfaces": total_surfaces - tested_surfaces,
            "total_findings": len(self._data.findings),
            "findings_by_severity": severity_counts,
            "agents_invoked": self._data.agents_invoked,
            "total_steps": self._data.total_steps_taken,
            "created_at": self._data.created_at.isoformat(),
            "updated_at": self._data.updated_at.isoformat(),
        }

    # Update methods

    def add_attack_surface(
        self,
        surface_id: str,
        surface_type: str,
        url: str,
        description: str,
        discovered_by: str,
        parameters: list[str] | None = None,
        technology_hints: list[str] | None = None,
        priority: str = "medium",
    ) -> AttackSurface:
        """
        Add a new attack surface to the document.

        Args:
            surface_id: Unique identifier (UUID)
            surface_type: Type of surface (endpoint, form, api, etc.)
            url: Full URL or location
            description: Detailed description
            discovered_by: Agent or tool that discovered it
            parameters: Optional list of parameters
            technology_hints: Optional technology indicators
            priority: Priority level (high, medium, low)

        Returns:
            The created AttackSurface
        """
        surface = AttackSurface(
            id=surface_id,
            surface_type=surface_type,
            url=url,
            description=description,
            parameters=parameters or [],
            technology_hints=technology_hints or [],
            priority=priority,
            discovered_at=datetime.utcnow(),
            discovered_by=discovered_by,
        )

        self._data.attack_surfaces.append(surface)
        self._data.updated_at = datetime.utcnow()

        return surface

    def add_finding(
        self,
        finding_id: str,
        title: str,
        severity: Severity,
        status: "FindingStatus",
        description: str,
        evidence: str,
        discovered_by: str,
        attack_surface_id: str | None = None,
        reproduction_steps: list[str] | None = None,
        remediation: str = "",
        validated_by: str | None = None,
    ) -> Finding:
        """
        Add a new security finding to the document.

        Args:
            finding_id: Unique identifier (UUID)
            title: Short descriptive title
            severity: Severity level
            status: Confirmation status
            description: Detailed description
            evidence: Supporting evidence
            discovered_by: Agent or tool that discovered it
            attack_surface_id: Optional ID of related attack surface
            reproduction_steps: Optional reproduction steps
            remediation: Optional remediation guidance
            validated_by: Optional validator

        Returns:
            The created Finding
        """
        finding = Finding(
            id=finding_id,
            title=title,
            severity=severity,
            status=status,
            attack_surface_id=attack_surface_id,
            description=description,
            evidence=evidence,
            reproduction_steps=reproduction_steps or [],
            remediation=remediation,
            discovered_at=datetime.utcnow(),
            discovered_by=discovered_by,
            validated_by=validated_by,
        )

        self._data.findings.append(finding)
        self._data.updated_at = datetime.utcnow()

        return finding

    def mark_surface_tested(self, surface_id: str) -> bool:
        """
        Mark an attack surface as tested.

        Args:
            surface_id: ID of the surface to mark

        Returns:
            True if surface was found and updated, False otherwise
        """
        for surface in self._data.attack_surfaces:
            if surface.id == surface_id:
                surface.tested = True
                self._data.updated_at = datetime.utcnow()
                return True

        return False

    def update_recon_summary(
        self,
        total_endpoints: int | None = None,
        total_forms: int | None = None,
        total_apis: int | None = None,
        technologies_detected: list[str] | None = None,
        authentication_mechanisms: list[str] | None = None,
        notes: str | None = None,
    ) -> ReconSummary:
        """
        Update or create the reconnaissance summary.

        Args:
            total_endpoints: Number of endpoints discovered
            total_forms: Number of forms found
            total_apis: Number of API endpoints
            technologies_detected: List of detected technologies
            authentication_mechanisms: List of auth mechanisms
            notes: General observations

        Returns:
            The updated ReconSummary
        """
        # Initialize if doesn't exist
        if self._data.recon_summary is None:
            self._data.recon_summary = ReconSummary()

        # Update fields if provided
        if total_endpoints is not None:
            self._data.recon_summary.total_endpoints = total_endpoints
        if total_forms is not None:
            self._data.recon_summary.total_forms = total_forms
        if total_apis is not None:
            self._data.recon_summary.total_apis = total_apis
        if technologies_detected is not None:
            self._data.recon_summary.technologies_detected = technologies_detected
        if authentication_mechanisms is not None:
            self._data.recon_summary.authentication_mechanisms = authentication_mechanisms
        if notes is not None:
            self._data.recon_summary.notes = notes

        self._data.updated_at = datetime.utcnow()

        return self._data.recon_summary

    # Metadata methods

    def add_agent_invocation(self, agent_name: str) -> None:
        """
        Record that an agent was invoked.

        Args:
            agent_name: Name of the agent
        """
        if agent_name not in self._data.agents_invoked:
            self._data.agents_invoked.append(agent_name)
            self._data.updated_at = datetime.utcnow()

    def increment_steps(self, count: int = 1) -> None:
        """
        Increment the total steps counter.

        Args:
            count: Number of steps to add (default 1)
        """
        self._data.total_steps_taken += count
        self._data.updated_at = datetime.utcnow()

    # Direct access to underlying data (for advanced use cases)

    @property
    def data(self) -> FindingsDocumentSchema:
        """Get the underlying Pydantic model."""
        return self._data

    # Async-safe methods for parallel subagent execution
    # These use asyncio.Lock to ensure thread-safe concurrent access

    async def add_attack_surface_async(
        self,
        surface_id: str,
        surface_type: str,
        url: str,
        description: str,
        discovered_by: str,
        parameters: list[str] | None = None,
        technology_hints: list[str] | None = None,
        priority: str = "medium",
    ) -> AttackSurface:
        """
        Thread-safe async version of add_attack_surface.

        Uses asyncio.Lock to ensure safe concurrent access during
        parallel subagent execution.
        """
        async with self._lock:
            return self.add_attack_surface(
                surface_id=surface_id,
                surface_type=surface_type,
                url=url,
                description=description,
                discovered_by=discovered_by,
                parameters=parameters,
                technology_hints=technology_hints,
                priority=priority,
            )

    async def add_finding_async(
        self,
        finding_id: str,
        title: str,
        severity: Severity,
        status: "FindingStatus",
        description: str,
        evidence: str,
        discovered_by: str,
        attack_surface_id: str | None = None,
        reproduction_steps: list[str] | None = None,
        remediation: str = "",
        validated_by: str | None = None,
    ) -> Finding:
        """
        Thread-safe async version of add_finding.

        Uses asyncio.Lock to ensure safe concurrent access during
        parallel subagent execution.
        """
        async with self._lock:
            return self.add_finding(
                finding_id=finding_id,
                title=title,
                severity=severity,
                status=status,
                description=description,
                evidence=evidence,
                discovered_by=discovered_by,
                attack_surface_id=attack_surface_id,
                reproduction_steps=reproduction_steps,
                remediation=remediation,
                validated_by=validated_by,
            )

    async def mark_surface_tested_async(self, surface_id: str) -> bool:
        """
        Thread-safe async version of mark_surface_tested.

        Uses asyncio.Lock to ensure safe concurrent access during
        parallel subagent execution.
        """
        async with self._lock:
            return self.mark_surface_tested(surface_id)

    async def update_recon_summary_async(
        self,
        total_endpoints: int | None = None,
        total_forms: int | None = None,
        total_apis: int | None = None,
        technologies_detected: list[str] | None = None,
        authentication_mechanisms: list[str] | None = None,
        notes: str | None = None,
    ) -> ReconSummary:
        """
        Thread-safe async version of update_recon_summary.

        Uses asyncio.Lock to ensure safe concurrent access during
        parallel subagent execution.
        """
        async with self._lock:
            return self.update_recon_summary(
                total_endpoints=total_endpoints,
                total_forms=total_forms,
                total_apis=total_apis,
                technologies_detected=technologies_detected,
                authentication_mechanisms=authentication_mechanisms,
                notes=notes,
            )

    async def save_async(self, file_path: str | None = None) -> None:
        """
        Thread-safe async save.

        Uses asyncio.Lock to ensure safe concurrent access during
        parallel subagent execution.
        """
        async with self._lock:
            self.save(file_path)

    async def add_agent_invocation_async(self, agent_name: str) -> None:
        """
        Thread-safe async version of add_agent_invocation.

        Uses asyncio.Lock to ensure safe concurrent access during
        parallel subagent execution.
        """
        async with self._lock:
            self.add_agent_invocation(agent_name)

    async def increment_steps_async(self, count: int = 1) -> None:
        """
        Thread-safe async version of increment_steps.

        Uses asyncio.Lock to ensure safe concurrent access during
        parallel subagent execution.
        """
        async with self._lock:
            self.increment_steps(count)

