# Tempo Sec - Architecture Diagrams

This directory contains architecture diagrams for the Tempo Sec cybersecurity agent.

> **Note**: Mermaid diagrams are the **primary source of truth**. PlantUML files and PNGs may be outdated.

## Quick Reference

| Diagram | Description |
|---------|-------------|
| [Component Diagram](mermaid/component_diagram.mermaid) | High-level architecture with all layers |
| [Class Diagram](mermaid/class_diagram.mermaid) | Core classes and relationships |
| [Sequence Diagram](mermaid/sequence_diagram.mermaid) | Agent step execution flow |
| [State Diagram](mermaid/state_diagram.mermaid) | Workflow phase transitions |
| [Branching Diagram](mermaid/branching_diagram.mermaid) | Parallel hypothesis testing |

---

## Viewing Diagrams

### Mermaid (Recommended)
- **GitHub**: Renders automatically in markdown
- **VS Code**: Install "Mermaid Preview" extension
- **Online**: Use [Mermaid Live Editor](https://mermaid.live)

### PlantUML (Legacy)
PlantUML files and PNGs in `plantuml/` may be outdated. Use mermaid versions for current architecture.

---

## Diagram Descriptions

### Component Diagram
Shows the high-level architecture with 6 main layers:
- **Agent Layer**: Runner, StepHandler, WorkflowManager, BranchCoordinator, EventBus
- **Context Layer**: ContextStore, Persistence
- **Tools Layer**: Registry, shell, browser tools (5), meta tools, task tools
- **Prompts Layer**: Builder, Templates, Phase Configs
- **Visualization Layer**: Server, Collector, UI
- **Infrastructure Layer**: LLM Client, Container Manager, Protocols

### Class Diagram
Core classes including:
- Context: `ContextStore`, `ContextFrame`, `Message`, `ToolCall`, `AgentState`
- Agent: `Agent`, `StepHandler`, `BranchCoordinator`, `WorkflowManager`
- Tools: `Tool` (abstract), `ToolRegistry`, `BrowserSession`
- Visualization: `VisualizationServer`, `VisualizationCollector`
- Infrastructure: `LLMClient`, `LLMResponse`, `ContainerManager`

### Sequence Diagram
Shows the flow of a single agent step:
1. Render context messages
2. Build system prompt
3. Call LLM with tools
4. StepHandler executes tool
5. EventBus broadcasts to VisualizationServer
6. Update context

### State Diagram
Workflow phase state machine:
- **RECON** → **HYPOTHESIZE** → **TEST** → **REFLECT**
- Transitions happen via `transition_phase` tool
- REFLECT can pause for user input
- Completion via `finish_task` tool

### Branching Diagram
Parallel hypothesis testing flow:
1. Main agent calls `branch_to_subtasks`
2. BranchCoordinator spawns subagents
3. Each subagent tests independently
4. Subagents call `finish_subtask`
5. Summaries merged back to main context

---

## Updating Diagrams

When making code changes that affect architecture:

1. Update the relevant mermaid file(s)
2. Test rendering in VS Code or Mermaid Live Editor
3. PlantUML files are optional - update only if needed for specific tooling

Last updated: December 2024
