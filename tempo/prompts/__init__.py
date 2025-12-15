"""
Prompts module for Tempo Sec.

Exports:
    - Phase: Workflow phase enum
    - PhaseConfig: Configuration for workflow phases
    - PHASE_CONFIGS: Default phase configurations
"""

from tempo.prompts.phases import (
    PHASE_CONFIGS,
    Phase,
    PhaseConfig,
)

__all__ = [
    "Phase",
    "PhaseConfig",
    "PHASE_CONFIGS",
]
