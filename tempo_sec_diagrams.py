#!/usr/bin/env python3
"""
Tempo Sec UML Diagram Generator

Generates UML diagrams in both PlantUML and Mermaid formats.
PlantUML diagrams can be rendered via the public PlantUML server.

Usage:
    python tempo_sec_diagrams.py [--output-dir DIR] [--render]
    
    --output-dir: Directory to save diagrams (default: ./diagrams)
    --render: Attempt to render PlantUML diagrams to PNG via public server
"""

import os
import argparse
import base64
import zlib
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError


# =============================================================================
# PlantUML Diagrams
# =============================================================================

PLANTUML_COMPONENT_DIAGRAM = """
@startuml component_diagram
!theme plain
skinparam componentStyle rectangle
skinparam backgroundColor #FEFEFE

title Tempo Sec - Component Architecture

package "Agent Layer" as agent_layer {
    [Agent Runner] as agent
    [Workflow Manager] as workflow
    [Output Summarizer] as summarizer
}

package "Context Layer" as context_layer {
    [Context Store] as context_store
    [Branch Manager] as branch_mgr
    [Persistence] as persistence
    database "JSON Files" as json_db
}

package "Prompts Layer" as prompts_layer {
    [Prompt Builder] as prompt_builder
    [Phase Configs] as phase_configs
    folder "Templates" as templates
}

package "Tools Layer" as tools_layer {
    [Tool Registry] as registry
    [Shell Tool] as shell
    [Browser Tool] as browser
    [Filesystem Tools] as filesystem
    [Installer Tool] as installer
}

package "Infrastructure Layer" as infra_layer {
    [LLM Client] as llm_client
    [Container Manager] as container_mgr
    cloud "LiteLLM" as litellm
    node "Docker" as docker
    file "config.toml" as config_file
}

' Agent dependencies
agent --> context_store : manages state
agent --> prompt_builder : builds prompts
agent --> registry : executes tools
agent --> llm_client : LLM calls
agent --> workflow : phase control
agent --> summarizer : compress outputs
agent --> config_file : loads config

' Internal dependencies
workflow --> phase_configs
summarizer --> llm_client
summarizer --> prompt_builder

context_store --> branch_mgr
context_store --> persistence
persistence --> json_db

prompt_builder --> templates
prompt_builder --> phase_configs

registry --> shell
registry --> browser
registry --> filesystem
registry --> installer

' Infra connections
llm_client --> litellm
container_mgr --> docker
shell --> container_mgr
browser --> container_mgr
filesystem --> container_mgr

note right of agent_layer
  Orchestration layer
  Composes all components
end note

note right of context_layer
  State management
  Branching & checkpoints
end note

note right of tools_layer
  Capability execution
  Sandboxed in container
end note

@enduml
"""

