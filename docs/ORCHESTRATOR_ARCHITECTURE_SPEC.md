# Orchestrator Architecture Specification

This document specifies the architecture for transitioning Tempo Sec to an orchestrator-based multi-agent system with shared findings.

> **Status**: Phase 3 Complete - OrchestratorAgent and CLI Integration
> **Last Updated**: 2025-12-27

---

## Executive Summary

The current system uses independent agents (ReconAgent, TestCycleAgent) that run sequentially via CLI. This specification proposes an **OrchestratorAgent** that dynamically dispatches specialized subagents based on analysis needs, with all agents contributing to a **shared FindingsDocument**.

### Key Benefits

| Benefit | Description |
|---------|-------------|
| **Autonomous Analysis** | Orchestrator decides when to recon, test, or reflect |
| **Parallel Testing** | Multiple attack surfaces can be tested concurrently |
| **Shared Knowledge** | Findings persist across all subagent invocations |
| **Modularity** | Easy to add new specialized subagents |
| **Efficiency** | Avoid redundant work through shared state |

---

## Current Architecture

```mermaid
flowchart LR
    CLI["CLI Runner"]
    CLI --> R["ReconAgent"]
    CLI --> T["TestCycleAgent"]
    R --> M["Manifest File"]
    M --> T
    T --> F["Final Output"]
    
    subgraph "Sub-agent (existing)"
        B["BrowserAgent"]
    end
    R -.->|"visual_browser_task"| B
    T -.->|"visual_browser_task"| B
```

**Current Limitations:**
1. Sequential execution only (recon → test)
2. No dynamic decision-making about what to investigate
3. Findings not shared between runs (only manifest transfer)
4. Manual intervention required to restart or redirect analysis

---

## Proposed Architecture

```mermaid
flowchart TB
    subgraph Orchestrator["OrchestratorAgent"]
        O["Orchestrator Loop"]
        FD["FindingsDocument (Shared)"]
    end
    
    subgraph Subagents["Specialized Subagents"]
        RA["ReconSubagent"]
        TA["TestSubagent"]
        BA["BrowserAgent (existing)"]
        VA["ValidationSubagent (future)"]
    end
    
    O -->|"dispatch_subagent"| RA
    O -->|"dispatch_subagent"| TA
    O -->|"dispatch_subagent"| VA
    TA -->|"visual_browser_task"| BA
    RA -->|"visual_browser_task"| BA
    
    RA -->|"update_findings"| FD
    TA -->|"update_findings"| FD
    VA -->|"update_findings"| FD
    
    FD -->|"read on dispatch"| RA
    FD -->|"read on dispatch"| TA
    FD -->|"read on dispatch"| VA
```

### Core Concepts

| Concept | Description |
|---------|-------------|
| **OrchestratorAgent** | Top-level agent that plans, dispatches, and synthesizes |
| **Subagent** | Specialized agent for a specific task (recon, test, validate) |
| **FindingsDocument** | Persistent, structured document updated by all agents |
| **Dispatch Tool** | Tool for orchestrator to invoke subagents |
| **Completion Tool** | Tool for subagents to report back to orchestrator |

---

## Detailed Component Specifications

### 1. FindingsDocument

A structured, persistent document that accumulates knowledge across all agent interactions.

#### Location

```
/Users/nathanwang/Projects/tempo-sec-2/tempo/findings/
├── __init__.py
├── document.py        # FindingsDocument class
├── schema.py          # Pydantic models for findings
└── persistence.py     # JSON/YAML serialization
```

#### Schema Design

```python
# tempo/findings/schema.py

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from enum import Enum

class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

class FindingStatus(str, Enum):
    SUSPECTED = "suspected"      # Hypothesis, not yet tested
    CONFIRMED = "confirmed"      # Validated vulnerability
    FALSE_POSITIVE = "false_positive"
    NEEDS_MANUAL = "needs_manual_verification"

class AttackSurface(BaseModel):
    """A potential attack surface identified during recon."""
    id: str
    surface_type: str           # endpoint, form, api, websocket, etc.
    url: str
    description: str
    parameters: list[str] = []
    technology_hints: list[str] = []
    tested: bool = False
    priority: str = "medium"
    discovered_at: datetime
    discovered_by: str          # Agent that found it

class Finding(BaseModel):
    """A security finding (vulnerability or observation)."""
    id: str
    title: str
    severity: Severity
    status: FindingStatus
    attack_surface_id: str | None = None
    description: str
    evidence: str
    reproduction_steps: list[str] = []
    remediation: str = ""
    discovered_at: datetime
    discovered_by: str          # Agent that found it
    validated_by: str | None = None
    
class ReconSummary(BaseModel):
    """Summary of reconnaissance results."""
    target_domain: str
    technologies: list[str] = []
    endpoints_discovered: int = 0
    forms_discovered: int = 0
    apis_discovered: int = 0
    notes: list[str] = []

class FindingsDocumentSchema:
    """
    Root schema for the findings document.
    
    Persisted as YAML for token efficiency and human readability.
    """
    version: str = "1.0"
    target: str = ""
    created_at: datetime = None
    updated_at: datetime = None
    
    # Accumulated data
    recon_summary: ReconSummary | None = None
    attack_surfaces: list[AttackSurface] = []
    findings: list[Finding] = []
    
    # Tracking
    agents_invoked: list[str] = []
    total_steps_taken: int = 0
```

#### FindingsDocument Class

