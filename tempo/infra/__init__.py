"""
Infrastructure module for Tempo Sec.

Exports:
    - LLMClient: Abstract LLM client
    - LiteLLMClient: LiteLLM-based implementation
    - LLMResponse: LLM response model
    - ContainerManager: Docker container management
    - Protocols: Type interfaces for cross-component type hints
    - utc_now: Timezone-aware UTC datetime helper
"""

from datetime import datetime, timezone

from tempo.infra.llm import LLMClient, LiteLLMClient, LLMResponse
from tempo.infra.container import ContainerManager
from tempo.infra.protocols import (
    ContextSummarizer,
    BranchSpawner,
    ToolOutputViewer,
    ToolCallFinder,
)


def utc_now() -> datetime:
    """Return current UTC time as a timezone-aware datetime.
    
    This replaces deprecated datetime.utcnow() which returns naive datetimes.
    """
    return datetime.now(timezone.utc)


__all__ = [
    "LLMClient",
    "LiteLLMClient",
    "LLMResponse",
    "ContainerManager",
    # Protocols
    "ContextSummarizer",
    "BranchSpawner",
    "ToolOutputViewer",
    "ToolCallFinder",
    # Utilities
    "utc_now",
]

