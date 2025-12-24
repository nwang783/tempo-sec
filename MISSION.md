# Tempo Sec: Mission & Philosophy

Tempo Sec is a versatile cybersecurity agent built for solving hard problems. A simple agent with some tools may be able to solve CTFs but will fall short when discovering novel vulnerabilities that require critical thinking and long-term analysis. We believe that by following the principles below, we can enable our agent to rise above what was previously thought impossible of AI agents.

---

## Guiding Principles

### 1. Context is Sacred
Every token in the context window should be intentional. Said another way, we should be fully aware of what is in the context at all times. For instance, using more RAM to run code with memory leaks may treat the symptom, but it doesn't attempt to solve the root of the problem. In the same way, a larger context window may treat poor context management, but it will never solve the heart of the issue.

### 2. Do Not Reinvent the Wheel
The agent should be guided to mimic a human's workflow, including how a human would think—not just what a human would do. Expert humans have discovered their practices out of necessity and utility, not out of mere preference.

### 3. Tools Should Expand, not Constrict
Tools should be simple to use but deliver powerful results. Examples: file system, shell commands, etc. Tools should not be used for scaffolding; that's what prompts are for.

---

## How Tempo Sec Implements These Principles

### Context Management

1. **Summarization of tool calls**: Each time the agent uses a tool, it can create a summary of the intention and results. This summary replaces the raw output in a token-efficient manner.

2. **Avoiding MCP servers with many tools**: MCP servers consume a large amount of the context window before the agent even gets a chance to act. The agent is presented with a lean toolset rather than a long list of highly specific tools.

3. **Using Subagents for Tangential Tasks**: There is no reason a single agent must complete the entire workflow. Allocating subagents to subtasks also reduces the amount of tool definitions and prompting needed for each agent.

4. **Context and Actions Are Reversible**: The agent can be restored to a previous state at any time through checkpointing.

### Mimicking Human Workflow

From our analysis, expert human security researchers typically follow a workflow like:

1. **Recon and Research**: Learn more about the target and note anything that draws attention. Gather the latest research and learn relevant techniques.
2. **Form Hypotheses**: Create a map of potential attack surfaces and a plan for how they could be explored.
3. **Test Each Hypothesis**: Use actual deterministic tools to validate/disprove each hypothesis. Create a PoC for each idea or test all possible angles before giving up.
4. **Reflect**: Consider what succeeded and what didn't. Revise and expand the original plan based on the findings.
5. **Repeat**: If nothing worked, revise the original plan entirely. If some success was identified, explore that path more.

**Why this is important**: Current agents are biased towards action over reflection. They begin too quickly and stop too early. Strictly defining the workflow helps counteract these tendencies.

### Choosing the Proper Toolset

Below is a list of core tools that best equip the agent for success:

| Tool | Abilities Granted |
|------|-------------------|
| **Shell Commands** | Almost infinite—create files, curl URLs, run code |
| **Browser Tools** | Access website content and links where simple curl fails |
| **Dynamic Tool Addition** | Agent can request/download more tools as needed |

> **Note**: More tools may be added for specific use cases. For example, Ghidra tools would be useful for an RE agent, but would just add bloat for a web analysis agent.

> **Security Note**: All agent actions run in a container with no sensitive info.

### Agent Hierarchy

Instead of just creating subagents, it's sometimes better to create clones of the original agent to complete tasks in parallel. This way, the subtleties of the previous context are not lost, but the context isn't cluttered with single-use info.

For example, if the agent identifies three separate attack surfaces, it could create three clones of itself to explore each path in parallel, then a summary of each path's actions and findings is presented back to the agent in the very next "context frame" immediately after delegating each task.

---

## Contributing

Contributing is highly encouraged and welcome. See [README.md](README.md) for getting started.