```python
# tempo/findings/document.py

from pathlib import Path
from datetime import datetime
from tempo.findings.schema import (
    FindingsDocumentSchema,
    AttackSurface,
    Finding,
    ReconSummary,
)

class FindingsDocument:
    """
    Thread-safe, persistent findings document.
    
    Used by all agents to read/write shared findings.
    Follows the project's dependency rules - lives in its own module,
    no imports from tools/prompts/context.
    """
    
    def __init__(self, target: str, path: Path | None = None):
        self._path = path or Path(f"./findings/{target.replace('.', '_')}.json")
        self._data = FindingsDocumentSchema(
            target=target,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    
    @classmethod
    def load(cls, path: Path) -> "FindingsDocument":
        """Load from existing file."""
        ...
    
    def save(self) -> None:
        """Persist to disk."""
        self._data.updated_at = datetime.utcnow()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(self._data.model_dump_json(indent=2))
    
    # === Query Methods ===
    
    def get_untested_surfaces(self, limit: int = 5) -> list[AttackSurface]:
        """Get attack surfaces that haven't been tested yet."""
        ...
    
    def get_findings_by_severity(self, severity: str) -> list[Finding]:
        """Get findings filtered by severity."""
        ...
    
    def get_summary(self) -> str:
        """Get a text summary for agent context."""
        ...
    
    # === Update Methods ===
    
    def add_attack_surface(self, surface: AttackSurface) -> None:
        """Add a new attack surface."""
        ...
    
    def add_finding(self, finding: Finding) -> None:
        """Add a new finding."""
        ...
    
    def mark_surface_tested(self, surface_id: str, tested_by: str) -> None:
        """Mark an attack surface as tested."""
        ...
    
    def update_recon_summary(self, summary: ReconSummary) -> None:
        """Update recon summary."""
        ...
```

---

### 2. OrchestratorAgent

The top-level agent that coordinates all analysis.

#### Location

```
tempo/agents/orchestrator.py
```

#### Design

```python
# tempo/agents/orchestrator.py

@register_agent
class OrchestratorAgent(BaseAgentDefinition):
    """
    Orchestrator agent that coordinates security analysis.
    
    Responsibilities:
    - Decides what analysis is needed next
    - Dispatches specialized subagents
    - Synthesizes findings into final report
    - Determines when analysis is complete
    """
    
    _name = "orchestrator"
    _model = "anthropic/claude-sonnet-4.5-20250514"  # Smartest model for planning
    _initial_phase = Phase.RECON  # Starts in recon
    
    def __init__(
        self,
        target: str,
        findings_path: str | None = None,
        max_iterations: int = 10,
        **kwargs,
    ):
        self.target = target
        self._findings_path = findings_path
        self._max_iterations = max_iterations
        self._findings: FindingsDocument | None = None
    
    @property
    def findings(self) -> FindingsDocument:
        """Lazy-load or create findings document."""
        if self._findings is None:
            if self._findings_path and Path(self._findings_path).exists():
                self._findings = FindingsDocument.load(Path(self._findings_path))
            else:
                self._findings = FindingsDocument(target=self.target)
        return self._findings
    
    def create_tools(self, context, container=None, workflow=None, **kwargs):
        tools = ToolRegistry()
        
        # Analysis tools - orchestrator can also do lightweight analysis
        tools.register(ShellTool(container_manager=container))
        tools.register(FileReadTool(container_manager=container))
        tools.register(FileWriteTool(container_manager=container))
        
        # Subagent dispatch tools (THE KEY ADDITION)
        tools.register(DispatchSubagentTool(
            findings=self.findings,
            container_manager=container,
        ))
        
        # Findings management
        tools.register(ReadFindingsTool(findings=self.findings))
        tools.register(AddFindingTool(findings=self.findings))
        tools.register(AddAttackSurfaceTool(findings=self.findings))
        
        # Meta tools
        tools.register(SummarizeOutputTool(context_store=context))
        tools.register(FinalizeAnalysisTool(findings=self.findings))
        
        return tools
    
    def build_objective(self, target: str | None = None, **kwargs) -> str:
        target = target or self.target
        findings_summary = self.findings.get_summary()
        
        return f"""## Security Analysis Orchestration

**Target:** {target}

### Your Role
You are the orchestrator for a comprehensive security analysis. Your job is to:
1. **Assess** the current state of knowledge (see findings below)
2. **Decide** what analysis is needed next
3. **Dispatch** specialized subagents to perform specific tasks
4. **Synthesize** results into actionable findings
5. **Determine** when the analysis is sufficiently complete

### Current Findings
{findings_summary if findings_summary else "No findings yet. Start with reconnaissance."}

### Available Subagents
- `recon`: Deep reconnaissance - crawling, technology fingerprinting, attack surface mapping
- `test`: Targeted security testing - test specific attack surfaces with specific hypotheses
- (future) `validate`: Validate and PoC confirmed findings

### Decision Framework
1. If little is known about the target → dispatch recon subagent
2. If attack surfaces exist but are untested → dispatch test subagent(s)
3. If critical findings need validation → dispatch validation subagent
4. If coverage is sufficient → finalize analysis

### Output
When analysis is complete, call `finalize_analysis` with a comprehensive report.
"""
```

---

### 3. Subagent Dispatch Mechanism

The key architectural piece - how the orchestrator invokes subagents.

#### Location

```
tempo/tools/dispatch_subagent.py
```

#### Design