PLANTUML_CLASS_DIAGRAM_CONTEXT = """
@startuml class_diagram_context
!theme plain
skinparam backgroundColor #FEFEFE

title Tempo Sec - Context Data Models

enum MessageRole {
    SYSTEM
    USER
    ASSISTANT
    TOOL_RESULT
}

class Message {
    +role: MessageRole
    +content: str
    +timestamp: datetime
    +metadata: dict
    --
    +to_dict(): dict
    +from_dict(data): Message
}

class ToolCall {
    +id: str
    +tool_name: str
    +input: dict
    +raw_output: str
    +summary: str | None
    +timestamp: datetime
    +duration_ms: int
    +success: bool
    +error: str | None
    --
    +output_for_context: str
    +tokens_saved: int
    +to_dict(): dict
    +from_dict(data): ToolCall
}

class AgentState {
    +current_phase: str
    +hypotheses: list[dict]
    +findings: list[dict]
    +notes: list[str]
    +custom: dict
    --
    +to_dict(): dict
    +from_dict(data): AgentState
}

class ContextFrame {
    +id: str
    +parent_id: str | None
    +created_at: datetime
    +messages: list[Message]
    +tool_calls: list[ToolCall]
    +state: AgentState
    +label: str
    +is_checkpoint: bool
    +is_branch_point: bool
    +branch_objective: str | None
    --
    +to_dict(): dict
    +from_dict(data): ContextFrame
}

class ContextStore {
    -frames: dict[str, ContextFrame]
    -current_frame_id: str
    -session_id: str
    -persistence_dir: str
    --
    +current_frame: ContextFrame
    +add_message(role, content): void
    +add_tool_call(tool_call): void
    +summarize_tool_call(id, summary): void
    +update_state(**kwargs): void
    +checkpoint(label): str
    +revert(frame_id): void
    +branch(n, objectives): list[str]
    +switch_to_branch(frame_id): void
    +merge_branches(ids, summaries): void
    +render_messages(): list[dict]
    +estimate_tokens(): int
    +save(): str
    +load(path): ContextStore
}

class BranchManager {
    -context_store: ContextStore
    --
    +branch_and_execute(objectives, executor): list[BranchResult]
}

class BranchResult {
    +branch_id: str
    +objective: str
    +summary: str
    +steps_taken: int
    +success: bool
    +error: str | None
}

Message --> MessageRole
ContextFrame "1" *-- "0..*" Message
ContextFrame "1" *-- "0..*" ToolCall
ContextFrame "1" *-- "1" AgentState
ContextStore "1" *-- "0..*" ContextFrame
ContextStore "1" -- "1" BranchManager
BranchManager ..> BranchResult : produces

note right of ContextFrame
  Forms a tree structure
  via parent_id references
end note

note bottom of ContextStore
  Core state management
  Handles checkpoints,
  branching, and rendering
end note

@enduml
"""

PLANTUML_CLASS_DIAGRAM_TOOLS = """
@startuml class_diagram_tools
!theme plain
skinparam backgroundColor #FEFEFE

title Tempo Sec - Tools Data Models

enum ToolCategory {
    EXECUTION
    BROWSING
    FILESYSTEM
    NETWORK
    ANALYSIS
    META
}

class ToolResult {
    +success: bool
    +output: str
    +error: str | None
    +metadata: dict
    +structured_data: Any
}

class ToolSchema {
    +name: str
    +description: str
    +parameters: dict
    --
    +to_openai_format(): dict
}

abstract class Tool {
    +name: str
    +description: str
    +category: ToolCategory
    --
    {abstract} +execute(**kwargs): ToolResult
    {abstract} +get_schema(): ToolSchema
    +default_summarizer(result): str
}

class ShellTool {
    -container: ContainerManager
    --
    +execute(command, timeout, working_dir): ToolResult
    +get_schema(): ToolSchema
    +default_summarizer(result): str
}

class BrowserTool {
    -playwright: Browser
    --
    +execute(url, extract_links, screenshot): ToolResult
    +get_schema(): ToolSchema
}

class FileReadTool {
    -container: ContainerManager
    --
    +execute(path, encoding, max_bytes): ToolResult
    +get_schema(): ToolSchema
}

class FileWriteTool {
    -container: ContainerManager
    --
    +execute(path, content, append): ToolResult
    +get_schema(): ToolSchema
}

class ToolInstallerTool {
    -container: ContainerManager
    --
    +execute(package, method): ToolResult
    +get_schema(): ToolSchema
}

class ToolRegistry {
    -tools: dict[str, Tool]
    --
    +register(tool): void
    +get(name): Tool | None
    +list_tools(): list[str]
    +get_schemas(): list[dict]
    +default(container): ToolRegistry
}

Tool --> ToolCategory
Tool --> ToolResult : produces
Tool --> ToolSchema : defines

ShellTool --|> Tool
BrowserTool --|> Tool
FileReadTool --|> Tool
FileWriteTool --|> Tool
ToolInstallerTool --|> Tool

ToolRegistry "1" o-- "0..*" Tool

@enduml
"""

