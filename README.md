# Tempo Sec

A cybersecurity agent for autonomous vulnerability discovery. Uses deliberate context management, human-like workflow phases, and sandboxed tool execution.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)

---

## Quick Start

### 1. Clone and Install

```bash
git clone https://github.com/nwang783/tempo-sec.git
cd tempo-sec

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .
```

### 2. Configure

```bash
# Copy example config
cp config.example.toml config.toml

# Edit with your API keys
# Required: ANTHROPIC_API_KEY or OPENAI_API_KEY or GEMINI_API_KEY in .env
cp .env.example .env
```

### 3. Run the Security Analysis

**Recommended: Use the Orchestrator (fully autonomous)**

```bash
# Run the Orchestrator Agent - coordinates recon and testing automatically
tempo --agent orchestrator --target https://mysouschef.com

# With custom findings path and max iterations
tempo --agent orchestrator --target https://example.com \
    --findings ./findings/example.yaml \
    --max-iterations 15
```

**Alternative: Run individual agents separately**

```bash
# Run the Recon Agent
tempo --agent recon --target https://mysouschef.com

# Run the Test Agent
tempo --agent test_cycle --manifest manifests/souschefhub_com_manifest.json
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [MISSION.md](MISSION.md) | Vision, guiding principles, philosophy |
| [AGENTS.md](AGENTS.md) | AI coding assistant guidance |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Component architecture, structure |
| [docs/WORKFLOW.md](docs/WORKFLOW.md) | Phase workflow, branching |
| [docs/TOOLS.md](docs/TOOLS.md) | Tool specifications |
| [diagrams/](diagrams/README.md) | Architecture diagrams |

---

## Project Structure

```
tempo-sec/
├── tempo/
│   ├── agent/          # Agent orchestration, workflow
│   ├── context/        # State management, persistence
│   ├── prompts/        # LLM instruction templates
│   ├── tools/          # Shell, browser, meta tools
│   ├── visualization/  # Real-time UI server
│   └── infra/          # LLM client, container, protocols
├── docs/               # Detailed documentation
├── diagrams/           # Architecture diagrams
├── tests/              # Test suite
└── config.toml         # Configuration
```

---

## Development

### Run Tests

```bash
python -m pytest tests/ -v
```

### Architecture Rules

**Note to Ryan:** This is my attempt to separate the main concerns of building an agentic systen. We can change this if you have a better idea.

> **CRITICAL**: Context, Prompts, and Tools MUST NOT import from each other.  
> They may only import from `infra/` or external packages.  
> Only Agent composes them together.

See [AGENTS.md](AGENTS.md) for complete development guidelines.

---

## Contributing

**Note to Ryan:** This is in here in case we do open source. 

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Run tests before submitting PR
4. Follow the architecture rules above

---

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.
