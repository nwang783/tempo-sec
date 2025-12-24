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

Playwright-style browser interaction with ref-based element targeting:

| Tool | Purpose |
|------|---------|
| `browser_navigate` | Navigate to URL, get page summary |
| `browser_snapshot` | Capture interactive elements with refs |
| `browser_click` | Click element by ref |
| `browser_type` | Type text into element |
| `browser_fill_form` | Fill multiple form fields |

**Example workflow:**
```python
# 1. Navigate and get summary
browser_navigate(url="https://example.com/login")

# 2. Snapshot to get element refs
browser_snapshot()  # Returns refs like [1], [2], [3]

# 3. Interact using refs
browser_type(ref="[1]", text="username")
browser_type(ref="[2]", text="password")
browser_click(ref="[3]")  # Click login button
```

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