PLANTUML_CLASS_DIAGRAM_AGENT = """
@startuml class_diagram_agent
!theme plain
skinparam backgroundColor #FEFEFE

title Tempo Sec - Agent & Infrastructure Models

class TokenUsage {
    +prompt_tokens: int
    +completion_tokens: int
    +total_tokens: int
}

class ToolCallRequest {
    +id: str
    +name: str
    +arguments: dict
}

class LLMResponse {
    +content: str | None
    +tool_calls: list[ToolCallRequest]
    +usage: TokenUsage
    +model: str
    +finish_reason: str
    +raw_response: Any
}

abstract class LLMClient {
    {abstract} +complete(messages, tools): LLMResponse
    {abstract} +complete_structured(messages, model): T
}

class LiteLLMClient {
    -model: str
    -instructor_client: Instructor
    --
    +complete(messages, tools, temp, max_tokens): LLMResponse
    +complete_structured(messages, response_model): T
    -_normalize_response(response): LLMResponse
}

class AgentConfig {
    +model: str
    +temperature: float
    +max_tokens: int
    +max_context_tokens: int
    +auto_summarize: bool
    +summarization_model: str | None
    +enforce_phases: bool
    +max_steps_per_phase: int
    +max_total_steps: int
    +max_branches: int
    +max_branch_depth: int
    +branch_step_limit: int
    +container_image: str
    +container_timeout: int
    +persistence_dir: str
    +auto_checkpoint: bool
    +allowed_domains: list[str]
    +excluded_domains: list[str]
    +allow_subdomains: bool
    +verbose: bool
}

class StepResult {
    +step_number: int
    +llm_response: LLMResponse
    +tool_calls: list[ToolCall]
    +phase_transition: Phase | None
    +should_continue: bool
    +error: str | None
}

class AgentResult {
    +success: bool
    +objective: str
    +steps_taken: int
    +final_phase: Phase
    +findings: list[dict]
    +hypotheses: list[dict]
    +context_id: str
    +error: str | None
}

class Agent {
    -context: ContextStore
    -prompts: PromptBuilder
    -tools: ToolRegistry
    -llm: LLMClient
    -config: AgentConfig
    -workflow: WorkflowManager
    -summarizer: OutputSummarizer
    --
    +run(objective, initial_phase, max_steps): AgentResult
    +step(): StepResult
    +branch_explore(objectives, steps): list[BranchResult]
    +checkpoint(label): str
    +revert(frame_id): void
}

class WorkflowManager {
    -config: AgentConfig
    -current_phase: Phase
    -phase_step_counts: dict
    -transition_history: list
    --
    +can_transition(to_phase): bool
    +transition(to_phase): void
    +record_step(): void
    +should_force_transition(): Phase | None
}

class OutputSummarizer {
    -llm: LLMClient
    -prompts: PromptBuilder
    -config: AgentConfig
    --
    +summarize(tool_call, objective, tool): str
    +should_summarize(tool_call): bool
}

LLMResponse *-- TokenUsage
LLMResponse *-- "0..*" ToolCallRequest
LiteLLMClient --|> LLMClient
LiteLLMClient ..> LLMResponse : produces

Agent *-- AgentConfig
Agent --> ContextStore
Agent --> PromptBuilder
Agent --> ToolRegistry
Agent --> LLMClient
Agent --> WorkflowManager
Agent --> OutputSummarizer
Agent ..> StepResult : produces
Agent ..> AgentResult : produces

OutputSummarizer --> LLMClient
OutputSummarizer --> PromptBuilder

@enduml
"""

