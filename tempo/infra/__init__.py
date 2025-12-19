"""
Infrastructure module for Tempo Sec.

Exports:
    - LLMClient: Abstract LLM client
    - LiteLLMClient: LiteLLM-based implementation
    - LLMResponse: LLM response model
    - ContainerManager: Docker container management
    - Protocols: Type interfaces for cross-component type hints
"""

from tempo.infra.llm import LLMClient, LiteLLMClient, LLMResponse
from tempo.infra.container import ContainerManager
from tempo.infra.protocols import (
    PhaseTransitioner,
    ContextSummarizer,
    BranchSpawner,
    ToolOutputViewer,
)

__all__ = [
    "LLMClient",
    "LiteLLMClient",
    "LLMResponse",
    "ContainerManager",
    # Protocols
    "PhaseTransitioner",
    "ContextSummarizer",
    "BranchSpawner",
    "ToolOutputViewer",
]
