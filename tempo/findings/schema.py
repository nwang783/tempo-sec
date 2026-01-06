"""
Findings document schema for structured security testing output.

Defines Pydantic models for the findings document produced during
security testing and consumed by the orchestrator.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Severity levels for security findings."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class FindingStatus(str, Enum):
    """Status of a security finding."""
    SUSPECTED = "suspected"
    CONFIRMED = "confirmed"
    FALSE_POSITIVE = "false_positive"
    NEEDS_MANUAL = "needs_manual"


class AttackSurface(BaseModel):
    """
    A potential attack surface identified during reconnaissance.

    Attack surfaces represent testable entry points in the application
    that may contain vulnerabilities.
    """
    id: str = Field(description="Unique identifier (UUID)")
    surface_type: str = Field(
        description="Type of surface (endpoint, form, api, websocket, etc.)"
    )
    url: str = Field(description="Full URL or location of the attack surface")
    description: str = Field(description="Detailed description of what this surface is")
    parameters: list[str] = Field(
        default_factory=list,
        description="Input parameters or fields that can be manipulated"
    )
    technology_hints: list[str] = Field(
        default_factory=list,
        description="Technology indicators (e.g., 'React', 'PHP', 'nginx')"
    )
    tested: bool = Field(default=False, description="Whether this surface has been tested")
    priority: str = Field(default="medium", description="Testing priority (high, medium, low)")
    discovered_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When this surface was discovered"
    )
    discovered_by: str = Field(description="Agent or tool that discovered this surface")

    model_config = {"extra": "allow"}


class Finding(BaseModel):
    """
    A security finding discovered during testing.

    Findings represent potential or confirmed vulnerabilities with
    evidence, reproduction steps, and remediation guidance.
    """
    id: str = Field(description="Unique identifier (UUID)")
    title: str = Field(description="Short descriptive title")
    severity: Severity = Field(description="Severity level of the finding")
    status: FindingStatus = Field(description="Confirmation status")
    attack_surface_id: str | None = Field(
        default=None,
        description="ID of the attack surface where this was found"
    )
    description: str = Field(description="Detailed description of the vulnerability")
    evidence: str = Field(description="Evidence supporting this finding")
    reproduction_steps: list[str] = Field(
        default_factory=list,
        description="Steps to reproduce the vulnerability"
    )
    remediation: str = Field(default="", description="Recommended remediation")
    discovered_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When this finding was discovered"
    )
    discovered_by: str = Field(description="Agent or tool that discovered this finding")
    validated_by: str | None = Field(
        default=None,
        description="Agent or tool that validated this finding"
    )

    model_config = {"extra": "allow"}


class ReconSummary(BaseModel):
    """
    High-level summary of reconnaissance results.

    Provides overview statistics and key takeaways from the recon phase.
    """
    total_endpoints: int = Field(default=0, description="Number of endpoints discovered")
    total_forms: int = Field(default=0, description="Number of forms found")
    total_apis: int = Field(default=0, description="Number of API endpoints found")
    technologies_detected: list[str] = Field(
        default_factory=list,
        description="List of detected technologies"
    )
    authentication_mechanisms: list[str] = Field(
        default_factory=list,
        description="Types of authentication observed"
    )
    notes: str = Field(default="", description="General observations from recon")

    model_config = {"extra": "allow"}


class FindingsDocumentSchema(BaseModel):
    """
    Complete findings document for a security testing session.

    This structured output captures all attack surfaces and findings
    discovered during security testing, along with metadata about the
    testing session.
    """
    version: str = Field(default="1.0", description="Schema version")
    target: str = Field(description="Primary target (URL, domain, application)")
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When this document was created"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Last update timestamp"
    )
    recon_summary: ReconSummary | None = Field(
        default=None,
        description="Summary of reconnaissance findings"
    )
    attack_surfaces: list[AttackSurface] = Field(
        default_factory=list,
        description="All discovered attack surfaces"
    )
    findings: list[Finding] = Field(
        default_factory=list,
        description="All security findings discovered"
    )
    agents_invoked: list[str] = Field(
        default_factory=list,
        description="List of agents that contributed to this document"
    )
    total_steps_taken: int = Field(
        default=0,
        description="Total number of testing steps across all agents"
    )

    model_config = {"extra": "allow"}