```python
# tempo/tools/dispatch_subagent.py

class DispatchSubagentTool(Tool):
    """
    Dispatch a specialized subagent to perform a focused task.
    
    This is the orchestrator's primary mechanism for delegating work.
    Each subagent runs independently but shares the FindingsDocument.
    """
    
    name = "dispatch_subagent"
    description = """Dispatch a specialized subagent to perform a focused task.

Available subagents:
- recon: Performs deep reconnaissance on a target or specific area
- test: Tests specific attack surfaces for vulnerabilities

The subagent will:
1. Receive the current findings as context
2. Execute its specialized workflow
3. Update the findings document with any discoveries
4. Return a summary of what was accomplished

Use this when you need focused, specialized analysis that benefits from
a dedicated agent workflow."""
    
    category = ToolCategory.META
    
    def __init__(
        self,
        findings: FindingsDocument,
        container_manager: "ContainerManager | None" = None,
    ):
        self._findings = findings
        self._container = container_manager
    
    async def execute(
        self,
        subagent_type: str,
        objective: str,
        focus_area: str = "",
        max_steps: int = 50,
        **kwargs,
    ) -> ToolResult:
        """
        Execute a subagent.
        
        Args:
            subagent_type: Type of subagent (recon, test)
            objective: What the subagent should accomplish
            focus_area: Optional focus area (URL, attack surface ID, etc.)
            max_steps: Maximum steps for subagent
        """
        # Get subagent class
        subagent_class = self._get_subagent_class(subagent_type)
        if not subagent_class:
            return ToolResult(
                success=False,
                error=f"Unknown subagent type: {subagent_type}",
            )
        
        # Create subagent with findings reference
        subagent = subagent_class(
            objective=objective,
            focus_area=focus_area,
            findings=self._findings,
        )
        
        # Create isolated context
        subagent_context = ContextStore()
        
        # Create tools
        tools = subagent.create_tools(
            context=subagent_context,
            container=self._container,
        )
        
        # Create and run agent
        from tempo.infra.llm import LiteLLMClient
        llm = LiteLLMClient(model=subagent.model)
        
        config = AgentConfig(
            model=subagent.model,
            max_total_steps=max_steps,
        )
        
        prompts = PromptBuilder()
        system_prompt = subagent.build_system_prompt(
            prompts=prompts,
            tool_schemas=tools.get_schemas(),
            scope_description=f"Security analysis of {self._findings._data.target}",
        )
        
        from tempo.context.frame import MessageRole
        subagent_context.add_message(MessageRole.SYSTEM, system_prompt)
        
        agent = Agent(
            config=config,
            llm=llm,
            tools=tools,
            context=subagent_context,
        )
        
        # Build objective with findings context
        full_objective = subagent.build_objective()
        
        try:
            result = await agent.run(
                objective=full_objective,
                max_steps=max_steps,
            )
            
            # Save findings (subagent may have updated them)
            self._findings.save()
            
            return ToolResult(
                success=result.success,
                output=self._format_subagent_result(subagent_type, result),
                metadata={
                    "subagent_type": subagent_type,
                    "steps_taken": result.steps_taken,
                    "findings_count": len(result.findings),
                },
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output=f"Subagent execution failed: {str(e)}",
                error=str(e),
            )
    
    def _get_subagent_class(self, subagent_type: str):
        """Get the subagent class by type."""
        from tempo.agents import get_agent
        
        mapping = {
            "recon": "recon_subagent",
            "test": "test_subagent",
        }
        
        agent_name = mapping.get(subagent_type)
        if agent_name:
            return get_agent(agent_name)
        return None
    
    def _format_subagent_result(self, subagent_type: str, result) -> str:
        """Format subagent result for orchestrator."""
        parts = [
            f"## {subagent_type.title()} Subagent Completed",
            f"**Steps taken:** {result.steps_taken}",
            f"**Success:** {result.success}",
        ]
        
        if result.findings:
            parts.append(f"**New findings:** {len(result.findings)}")
            for f in result.findings[:5]:  # Show first 5
                parts.append(f"- {f.get('title', 'Untitled')}")
        
        if result.error:
            parts.append(f"**Error:** {result.error}")
        
        return "\n".join(parts)
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "subagent_type": {
                        "type": "string",
                        "enum": ["recon", "test"],
                        "description": "Type of subagent to dispatch",
                    },
                    "objective": {
                        "type": "string",
                        "description": "What the subagent should accomplish",
                    },
                    "focus_area": {
                        "type": "string",
                        "description": "Optional: specific area to focus on (URL, attack surface ID)",
                    },
                    "max_steps": {
                        "type": "integer",
                        "description": "Maximum steps for subagent (default: 50)",
                        "default": 50,
                    },
                },
                "required": ["subagent_type", "objective"],
            },
        )
```

---

### 4. Specialized Subagents

Refactored versions of existing agents designed to work with the orchestrator.

#### ReconSubagent