PLANTUML_SEQUENCE_DIAGRAM = """
@startuml sequence_diagram
!theme plain
skinparam backgroundColor #FEFEFE

title Tempo Sec - Agent Step Sequence

participant "User" as user
participant "Agent" as agent
participant "ContextStore" as context
participant "PromptBuilder" as prompts
participant "ToolRegistry" as tools
participant "LLMClient" as llm
participant "OutputSummarizer" as summarizer
participant "Container" as container

user -> agent: run(objective)
activate agent

loop for each step until done
    agent -> context: render_messages()
    activate context
    context --> agent: messages[]
    deactivate context
    
    agent -> prompts: build_system_prompt(phase, tools)
    activate prompts
    prompts --> agent: system_prompt
    deactivate prompts
    
    agent -> tools: get_schemas()
    activate tools
    tools --> agent: tool_schemas[]
    deactivate tools
    
    agent -> llm: complete(messages, tools)
    activate llm
    llm --> agent: LLMResponse
    deactivate llm
    
    alt LLM requests tool call
        agent -> tools: get(tool_name)
        tools --> agent: Tool
        
        agent -> container: execute(tool_input)
        activate container
        container --> agent: ToolResult
        deactivate container
        
        agent -> context: add_tool_call(tool_call)
        
        alt auto_summarize enabled
            agent -> summarizer: summarize(tool_call, objective)
            activate summarizer
            summarizer -> llm: complete(summarize_prompt)
            llm --> summarizer: summary
            summarizer --> agent: summary
            deactivate summarizer
            
            agent -> context: summarize_tool_call(id, summary)
        end
        
    else LLM returns content
        agent -> context: add_message(ASSISTANT, content)
        
        alt phase transition detected
            agent -> agent: workflow.transition(new_phase)
            agent -> context: update_state(current_phase)
        end
    end
    
    agent -> context: checkpoint() [if auto_checkpoint]
end

agent --> user: AgentResult

deactivate agent

@enduml
"""

PLANTUML_STATE_DIAGRAM = """
@startuml state_diagram
!theme plain
skinparam backgroundColor #FEFEFE

title Tempo Sec - Workflow Phase State Machine

[*] --> RECON : start

state RECON {
    [*] --> Gathering
    Gathering : Scan target
    Gathering : Identify services
    Gathering : Note anomalies
    Gathering --> [*] : info gathered
}

state HYPOTHESIZE {
    [*] --> Analyzing
    Analyzing : Review recon data
    Analyzing : Form theories
    Analyzing : Prioritize by risk
    Analyzing --> [*] : hypotheses ready
}

state TEST {
    [*] --> Testing
    Testing : Execute test plan
    Testing : Record results
    Testing : Build PoCs
    Testing --> [*] : tests complete
}

state REFLECT {
    [*] --> Evaluating
    Evaluating : Analyze findings
    Evaluating : Identify patterns
    Evaluating : Plan next steps
    Evaluating --> [*] : reflection done
}

RECON --> HYPOTHESIZE : PHASE: hypothesize
RECON --> RECON : need more info

HYPOTHESIZE --> TEST : PHASE: test
HYPOTHESIZE --> RECON : need more recon

TEST --> REFLECT : PHASE: reflect
TEST --> TEST : more tests needed

REFLECT --> RECON : new attack surface
REFLECT --> HYPOTHESIZE : new hypothesis
REFLECT --> TEST : need verification
REFLECT --> [*] : complete

note right of RECON
  Max steps enforced
  per phase
end note

note right of TEST
  Can branch here for
  parallel hypothesis testing
end note

@enduml
"""

PLANTUML_ACTIVITY_BRANCHING = """
@startuml activity_branching
!theme plain
skinparam backgroundColor #FEFEFE

title Tempo Sec - Branching Flow

start

:Agent identifies multiple\\nattack surfaces;

:Create checkpoint;

fork
    :Clone A\\n(Surface 1);
    :Explore path;
    :Generate summary A;
fork again
    :Clone B\\n(Surface 2);
    :Explore path;
    :Generate summary B;
fork again
    :Clone C\\n(Surface 3);
    :Explore path;
    :Generate summary C;
end fork

:Merge summaries into\\nmain context;

:Main agent continues\\nwith all findings;

stop

note right
  Each clone gets identical
  context up to branch point
  
  Clones execute in parallel
  (or sequentially if resources limited)
  
  Summaries injected into
  next "context frame"
end note

@enduml
"""


