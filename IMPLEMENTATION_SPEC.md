# Tempo Sec: Implementation Plan

## Executive Summary

Tempo Sec is a cybersecurity agent designed for discovering novel vulnerabilities through deliberate context management, human-like workflow emulation, and minimal but powerful tooling. This document provides the complete implementation specification.

**Core Innovation**: Unlike typical agents that treat context as an opaque message list, Tempo Sec makes context a first-class, mutable data structure with branching, summarization, and rollback capabilities.

---

## Table of Contents

1. [Architectural Principles](#1-architectural-principles)
2. [Component Architecture](#2-component-architecture)
3. [Project Structure](#3-project-structure)
4. [Data Models](#4-data-models)
5. [Component Specifications](#5-component-specifications)
6. [Implementation Order](#6-implementation-order)
7. [Dependencies](#7-dependencies)
8. [Example Usage](#8-example-usage)

---

## 1. Architectural Principles

### 1.1 Why This Architecture?

The design follows an "MVC for Agents" pattern, separating concerns into four independent primitives:

| Component | Responsibility | Rationale |
|-----------|---------------|-----------|
| **Context** | State management, history, branching | Enables the core innovation: mutable, branchable context |
| **Prompts** | LLM instruction formatting | Separates "what to say" from "how to act" |
| **Tools** | Capability execution | Isolates side effects from orchestration logic |
| **Agent** | Orchestration and composition | Single place where primitives are combined |

### 1.2 Design Goals

1. **Maximize Cohesion**: Each component has a single, clear responsibility
2. **Minimize Coupling**: Components have zero dependencies on each other; only Agent composes them
3. **Enable Testing**: Each component can be unit tested in isolation
4. **Support Extension**: New tools, prompts, or context backends can be added without modifying other components

### 1.3 Dependency Rules

```
                    ┌─────────┐
                    │  Agent  │
                    └────┬────┘
                         │ depends on
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
     ┌─────────┐   ┌──────────┐   ┌─────────┐
     │ Context │   │  Prompts │   │  Tools  │
     └─────────┘   └──────────┘   └─────────┘
          │              │              │
          ▼              ▼              ▼
     ┌─────────┐   ┌──────────┐   ┌─────────┐
     │  Infra  │   │  Infra   │   │  Infra  │
     └─────────┘   └──────────┘   └─────────┘
```

**Rule**: Context, Prompts, and Tools MUST NOT import from each other. They may only import from `infra/` or external packages.

---

## 2. Component Architecture

### 2.1 Context Component

Manages the agent's state as a tree of frames, enabling:
- **Checkpointing**: Save state at any point
- **Rollback**: Restore to a previous checkpoint
- **Branching**: Create parallel exploration paths (clones)
- **Merging**: Collect results from branches back into main context
- **Summarization**: Replace verbose tool outputs with compressed summaries

```
Frame 1 ─── Frame 2 ─── Frame 3 ─┬─ Frame 4a (branch)
                                 ├─ Frame 4b (branch)
                                 └─ Frame 4c (branch)
                                          │
                                          ▼ (merge summaries)
                                      Frame 5
```

### 2.2 Prompts Component

Manages instruction templates with:
- **System prompts**: Base agent identity and capabilities
- **Phase prompts**: Workflow-specific instructions (recon, hypothesize, test, reflect)
- **Dynamic injection**: Insert context summaries, tool schemas, phase state

### 2.3 Tools Component

Provides capabilities through:
- **Tool base class**: Common interface for all tools
- **Registry**: Discovery, schema generation, lookup by name
- **Built-in tools**: Shell, browser, filesystem, installer
- **Extensibility**: Easy addition of new tools

### 2.4 Agent Component

Orchestrates everything:
- **Run loop**: Prompt → LLM → Parse → Execute Tool → Summarize → Update Context
- **Workflow state machine**: Enforce phase transitions
- **Branch coordination**: Spawn clones, collect results, merge
- **Configuration**: Model selection, limits, behavior flags

### 2.5 Infra Component

Cross-cutting concerns:
- **LLM client**: Model-agnostic interface over LiteLLM + Instructor
- **Container manager**: Docker lifecycle for sandboxed execution
- **Logging**: Structured logging for debugging and analysis

---

## 3. Project Structure

```
tempo-sec/
├── tempo/
│   ├── __init__.py
│   │
│   ├── context/
│   │   ├── __init__.py             # Exports: ContextStore, ContextFrame, Message, ToolCall, BranchManager
│   │   ├── frame.py                # Data classes for frames, messages, tool calls
│   │   ├── store.py                # ContextStore class - main interface
│   │   ├── branch.py               # BranchManager - branching/merging logic
│   │   └── persistence.py          # JSON serialization, file I/O
│   │
│   ├── prompts/
│   │   ├── __init__.py             # Exports: PromptBuilder, Phase
│   │   ├── builder.py              # PromptBuilder class - assembles prompts
│   │   ├── phases.py               # Phase enum and phase configurations
│   │   └── templates/
│   │       ├── system.md           # Base system prompt
│   │       ├── recon.md            # Recon phase instructions
│   │       ├── hypothesize.md      # Hypothesis phase instructions
│   │       ├── test.md             # Testing phase instructions
│   │       ├── reflect.md          # Reflection phase instructions
│   │       └── summarize.md        # Tool output summarization prompt
│   │
│   ├── tools/
│   │   ├── __init__.py             # Exports: Tool, ToolResult, ToolRegistry
│   │   ├── base.py                 # Tool ABC, ToolResult dataclass
│   │   ├── registry.py             # ToolRegistry class
│   │   ├── shell.py                # ShellTool implementation
│   │   ├── browser.py              # BrowserTool implementation
│   │   ├── filesystem.py           # FileReadTool, FileWriteTool implementations
│   │   └── installer.py            # ToolInstallerTool implementation
│   │
│   ├── agent/
│   │   ├── __init__.py             # Exports: Agent, AgentConfig
│   │   ├── runner.py               # Agent class - main orchestration
│   │   ├── workflow.py             # WorkflowManager - phase state machine
│   │   ├── summarizer.py           # OutputSummarizer - compresses tool outputs
│   │   └── config.py               # AgentConfig dataclass
│   │
│   └── infra/
│       ├── __init__.py             # Exports: LLMClient, ContainerManager
│       ├── llm.py                  # LLMClient ABC + LiteLLMClient implementation
│       ├── container.py            # ContainerManager - Docker wrapper
│       └── logging.py              # Logging configuration
│
├── contexts/                       # Persisted context JSON files (gitignored)
│   └── .gitkeep
│
├── containers/
│   └── base/
│       └── Dockerfile              # Base container image
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Shared pytest fixtures
│   ├── context/
│   │   ├── __init__.py
│   │   ├── test_frame.py
│   │   ├── test_store.py
│   │   ├── test_branch.py
│   │   └── test_persistence.py
│   ├── prompts/
│   │   ├── __init__.py
│   │   ├── test_builder.py
│   │   └── test_phases.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── test_registry.py
│   │   ├── test_shell.py
│   │   └── test_filesystem.py
│   └── agent/
│       ├── __init__.py
│       ├── test_runner.py
│       └── test_workflow.py
│
├── examples/
│   ├── simple_scan.py              # Basic usage example
│   └── ctf_challenge.py            # Full CTF workflow example
│
├── pyproject.toml
├── config.toml                     # Configuration for API keys and scope
├── README.md
└── .gitignore
```

---

## 4. Data Models

### 4.1 Context Data Models

```python
# tempo/context/frame.py

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
import uuid


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL_RESULT = "tool_result"


@dataclass
class Message:
    """A single message in the conversation."""
    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        return cls(
            role=MessageRole(data["role"]),
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ToolCall:
    """Record of a tool invocation."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    raw_output: str = ""                    # Original output (preserved for reference)
    summary: str | None = None              # Compressed version (used in context if set)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    duration_ms: int = 0
    success: bool = True
    error: str | None = None
    
    @property
    def output_for_context(self) -> str:
        """Returns summary if available, otherwise raw output."""
        return self.summary if self.summary is not None else self.raw_output
    
    @property
    def tokens_saved(self) -> int:
        """Approximate tokens saved by summarization."""
        if self.summary is None:
            return 0
        # Rough estimate: 4 chars per token
        return (len(self.raw_output) - len(self.summary)) // 4
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "input": self.input,
            "raw_output": self.raw_output,
            "summary": self.summary,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error": self.error,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ToolCall":
        return cls(
            id=data["id"],
            tool_name=data["tool_name"],
            input=data["input"],
            raw_output=data["raw_output"],
            summary=data.get("summary"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            duration_ms=data["duration_ms"],
            success=data["success"],
            error=data.get("error"),
        )


@dataclass
class AgentState:
    """Working memory for the agent - hypotheses, notes, findings."""
    current_phase: str = "recon"
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    custom: dict[str, Any] = field(default_factory=dict)  # Extensible state
    
    def to_dict(self) -> dict:
        return {
            "current_phase": self.current_phase,
            "hypotheses": self.hypotheses,
            "findings": self.findings,
            "notes": self.notes,
            "custom": self.custom,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AgentState":
        return cls(
            current_phase=data.get("current_phase", "recon"),
            hypotheses=data.get("hypotheses", []),
            findings=data.get("findings", []),
            notes=data.get("notes", []),
            custom=data.get("custom", {}),
        )


@dataclass
class ContextFrame:
    """
    A snapshot of the agent's context at a point in time.
    Forms nodes in the context tree.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_id: str | None = None            # None for root frame
    created_at: datetime = field(default_factory=datetime.utcnow)
    messages: list[Message] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    state: AgentState = field(default_factory=AgentState)
    
    # Metadata
    label: str = ""                         # Optional human-readable label
    is_checkpoint: bool = False             # Marked as explicit checkpoint
    is_branch_point: bool = False           # Has multiple children
    branch_objective: str | None = None     # If this is a branch, what's its goal?
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "created_at": self.created_at.isoformat(),
            "messages": [m.to_dict() for m in self.messages],
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "state": self.state.to_dict(),
            "label": self.label,
            "is_checkpoint": self.is_checkpoint,
            "is_branch_point": self.is_branch_point,
            "branch_objective": self.branch_objective,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ContextFrame":
        return cls(
            id=data["id"],
            parent_id=data.get("parent_id"),
            created_at=datetime.fromisoformat(data["created_at"]),
            messages=[Message.from_dict(m) for m in data["messages"]],
            tool_calls=[ToolCall.from_dict(tc) for tc in data["tool_calls"]],
            state=AgentState.from_dict(data["state"]),
            label=data.get("label", ""),
            is_checkpoint=data.get("is_checkpoint", False),
            is_branch_point=data.get("is_branch_point", False),
            branch_objective=data.get("branch_objective"),
        )
```

### 4.2 Tool Data Models

```python
# tempo/tools/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from enum import Enum


class ToolCategory(str, Enum):
    """Categories for organizing tools."""
    EXECUTION = "execution"     # Shell, code execution
    BROWSING = "browsing"       # Web access
    FILESYSTEM = "filesystem"   # File operations
    NETWORK = "network"         # Network operations
    ANALYSIS = "analysis"       # Code analysis, RE tools
    META = "meta"               # Tool installation, agent control


@dataclass
class ToolResult:
    """Result of a tool execution."""
    success: bool
    output: str
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    # For structured results
    structured_data: Any = None


@dataclass  
class ToolSchema:
    """JSON Schema representation of a tool for LLM consumption."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema format
    
    def to_openai_format(self) -> dict:
        """Convert to OpenAI/Anthropic tool format."""
        # Ensure 'purpose' is in the parameters
        if "purpose" not in self.parameters.get("properties", {}):
            if "properties" not in self.parameters:
                self.parameters["properties"] = {}
            self.parameters["properties"]["purpose"] = {
                "type": "string",
                "description": "A one-sentence summary of why this tool is being called."
            }
            if "required" not in self.parameters:
                self.parameters["required"] = []
            if "purpose" not in self.parameters["required"]:
                self.parameters["required"].append("purpose")

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }


class Tool(ABC):
    """Abstract base class for all tools."""
    
    name: str
    description: str
    category: ToolCategory
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given parameters."""
        pass
    
    @abstractmethod
    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        pass
    
    def default_summarizer(self, result: ToolResult) -> str:
        """
        Default strategy for summarizing this tool's output.
        Override in subclasses for tool-specific summarization.
        """
        if not result.success:
            return f"Error: {result.error}"
        # Default: truncate long outputs
        if len(result.output) > 500:
            return result.output[:250] + "\n...[truncated]...\n" + result.output[-250:]
        return result.output
```

### 4.3 LLM Data Models

```python
# tempo/infra/llm.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass
class TokenUsage:
    """Token usage statistics."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ToolCallRequest:
    """A tool call requested by the LLM."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Normalized response from any LLM provider."""
    content: str | None = None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)
    model: str = ""
    finish_reason: str = ""
    raw_response: Any = None  # Original provider response for debugging


class LLMClient(ABC):
    """Model-agnostic LLM interface."""
    
    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """
        Send a completion request.
        
        Args:
            messages: List of {"role": str, "content": str} dicts
            tools: Optional list of tool schemas in OpenAI format
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            
        Returns:
            Normalized LLMResponse
        """
        pass
    
    @abstractmethod
    async def complete_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
    ) -> T:
        """
        Request a structured response matching a Pydantic model.
        
        Args:
            messages: List of {"role": str, "content": str} dicts
            response_model: Pydantic model class for the response
            temperature: Sampling temperature
            
        Returns:
            Instance of response_model
        """
        pass
```

### 4.4 Agent Configuration

```python
# tempo/agent/config.py

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentConfig:
    """Configuration for the agent runtime."""
    
    # Model settings
    model: str = "anthropic/claude-sonnet-4-20250514"
    # temperature and max_tokens are managed by the model/provider defaults or per-request logic
    
    # Context management
    max_context_tokens: int = 100000        # Trigger summarization near this limit
    auto_summarize: bool = True             # Automatically summarize tool outputs
    summarization_model: str | None = None  # Use cheaper model for summaries (None = same model)
    
    # Workflow settings
    enforce_phases: bool = True             # Require explicit phase transitions
    max_steps_per_phase: int = 20           # Prevent runaway phases
    max_total_steps: int = 100              # Hard limit on agent steps
    
    # Branching settings
    max_branches: int = 5                   # Maximum parallel branches
    max_branch_depth: int = 3               # Maximum nested branching
    branch_step_limit: int = 10             # Max steps per branch
    
    # Container settings
    container_image: str = "tempo-sec-base:latest"
    container_timeout: int = 300            # Seconds
    
    # Persistence
    persistence_dir: str = "./contexts"
    auto_checkpoint: bool = True            # Checkpoint after each tool call

    # Scope
    allowed_domains: list[str] = field(default_factory=list)
    excluded_domains: list[str] = field(default_factory=list)
    allow_subdomains: bool = True
    
    # Debugging
    verbose: bool = False
    log_level: str = "INFO"
```



### 4.5 External Configuration

The agent supports loading sensitive credentials and scope definitions from a TOML configuration file (default: `config.toml`).

```toml
[api_keys]
openai = "sk-..."
anthropic = "sk-ant-..."
github = "ghp_..."

[scope]
allowed_domains = ["example.com", "api.example.com"]
excluded_domains = ["internal.example.com"]
allowed_ips = ["192.168.1.0/24"]
excluded_ips = ["192.168.1.1"]
allow_subdomains = true
```

**Scope Enforcement**:
- **Allowed Domains**: The agent will only interact with these domains.
- **Excluded Domains**: Explicitly forbidden domains, even if they match allowed patterns.
- **Subdomains**: If `allow_subdomains` is true, any subdomain of an allowed domain is permitted.

---

## 5. Component Specifications

### 5.1 Context Store (`tempo/context/store.py`)

```python
class ContextStore:
    """
    Manages the context tree and provides operations for
    checkpointing, branching, and context rendering.
    """
    
    def __init__(
        self,
        persistence_dir: str = "./contexts",
        session_id: str | None = None,
    ):
        """
        Initialize a new context store.
        
        Args:
            persistence_dir: Directory for saving context files
            session_id: Optional ID to resume an existing session
        """
        pass
    
    # === Core Properties ===
    
    @property
    def current_frame(self) -> ContextFrame:
        """Get the current (active) frame."""
        pass
    
    @property
    def session_id(self) -> str:
        """Get the session ID for this context tree."""
        pass
    
    # === Message Management ===
    
    def add_message(self, role: MessageRole, content: str) -> None:
        """Add a message to the current frame."""
        pass
    
    def add_tool_call(self, tool_call: ToolCall) -> None:
        """Record a tool call in the current frame."""
        pass
    
    def summarize_tool_call(self, tool_call_id: str, summary: str) -> None:
        """
        Replace a tool call's raw output with a summary.
        The raw output is preserved but won't be included in rendered context.
        """
        pass
    
    # === State Management ===
    
    def update_state(self, **kwargs) -> None:
        """Update the agent state in the current frame."""
        pass
    
    def get_state(self) -> AgentState:
        """Get the current agent state."""
        pass
    
    # === Checkpointing ===
    
    def checkpoint(self, label: str = "") -> str:
        """
        Create a checkpoint of the current state.
        Returns the frame ID that can be used for revert.
        """
        pass
    
    def revert(self, frame_id: str) -> None:
        """
        Revert to a previous checkpoint.
        Creates a new frame branching from the checkpoint.
        """
        pass
    
    def list_checkpoints(self) -> list[tuple[str, str, datetime]]:
        """List all checkpoints as (frame_id, label, timestamp) tuples."""
        pass
    
    # === Branching ===
    
    def branch(self, n: int, objectives: list[str] | None = None) -> list[str]:
        """
        Create n branches from the current frame.
        
        Args:
            n: Number of branches to create
            objectives: Optional list of objectives for each branch
            
        Returns:
            List of frame IDs for the new branches
        """
        pass
    
    def switch_to_branch(self, frame_id: str) -> None:
        """Switch the active context to a specific branch."""
        pass
    
    def get_branch_ids(self) -> list[str]:
        """Get frame IDs of all branches from the current branch point."""
        pass
    
    def merge_branches(
        self,
        branch_ids: list[str],
        summaries: list[str],
    ) -> None:
        """
        Merge branch results back into the parent context.
        Creates a new frame with summaries injected as messages.
        """
        pass
    
    # === Context Rendering ===
    
    def render_messages(
        self,
        include_system: bool = True,
        max_tokens: int | None = None,
    ) -> list[dict[str, str]]:
        """
        Render the context as a list of messages for the LLM.
        
        Walks the frame tree from root to current, assembling messages.
        Uses summaries instead of raw outputs where available.
        
        Args:
            include_system: Whether to include system messages
            max_tokens: Optional token limit (triggers truncation strategy)
            
        Returns:
            List of {"role": str, "content": str} dicts
        """
        pass
    
    def estimate_tokens(self) -> int:
        """Estimate the current context size in tokens."""
        pass
    
    # === Persistence ===
    
    def save(self) -> str:
        """
        Save the entire context tree to disk.
        Returns the path to the saved file.
        """
        pass
    
    @classmethod
    def load(cls, path: str) -> "ContextStore":
        """Load a context tree from disk."""
        pass
```

### 5.2 Branch Manager (`tempo/context/branch.py`)

```python
class BranchManager:
    """
    Handles the logic for branching, parallel execution, and merging.
    Works with ContextStore but encapsulates branching complexity.
    """
    
    def __init__(self, context_store: ContextStore):
        pass
    
    async def branch_and_execute(
        self,
        objectives: list[str],
        executor: Callable[[ContextStore, str], Awaitable[str]],
        max_parallel: int = 3,
    ) -> list[BranchResult]:
        """
        Create branches, execute each with the given executor, collect results.
        
        Args:
            objectives: List of objectives, one per branch
            executor: Async function that takes (context_store, objective) and returns summary
            max_parallel: Maximum concurrent branches
            
        Returns:
            List of BranchResult with summaries and metadata
        """
        pass


@dataclass
class BranchResult:
    branch_id: str
    objective: str
    summary: str
    steps_taken: int
    success: bool
    error: str | None = None
```

### 5.3 Prompt Builder (`tempo/prompts/builder.py`)

```python
class PromptBuilder:
    """
    Assembles prompts from templates with dynamic injection.
    """
    
    def __init__(self, templates_dir: str):
        """
        Initialize with path to templates directory.
        
        Expected files:
            - system.md
            - recon.md, hypothesize.md, test.md, reflect.md
            - summarize.md
        """
        pass
    
    @classmethod
    def from_templates(cls, templates_dir: str) -> "PromptBuilder":
        """Factory method for cleaner initialization."""
        pass
    
    def build_system_prompt(
        self,
        phase: Phase,
        tools: list[ToolSchema],
        custom_instructions: str | None = None,
    ) -> str:
        """
        Build the complete system prompt.
        
        Combines:
            - Base system template
            - Phase-specific instructions
            - Tool descriptions
            - Custom instructions
        """
        pass
    
    def build_phase_prompt(self, phase: Phase) -> str:
        """Get the prompt for a specific phase."""
        pass
    
    def build_summarization_prompt(
        self,
        tool_name: str,
        tool_input: dict,
        tool_output: str,
        objective: str,
    ) -> str:
        """Build prompt for summarizing tool output."""
        pass
    
    def inject_context(
        self,
        template: str,
        **kwargs,
    ) -> str:
        """Inject variables into a template string."""
        pass
```

### 5.4 Phases (`tempo/prompts/phases.py`)

```python
from enum import Enum
from dataclasses import dataclass


class Phase(str, Enum):
    RECON = "recon"
    HYPOTHESIZE = "hypothesize"
    TEST = "test"
    REFLECT = "reflect"


@dataclass
class PhaseConfig:
    """Configuration for a workflow phase."""
    phase: Phase
    description: str
    allowed_transitions: list[Phase]
    max_steps: int = 20
    required_outputs: list[str] = field(default_factory=list)  # e.g., ["hypotheses"] for HYPOTHESIZE


# Default phase flow
PHASE_CONFIGS = {
    Phase.RECON: PhaseConfig(
        phase=Phase.RECON,
        description="Gather information about the target",
        allowed_transitions=[Phase.HYPOTHESIZE, Phase.RECON],
        required_outputs=[],
    ),
    Phase.HYPOTHESIZE: PhaseConfig(
        phase=Phase.HYPOTHESIZE,
        description="Form hypotheses about potential vulnerabilities",
        allowed_transitions=[Phase.TEST, Phase.RECON],
        required_outputs=["hypotheses"],
    ),
    Phase.TEST: PhaseConfig(
        phase=Phase.TEST,
        description="Test each hypothesis systematically",
        allowed_transitions=[Phase.REFLECT, Phase.TEST],
        required_outputs=["findings"],
    ),
    Phase.REFLECT: PhaseConfig(
        phase=Phase.REFLECT,
        description="Analyze results and plan next steps",
        allowed_transitions=[Phase.RECON, Phase.HYPOTHESIZE, Phase.TEST],
        required_outputs=[],
    ),
}
```

### 5.5 Tool Registry (`tempo/tools/registry.py`)

```python
class ToolRegistry:
    """
    Registry for discovering, storing, and retrieving tools.
    """
    
    def __init__(self):
        self._tools: dict[str, Tool] = {}
    
    def register(self, tool: Tool) -> None:
        """Register a tool instance."""
        pass
    
    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        pass
    
    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        pass
    
    def get_schemas(self) -> list[dict]:
        """Get all tool schemas in OpenAI format for LLM consumption."""
        pass
    
    def get_schema(self, name: str) -> dict | None:
        """Get a specific tool's schema."""
        pass
    
    @classmethod
    def default(cls, container_manager: ContainerManager | None = None) -> "ToolRegistry":
        """
        Create a registry with the default tool set.
        
        Default tools:
            - shell: Execute shell commands
            - file_read: Read file contents
            - file_write: Write file contents
            - browser: Browse web pages
            - install_tool: Install additional tools
        """
        pass
```

### 5.6 Built-in Tools

#### Shell Tool (`tempo/tools/shell.py`)

```python
class ShellTool(Tool):
    """Execute shell commands in the container."""
    
    name = "shell"
    description = "Execute a shell command in the sandbox environment"
    category = ToolCategory.EXECUTION
    
    def __init__(self, container_manager: ContainerManager):
        self.container = container_manager
    
    async def execute(
        self,
        command: str,
        timeout: int = 60,
        working_dir: str = "/workspace",
    ) -> ToolResult:
        """
        Execute a shell command.
        
        Args:
            command: The command to execute
            timeout: Maximum execution time in seconds
            working_dir: Working directory for the command
        """
        pass
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 60)",
                        "default": 60,
                    },
                    "working_dir": {
                        "type": "string", 
                        "description": "Working directory (default: /workspace)",
                        "default": "/workspace",
                    },
                },
                "required": ["command"],
            },
        )
    
    def default_summarizer(self, result: ToolResult) -> str:
        """Summarize shell output, focusing on key information."""
        if not result.success:
            return f"Command failed: {result.error}"
        
        output = result.output
        lines = output.strip().split("\n")
        
        # For short outputs, return as-is
        if len(lines) <= 10:
            return output
        
        # For long outputs, keep first and last lines with indicator
        return "\n".join(lines[:5]) + f"\n... ({len(lines) - 10} lines omitted) ...\n" + "\n".join(lines[-5:])
```

#### Browser Tool (`tempo/tools/browser.py`)

```python
class BrowserTool(Tool):
    """Browse web pages and extract content."""
    
    name = "browser"
    description = "Navigate to a URL and extract page content"
    category = ToolCategory.BROWSING
    
    async def execute(
        self,
        url: str,
        extract_links: bool = False,
        screenshot: bool = False,
        wait_for: str | None = None,
    ) -> ToolResult:
        """
        Browse to a URL and extract content.
        
        Args:
            url: The URL to navigate to
            extract_links: Whether to extract all links from the page
            screenshot: Whether to capture a screenshot
            wait_for: CSS selector to wait for before extracting
        """
        pass
    
    def get_schema(self) -> ToolSchema:
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
```

#### Filesystem Tools (`tempo/tools/filesystem.py`)

```python
class FileReadTool(Tool):
    """Read contents of a file."""
    
    name = "file_read"
    description = "Read the contents of a file"
    category = ToolCategory.FILESYSTEM
    
    async def execute(
        self,
        path: str,
        encoding: str = "utf-8",
        max_bytes: int | None = None,
    ) -> ToolResult:
        pass
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read",
                    },
                    "encoding": {
                        "type": "string",
                        "description": "File encoding (default: utf-8)",
                        "default": "utf-8",
                    },
                    "max_bytes": {
                        "type": "integer",
                        "description": "Maximum bytes to read (optional)",
                    },
                },
                "required": ["path"],
            },
        )


class FileWriteTool(Tool):
    """Write contents to a file."""
    
    name = "file_write"
    description = "Write content to a file (creates or overwrites)"
    category = ToolCategory.FILESYSTEM
    
    async def execute(
        self,
        path: str,
        content: str,
        append: bool = False,
        encoding: str = "utf-8",
    ) -> ToolResult:
        pass
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to write",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write",
                    },
                    "append": {
                        "type": "boolean",
                        "description": "Append instead of overwrite",
                        "default": False,
                    },
                },
                "required": ["path", "content"],
            },
        )
```

### 5.7 Meta Tools

#### Transition Phase Tool (`tempo/tools/meta.py`)

```python
class TransitionPhaseTool(Tool):
    """Transition the agent to a new workflow phase."""
    
    name = "transition_phase"
    description = "Transition to a new phase (recon, hypothesize, test, reflect)"
    category = ToolCategory.META
    
    def __init__(self, workflow_manager: WorkflowManager):
        self.workflow = workflow_manager
        
    async def execute(self, phase: str, justification: str, purpose: str) -> ToolResult:
        try:
            target_phase = Phase(phase.lower())
            self.workflow.transition(target_phase)
            return ToolResult(
                success=True,
                output=f"Transitioned to {target_phase.value}. Justification: {justification}"
            )
        except ValueError:
            return ToolResult(success=False, output=f"Invalid phase: {phase}")
        except WorkflowError as e:
            return ToolResult(success=False, output=str(e))
            
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "phase": {
                        "type": "string",
                        "enum": [p.value for p in Phase],
                        "description": "The target phase",
                    },
                    "justification": {
                        "type": "string",
                        "description": "Why you are moving to this phase",
                    },
                    "purpose": {
                        "type": "string",
                        "description": "A one-sentence summary of why this tool is being called.",
                    },
                },
                "required": ["phase", "justification", "purpose"],
            },
        )
```

#### Summarize Output Tool (`tempo/tools/meta.py`)

```python
class SummarizeOutputTool(Tool):
    """Summarize the output of a previous tool call."""
    
    name = "summarize_tool_output"
    description = "Summarize a previous tool output to save context tokens"
    category = ToolCategory.META
    
    def __init__(self, context_store: ContextStore, summarizer: OutputSummarizer):
        self.context = context_store
        self.summarizer = summarizer
        
    async def execute(self, tool_call_id: str, summary: str, purpose: str) -> ToolResult:
        self.context.summarize_tool_call(tool_call_id, summary)
        return ToolResult(
            success=True,
            output=f"Summarized tool call {tool_call_id}"
        )

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "tool_call_id": {
                        "type": "string",
                        "description": "ID of the tool call to summarize",
                    },
                    "summary": {
                        "type": "string",
                        "description": "Concise summary of the tool output",
                    },
                    "purpose": {
                        "type": "string",
                        "description": "A one-sentence summary of why this tool is being called.",
                    },
                },
                "required": ["tool_call_id", "summary", "purpose"],
            },
        )
```

### 5.7 LLM Client (`tempo/infra/llm.py`)

```python
import litellm
import instructor
from typing import TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LiteLLMClient(LLMClient):
    """LiteLLM + Instructor implementation of LLMClient."""
    
    def __init__(self, model: str, **default_kwargs):
        """
        Initialize the LiteLLM client.
        
        Args:
            model: Model identifier (e.g., "anthropic/claude-sonnet-4-20250514", "openai/gpt-4o")
            **default_kwargs: Default arguments for all completions
        """
        self.model = model
        self.default_kwargs = default_kwargs
        self.instructor_client = instructor.from_litellm(litellm.acompletion)
    
    async def complete(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send a completion request."""
        try:
            response = await litellm.acompletion(
                model=self.model,
                messages=messages,
                tools=tools,
                **self.default_kwargs,
            )
            return self._normalize_response(response)
        except Exception as e:
            # Handle and wrap provider-specific errors
            raise LLMError(f"Completion failed: {e}") from e
    
    async def complete_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
        temperature: float = 0.7,
    ) -> T:
        """Request a structured response."""
        return await self.instructor_client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_model=response_model,
        )
    
    def _normalize_response(self, response) -> LLMResponse:
        """Convert LiteLLM response to our normalized format."""
        choice = response.choices[0]
        message = choice.message
        
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(ToolCallRequest(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                ))
        
        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            usage=TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            ),
            model=response.model,
            finish_reason=choice.finish_reason,
            raw_response=response,
        )


class LLMError(Exception):
    """Wrapper for LLM-related errors."""
    pass
```

### 5.8 Container Manager (`tempo/infra/container.py`)

```python
import docker
from dataclasses import dataclass


@dataclass
class ContainerConfig:
    image: str = "tempo-sec-base:latest"
    memory_limit: str = "2g"
    cpu_count: int = 2
    network_mode: str = "bridge"
    timeout: int = 300


class ContainerManager:
    """
    Manages Docker container lifecycle for sandboxed tool execution.
    """
    
    def __init__(self, config: ContainerConfig | None = None):
        self.config = config or ContainerConfig()
        self.client = docker.from_env()
        self._container: docker.models.containers.Container | None = None
    
    async def start(self) -> None:
        """Start the container."""
        pass
    
    async def stop(self) -> None:
        """Stop and remove the container."""
        pass
    
    async def exec(
        self,
        command: str,
        working_dir: str = "/workspace",
        timeout: int | None = None,
        environment: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        """
        Execute a command in the container.
        
        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        pass
    
    async def copy_to(self, local_path: str, container_path: str) -> None:
        """Copy a file into the container."""
        pass
    
    async def copy_from(self, container_path: str, local_path: str) -> None:
        """Copy a file from the container."""
        pass
    
    async def file_exists(self, path: str) -> bool:
        """Check if a file exists in the container."""
        pass
    
    async def read_file(self, path: str) -> str:
        """Read a file from the container."""
        pass
    
    async def write_file(self, path: str, content: str) -> None:
        """Write a file to the container."""
        pass
    
    @property
    def is_running(self) -> bool:
        """Check if container is running."""
        pass
    
    def __enter__(self):
        """Context manager entry."""
        pass
    
    def __exit__(self, *args):
        """Context manager exit - cleanup container."""
        pass
```

### 5.9 Agent Runner (`tempo/agent/runner.py`)

```python
class Agent:
    """
    Main agent orchestrator. Ties together context, prompts, tools, and LLM.
    """
    
    def __init__(
        self,
        context: ContextStore,
        prompts: PromptBuilder,
        tools: ToolRegistry,
        llm: LLMClient,
        config: AgentConfig | None = None,
    ):
        self.context = context
        self.prompts = prompts
        self.tools = tools
        self.llm = llm
        self.config = config or AgentConfig()
        self.workflow = WorkflowManager(config)
        self.summarizer = OutputSummarizer(llm, prompts, config)
        
        # Register meta tools
        self.tools.register(TransitionPhaseTool(self.workflow))
        self.tools.register(SummarizeOutputTool(self.context, self.summarizer))
    
    async def run(
        self,
        objective: str,
        initial_phase: Phase = Phase.RECON,
        max_steps: int | None = None,
    ) -> AgentResult:
        """
        Run the agent on an objective.
        
        Args:
            objective: What the agent should accomplish
            initial_phase: Starting phase (default: RECON)
            max_steps: Override max steps from config
            
        Returns:
            AgentResult with findings, final state, etc.
        """
        pass
    
    async def step(self) -> StepResult:
        """
        Execute a single agent step.
        
        1. Build prompt from current context and phase
        2. Call LLM
        3. If tool call: 
            a. Execute tool
            b. Append "Output captured. Now call `summarize_tool_output` to compress this data." to output
            c. Update context (raw output)
        4. If phase transition tool: update workflow state
        5. Return step result
        """
        pass
    
    async def branch_explore(
        self,
        objectives: list[str],
        steps_per_branch: int | None = None,
    ) -> list[BranchResult]:
        """
        Create branches and explore each objective in parallel.
        """
        pass
    
    def checkpoint(self, label: str = "") -> str:
        """Create a checkpoint, return frame ID."""
        return self.context.checkpoint(label)
    
    def revert(self, frame_id: str) -> None:
        """Revert to a checkpoint."""
        self.context.revert(frame_id)


@dataclass
class StepResult:
    """Result of a single agent step."""
    step_number: int
    llm_response: LLMResponse
    tool_calls: list[ToolCall]
    phase_transition: Phase | None
    should_continue: bool
    error: str | None = None


@dataclass
class AgentResult:
    """Final result of an agent run."""
    success: bool
    objective: str
    steps_taken: int
    final_phase: Phase
    findings: list[dict]
    hypotheses: list[dict]
    context_id: str  # For resumption
    error: str | None = None
```

### 5.10 Workflow Manager (`tempo/agent/workflow.py`)

```python
class WorkflowManager:
    """
    Manages phase transitions and enforces workflow rules.
    """
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.current_phase = Phase.RECON
        self.phase_step_counts: dict[Phase, int] = {p: 0 for p in Phase}
        self.transition_history: list[tuple[Phase, Phase, datetime]] = []
    
    def can_transition(self, to_phase: Phase) -> bool:
        """Check if transition to given phase is allowed."""
        pass
    
    def transition(self, to_phase: Phase) -> None:
        """
        Transition to a new phase.
        Raises WorkflowError if transition is invalid.
        """
        pass
    
    def record_step(self) -> None:
        """Record that a step was taken in the current phase."""
        pass
    
    def should_force_transition(self) -> Phase | None:
        """
        Check if we should force a phase transition due to limits.
        Returns the phase to transition to, or None.
        """
        pass
    
    def get_phase_prompt_additions(self) -> str:
        """Get additional prompt content for current phase state."""
        pass


class WorkflowError(Exception):
    """Raised when workflow rules are violated."""
    pass
```

### 5.11 Output Summarizer (`tempo/agent/summarizer.py`)

```python
class OutputSummarizer:
    """
    Handles summarization of tool outputs to save context tokens.
    """
    
    def __init__(
        self,
        llm: LLMClient,
        prompts: PromptBuilder,
        config: AgentConfig,
    ):
        self.llm = llm
        self.prompts = prompts
        self.config = config
    
    async def summarize(
        self,
        tool_call: ToolCall,
        objective: str,
        tool: Tool | None = None,
    ) -> str:
        """
        Summarize a tool call's output.
        
        Strategy:
        1. If tool has a default_summarizer and output is short, use it
        2. Otherwise, use LLM summarization
        
        Args:
            tool_call: The tool call to summarize
            objective: Current agent objective (for relevance filtering)
            tool: Optional tool instance for custom summarization
        """
        pass
    
    async def _llm_summarize(
        self,
        tool_call: ToolCall,
        objective: str,
    ) -> str:
        """Use LLM to generate summary."""
        prompt = self.prompts.build_summarization_prompt(
            tool_name=tool_call.tool_name,
            tool_input=tool_call.input,
            tool_output=tool_call.raw_output,
            objective=objective,
        )
        
        response = await self.llm.complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,  # Lower temperature for factual summarization
            max_tokens=500,
        )
        
        return response.content
    
    def should_summarize(self, tool_call: ToolCall) -> bool:
        """
        Determine if a tool call output should be summarized.
        Note: The agent is now responsible for initiating summarization via the `summarize_tool_output` tool.
        This method might be used for auto-summarization fallbacks if configured.
        """
        pass
```

---

## 6. Implementation Order

Build in this order to minimize blocked dependencies:

### Phase 1: Foundation (No external dependencies between components)

```
1. tempo/context/frame.py          # Data classes only
2. tempo/tools/base.py             # Tool ABC and ToolResult  
3. tempo/infra/llm.py              # LLMClient ABC and LiteLLMClient
4. tempo/agent/config.py           # AgentConfig dataclass
5. tempo/prompts/phases.py         # Phase enum and configs
```

### Phase 2: Core Infrastructure

```
6. tempo/infra/container.py        # ContainerManager
7. tempo/context/persistence.py    # JSON serialization
8. tempo/context/store.py          # ContextStore (depends on frame, persistence)
9. tempo/context/branch.py         # BranchManager (depends on store)
```

### Phase 3: Tools

```
10. tempo/tools/registry.py        # ToolRegistry
11. tempo/tools/shell.py           # ShellTool (depends on container)
12. tempo/tools/filesystem.py      # FileReadTool, FileWriteTool
13. tempo/tools/browser.py         # BrowserTool
14. tempo/tools/installer.py       # ToolInstallerTool
```

### Phase 4: Prompts

```
15. tempo/prompts/templates/*      # All template files
16. tempo/prompts/builder.py       # PromptBuilder
```

### Phase 5: Agent

```
17. tempo/agent/workflow.py        # WorkflowManager
18. tempo/agent/summarizer.py      # OutputSummarizer
19. tempo/agent/runner.py          # Agent (depends on everything)
```

### Phase 6: Integration

```
20. containers/base/Dockerfile     # Base container image
21. examples/simple_scan.py        # Basic usage example
22. tests/*                        # Test suite
```

---

## 7. Dependencies

### Python Dependencies (`pyproject.toml`)

```toml
[project]
name = "tempo-sec"
version = "0.1.0"
description = "Context-aware cybersecurity agent"
requires-python = ">=3.11"
dependencies = [
    # LLM
    "litellm>=1.40.0",
    "instructor>=1.0.0",
    
    # Data validation
    "pydantic>=2.0.0",
    
    # Container management
    "docker>=7.0.0",
    
    # Browser automation
    "playwright>=1.40.0",
    
    # Async
    "asyncio>=3.4.3",
    "aiofiles>=23.0.0",
    
    # Utilities
    "structlog>=24.0.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.0.0",
    "ruff>=0.3.0",
    "mypy>=1.8.0",
]
```

### Container Dependencies (`containers/base/Dockerfile`)

```dockerfile
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Base system tools
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    git \
    vim \
    netcat-openbsd \
    dnsutils \
    iputils-ping \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

# Security tools
RUN apt-get update && apt-get install -y \
    nmap \
    nikto \
    sqlmap \
    gobuster \
    dirb \
    hydra \
    john \
    hashcat \
    && rm -rf /var/lib/apt/lists/*

# Python
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Node.js (for some tools)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs

# Playwright for browser automation
RUN pip3 install playwright && playwright install chromium --with-deps

# Working directory
WORKDIR /workspace

# Non-root user for safety
RUN useradd -m -s /bin/bash agent
USER agent
```

---

## 8. Example Usage

### Basic Usage (`examples/simple_scan.py`)

```python
import asyncio
from tempo.context import ContextStore
from tempo.prompts import PromptBuilder
from tempo.tools import ToolRegistry
from tempo.agent import Agent, AgentConfig
from tempo.infra import LiteLLMClient, ContainerManager


async def main():
    # Initialize components
    container = ContainerManager()
    await container.start()
    
    try:
        context = ContextStore(persistence_dir="./contexts")
        prompts = PromptBuilder.from_templates("./tempo/prompts/templates")
        tools = ToolRegistry.default(container_manager=container)
        llm = LiteLLMClient(model="anthropic/claude-sonnet-4-20250514")
        
        agent = Agent(
            context=context,
            prompts=prompts,
            tools=tools,
            llm=llm,
            config=AgentConfig(
                max_steps_per_phase=10,
                auto_summarize=True,
            ),
        )
        
        # Run the agent
        result = await agent.run(
            objective="Identify potential vulnerabilities in example.com",
        )
        
        print(f"Completed in {result.steps_taken} steps")
        print(f"Findings: {result.findings}")
        
        # Save context for later analysis
        context.save()
        
    finally:
        await container.stop()


if __name__ == "__main__":
    asyncio.run(main())
```

### Branching Example

```python
async def explore_attack_surfaces(agent: Agent, surfaces: list[str]):
    """Explore multiple attack surfaces in parallel."""
    
    # Create a checkpoint before branching
    checkpoint_id = agent.checkpoint("pre-branch")
    
    # Branch and explore each surface
    results = await agent.branch_explore(
        objectives=[f"Investigate: {surface}" for surface in surfaces],
        steps_per_branch=5,
    )
    
    # Results are automatically merged back into main context
    for result in results:
        print(f"Surface: {result.objective}")
        print(f"  Success: {result.success}")
        print(f"  Summary: {result.summary}")
```

### Resuming a Session

```python
async def resume_session(session_path: str):
    """Resume an agent from a saved context."""
    
    context = ContextStore.load(session_path)
    
    # Reconstruct agent with same config
    prompts = PromptBuilder.from_templates("./tempo/prompts/templates")
    tools = ToolRegistry.default()
    llm = LiteLLMClient(model="anthropic/claude-sonnet-4-20250514")
    
    agent = Agent(
        context=context,
        prompts=prompts,
        tools=tools,
        llm=llm,
    )
    
    # Continue from where we left off
    result = await agent.run(
        objective="Continue previous analysis",
    )
```

---

## 9. Prompt Templates

### System Prompt (`tempo/prompts/templates/system.md`)

```markdown
You are Tempo Sec, an expert cybersecurity researcher specializing in vulnerability discovery. You approach security analysis methodically, following a structured workflow:

1. **Recon**: Gather information, understand the target, note anomalies
2. **Hypothesize**: Form theories about potential vulnerabilities
3. **Test**: Systematically validate each hypothesis
4. **Reflect**: Analyze results, refine approach, plan next steps

## Your Capabilities

You have access to the following tools:

{tool_descriptions}

## Guidelines

- **Be thorough**: Don't skip steps. Document everything.
- **Be methodical**: Test one hypothesis at a time.
- **Be patient**: Some vulnerabilities require multiple attempts to confirm.
- **Be safe**: Never cause permanent damage or access unauthorized systems.

## Phase Transitions
 
 Use the `transition_phase` tool to move between phases when you have completed the requirements for the current phase.
 
 Valid phases: recon, hypothesize, test, reflect
 
 {phase_instructions}
 ```

### Recon Phase (`tempo/prompts/templates/recon.md`)

```markdown
## Current Phase: RECON

Your goal is to gather information about the target. Focus on:

- **Attack surface mapping**: What endpoints, services, and entry points exist?
- **Technology identification**: What frameworks, languages, and infrastructure are in use?
- **Anomaly detection**: What seems unusual, misconfigured, or interesting?

Do NOT attempt exploits yet. Focus purely on information gathering.

When you have sufficient information, transition to HYPOTHESIZE with: `PHASE: hypothesize`
```

### Hypothesize Phase (`tempo/prompts/templates/hypothesize.md`)

```markdown
## Current Phase: HYPOTHESIZE

Based on your reconnaissance, form hypotheses about potential vulnerabilities.

For each hypothesis, specify:
1. **Attack surface**: Where is the potential vulnerability?
2. **Vulnerability type**: What kind of issue might this be?
3. **Likelihood**: How likely is this to be exploitable? (high/medium/low)
4. **Impact**: What could an attacker achieve? (high/medium/low)
5. **Test plan**: How will you validate this hypothesis?

Prioritize hypotheses by likelihood × impact.

When you have your hypotheses ready, transition to TEST with: `PHASE: test`
```

### Test Phase (`tempo/prompts/templates/test.md`)

```markdown
## Current Phase: TEST

Systematically test each hypothesis. For each test:

1. **State the hypothesis** you're testing
2. **Execute the test** using appropriate tools
3. **Record the result**: Confirmed, Disproven, or Inconclusive
4. **Document evidence**: What proves or disproves the hypothesis?

If a hypothesis is confirmed, develop a proof of concept.
If inconclusive, note what additional testing might help.

When you've tested your hypotheses, transition to REFLECT with: `PHASE: reflect`
```

### Reflect Phase (`tempo/prompts/templates/reflect.md`)

```markdown
## Current Phase: REFLECT

Analyze your results and plan next steps.

Consider:
- What vulnerabilities were confirmed?
- What hypotheses were disproven and why?
- What new attack surfaces were discovered during testing?
- What should be investigated next?

Based on your reflection:
- If you found confirmed vulnerabilities, document them clearly
- If you found new leads, return to RECON: `PHASE: recon`
- If you have new hypotheses, go to HYPOTHESIZE: `PHASE: hypothesize`
- If you need more testing, return to TEST: `PHASE: test`
```

### Summarization Prompt (`tempo/prompts/templates/summarize.md`)

```markdown
Summarize the following tool output concisely. Focus only on information relevant to the objective.

**Objective**: {objective}

**Tool**: {tool_name}
**Input**: {tool_input}

**Output**:
```
{tool_output}
```

Provide a brief summary (2-5 sentences) capturing:
- Key findings relevant to the objective
- Any errors or unexpected results
- Actionable information for next steps

Summary:
```

---

## 10. Testing Strategy

### Unit Tests

Each component should have isolated unit tests:

```python
# tests/context/test_store.py

import pytest
from tempo.context import ContextStore, ContextFrame, Message, MessageRole


class TestContextStore:
    def test_add_message(self):
        store = ContextStore()
        store.add_message(MessageRole.USER, "Hello")
        
        assert len(store.current_frame.messages) == 1
        assert store.current_frame.messages[0].content == "Hello"
    
    def test_checkpoint_and_revert(self):
        store = ContextStore()
        store.add_message(MessageRole.USER, "First")
        
        checkpoint_id = store.checkpoint("test")
        
        store.add_message(MessageRole.USER, "Second")
        assert len(store.current_frame.messages) == 2
        
        store.revert(checkpoint_id)
        # After revert, we branch from checkpoint, so messages from checkpoint are inherited
        assert store.current_frame.messages[-1].content == "First"
    
    def test_branching(self):
        store = ContextStore()
        store.add_message(MessageRole.USER, "Setup")
        
        branch_ids = store.branch(3, objectives=["A", "B", "C"])
        
        assert len(branch_ids) == 3
        for bid in branch_ids:
            store.switch_to_branch(bid)
            assert store.current_frame.branch_objective in ["A", "B", "C"]
```

### Integration Tests

Test component interactions:

```python
# tests/agent/test_runner.py

import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.complete.return_value = LLMResponse(
        content="I'll start by scanning the target.",
        tool_calls=[],
    )
    return llm

@pytest.fixture  
def agent(mock_llm):
    return Agent(
        context=ContextStore(),
        prompts=PromptBuilder.from_templates("./tempo/prompts/templates"),
        tools=ToolRegistry(),  # Empty registry for testing
        llm=mock_llm,
    )

async def test_agent_step(agent):
    result = await agent.step()
    
    assert result.llm_response.content is not None
    assert result.should_continue is True
```

---

## Appendix A: Key Design Decisions

### Why JSON for Context Persistence?

1. **Human readable**: Easy to inspect and debug
2. **Git friendly**: Can diff context files
3. **Simple**: No database setup required
4. **Portable**: Easy to share sessions

For production, could swap to SQLite or PostgreSQL via the persistence interface.

### Why LiteLLM?

1. **True model agnosticism**: 100+ providers supported
2. **Unified interface**: Same code for Claude, GPT, Gemini, local models
3. **Cost tracking**: Built-in token counting
4. **Fallbacks**: Can configure automatic model fallbacks

### Why Separate Summarization?

Summarization is separated because:
1. **Different requirements**: May want cheaper/faster model for summaries
2. **Customizable**: Tools can override with structured extraction
3. **Optional**: Can disable for debugging full context

### Why Phase-Based Workflow?

Explicit phases combat the "action bias" in LLMs:
1. **Forces planning**: Can't test before hypothesizing
2. **Prevents loops**: Phase limits prevent infinite loops
3. **Enables reflection**: Dedicated phase for analysis
4. **Auditable**: Clear record of workflow progression
```