```python
# tempo/agents/recon_subagent.py

@register_agent
class ReconSubagent(BaseAgentDefinition):
    """
    Reconnaissance subagent for deep target analysis.
    
    Unlike the standalone ReconAgent, this:
    - Receives findings as input context
    - Updates the shared FindingsDocument
    - Reports back to orchestrator
    """
    
    _name = "recon_subagent"
    _model = "openai/gpt-5-mini"  # Fast model for subagent tasks
    _initial_phase = Phase.RECON
    
    def __init__(
        self,
        objective: str,
        findings: FindingsDocument,
        focus_area: str = "",
        **kwargs,
    ):
        self.objective = objective
        self.focus_area = focus_area
        self._findings = findings
    
    def create_tools(self, context, container=None, workflow=None, **kwargs):
        tools = ToolRegistry()
        
        # Core tools
        tools.register(ShellTool(container_manager=container))
        tools.register(FileReadTool(container_manager=container))
        tools.register(FileWriteTool(container_manager=container))
        tools.register(BrowserTaskTool(container_manager=container))
        
        # Findings tools (write to shared document)
        tools.register(AddAttackSurfaceTool(findings=self._findings))
        tools.register(UpdateReconSummaryTool(findings=self._findings))
        
        # Meta
        tools.register(SummarizeOutputTool(context_store=context))
        tools.register(CompleteSubtaskTool())  # Signal completion
        
        return tools
    
    def build_objective(self, **kwargs) -> str:
        findings_summary = self._findings.get_summary()
        
        return f"""## Reconnaissance Task

**Objective:** {self.objective}

{"**Focus Area:** " + self.focus_area if self.focus_area else ""}

### Current Knowledge
{findings_summary if findings_summary else "No prior findings."}

### Your Task
Perform focused reconnaissance:
1. Crawl and map the target
2. Identify technologies and frameworks
3. Discover attack surfaces (endpoints, forms, APIs)
4. Add each discovered attack surface using `add_attack_surface`
5. When complete, call `complete_subtask` with a summary

### Important
- Focus on DISCOVERY, not exploitation
- Add ALL attack surfaces you find to the findings document
- Be thorough but efficient
"""
```

#### TestSubagent

```python
# tempo/agents/test_subagent.py

@register_agent
class TestSubagent(BaseAgentDefinition):
    """
    Testing subagent for vulnerability validation.
    
    Focused on testing specific attack surfaces with specific hypotheses.
    Updates findings with confirmed vulnerabilities.
    """
    
    _name = "test_subagent"
    _model = "openai/gpt-5-mini"  # Fast model for subagent tasks
    _initial_phase = Phase.TEST
    
    def __init__(
        self,
        objective: str,
        findings: FindingsDocument,
        focus_area: str = "",
        **kwargs,
    ):
        self.objective = objective
        self.focus_area = focus_area
        self._findings = findings
    
    def create_tools(self, context, container=None, workflow=None, **kwargs):
        tools = ToolRegistry()
        
        # Core tools
        tools.register(ShellTool(container_manager=container))
        tools.register(FileReadTool(container_manager=container))
        tools.register(FileWriteTool(container_manager=container))
        tools.register(BrowserTaskTool(container_manager=container))
        
        # Findings tools
        tools.register(AddFindingTool(findings=self._findings))
        tools.register(MarkSurfaceTestedTool(findings=self._findings))
        
        # Meta
        tools.register(SummarizeOutputTool(context_store=context))
        tools.register(CompleteSubtaskTool())
        
        return tools
    
    def build_objective(self, **kwargs) -> str:
        # Get relevant attack surfaces
        if self.focus_area:
            surfaces = [s for s in self._findings._data.attack_surfaces 
                       if s.id == self.focus_area or self.focus_area in s.url]
        else:
            surfaces = self._findings.get_untested_surfaces(limit=5)
        
        surfaces_text = "\n".join([
            f"- [{s.priority}] {s.surface_type}: {s.url}"
            for s in surfaces
        ]) if surfaces else "No specific attack surfaces assigned."
        
        return f"""## Security Testing Task

**Objective:** {self.objective}

### Attack Surfaces to Test
{surfaces_text}

### Your Task
1. Form specific, testable hypotheses for each attack surface
2. Execute tests to validate/disprove hypotheses
3. For confirmed vulnerabilities:
   - Add finding using `add_finding` with evidence
   - Mark the surface as tested
4. For negative results:
   - Still mark the surface as tested
5. Call `complete_subtask` when done

### Testing Guidelines
- Always test in a non-destructive manner
- Collect clear evidence for any findings
- Include reproduction steps
"""
```

---

### 5. Findings Tools

Tools for interacting with the shared findings document.

#### Location

```
tempo/tools/findings_tools.py
```

#### Design

```python
# tempo/tools/findings_tools.py

class ReadFindingsTool(Tool):
    """Read current findings summary."""
    name = "read_findings"
    description = "Get the current state of all findings and attack surfaces."
    
    def __init__(self, findings: FindingsDocument):
        self._findings = findings
    
    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(
            success=True,
            output=self._findings.get_summary(),
        )


class AddAttackSurfaceTool(Tool):
    """Add a discovered attack surface."""
    name = "add_attack_surface"
    description = "Add a newly discovered attack surface to the findings."
    
    async def execute(
        self,
        surface_type: str,
        url: str,
        description: str,
        parameters: list[str] = None,
        priority: str = "medium",
        **kwargs,
    ) -> ToolResult:
        surface = AttackSurface(
            id=str(uuid.uuid4()),
            surface_type=surface_type,
            url=url,
            description=description,
            parameters=parameters or [],
            priority=priority,
            discovered_at=datetime.utcnow(),
            discovered_by=kwargs.get("agent_name", "unknown"),
        )
        self._findings.add_attack_surface(surface)
        self._findings.save()
        
        return ToolResult(
            success=True,
            output=f"Added attack surface: {surface_type} at {url}",
            metadata={"surface_id": surface.id},
        )


class AddFindingTool(Tool):
    """Add a security finding."""
    name = "add_finding"
    description = "Record a confirmed or suspected security finding."
    
    async def execute(
        self,
        title: str,
        severity: str,
        status: str,
        description: str,
        evidence: str,
        attack_surface_id: str = None,
        reproduction_steps: list[str] = None,
        **kwargs,
    ) -> ToolResult:
        finding = Finding(
            id=str(uuid.uuid4()),
            title=title,
            severity=Severity(severity),
            status=FindingStatus(status),
            attack_surface_id=attack_surface_id,
            description=description,
            evidence=evidence,
            reproduction_steps=reproduction_steps or [],
            discovered_at=datetime.utcnow(),
            discovered_by=kwargs.get("agent_name", "unknown"),
        )
        self._findings.add_finding(finding)
        self._findings.save()
        
        return ToolResult(
            success=True,
            output=f"Added {severity} finding: {title}",
            metadata={"finding_id": finding.id},
        )


class MarkSurfaceTestedTool(Tool):
    """Mark an attack surface as tested."""
    name = "mark_surface_tested"
    
    async def execute(self, surface_id: str, **kwargs) -> ToolResult:
        self._findings.mark_surface_tested(
            surface_id, 
            tested_by=kwargs.get("agent_name", "unknown"),
        )
        self._findings.save()
        return ToolResult(success=True, output=f"Marked {surface_id} as tested")
```

