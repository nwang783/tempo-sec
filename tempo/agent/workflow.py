"""
Workflow manager for phase transitions and workflow rules.
"""

from datetime import datetime

from tempo.agent.config import AgentConfig
from tempo.prompts.phases import Phase, PHASE_CONFIGS


class WorkflowError(Exception):
    """Raised when workflow rules are violated."""
    pass


class WorkflowManager:
    """
    Manages phase transitions and enforces workflow rules.
    
    Tracks the current phase, enforces valid transitions,
    and monitors step counts per phase.
    """
    
    def __init__(self, config: AgentConfig, initial_phase: Phase = Phase.RECON):
        """
        Initialize the workflow manager.
        
        Args:
            config: Agent configuration
            initial_phase: Starting phase (default: RECON)
        """
        self.config = config
        self.current_phase = initial_phase
        self.phase_step_counts: dict[Phase, int] = {p: 0 for p in Phase}
        self.transition_history: list[tuple[Phase, Phase, datetime]] = []
    
    def can_transition(self, to_phase: Phase) -> bool:
        """
        Check if transition to given phase is allowed.
        
        Valid transitions are defined in PHASE_CONFIGS.
        
        Args:
            to_phase: Target phase
            
        Returns:
            True if transition is valid
        """
        current_config = PHASE_CONFIGS[self.current_phase]
        return to_phase in current_config.allowed_transitions
    
    def transition(self, to_phase: Phase) -> None:
        """
        Transition to a new phase.
        
        Args:
            to_phase: Target phase
            
        Raises:
            WorkflowError: If transition is invalid
        """
        if not self.can_transition(to_phase):
            raise WorkflowError(
                f"Cannot transition from {self.current_phase.value} to {to_phase.value}. "
                f"Allowed: {[p.value for p in PHASE_CONFIGS[self.current_phase].allowed_transitions]}"
            )
        
        # Record transition
        self.transition_history.append((self.current_phase, to_phase, datetime.utcnow()))
        self.current_phase = to_phase
    
    def record_step(self) -> None:
        """Record that a step was taken in the current phase."""
        self.phase_step_counts[self.current_phase] += 1
    
    def get_step_count(self, phase: Phase | None = None) -> int:
        """
        Get step count for a phase.
        
        Args:
            phase: Phase to check (default: current phase)
            
        Returns:
            Number of steps taken in that phase
        """
        phase = phase or self.current_phase
        return self.phase_step_counts[phase]
    
    def get_total_steps(self) -> int:
        """Get total steps across all phases."""
        return sum(self.phase_step_counts.values())
    
    def should_force_transition(self) -> Phase | None:
        """
        Check if we should force a phase transition due to limits.
        
        Returns:
            The phase to transition to, or None if no force needed.
        """
        current_config = PHASE_CONFIGS[self.current_phase]
        current_steps = self.phase_step_counts[self.current_phase]
        
        # Check phase-specific max steps
        if current_config.max_steps and current_steps >= current_config.max_steps:
            # Force transition to next logical phase
            if self.current_phase == Phase.RECON:
                return Phase.HYPOTHESIZE
            elif self.current_phase == Phase.HYPOTHESIZE:
                return Phase.TEST
            elif self.current_phase == Phase.TEST:
                return Phase.REFLECT
            # REFLECT has no forced transition - agent should finish
            return None
        
        # Check global max steps
        if self.config.max_steps and self.get_total_steps() >= self.config.max_steps:
            # Force to REFLECT to conclude
            if self.current_phase != Phase.REFLECT:
                return Phase.REFLECT
        
        return None
    
    def get_phase_prompt_additions(self) -> str:
        """
        Get additional prompt content for current phase state.
        
        Returns:
            Additional context about phase state
        """
        current_steps = self.phase_step_counts[self.current_phase]
        total_steps = self.get_total_steps()
        
        parts = [
            f"Current phase: {self.current_phase.value}",
            f"Steps in this phase: {current_steps}",
            f"Total steps: {total_steps}",
        ]
        
        # Add warnings if approaching limits
        current_config = PHASE_CONFIGS[self.current_phase]
        if current_config.max_steps:
            remaining = current_config.max_steps - current_steps
            if remaining <= 3:
                parts.append(f"⚠️ Only {remaining} steps remaining in this phase!")
        
        if self.config.max_steps:
            remaining = self.config.max_steps - total_steps
            if remaining <= 5:
                parts.append(f"⚠️ Only {remaining} total steps remaining!")
        
        return "\n".join(parts)
    
    def reset(self, initial_phase: Phase = Phase.RECON) -> None:
        """Reset the workflow to initial state."""
        self.current_phase = initial_phase
        self.phase_step_counts = {p: 0 for p in Phase}
        self.transition_history = []
