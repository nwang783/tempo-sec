# Tools

Tempo Sec provides a lean but powerful set of tools. The philosophy is **"simple to use, powerful results"**.

---

## Tool Categories

| Category | Tools | Purpose |
|----------|-------|---------|
| **Execution** | `shell` | Run shell commands |
| **Browsing** | `browser_*` | Web navigation and interaction |
| **Filesystem** | `file_read`, `file_write` | File operations |
| **Meta** | `transition_phase`, `summarize_tool_output`, etc. | Agent control |
| **Task** | Test plan, manifest tools | Workflow management |

---

## Core Tools

### Shell Tool

Execute shell commands in the container sandbox:

```python
shell(
    command="curl -s https://example.com | grep -o 'href=\"[^\"]*\"'",
    timeout=60,
    working_dir="/workspace",
    purpose="Extract all links from the target homepage"
)
```

### Browser Tools

Playwright-style browser interaction with ref-based element targeting and persistent state management.

#### Core Browser Tools

| Tool | Purpose |
|------|---------|
| `browser_navigate` | Navigate to URL, get page summary |
| `browser_snapshot` | Capture interactive elements with refs |
| `browser_click` | Click element by ref |
| `browser_type` | Type text into element |
| `browser_fill_form` | Fill multiple form fields |

#### Visual & Interaction Tools

| Tool | Purpose |
|------|---------|
| `browser_screenshot` | Capture screenshot (optional base64 for vision models) |
| `browser_click_coords` | Click at x,y coordinates (fallback when refs fail) |
| `browser_scroll` | Scroll page up/down by pixels |
| `browser_wait` | Wait for element or timeout |

#### State Management Tools

| Tool | Purpose |
|------|---------|
| `browser_list_states` | List all saved browser states with metadata |
| `browser_save_state` | Save current cookies/localStorage/sessionStorage |
| `browser_load_state` | Restore a previously saved state |
| `browser_delete_state` | Delete a saved state |
| `browser_cleanup_states` | Remove all expired states |

**Example workflow:**
```python
# 1. Navigate and get summary
browser_navigate(url="https://example.com/login")

# 2. Snapshot to get element refs
browser_snapshot()  # Returns refs like [ref_0], [ref_1], [ref_2]

# 3. Interact using refs
browser_type(ref="ref_0", text="username")
browser_type(ref="ref_1", text="password")
browser_click(ref="ref_2")  # Click login button
```

**State persistence workflow:**
```python
# Login and save session for later use
browser_navigate(url="https://example.com/login")
browser_snapshot()
browser_type(ref="ref_0", text="admin")
browser_type(ref="ref_1", text="password123")
browser_click(ref="ref_2")
browser_save_state(name="admin_session", description="Admin account")

# Later: reuse the saved session
browser_load_state(name="admin_session")
browser_navigate(url="https://example.com/admin")  # Already authenticated!
```

### Browser Task Tool

For parent agents (Recon, Test) to delegate browser tasks to a specialized browser agent:

```python
browser_task(
    task="Log in and explore the admin panel",
    url="https://example.com/login",
    state_name="",              # Optional: load existing session
    save_state_as="admin_session",  # Optional: save session after task
    scope="Only explore example.com domain",  # Optional: constraints
    max_steps=10
)
```

**Key parameters:**
- `task`: Description of what the browser agent should accomplish
- `url`: Starting URL (optional)
- `state_name`: Load a saved browser state before starting
- `save_state_as`: Save browser state after task completion
- `scope`: Constraints for the browser agent
- `max_steps`: Maximum steps (default: 10)

### Filesystem Tools

```python
file_read(path="/workspace/config.json")
file_write(path="/workspace/output.txt", content="...")
```

---

## Meta Tools

Control agent behavior and workflow:

### `transition_phase`
Move to a new workflow phase:
```python
transition_phase(
    phase="test",
    justification="Hypotheses complete, ready for testing",
    purpose="Begin testing phase"
)
```

### `summarize_tool_output`
Compress tool output to save context tokens:
```python
summarize_tool_output(
    tool_call_id="abc123",
    summary="Found 3 endpoints: /api/users, /api/admin, /api/login",
    purpose="Reduce context usage"
)
```

### `branch_to_subtasks`
Spawn parallel subagents:
```python
branch_to_subtasks(
    subtasks=[
        "Test SQL injection on /api/users",
        "Test XSS on search form",
        "Check for IDOR on /api/admin"
    ],
    purpose="Test hypotheses in parallel"
)
```

### `finish_subtask`
Signal subtask completion (used by subagents):
```python
finish_subtask(
    summary="Tested SQL injection, no vulnerabilities found",
    findings=[],
    purpose="Report results to main agent"
)
```

### `finish_task`
Signal overall task completion:
```python
finish_task(
    findings="Discovered XSS vulnerability in search form...",
    purpose="Complete the security assessment"
)
```

---

## Task Tools

### Test Plan Tools
- `create_test_plan` - Create structured test plan
- `update_test_plan` - Update plan items
- `get_test_plan` - Retrieve current plan

### Manifest Tools
- `save_manifest` - Save target manifest
- `load_manifest` - Load existing manifest

### View Output Tool
- `view_tool_output` - View full output of previous tool call

---

## Adding New Tools

1. **Create tool file** in `tempo/tools/`:
```python
from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema

class MyTool(Tool):
    name = "my_tool"
    description = "What this tool does"
    category = ToolCategory.ANALYSIS
    
    async def execute(self, param: str, purpose: str = "") -> ToolResult:
        # Implementation
        return ToolResult(success=True, output="...")
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "param": {"type": "string", "description": "..."},
                },
                "required": ["param"],
            },
        )
```

2. **Register in `tool_factory.py`**:
```python
from tempo.tools.my_tool import MyTool

def create_tools(...):
    registry.register(MyTool())
```

---

## Tool Output Summarization

Long outputs are automatically truncated with a message:
```
[Showing first 10000 chars of 45000 total]
...output...
[Use view_tool_output to see full output, then call summarize_tool_output]
```

The agent should then either:
1. Use `view_tool_output` if more detail needed
2. Call `summarize_tool_output` to compress for context

---

## See Also

- [ARCHITECTURE.md](ARCHITECTURE.md) - Component structure
- [WORKFLOW.md](WORKFLOW.md) - Phase workflow