---

### 6. Subagent Completion Mechanism

#### Location

```
tempo/tools/complete_subtask.py
```

#### Design

```python
# tempo/tools/complete_subtask.py

class CompleteSubtaskTool(Tool):
    """
    Signal that a subagent has completed its task.
    
    Similar to the existing CompleteBrowserTaskTool, but for
    orchestrated subagents.
    """
    
    name = "complete_subtask"
    description = """Signal that you have completed your assigned subtask.

Call this when you have:
1. Completed the assigned objective
2. Added all relevant findings/surfaces to the shared document
3. Are ready to return control to the orchestrator

Provide a summary of what was accomplished and any important observations."""
    
    category = ToolCategory.META
    
    async def execute(
        self,
        summary: str,
        surfaces_added: int = 0,
        findings_added: int = 0,
        notes: str = "",
        **kwargs,
    ) -> ToolResult:
        """
        Complete the subtask.
        
        The runner will detect this special tool and terminate the subagent.
        """
        return ToolResult(
            success=True,
            output=f"Subtask completed: {summary}",
            metadata={
                "subtask_complete": True,  # Signal to runner
                "summary": summary,
                "surfaces_added": surfaces_added,
                "findings_added": findings_added,
                "notes": notes,
            },
        )
```

---

## File Structure

Complete proposed file structure:

```
tempo/
├── agents/
│   ├── __init__.py           # Agent registry (update)
│   ├── base.py               # BaseAgentDefinition (no changes)
│   ├── browser.py            # BrowserAgent (no changes)
│   ├── recon.py              # ReconAgent (keep for standalone use)
│   ├── test_cycle.py         # TestCycleAgent (keep for standalone use)
│   ├── orchestrator.py       # NEW: OrchestratorAgent
│   ├── recon_subagent.py     # NEW: ReconSubagent
│   └── test_subagent.py      # NEW: TestSubagent
│
├── findings/                  # NEW module
│   ├── __init__.py
│   ├── schema.py             # Pydantic models
│   ├── document.py           # FindingsDocument class
│   └── persistence.py        # JSON serialization
│
├── tools/
│   ├── ...                   # Existing tools
│   ├── dispatch_subagent.py  # NEW: Dispatch tool
│   ├── findings_tools.py     # NEW: Findings manipulation tools
│   └── complete_subtask.py   # NEW: Subtask completion tool
│
├── prompts/
│   └── templates/
│       ├── ...               # Existing templates
│       └── orchestrator.txt  # NEW: Orchestrator system prompt
│
└── scripts/
    └── run.py                # Update to support orchestrator
```

---

## Dependency Rules Compliance

This design strictly follows the project's dependency rules:

```
                    ┌──────────────┐
                    │ OrchestratorAgent │
                    └───────┬──────┘
                            │ depends on
         ┌──────────────────┼──────────────────┐
         ▼                  ▼                  ▼
    ┌─────────┐       ┌──────────┐       ┌─────────┐
    │ Context │       │  Prompts │       │  Tools  │
    └─────────┘       └──────────┘       └─────────┘
         │                  │                  │
         ▼                  ▼                  ▼
    ┌─────────────────────────────────────────────┐
    │                   Infra                      │
    │  (includes FindingsDocument as new module)   │
    └─────────────────────────────────────────────┘
```

**Key Points:**
- `FindingsDocument` lives in `findings/` (sibling to `infra/`)
- Tools can import from `findings/` (same level as `infra/`)
- Agents compose everything together
- No circular dependencies

---

## Protocol Additions

New protocols for `tempo/infra/protocols.py`:

```python
# New additions to protocols.py

class SubagentDispatcher(Protocol):
    """Protocol for components that can dispatch subagents."""
    
    async def dispatch(
        self,
        subagent_type: str,
        objective: str,
        **kwargs,
    ) -> Any:
        """Dispatch a subagent with the given objective."""
        ...


class FindingsUpdater(Protocol):
    """Protocol for components that can update findings."""
    
    def add_finding(self, finding: dict) -> str:
        """Add a finding, return its ID."""
        ...
    
    def add_attack_surface(self, surface: dict) -> str:
        """Add an attack surface, return its ID."""
        ...
    
    def get_summary(self) -> str:
        """Get current findings summary."""
        ...
```

---

## Configuration

Add orchestrator configuration to `config.toml`:

```toml
[orchestrator]
# Maximum iterations for orchestrator loop
max_iterations = 10

# Default max steps per subagent dispatch
default_subagent_steps = 50

# Model for orchestrator (uses smarter model)
model = "anthropic/claude-sonnet-4-20250514"

# Model for subagents (faster model)
subagent_model = "openai/gpt-4o-mini"

[orchestrator.auto_dispatch]
# Automatically dispatch recon if no attack surfaces
auto_recon = true

# Maximum concurrent subagents (future)
max_concurrent = 3
```

