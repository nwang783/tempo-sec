# Tempo Sec

Tempo Sec is a versatile cybersecurity agent built for solving hard problems. A simple agent with some tools may be able to solve CTFs but will fall short when discovering novel vulnerabilities that require critical thinking and long-term analysis. We believe that by following the principles below, we can enable our agent to rise above what was previously thought imposible of AI agents. While there is nothing too novel about any of these ideas, I have never seen them implemented together in a cybersecurity agent from the ground up. 

## Guiding Principles

**1. Context is Sacred:** Every token in the context window should be intentional. Said another way, we should be fully aware of what is in the context at all times. For instance, using more RAM to run code with memory leaks may treat the symptom, but it doesn't attempt to solve the root of the problem. In the same way, a larger context window may treat poor context management, but it will never solve the heart of the issue. 

**2. Do Not Reinvent the Wheel:** The agent should be guided to mimic a human's workflow, including how a human would think -- not just what a human would do. Expert humans have discovered their practices out of necessity and utility, not out of mere preference. 

**3. Tools Should Expand, not Constrict:** Tools should be simple to use but deliver powerful results. Examples: file system, shell commmands, etc. Tools should not be used for scalfolding, that's what prompts are for. 

## How Tempo Sec Implements These Principles

### Context Management:

**1. Summarization of tool calls:** Each time the agent uses a tool, it will create a summary of the intention of the tool call and any useful results or observations. This summary will then replace the context of the tool call in a token efficient manner. 

**2. Avoiding MCP servers with a large amount of tools:** MCP servers consume a large amount of the context window before the agent even gets a chance to act. The agent should be presented with a lean toolset (more on this later) rather than a long list of highly specific tools. 

**3. Using Subagents for Tangential Tasks:** There is no reason a sinlge agent must complete the entire workflow. Allocating subagents to subtasks also reduces the amount of tool definitions and prompting needed for each agent. 

**4. Context and Actions Are Reversible:** The agent should be able to be restored to a previous state at any time. 

### Mimicing Human Workflow

From my analysis, it appears expert human security researchers typically follow a workflow that looks something like the following:

1. Recon and Research: Learn more about the target and note anything that draws attention. Gather the latest research and learn relevant techniques. 
2. Form Hypotheses: Create a map of potential attack surfaces and a plan for how they could be explored.
3. Test the Each Hypothesis: Use actual deterministic tools to validate/disprove each hypothesis. Create a PoC for each idea or test all possible angles before giving up.
4. Reflect: Consider what succeeded and what didn't. Revise and expand the original plan based on the findings.
5. Repeat steps 1-4: If nothing worked, then revise the original plan entirely. If some success was identified, explore that path more.

**Why this is important:** Current agents are biased towards action over reflection. They begin too quickly and stop too early. Strictly defining the workflow will help counteract some of these tendencies. 

### Choosing the Proper Toolset

Below is a list of tools that we believe will best equip the agent for success. It is subject to addition/deletion with proper justification. 

1. Running Shell Commands
- Abilities Granted: Almost infinite. It can create files, curl URLs, and run code.

2. Browser Tools
- Abilities Granted: Being able to access website content and links in a way that a simple curl request would have failed.

3. Ability to Add More Tools
- The agent should be able to request/download more tools as it sees fit.

Note: More tools may be added for specific use cases. For example, Ghidra tools would be useful for an RE agent, but would just add bloat for a web analysis agent. 

Note on security: All of the agents actions should be run in a container with no sensitive info. 

### Choosing the Proper Agent Hierarchy

For reasons mentioned above, it would be best to use more than a single agent. However, sometimes instead of creating subagents, it's better to create clones of the original agent to complete tasks in parallel. This way, the subtlities of the previous context is not lost, but the context is not cluttered with single use info. For example, if the agent identifies three separate attack surfaces, it could create three clones of itself to explore each path in parallel, then a summary of each path's actions and findings could be presented back to the agent in the very next "context frame" immediately after delegating each task. 

## Usage

### Running the Agent

You can run the agent using the provided `main.py` script:

```bash
# Basic run (uses config.toml)
python main.py

# Specify a different config
python main.py --config my_config.toml
```

### Restarting / Resuming

To restart from a specific step or phase, provide the context file from a previous run:

```bash
# Restart from step 5
python main.py --context contexts/uuid.json --restart-step 5

# Restart from 'TEST' phase
python main.py --context contexts/uuid.json --restart-phase test
```

## Contributing

Contributing is highly encouraged and welcome. This README will be updated with any new findings from building the agent.
