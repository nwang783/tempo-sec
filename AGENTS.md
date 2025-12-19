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
| **Infra** | `tempo/infra/` | Cross-cutting (LLM client, container, protocols) |

### Dependency Rules

> **CRITICAL**: Context, Prompts, and Tools MUST NOT import from each other.  
> They may only import from `infra/` or external packages.  
> Only Agent composes them together.

Use `tempo/infra/protocols.py` for cross-component type hints.

## Key Files

- `tempo/agent/runner.py` — Main agent loop
- `tempo/agent/config.py` — Configuration (supports TOML via `AgentConfig.from_toml()`)
- `tempo/agent/step_handler.py` — Tool execution logic
- `tempo/tools/registry.py` — Tool registration
- `tempo/context/store.py` — Context tree management

## Workflow Phases

The agent follows a security researcher workflow: **RECON** → **HYPOTHESIZE** → **TEST** → **REFLECT**

Phase transitions happen via tool calls (`transition_phase`), not hardcoded logic.

## Testing

```bash
python -m pytest tests/ -v        # All tests
python -m pytest tests/agent/ -v  # Agent-specific tests
```

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
| Modify prompts | Edit `prompts/templates/` and `phases.py` |
| Add config option | Update `AgentConfig` dataclass + `from_dict()` mapping |
| Extend workflow | Modify `workflow.py` phase transitions |