---

## CLI Interface

Update `tempo/scripts/run.py`:

```bash
# Run orchestrator (new recommended workflow)
tempo orchestrator \
    --target https://example.com \
    --findings ./findings/example.json \
    --max-iterations 10

# Still support standalone agents
tempo recon --target https://example.com
tempo test_cycle --manifest ./manifests/example.json
```

---

## Migration Path

### Phase 1: Foundations (Non-Breaking) - COMPLETE
1. [x] Create `tempo/findings/` module with schema and document
2. [x] Add findings tools to `tempo/tools/`
3. [x] Add protocols to `protocols.py`
4. [x] Write tests for findings module

### Phase 2: Subagents (Non-Breaking) - COMPLETE
1. [x] Create `ReconSubagent` and `TestSubagent`
2. [x] Create `DispatchSubagentTool` and `CompleteSubtaskTool`
3. [x] Add subagent prompts
4. [x] Write integration tests

### Phase 3: Orchestrator (New Feature) - COMPLETE
1. [x] Create `OrchestratorAgent`
2. [x] Create `FinalizeAnalysisTool`
3. [x] Update CLI to support orchestrator command (--findings, --max-iterations)
4. [x] Update step_handler for finalize_analysis
5. [x] Write unit and integration tests
6. [x] Update documentation

### Phase 4: Enhancements (Future)
1. Parallel subagent dispatch
2. ValidationSubagent
3. ExploitSubagent
4. Progress visualization in UI

---

## Testing Strategy

### Unit Tests

```
tests/
├── findings/
│   ├── test_schema.py        # Schema validation
│   ├── test_document.py      # FindingsDocument operations
│   └── test_persistence.py   # Save/load
│
├── tools/
│   ├── test_dispatch_subagent.py
│   ├── test_findings_tools.py
│   └── test_complete_subtask.py
│
└── agents/
    ├── test_orchestrator.py
    ├── test_recon_subagent.py
    └── test_test_subagent.py
```

### Integration Tests

```python
# tests/integration/test_orchestrator_flow.py

@pytest.mark.asyncio
async def test_orchestrator_dispatches_recon():
    """Orchestrator should dispatch recon when no findings exist."""
    ...

@pytest.mark.asyncio
async def test_orchestrator_dispatches_test_after_recon():
    """Orchestrator should dispatch test after surfaces are discovered."""
    ...

@pytest.mark.asyncio
async def test_findings_shared_between_subagents():
    """Findings from one subagent should be visible to another."""
    ...
```

---

## Design Decisions

The following decisions have been made:

| Decision | Choice | Rationale |
|----------|--------|----------|
| **Parallel Subagents** | Sequential in v1 | Simpler to implement and debug; parallel can be added later |
| **Findings Format** | YAML | More token-efficient, more human-readable |
| **Orchestrator Autonomy** | Auto-dispatch | Faster, more autonomous analysis |
| **Existing Agents** | Keep for now | Backward compatibility; remove in future PR |

### Parallel Subagents: Complexity Analysis

Adding parallel subagent support would require:

| Component | Sequential | Parallel | Delta |
|-----------|-----------|----------|-------|
| DispatchSubagentTool | ~50 LOC | ~120 LOC | +70 LOC |
| FindingsDocument | Simple writes | Locking/merging | +80 LOC |
| VisualizationCollector | Single stream | Multi-stream routing | +100 LOC |
| UI Agent Tree | Single path | Multiple branches | +150 LOC |
| Testing | Unit tests only | Concurrency tests | +200 LOC |
| **Total** | **Baseline** | **+600 LOC** | |

**Recommendation**: Start sequential, add parallel in Phase 4 when the orchestrator pattern is proven.

---

## Visualization Server Changes

The visualization server needs significant updates to support the orchestrator/subagent hierarchy.

### Current Architecture

```mermaid
flowchart LR
    A["Agent"] -->|"events"| VC["VisualizationCollector"]
    VC -->|"WebSocket"| VS["VisualizationServer"]
    VS -->|"broadcast"| UI["Web UI"]
    
    subgraph UI
        LP["Left Panel<br>Agent State"]
        CP["Center Panel<br>Graph View"]
        RP["Right Panel<br>Details"]
    end
```

### Proposed Architecture

```mermaid
flowchart TB
    subgraph Backend
        OA["OrchestratorAgent"] -->|"events"| OC["OrchestratorCollector"]
        OA -->|"dispatch"| SA1["ReconSubagent"]
        OA -->|"dispatch"| SA2["TestSubagent"]
        SA1 -->|"events"| SC1["SubagentCollector"]
        SA2 -->|"events"| SC2["SubagentCollector"]
        OC --> VS["VisualizationServer"]
        SC1 --> VS
        SC2 --> VS
    end
    
    subgraph Frontend
        VS -->|"WebSocket"| UI["Web UI"]
        UI --> AT["Agent Tree Panel"]
        UI --> GV["Graph View"]
        UI --> DP["Details Panel"]
    end
```

### UI Changes: Agent Tree Panel

Replace the current "Symbol Tree" left panel with a hierarchical **Agent Tree** that shows the orchestrator and all subagent runs.

#### Mockup

