"""Tests for tempo/prompts/phases.py."""

import pytest

from tempo.prompts.phases import (
    PHASE_CONFIGS,
    Phase,
    PhaseConfig,
)


class TestPhase:
    """Tests for Phase enum."""
    
    def test_phase_values(self):
        """Test all phase values exist."""
        assert Phase.RECON.value == "recon"
        assert Phase.HYPOTHESIZE.value == "hypothesize"
        assert Phase.TEST.value == "test"
        assert Phase.REFLECT.value == "reflect"
    
    def test_phase_from_string(self):
        """Test creating phase from string value."""
        assert Phase("recon") == Phase.RECON
        assert Phase("test") == Phase.TEST
    
    def test_phase_is_string(self):
        """Test Phase is a string enum for easy comparison."""
        assert Phase.RECON == "recon"
        assert Phase.TEST == "test"


class TestPhaseConfig:
    """Tests for PhaseConfig dataclass."""
    
    def test_all_phases_have_config(self):
        """Test that all phases have a configuration."""
        for phase in Phase:
            assert phase in PHASE_CONFIGS
    
    def test_recon_config(self):
        """Test RECON phase configuration."""
        config = PHASE_CONFIGS[Phase.RECON]
        
        assert config.phase == Phase.RECON
        assert config.description == "Gather information about the target"
        assert Phase.HYPOTHESIZE in config.allowed_transitions
        assert Phase.RECON in config.allowed_transitions  # Can stay in recon
        assert config.required_outputs == []
    
    def test_hypothesize_config(self):
        """Test HYPOTHESIZE phase configuration."""
        config = PHASE_CONFIGS[Phase.HYPOTHESIZE]
        
        assert config.phase == Phase.HYPOTHESIZE
        assert Phase.TEST in config.allowed_transitions
        assert Phase.RECON in config.allowed_transitions  # Can go back
        assert "hypotheses" in config.required_outputs
    
    def test_test_config(self):
        """Test TEST phase configuration."""
        config = PHASE_CONFIGS[Phase.TEST]
        
        assert config.phase == Phase.TEST
        assert Phase.REFLECT in config.allowed_transitions
        assert Phase.TEST in config.allowed_transitions  # Can continue testing
        assert "findings" in config.required_outputs
    
    def test_reflect_config(self):
        """Test REFLECT phase configuration."""
        config = PHASE_CONFIGS[Phase.REFLECT]
        
        assert config.phase == Phase.REFLECT
        # Reflect can go to any phase
        assert Phase.RECON in config.allowed_transitions
        assert Phase.HYPOTHESIZE in config.allowed_transitions
        assert Phase.TEST in config.allowed_transitions
        assert config.required_outputs == []
    
    def test_default_max_steps(self):
        """Test default max steps for phases."""
        for config in PHASE_CONFIGS.values():
            assert config.max_steps == 20


class TestPhaseTransitions:
    """Tests for valid phase transitions."""
    
    def test_recon_to_hypothesize(self):
        """Test can transition from RECON to HYPOTHESIZE."""
        config = PHASE_CONFIGS[Phase.RECON]
        assert Phase.HYPOTHESIZE in config.allowed_transitions
    
    def test_hypothesize_to_test(self):
        """Test can transition from HYPOTHESIZE to TEST."""
        config = PHASE_CONFIGS[Phase.HYPOTHESIZE]
        assert Phase.TEST in config.allowed_transitions
    
    def test_test_to_reflect(self):
        """Test can transition from TEST to REFLECT."""
        config = PHASE_CONFIGS[Phase.TEST]
        assert Phase.REFLECT in config.allowed_transitions
    
    def test_cannot_skip_phases(self):
        """Test cannot skip from RECON directly to TEST."""
        config = PHASE_CONFIGS[Phase.RECON]
        assert Phase.TEST not in config.allowed_transitions
    
    def test_cannot_skip_to_reflect(self):
        """Test cannot skip from RECON directly to REFLECT."""
        config = PHASE_CONFIGS[Phase.RECON]
        assert Phase.REFLECT not in config.allowed_transitions
