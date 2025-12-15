"""Tests for tempo/agent/workflow.py."""

import pytest

from tempo.agent.config import AgentConfig
from tempo.agent.workflow import WorkflowManager, WorkflowError
from tempo.prompts.phases import Phase


class TestWorkflowManager:
    """Tests for WorkflowManager class."""
    
    def test_init_default(self):
        """Test default initialization."""
        config = AgentConfig()
        wf = WorkflowManager(config)
        
        assert wf.current_phase == Phase.RECON
        assert wf.get_total_steps() == 0
    
    def test_init_custom_phase(self):
        """Test initialization with custom phase."""
        config = AgentConfig()
        wf = WorkflowManager(config, initial_phase=Phase.HYPOTHESIZE)
        
        assert wf.current_phase == Phase.HYPOTHESIZE
    
    def test_can_transition_valid(self):
        """Test valid phase transitions."""
        config = AgentConfig()
        wf = WorkflowManager(config)
        
        # RECON -> HYPOTHESIZE is valid
        assert wf.can_transition(Phase.HYPOTHESIZE) is True
    
    def test_can_transition_invalid(self):
        """Test invalid phase transitions."""
        config = AgentConfig()
        wf = WorkflowManager(config)
        
        # RECON -> REFLECT is not valid (must go through HYPOTHESIZE and TEST)
        assert wf.can_transition(Phase.REFLECT) is False
    
    def test_transition_success(self):
        """Test successful transition."""
        config = AgentConfig()
        wf = WorkflowManager(config)
        
        wf.transition(Phase.HYPOTHESIZE)
        
        assert wf.current_phase == Phase.HYPOTHESIZE
        assert len(wf.transition_history) == 1
    
    def test_transition_invalid_raises(self):
        """Test that invalid transition raises error."""
        config = AgentConfig()
        wf = WorkflowManager(config)
        
        with pytest.raises(WorkflowError, match="Cannot transition"):
            wf.transition(Phase.REFLECT)
    
    def test_record_step(self):
        """Test step recording."""
        config = AgentConfig()
        wf = WorkflowManager(config)
        
        wf.record_step()
        wf.record_step()
        
        assert wf.get_step_count(Phase.RECON) == 2
        assert wf.get_total_steps() == 2
    
    def test_steps_per_phase(self):
        """Test step counts are tracked per phase."""
        config = AgentConfig()
        wf = WorkflowManager(config)
        
        wf.record_step()
        wf.record_step()
        wf.transition(Phase.HYPOTHESIZE)
        wf.record_step()
        
        assert wf.get_step_count(Phase.RECON) == 2
        assert wf.get_step_count(Phase.HYPOTHESIZE) == 1
        assert wf.get_total_steps() == 3
    
    def test_should_force_transition_global_limit(self):
        """Test forced transition when hitting global limit."""
        config = AgentConfig(max_total_steps=3)
        wf = WorkflowManager(config)
        
        wf.record_step()
        wf.record_step()
        wf.record_step()
        
        # Should force to REFLECT
        assert wf.should_force_transition() == Phase.REFLECT
    
    def test_get_phase_prompt_additions(self):
        """Test phase prompt additions."""
        config = AgentConfig(max_total_steps=5)
        wf = WorkflowManager(config)
        
        wf.record_step()
        wf.record_step()
        
        additions = wf.get_phase_prompt_additions()
        
        assert "recon" in additions.lower()
        assert "2" in additions  # Steps in phase
    
    def test_reset(self):
        """Test workflow reset."""
        config = AgentConfig()
        wf = WorkflowManager(config)
        
        wf.record_step()
        wf.transition(Phase.HYPOTHESIZE)
        wf.reset()
        
        assert wf.current_phase == Phase.RECON
        assert wf.get_total_steps() == 0
        assert len(wf.transition_history) == 0


class TestWorkflowError:
    """Tests for WorkflowError exception."""
    
    def test_workflow_error(self):
        """Test WorkflowError can be raised."""
        with pytest.raises(WorkflowError):
            raise WorkflowError("Test error")