```
┌─────────────────────────────────────┐
│ AGENT TREE                          │
├─────────────────────────────────────┤
│ ▼ 🎯 Orchestrator (example.com)     │
│   ├─ Model: sonnet-4.5              │
│   ├─ Phase: COORDINATING            │
│   └─ Steps: 12                      │
│                                     │
│   ▼ 📡 Subagent: recon_1            │
│     ├─ Status: ✓ Complete           │
│     ├─ Steps: 8                     │
│     └─ Surfaces: 5 added            │
│                                     │
│   ▼ 🔬 Subagent: test_1             │
│     ├─ Status: ⏳ Running           │
│     ├─ Steps: 3/50                  │
│     └─ Findings: 1                  │
│                                     │
│   ▷ 🔬 Subagent: test_2             │
│     └─ Status: 📋 Queued            │
│                                     │
├─────────────────────────────────────┤
│ 📊 FINDINGS SUMMARY                 │
│   Critical: 0  High: 1  Medium: 2   │
│   Attack Surfaces: 12 (7 tested)    │
└─────────────────────────────────────┘
```

#### Interaction

- Clicking an agent/subagent switches the Graph View to show that agent's workflow
- The orchestrator shows dispatch_subagent tool calls
- Each subagent shows its own step/tool history
- Findings summary updates in real-time

### Backend Changes

#### 1. Event Schema Updates

Add new event types to `VisualizationCollector`:

```python
# tempo/visualization/collector.py

class VisualizationCollector:
    def on_subagent_start(
        self, 
        subagent_id: str,
        subagent_type: str,
        objective: str,
        parent_id: str | None = None,  # orchestrator ID
    ) -> None:
        """Called when a subagent is dispatched."""
        self.emit("subagent_start", {
            "subagent_id": subagent_id,
            "subagent_type": subagent_type,
            "objective": objective,
            "parent_id": parent_id,
        })
    
    def on_subagent_finish(
        self,
        subagent_id: str,
        success: bool,
        summary: str,
        findings_count: int,
        surfaces_count: int,
    ) -> None:
        """Called when a subagent completes."""
        self.emit("subagent_finish", {
            "subagent_id": subagent_id,
            "success": success,
            "summary": summary,
            "findings_count": findings_count,
            "surfaces_count": surfaces_count,
        })
    
    def on_findings_update(self, findings_summary: dict) -> None:
        """Called when findings document is updated."""
        self.emit("findings_update", findings_summary)
```

#### 2. Server Changes

Add endpoints for subagent data:

```python
# tempo/visualization/server.py

@app.get("/api/subagents")
async def list_subagents():
    """List all subagent runs for current session."""
    return {"subagents": self._subagent_registry}

@app.get("/api/subagent/{subagent_id}/context")
async def get_subagent_context(subagent_id: str):
    """Get context for a specific subagent."""
    # Each subagent has its own ContextStore
    context_store = self._subagent_contexts.get(subagent_id)
    if not context_store:
        return {"error": "Subagent not found"}
    return process_context_for_ui(context_store)
```

#### 3. Subagent Context Management

Track subagent contexts separately:

```python
# tempo/visualization/server.py

class VisualizationServer:
    def __init__(self, ...):
        # ... existing init ...
        self._subagent_contexts: dict[str, ContextStore] = {}
        self._subagent_registry: list[dict] = []
    
    def register_subagent(self, subagent_id: str, context: ContextStore, metadata: dict):
        """Register a subagent for visualization."""
        self._subagent_contexts[subagent_id] = context
        self._subagent_registry.append({
            "id": subagent_id,
            **metadata,
        })
```

### Frontend Changes

#### 1. New File: `agentTree.js`

```javascript
// tempo/visualization/ui/agentTree.js

import * as state from './state.js';

/**
 * Render the hierarchical agent tree in the left panel.
 */
export function render() {
    const container = document.getElementById('agent-tree-content');
    if (!container) return;
    
    const { orchestrator, subagents } = state.agentHierarchy;
    
    let html = `
        <div class="agent-node orchestrator ${orchestrator.active ? 'active' : ''}" 
             data-agent-id="${orchestrator.id}">
            <div class="agent-header">
                <span class="agent-icon">🎯</span>
                <span class="agent-name">Orchestrator</span>
            </div>
            <div class="agent-details">
                <div>Model: ${orchestrator.model}</div>
                <div>Steps: ${orchestrator.steps}</div>
            </div>
        </div>
    `;
    
    for (const subagent of subagents) {
        html += renderSubagentNode(subagent);
    }
    
    // Findings summary
    html += renderFindingsSummary(state.findingsSummary);
    
    container.innerHTML = html;
    attachEventListeners();
}

function renderSubagentNode(subagent) {
    const statusIcon = {
        'running': '⏳',
        'complete': '✓',
        'failed': '✗',
        'queued': '📋',
    }[subagent.status] || '?';
    
    const typeIcon = subagent.type === 'recon' ? '📡' : '🔬';
    
    return `
        <div class="agent-node subagent ${subagent.active ? 'active' : ''}" 
             data-agent-id="${subagent.id}">
            <div class="agent-header">
                <span class="agent-icon">${typeIcon}</span>
                <span class="agent-name">${subagent.name}</span>
                <span class="status-icon">${statusIcon}</span>
            </div>
            <div class="agent-details">
                <div>Steps: ${subagent.steps}</div>
                ${subagent.findings ? `<div>Findings: ${subagent.findings}</div>` : ''}
            </div>
        </div>
    `;
}

function attachEventListeners() {
    document.querySelectorAll('.agent-node').forEach(node => {
        node.addEventListener('click', () => {
            const agentId = node.dataset.agentId;
            switchToAgentView(agentId);
        });
    });
}

export function switchToAgentView(agentId) {
    // Update active state
    state.setActiveAgent(agentId);
    
    // Re-render tree with new active state
    render();
    
    // Load graph data for selected agent
    if (agentId === 'orchestrator') {
        graph.loadOrchestratorData();
    } else {
        graph.loadSubagentData(agentId);
    }
}
```

