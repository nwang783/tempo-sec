"""
Workflow phases for the security agent.

Defines the Phase enum and PhaseConfig for controlling
the agent's structured workflow progression.

Note: Phase enum is defined in infra/phases.py to allow tools
to import it without violating the dependency rule that
Context/Prompts/Tools must not import from each other.
"""

from dataclasses import dataclass, field

# Import Phase from infra/ - this is the canonical location
# Re-exported here for backward compatibility
from tempo.infra.phases import Phase


@dataclass
class PhaseConfig:
    """Configuration for a workflow phase."""
    phase: Phase
    description: str
    allowed_transitions: list[Phase]
    max_steps: int | None = None  # None = no per-phase limit, use global config only
    required_outputs: list[str] = field(default_factory=list)  # e.g., ["hypotheses"] for HYPOTHESIZE


# Default phase flow configuration
PHASE_CONFIGS: dict[Phase, PhaseConfig] = {
    Phase.RECON: PhaseConfig(
        phase=Phase.RECON,
        description="Gather information about the target",
        allowed_transitions=[Phase.HYPOTHESIZE, Phase.RECON],
        required_outputs=[],
    ),
    Phase.HYPOTHESIZE: PhaseConfig(
        phase=Phase.HYPOTHESIZE,
        description="Form hypotheses about potential vulnerabilities",
        allowed_transitions=[Phase.TEST, Phase.RECON],
        required_outputs=["hypotheses"],
    ),
    Phase.TEST: PhaseConfig(
        phase=Phase.TEST,
        description="Test each hypothesis systematically",
        allowed_transitions=[Phase.REFLECT, Phase.TEST],
        required_outputs=["findings"],
    ),
    Phase.REFLECT: PhaseConfig(
        phase=Phase.REFLECT,
        description="Analyze results and plan next steps",
        allowed_transitions=[Phase.RECON, Phase.HYPOTHESIZE, Phase.TEST],
        required_outputs=[],
    ),
}
