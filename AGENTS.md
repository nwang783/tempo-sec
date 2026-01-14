# AGENTS.md

This file provides guidance for AI coding assistants working on the Tempo Sec codebase.

## Project Overview

**Tempo Sec** is a cybersecurity agent for autonomous vulnerability discovery. It uses an LLM-powered agent with deliberate context management, phase-based workflows, and sandboxed tool execution.

## Architecture: MVC for Agents

The codebase follows a strict separation pattern with four primitives:

| Component | Location | Responsibility |
|-----------|----------|----------------|
| **Context** | `tempo/context/` | State management, conversation history, branching |
| **Prompts** | `tempo/prompts/` | LLM instruction templates, phase configurations |
| **Tools** | `tempo/tools/` | Capability execution (shell, browser, files) |
| **Agent** | `tempo/agent/` | Orchestration, workflow control |
| **Agents** | `tempo/agents/` | Agent definitions (Recon, TestCycle) |
| **Infra** | `tempo/infra/` | Cross-cutting (LLM client, container, protocols) |

### Dependency Rules

> **CRITICAL**: Context, Prompts, and Tools MUST NOT import from each other.  
> They may only import from `infra/` or external packages.  
> Only Agent composes them together.

Use `tempo/infra/protocols.py` for cross-component type hints.

## Key Files

- `tempo/scripts/run.py` — Unified CLI runner
- `tempo/agents/base.py` — BaseAgentDefinition
- `tempo/agent/runner.py` — Main agent loop
- `tempo/agent/config.py` — Configuration (supports TOML via `AgentConfig.from_toml()`)
- `tempo/agent/step_handler.py` — Tool execution logic
- `tempo/tools/registry.py` — Tool registration
- `tempo/context/store.py` — Context tree management
- `tempo/infra/phases.py` — Workflow phase definitions (Phase enum)
- `tempo/infra/protocols.py` — Cross-component type interfaces

## Workflow

The agent follows a security researcher workflow via the **orchestrator pattern**:
1. **Reconnaissance**: Dispatch `recon` subagents to discover attack surfaces
2. **Testing**: Dispatch `test` subagents to validate vulnerabilities
3. **Reporting**: Finalize analysis with comprehensive report

The orchestrator coordinates subagent dispatch dynamically based on findings state.

## Testing

```bash
python -m pytest tests/ -v        # All tests
python -m pytest tests/agent/ -v  # Agent-specific tests
```

## Orchestrator Architecture

The **OrchestratorAgent** is the recommended entry point for comprehensive security analysis. It coordinates specialized subagents and manages a shared findings document.

### How It Works

```
OrchestratorAgent (claude-sonnet-4)
    |
    +-- dispatch_subagents("recon") --> ReconSubagent
    |       |                              |
    |       +-- Updates shared findings <--+
    |
    +-- dispatch_subagents("test") --> TestSubagent
    |       |                              |
    |       +-- Updates shared findings <--+
    |
    +-- finalize_analysis() --> Final Report
```

### Key Components

| Component | Purpose |
|-----------|---------|
| `OrchestratorAgent` | Strategic planning, subagent dispatch, final reporting |
| `ReconSubagent` | Attack surface discovery, technology fingerprinting |
| `TestSubagent` | Vulnerability testing, finding validation |
| `FindingsDocument` | Shared state across all agents |
| `FinalizeAnalysisTool` | Generates final report and stops orchestrator |

### Running the Orchestrator

```bash
# Basic usage
tempo --agent orchestrator --target https://example.com

# With custom findings path
tempo --agent orchestrator --target https://example.com \
    --findings ./findings/example.yaml \
    --max-iterations 15
```

### Configuration

See `config.toml` for orchestrator settings:

```toml
[orchestrator]
max_iterations = 10
default_subagent_steps = 50
model = "anthropic/claude-sonnet-4-20250514"
subagent_model = "openai/gpt-5-mini"
```

## Browser Agent

The **BrowserAgent** is a specialized subagent for web browsing tasks. It uses Playwright for browser automation.

### Capabilities

| Feature | Description |
|---------|-------------|
| **Page Navigation** | Navigate to URLs, get page summaries |
| **Element Interaction** | Click, type, fill forms using element refs |
| **Visual Capture** | Screenshots, coordinate-based clicking |
| **Scope Constraints** | Respect domain/action restrictions |

### Configuration

```toml
[browser]
headless = true          # Set to false to show browser window
default_timeout = 30000  # Navigation timeout (ms)
viewport_width = 1280
viewport_height = 720
```

### When to Use Browser Agent

**Good use cases:**
- JavaScript-rendered content (SPAs, React apps)
- Multi-step form interactions
- Authentication flows requiring cookies
- Visual verification (screenshots)
- AJAX/fetch request discovery

**Use shell/curl instead for:**
- Simple HTTP requests
- API testing
- Static HTML analysis
- Performance-critical operations

## Best Practices

1. **Follow dependency rules** — No cross-imports between Context/Prompts/Tools
2. **Use protocols** — Add new interfaces to `infra/protocols.py`
3. **Keep Agent lean** — Extract logic to helpers like `StepHandler`
4. **Tool execution in containers** — Network tools run in Docker sandbox
5. **Configuration via TOML** — Use `config.toml` pattern, not hardcoded values

## Common Tasks

| Task | Approach |
|------|----------|
| Add new tool | Create in `tools/`, register in `tool_factory.py` |
| Create new agent | Create in `agents/`, inherit `BaseAgentDefinition`, register |
| Modify prompts | Edit `prompts/templates/` and `phases.py` |
| Add config option | Update `AgentConfig` dataclass + `from_dict()` mapping |
| Extend workflow | Modify `workflow.py` phase transitions |

## Documentation

For detailed documentation, see:
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - Component architecture and structure
- [docs/WORKFLOW.md](docs/WORKFLOW.md) - Phase workflow and branching
- [docs/TOOLS.md](docs/TOOLS.md) - Tool specifications and how to add new tools
- [MISSION.md](MISSION.md) - Vision and philosophy