# =============================================================================
# Mermaid Diagrams (Alternative format)
# =============================================================================

MERMAID_COMPONENT_DIAGRAM = """
```mermaid
flowchart TB
    subgraph Agent["Agent Layer"]
        AR[Agent Runner]
        WM[Workflow Manager]
        OS[Output Summarizer]
    end
    
    subgraph Context["Context Layer"]
        CS[Context Store]
        BM[Branch Manager]
        PS[Persistence]
        JF[(JSON Files)]
    end
    
    subgraph Prompts["Prompts Layer"]
        PB[Prompt Builder]
        PC[Phase Configs]
        TM[Templates]
    end
    
    subgraph Tools["Tools Layer"]
        TR[Tool Registry]
        ST[Shell Tool]
        BT[Browser Tool]
        FT[Filesystem Tools]
        IT[Installer Tool]
    end
    
    subgraph Infra["Infrastructure Layer"]
        LC[LLM Client]
        CM[Container Manager]
        LL{{LiteLLM}}
        DK{{Docker}}
        CF[config.toml]
    end
    
    AR --> CS
    AR --> PB
    AR --> TR
    AR --> LC
    AR --> WM
    AR --> OS
    AR --> CF
    
    WM --> PC
    OS --> LC
    OS --> PB
    
    CS --> BM
    CS --> PS
    PS --> JF
    
    PB --> TM
    PB --> PC
    
    TR --> ST
    TR --> BT
    TR --> FT
    TR --> IT
    
    LC --> LL
    CM --> DK
    ST --> CM
    BT --> CM
    FT --> CM
```
"""

MERMAID_CLASS_DIAGRAM = """
```mermaid
classDiagram
    class ContextFrame {
        +String id
        +String parent_id
        +DateTime created_at
        +List~Message~ messages
        +List~ToolCall~ tool_calls
        +AgentState state
        +String label
        +Boolean is_checkpoint
        +Boolean is_branch_point
        +to_dict() Dict
        +from_dict(data) ContextFrame
    }
    
    class Message {
        +MessageRole role
        +String content
        +DateTime timestamp
        +Dict metadata
    }
    
    class ToolCall {
        +String id
        +String tool_name
        +Dict input
        +String raw_output
        +String summary
        +Boolean success
        +output_for_context() String
        +tokens_saved() Int
    }
    
    class AgentState {
        +String current_phase
        +List hypotheses
        +List findings
        +List notes
    }
    
    class ContextStore {
        +ContextFrame current_frame
        +add_message(role, content)
        +add_tool_call(tool_call)
        +summarize_tool_call(id, summary)
        +checkpoint(label) String
        +revert(frame_id)
        +branch(n, objectives) List
        +merge_branches(ids, summaries)
        +render_messages() List
    }
    
    class Agent {
        +ContextStore context
        +PromptBuilder prompts
        +ToolRegistry tools
        +LLMClient llm
        +AgentConfig config
        +run(objective) AgentResult
        +step() StepResult
        +branch_explore(objectives) List
    }
    
    ContextFrame "1" *-- "0..*" Message
    ContextFrame "1" *-- "0..*" ToolCall
    ContextFrame "1" *-- "1" AgentState
    ContextStore "1" *-- "0..*" ContextFrame
    Agent --> ContextStore
    Agent --> ToolRegistry
    Agent --> LLMClient
```
"""

