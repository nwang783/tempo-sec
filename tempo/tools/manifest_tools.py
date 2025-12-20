"""
Manifest tools for recon completion and manifest management.

Provides tools for completing the recon phase with structured output
and loading manifests for the testing phase.
"""

import json
from datetime import datetime
from typing import Any, TYPE_CHECKING

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema
from tempo.schema.manifest import (
    TargetManifest,
    ManifestMetadata,
    ReconAction,
    SitemapEntry,
    AttackSurface,
    TechnologyFingerprint,
    ActionType,
    RiskLevel,
    AttackSurfaceType,
)

if TYPE_CHECKING:
    from tempo.context.store import ContextStore


class CompleteReconTool(Tool):
    """Complete the reconnaissance phase and produce a structured manifest."""
    
    name = "complete_recon"
    description = """Complete the reconnaissance phase and produce a structured target manifest.

    Call this when you have gathered sufficient information about the target.
    You must provide a complete summary of:
    - All actions taken during recon (crawls, scans, fingerprinting)
    - The sitemap of discovered endpoints
    - Potential attack surfaces identified
    - Technologies detected
    - Any additional notes
    
    This will save a target_manifest.json file that can be used for the testing phase.
    
    IMPORTANT: Only call this when you are done with reconnaissance."""
    category = ToolCategory.META
    
    def __init__(
        self,
        output_path: str,
        target_domain: str,
        agent_model: str,
        session_id: str,
        context_store: "ContextStore | None" = None,
    ):
        """
        Initialize the complete recon tool.
        
        Args:
            output_path: Path to save the manifest JSON
            target_domain: Primary target domain
            agent_model: LLM model name
            session_id: Session identifier
            context_store: Optional context store for extracting actions
        """
        self.output_path = output_path
        self.target_domain = target_domain
        self.agent_model = agent_model
        self.session_id = session_id
        self.context = context_store
        self._start_time = datetime.utcnow()
    
    async def execute(
        self,
        sitemap: list[dict],
        attack_surfaces: list[dict],
        technologies: list[dict] | None = None,
        actions: list[dict] | None = None,
        notes: str = "",
        purpose: str = "",
    ) -> ToolResult:
        """
        Complete recon and save the manifest.
        
        Args:
            sitemap: List of discovered endpoints
            attack_surfaces: List of potential attack surfaces
            technologies: List of detected technologies
            actions: List of recon actions taken
            notes: General observations
            purpose: Why this tool is being called
            
        Returns:
            ToolResult with manifest save confirmation
        """
        try:
            # Build metadata
            metadata = ManifestMetadata(
                target_domain=self.target_domain,
                start_time=self._start_time,
                end_time=datetime.utcnow(),
                agent_model=self.agent_model,
                steps_taken=self._get_step_count(),
                session_id=self.session_id,
            )
            
            # Parse sitemap entries
            parsed_sitemap = []
            for entry in sitemap:
                try:
                    parsed_sitemap.append(SitemapEntry.model_validate(entry))
                except Exception as e:
                    # Be lenient - include partial data
                    parsed_sitemap.append(SitemapEntry(
                        url=entry.get("url", "unknown"),
                        method=entry.get("method", "GET"),
                        parameters=entry.get("parameters", []),
                        notes=str(e),
                    ))
            
            # Parse attack surfaces
            parsed_surfaces = []
            for surface in attack_surfaces:
                try:
                    parsed_surfaces.append(AttackSurface.model_validate(surface))
                except Exception as e:
                    # Be lenient
                    parsed_surfaces.append(AttackSurface(
                        name=surface.get("name", "unknown"),
                        surface_type=AttackSurfaceType.OTHER,
                        location=surface.get("location", "unknown"),
                        description=surface.get("description", str(surface)),
                        notes=str(e),
                    ))
            
            # Parse technologies
            parsed_tech = []
            for tech in (technologies or []):
                try:
                    parsed_tech.append(TechnologyFingerprint.model_validate(tech))
                except Exception:
                    parsed_tech.append(TechnologyFingerprint(
                        name=tech.get("name", "unknown"),
                        category=tech.get("category", "unknown"),
                    ))
            
            # Parse actions
            parsed_actions = []
            for action in (actions or []):
                try:
                    parsed_actions.append(ReconAction.model_validate(action))
                except Exception:
                    parsed_actions.append(ReconAction(
                        action_type=ActionType.OTHER,
                        tool_used=action.get("tool_used", "unknown"),
                        target=action.get("target", "unknown"),
                        result_summary=action.get("result_summary", str(action)),
                    ))
            
            # Build manifest
            manifest = TargetManifest(
                metadata=metadata,
                actions=parsed_actions,
                sitemap=parsed_sitemap,
                attack_surfaces=parsed_surfaces,
                technologies=parsed_tech,
                notes=notes,
            )
            
            # Save to file
            manifest.save(self.output_path)
            
            summary = (
                f"Manifest saved to {self.output_path}\n"
                f"- {len(parsed_sitemap)} endpoints mapped\n"
                f"- {len(parsed_surfaces)} attack surfaces identified\n"
                f"- {len(parsed_tech)} technologies detected\n"
                f"- {len(parsed_actions)} actions recorded"
            )
            
            return ToolResult(
                success=True,
                output=summary,
                metadata={
                    "manifest_path": self.output_path,
                    "endpoint_count": len(parsed_sitemap),
                    "surface_count": len(parsed_surfaces),
                    "recon_complete": True,
                },
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to save manifest: {str(e)}",
            )
    
    def _get_step_count(self) -> int:
        """Get step count from context if available."""
        if self.context:
            try:
                return len(self.context.current_frame.tool_calls)
            except Exception:
                pass
        return 0
    
    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "sitemap": {
                        "type": "array",
                        "description": "List of discovered endpoints",
                        "items": {
                            "type": "object",
                            "properties": {
                                "url": {"type": "string", "description": "Full URL"},
                                "method": {"type": "string", "description": "HTTP method"},
                                "parameters": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Query/body parameters",
                                },
                                "content_type": {"type": "string"},
                                "notes": {"type": "string"},
                            },
                            "required": ["url"],
                        },
                    },
                    "attack_surfaces": {
                        "type": "array",
                        "description": "Potential attack surfaces identified",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Short name"},
                                "surface_type": {
                                    "type": "string",
                                    "enum": [t.value for t in AttackSurfaceType],
                                    "description": "Category of attack surface",
                                },
                                "location": {"type": "string", "description": "URL or endpoint"},
                                "risk_level": {
                                    "type": "string",
                                    "enum": [r.value for r in RiskLevel],
                                    "description": "Assessed risk",
                                },
                                "description": {"type": "string", "description": "Details"},
                                "evidence": {"type": "string", "description": "Supporting evidence"},
                            },
                            "required": ["name", "surface_type", "location", "description"],
                        },
                    },
                    "technologies": {
                        "type": "array",
                        "description": "Technologies detected on target",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "version": {"type": "string"},
                                "category": {"type": "string"},
                                "confidence": {"type": "string"},
                            },
                            "required": ["name", "category"],
                        },
                    },
                    "actions": {
                        "type": "array",
                        "description": "List of recon actions taken",
                        "items": {
                            "type": "object",
                            "properties": {
                                "action_type": {
                                    "type": "string",
                                    "enum": [a.value for a in ActionType],
                                },
                                "tool_used": {"type": "string"},
                                "target": {"type": "string"},
                                "result_summary": {"type": "string"},
                            },
                            "required": ["action_type", "tool_used", "target", "result_summary"],
                        },
                    },
                    "notes": {
                        "type": "string",
                        "description": "General observations from reconnaissance",
                    },
                },
                "required": ["sitemap", "attack_surfaces"],
            },
        )
