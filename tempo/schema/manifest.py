"""
Target manifest schema for structured reconnaissance output.

Defines Pydantic models for the target manifest produced by the recon script
and consumed by the testing script.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """Types of reconnaissance actions."""
    CRAWL = "crawl"
    SCAN = "scan"
    FINGERPRINT = "fingerprint"
    ENUMERATE = "enumerate"
    ANALYZE = "analyze"
    OTHER = "other"


class RiskLevel(str, Enum):
    """Risk levels for attack surfaces."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class AttackSurfaceType(str, Enum):
    """Types of attack surfaces."""
    ENDPOINT = "endpoint"
    FORM = "form"
    API = "api"
    AUTHENTICATION = "authentication"
    FILE_UPLOAD = "file_upload"
    INJECTION_POINT = "injection_point"
    SESSION_MANAGEMENT = "session_management"
    CORS = "cors"
    HEADER = "header"
    COOKIE = "cookie"
    OTHER = "other"


class ReconAction(BaseModel):
    """A single reconnaissance action taken by the agent."""
    action_type: ActionType = Field(description="Type of recon action performed")
    tool_used: str = Field(description="Name of the tool used")
    target: str = Field(description="Target URL, IP, or resource")
    result_summary: str = Field(description="Brief summary of what was found")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = {"extra": "allow"}


class SitemapEntry(BaseModel):
    """An entry in the discovered site map."""
    url: str = Field(description="Full URL of the endpoint")
    method: str = Field(default="GET", description="HTTP method")
    parameters: list[str] = Field(default_factory=list, description="Query/body parameters")
    content_type: Optional[str] = Field(default=None, description="Response content type")
    status_code: Optional[int] = Field(default=None, description="HTTP status code observed")
    notes: Optional[str] = Field(default=None, description="Additional notes")
    
    model_config = {"extra": "allow"}


class AttackSurface(BaseModel):
    """A potential attack surface identified during reconnaissance."""
    name: str = Field(description="Short name for this attack surface")
    surface_type: AttackSurfaceType = Field(description="Category of attack surface")
    location: str = Field(description="URL, endpoint, or location where this was found")
    risk_level: RiskLevel = Field(default=RiskLevel.UNKNOWN, description="Assessed risk level")
    description: str = Field(description="Detailed description of the potential vulnerability")
    evidence: Optional[str] = Field(default=None, description="Evidence supporting this finding")
    notes: Optional[str] = Field(default=None, description="Additional notes or context")
    
    model_config = {"extra": "allow"}


class TechnologyFingerprint(BaseModel):
    """Technology identified on the target."""
    name: str = Field(description="Technology name (e.g., 'nginx', 'React', 'PHP')")
    version: Optional[str] = Field(default=None, description="Version if detected")
    category: str = Field(description="Category (e.g., 'web_server', 'framework', 'cms')")
    confidence: str = Field(default="medium", description="Confidence level: low, medium, high")
    
    model_config = {"extra": "allow"}


class ManifestMetadata(BaseModel):
    """Metadata about the reconnaissance run."""
    target_domain: str = Field(description="Primary target domain")
    start_time: datetime = Field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = Field(default=None)
    agent_model: str = Field(description="LLM model used for recon")
    steps_taken: int = Field(default=0, description="Number of agent steps")
    session_id: str = Field(description="Unique session identifier")
    scope_description: Optional[str] = Field(default=None, description="Scope or constraints")
    
    model_config = {"extra": "allow"}


class TargetManifest(BaseModel):
    """
    Complete target manifest produced by reconnaissance phase.
    
    This structured output captures all findings from recon and serves as
    input to the testing phase.
    """
    metadata: ManifestMetadata = Field(description="Run metadata")
    actions: list[ReconAction] = Field(
        default_factory=list, 
        description="List of all reconnaissance actions taken"
    )
    sitemap: list[SitemapEntry] = Field(
        default_factory=list,
        description="Discovered endpoints and URLs"
    )
    attack_surfaces: list[AttackSurface] = Field(
        default_factory=list,
        description="Potential attack surfaces identified"
    )
    technologies: list[TechnologyFingerprint] = Field(
        default_factory=list,
        description="Technologies fingerprinted on the target"
    )
    notes: str = Field(
        default="",
        description="General observations and notes from recon"
    )
    raw_findings: dict = Field(
        default_factory=dict,
        description="Additional unstructured findings"
    )
    
    model_config = {"extra": "allow"}
    
    def to_summary(self) -> str:
        """Generate a text summary for injection into prompts."""
        lines = [
            f"# Target: {self.metadata.target_domain}",
            "",
            f"**Recon completed**: {self.metadata.end_time or 'ongoing'}",
            f"**Steps taken**: {self.metadata.steps_taken}",
            "",
        ]
        
        if self.technologies:
            lines.append("## Technologies Detected")
            for tech in self.technologies:
                version = f" v{tech.version}" if tech.version else ""
                lines.append(f"- {tech.name}{version} ({tech.category})")
            lines.append("")
        
        if self.sitemap:
            lines.append(f"## Sitemap ({len(self.sitemap)} endpoints)")
            for entry in self.sitemap[:10]:  # Limit to first 10
                params = f" params={entry.parameters}" if entry.parameters else ""
                lines.append(f"- {entry.method} {entry.url}{params}")
            if len(self.sitemap) > 10:
                lines.append(f"  ... and {len(self.sitemap) - 10} more")
            lines.append("")
        
        if self.attack_surfaces:
            lines.append(f"## Attack Surfaces ({len(self.attack_surfaces)} identified)")
            for surface in self.attack_surfaces:
                lines.append(f"- **{surface.name}** [{surface.risk_level.value}]")
                lines.append(f"  Type: {surface.surface_type.value}")
                lines.append(f"  Location: {surface.location}")
                lines.append(f"  {surface.description}")
            lines.append("")
        
        if self.notes:
            lines.append("## Notes")
            lines.append(self.notes)
        
        return "\n".join(lines)
    
    def save(self, path: str) -> None:
        """Save manifest to a JSON file."""
        from pathlib import Path
        import json
        
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(self.model_dump_json(indent=2))
    
    @classmethod
    def load(cls, path: str) -> "TargetManifest":
        """Load manifest from a JSON file."""
        import json
        
        with open(path, "r") as f:
            data = json.load(f)
        return cls.model_validate(data)