MERMAID_SEQUENCE_DIAGRAM = """
```mermaid
sequenceDiagram
    participant U as User
    participant A as Agent
    participant C as ContextStore
    participant P as PromptBuilder
    participant T as ToolRegistry
    participant L as LLMClient
    participant S as Summarizer
    participant D as Container
    
    U->>A: run(objective)
    
    loop Each Step
        A->>C: render_messages()
        C-->>A: messages[]
        
        A->>P: build_system_prompt(phase)
        P-->>A: prompt
        
        A->>T: get_schemas()
        T-->>A: schemas[]
        
        A->>L: complete(messages, tools)
        L-->>A: LLMResponse
        
        alt Tool Call Requested
            A->>T: get(tool_name)
            T-->>A: Tool
            A->>D: execute(input)
            D-->>A: ToolResult
            A->>C: add_tool_call()
            
            opt Auto Summarize
                A->>S: summarize(tool_call)
                S->>L: complete(prompt)
                L-->>S: summary
                S-->>A: summary
                A->>C: summarize_tool_call()
            end
        else Content Response
            A->>C: add_message()
        end
    end
    
    A-->>U: AgentResult
```
"""

MERMAID_STATE_DIAGRAM = """
```mermaid
stateDiagram-v2
    [*] --> RECON
    
    RECON --> HYPOTHESIZE: PHASE: hypothesize
    RECON --> RECON: need more info
    
    HYPOTHESIZE --> TEST: PHASE: test
    HYPOTHESIZE --> RECON: need more recon
    
    TEST --> REFLECT: PHASE: reflect
    TEST --> TEST: more tests
    
    REFLECT --> RECON: new surface
    REFLECT --> HYPOTHESIZE: new hypothesis
    REFLECT --> TEST: verify
    REFLECT --> [*]: complete
    
    note right of RECON
        Gather info
        Map attack surface
        Note anomalies
    end note
    
    note right of TEST
        Can branch for
        parallel testing
    end note
```
"""

MERMAID_BRANCHING_DIAGRAM = """
```mermaid
flowchart TD
    A[Main Agent @ Frame 5] --> B{Identify Attack Surfaces}
    B --> C[Clone A: Surface 1]
    B --> D[Clone B: Surface 2]
    B --> E[Clone C: Surface 3]
    
    C --> F[Explore & Test]
    D --> G[Explore & Test]
    E --> H[Explore & Test]
    
    F --> I[Summary A]
    G --> J[Summary B]
    H --> K[Summary C]
    
    I --> L[Merge into Main Context]
    J --> L
    K --> L
    
    L --> M[Main Agent @ Frame 6<br/>Contains all summaries]
```
"""


# =============================================================================
# Diagram Generation Functions
# =============================================================================

def ensure_dir(path: str) -> None:
    """Create directory if it doesn't exist."""
    Path(path).mkdir(parents=True, exist_ok=True)


def save_plantuml(content: str, filename: str, output_dir: str) -> str:
    """Save PlantUML content to file."""
    filepath = os.path.join(output_dir, f"{filename}.puml")
    with open(filepath, 'w') as f:
        f.write(content.strip())
    return filepath


def save_mermaid(content: str, filename: str, output_dir: str) -> str:
    """Save Mermaid content to file."""
    filepath = os.path.join(output_dir, f"{filename}.mermaid")
    # Strip the markdown code fence if present
    clean_content = content.strip()
    if clean_content.startswith("```mermaid"):
        clean_content = clean_content[10:]
    if clean_content.endswith("```"):
        clean_content = clean_content[:-3]
    with open(filepath, 'w') as f:
        f.write(clean_content.strip())
    return filepath


def plantuml_encode(text: str) -> str:
    """Encode PlantUML text for URL."""
    # PlantUML uses a custom base64 encoding
    compressed = zlib.compress(text.encode('utf-8'))[2:-4]
    
    # Custom base64 alphabet used by PlantUML
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
    
    result = []
    for i in range(0, len(compressed), 3):
        chunk = compressed[i:i+3]
        if len(chunk) == 3:
            b1, b2, b3 = chunk
            result.append(alphabet[b1 >> 2])
            result.append(alphabet[((b1 & 0x3) << 4) | (b2 >> 4)])
            result.append(alphabet[((b2 & 0xF) << 2) | (b3 >> 6)])
            result.append(alphabet[b3 & 0x3F])
        elif len(chunk) == 2:
            b1, b2 = chunk
            result.append(alphabet[b1 >> 2])
            result.append(alphabet[((b1 & 0x3) << 4) | (b2 >> 4)])
            result.append(alphabet[(b2 & 0xF) << 2])
        elif len(chunk) == 1:
            b1 = chunk[0]
            result.append(alphabet[b1 >> 2])
            result.append(alphabet[(b1 & 0x3) << 4])
    
    return ''.join(result)