#### 2. State Updates

```javascript
// tempo/visualization/ui/state.js additions

export const agentHierarchy = {
    orchestrator: {
        id: 'orchestrator',
        model: '',
        steps: 0,
        active: true,
    },
    subagents: [],
};

export const findingsSummary = {
    critical: 0,
    high: 0,
    medium: 0,
    low: 0,
    surfaces_total: 0,
    surfaces_tested: 0,
};

export function addSubagent(subagentData) {
    agentHierarchy.subagents.push({
        id: subagentData.subagent_id,
        type: subagentData.subagent_type,
        name: `${subagentData.subagent_type}_${agentHierarchy.subagents.length + 1}`,
        status: 'running',
        steps: 0,
        findings: 0,
        active: false,
    });
}

export function updateSubagent(subagentId, updates) {
    const subagent = agentHierarchy.subagents.find(s => s.id === subagentId);
    if (subagent) {
        Object.assign(subagent, updates);
    }
}

export function setActiveAgent(agentId) {
    agentHierarchy.orchestrator.active = (agentId === 'orchestrator');
    agentHierarchy.subagents.forEach(s => {
        s.active = (s.id === agentId);
    });
}
```

#### 3. Event Handler Updates

```javascript
// tempo/visualization/ui/events.js additions

import * as agentTree from './agentTree.js';

// Add handlers for new event types
case 'subagent_start':
    state.addSubagent(msg.data);
    agentTree.render();
    break;

case 'subagent_finish':
    state.updateSubagent(msg.data.subagent_id, {
        status: msg.data.success ? 'complete' : 'failed',
        findings: msg.data.findings_count,
    });
    agentTree.render();
    break;

case 'findings_update':
    Object.assign(state.findingsSummary, msg.data);
    agentTree.render();
    break;
```

#### 4. HTML Updates

```html
<!-- tempo/visualization/ui/index.html updates -->

<!-- Replace Symbol Tree section with Agent Tree -->
<div class="pane left-pane">
    <div class="pane-header">
        <span class="pane-title">AGENT TREE</span>
    </div>
    <div class="pane-content scrollable">
        <div id="agent-tree-content" class="agent-tree">
            <!-- Dynamically populated by agentTree.js -->
        </div>
        
        <!-- Keep existing sections below the tree -->
        <div class="tree-section expanded">
            <div class="section-header">▼ Run Cost</div>
            <!-- ... existing cost content ... -->
        </div>
    </div>
</div>
```

#### 5. CSS Additions

```css
/* tempo/visualization/ui/style.css additions */

.agent-tree {
    padding: 10px;
}

.agent-node {
    background: #1e1e1e;
    border: 1px solid #333;
    border-radius: 6px;
    margin-bottom: 8px;
    padding: 10px;
    cursor: pointer;
    transition: all 0.2s ease;
}

.agent-node:hover {
    border-color: #555;
    background: #252525;
}

.agent-node.active {
    border-color: var(--accent-blue);
    background: rgba(0, 122, 204, 0.1);
}

.agent-node.orchestrator .agent-header {
    color: var(--accent-orange);
}

.agent-node.subagent {
    margin-left: 20px;
    font-size: 0.9em;
}

.agent-header {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 600;
}

.agent-icon {
    font-size: 16px;
}

.status-icon {
    margin-left: auto;
}

.agent-details {
    margin-top: 6px;
    font-size: 11px;
    color: #888;
}

.findings-summary {
    margin-top: 16px;
    padding: 12px;
    background: #1a1a1a;
    border-radius: 6px;
    border: 1px solid #333;
}

.findings-summary-title {
    font-size: 11px;
    color: #888;
    margin-bottom: 8px;
    text-transform: uppercase;
}

.findings-counts {
    display: flex;
    gap: 12px;
}

.finding-badge {
    font-size: 12px;
    padding: 2px 8px;
    border-radius: 4px;
}

.finding-badge.critical { background: #d32f2f; }
.finding-badge.high { background: #f57c00; }
.finding-badge.medium { background: #ffc107; color: #000; }
.finding-badge.low { background: #4caf50; }
```

### File Structure for Visualization Changes

```
tempo/visualization/
├── collector.py           # MODIFY: Add subagent events
├── server.py              # MODIFY: Add subagent registry, endpoints
├── subagent_tracker.py    # NEW: Track subagent states
└── ui/
    ├── index.html         # MODIFY: Update left panel structure
    ├── style.css          # MODIFY: Add agent tree styles
    ├── state.js           # MODIFY: Add agent hierarchy state
    ├── events.js          # MODIFY: Handle new event types
    ├── agentTree.js       # NEW: Agent tree rendering
    ├── graph.js           # MODIFY: Support agent switching
    └── ... (other files unchanged)
```

---

## Success Criteria

The refactor is successful when:

- [ ] Orchestrator can complete a full analysis autonomously
- [ ] Findings persist in YAML and accumulate across subagent runs
- [ ] Adding a new subagent type requires < 100 lines of code
- [ ] All existing tests pass
- [ ] New integration tests cover orchestrator flow
- [ ] Visualization shows orchestrator and subagent hierarchy
- [ ] Switching between agents in the UI shows correct context
- [ ] Findings summary updates in real-time
- [ ] Documentation updated

---

## References

- [AGENTS.md](../AGENTS.md) - Project principles
- [ARCHITECTURE.md](ARCHITECTURE.md) - Current architecture
- [WORKFLOW.md](WORKFLOW.md) - Phase workflow
- [TOOLS.md](TOOLS.md) - Tool specifications