def render_plantuml_url(content: str, format: str = "png") -> str:
    """Generate PlantUML server URL for rendering."""
    encoded = plantuml_encode(content.strip())
    return f"https://www.plantuml.com/plantuml/{format}/{encoded}"


def download_plantuml_image(content: str, filepath: str) -> bool:
    """Download rendered PlantUML image from public server."""
    url = render_plantuml_url(content, "png")
    try:
        req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urlopen(req, timeout=30) as response:
            with open(filepath, 'wb') as f:
                f.write(response.read())
        return True
    except URLError as e:
        print(f"  Warning: Could not download from PlantUML server: {e}")
        return False
    except Exception as e:
        print(f"  Warning: Error downloading image: {e}")
        return False


def generate_all_diagrams(output_dir: str, render: bool = False) -> dict:
    """Generate all diagrams and optionally render them."""
    
    ensure_dir(output_dir)
    plantuml_dir = os.path.join(output_dir, "plantuml")
    mermaid_dir = os.path.join(output_dir, "mermaid")
    ensure_dir(plantuml_dir)
    ensure_dir(mermaid_dir)
    
    results = {
        "plantuml": [],
        "mermaid": [],
        "rendered": []
    }
    
    # PlantUML diagrams
    plantuml_diagrams = [
        ("component_diagram", PLANTUML_COMPONENT_DIAGRAM, "High-level component architecture"),
        ("class_diagram_context", PLANTUML_CLASS_DIAGRAM_CONTEXT, "Context layer data models"),
        ("class_diagram_tools", PLANTUML_CLASS_DIAGRAM_TOOLS, "Tools layer data models"),
        ("class_diagram_agent", PLANTUML_CLASS_DIAGRAM_AGENT, "Agent & infrastructure models"),
        ("sequence_diagram", PLANTUML_SEQUENCE_DIAGRAM, "Agent step execution flow"),
        ("state_diagram", PLANTUML_STATE_DIAGRAM, "Workflow phase state machine"),
        ("activity_branching", PLANTUML_ACTIVITY_BRANCHING, "Branching/cloning flow"),
    ]
    
    print("Generating PlantUML diagrams...")
    for name, content, description in plantuml_diagrams:
        filepath = save_plantuml(content, name, plantuml_dir)
        results["plantuml"].append({
            "name": name,
            "path": filepath,
            "description": description,
            "url": render_plantuml_url(content)
        })
        print(f"  ✓ {name}.puml - {description}")
        
        if render:
            png_path = os.path.join(plantuml_dir, f"{name}.png")
            print(f"    Rendering to {name}.png...")
            if download_plantuml_image(content, png_path):
                results["rendered"].append(png_path)
                print(f"    ✓ Rendered successfully")
    
    # Mermaid diagrams
    mermaid_diagrams = [
        ("component_diagram", MERMAID_COMPONENT_DIAGRAM, "High-level component architecture"),
        ("class_diagram", MERMAID_CLASS_DIAGRAM, "Core class relationships"),
        ("sequence_diagram", MERMAID_SEQUENCE_DIAGRAM, "Agent step execution flow"),
        ("state_diagram", MERMAID_STATE_DIAGRAM, "Workflow phase state machine"),
        ("branching_diagram", MERMAID_BRANCHING_DIAGRAM, "Branching/cloning flow"),
    ]
    
    print("\nGenerating Mermaid diagrams...")
    for name, content, description in mermaid_diagrams:
        filepath = save_mermaid(content, name, mermaid_dir)
        results["mermaid"].append({
            "name": name,
            "path": filepath,
            "description": description
        })
        print(f"  ✓ {name}.mermaid - {description}")
    
    # Generate index file
    generate_index(output_dir, results)
    
    return results


def generate_index(output_dir: str, results: dict) -> None:
    """Generate an index markdown file with all diagrams."""
    
    index_content = """# Tempo Sec - UML Diagrams

This directory contains UML diagrams for the Tempo Sec cybersecurity agent.

## Viewing the Diagrams

### PlantUML Diagrams

PlantUML files (`.puml`) can be viewed in several ways:

1. **Online**: Click the URLs below to view rendered diagrams
2. **VS Code**: Install the "PlantUML" extension
3. **IntelliJ**: Built-in PlantUML support
4. **Command line**: `java -jar plantuml.jar diagram.puml`

### Mermaid Diagrams

Mermaid files (`.mermaid`) can be viewed in:

1. **GitHub**: Renders automatically in markdown
2. **VS Code**: Install "Mermaid Preview" extension
3. **Online**: Use [Mermaid Live Editor](https://mermaid.live)

---

## PlantUML Diagrams

| Diagram | Description | View Online |
|---------|-------------|-------------|
"""
    
    for item in results["plantuml"]:
        index_content += f"| [{item['name']}](plantuml/{item['name']}.puml) | {item['description']} | [View]({item['url']}) |\n"
    
    index_content += """
## Mermaid Diagrams

| Diagram | Description |
|---------|-------------|
"""
    
    for item in results["mermaid"]:
        index_content += f"| [{item['name']}](mermaid/{item['name']}.mermaid) | {item['description']} |\n"
    
    index_content += """
---

## Diagram Descriptions

### Component Diagram
Shows the high-level architecture of Tempo Sec with its four main layers:
- **Agent Layer**: Orchestration and workflow management
- **Context Layer**: State management with branching/checkpointing
- **Tools Layer**: Capability execution in sandboxed container
- **Prompts Layer**: LLM instruction templates
- **Infrastructure Layer**: LLM client and container management

### Class Diagrams
Detail the data models for each component:
- **Context models**: ContextFrame, Message, ToolCall, AgentState
- **Tool models**: Tool base class, ToolRegistry, specific tools
- **Agent models**: Agent, AgentConfig, LLMClient, WorkflowManager

### Sequence Diagram
Shows the flow of a single agent step:
1. Render context messages
2. Build system prompt
3. Call LLM with tools
4. Execute tool if requested
5. Summarize output (optional)
6. Update context

### State Diagram
Shows the workflow phase state machine:
- RECON → HYPOTHESIZE → TEST → REFLECT
- Valid transitions between phases
- Enforced step limits per phase

### Branching Diagram
Shows how the agent clones itself to explore multiple paths:
1. Identify attack surfaces
2. Create checkpoint
3. Spawn clones (parallel exploration)
4. Collect summaries
5. Merge back to main context
"""
    
    index_path = os.path.join(output_dir, "README.md")
    with open(index_path, 'w') as f:
        f.write(index_content)
    
    print(f"\n✓ Generated index at {index_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate UML diagrams for Tempo Sec"
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="./diagrams",
        help="Output directory for diagrams (default: ./diagrams)"
    )
    parser.add_argument(
        "--render", "-r",
        action="store_true",
        help="Render PlantUML diagrams to PNG via public server"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Tempo Sec UML Diagram Generator")
    print("=" * 60)
    print(f"\nOutput directory: {args.output_dir}")
    print(f"Render to PNG: {args.render}\n")
    
    results = generate_all_diagrams(args.output_dir, args.render)
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"PlantUML diagrams: {len(results['plantuml'])}")
    print(f"Mermaid diagrams:  {len(results['mermaid'])}")
    if args.render:
        print(f"Rendered PNGs:     {len(results['rendered'])}")
    print(f"\nAll files saved to: {args.output_dir}")
    print("\nView online by visiting the URLs in diagrams/README.md")


if __name__ == "__main__":
    main()
