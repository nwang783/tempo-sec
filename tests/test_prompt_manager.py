"""
Unit tests for UserPromptManager.

Tests the prompt queue, pause/resume signaling, and async behavior.
"""

import asyncio
import pytest
import time

from tempo.visualization.prompt_manager import UserPromptManager, UserPrompt


class TestUserPrompt:
    """Tests for the UserPrompt dataclass."""
    
    def test_prompt_creation(self):
        """Test basic prompt creation."""
        prompt = UserPrompt(content="Test message")
        assert prompt.content == "Test message"
        assert prompt.timestamp > 0
    
    def test_prompt_with_timestamp(self):
        """Test prompt with explicit timestamp."""
        ts = 1234567890.0
        prompt = UserPrompt(content="Test", timestamp=ts)
        assert prompt.timestamp == ts


class TestUserPromptManagerBasics:
    """Basic tests for UserPromptManager."""
    
    def test_initial_state(self):
        """Test initial state is not paused and no pending prompts."""
        pm = UserPromptManager()
        assert not pm.is_paused
        assert not pm.has_pending
        assert pm.queue_size == 0
    
    @pytest.mark.asyncio
    async def test_enqueue_and_get(self):
        """Test enqueuing and retrieving prompts."""
        pm = UserPromptManager()
        
        await pm.enqueue("Hello agent")
        
        assert pm.has_pending
        assert pm.queue_size == 1
        
        prompt = await pm.get_pending_prompt()
        assert prompt is not None
        assert prompt.content == "Hello agent"
        
        # Queue should be empty now
        assert not pm.has_pending
        assert pm.queue_size == 0
    
    @pytest.mark.asyncio
    async def test_get_from_empty_queue(self):
        """Test getting from an empty queue returns None."""
        pm = UserPromptManager()
        prompt = await pm.get_pending_prompt()
        assert prompt is None
    
    @pytest.mark.asyncio
    async def test_multiple_prompts(self):
        """Test queuing multiple prompts."""
        pm = UserPromptManager()
        
        await pm.enqueue("First")
        await pm.enqueue("Second")
        await pm.enqueue("Third")
        
        assert pm.queue_size == 3
        
        # Should get them in FIFO order
        p1 = await pm.get_pending_prompt()
        p2 = await pm.get_pending_prompt()
        p3 = await pm.get_pending_prompt()
        
        assert p1.content == "First"
        assert p2.content == "Second"
        assert p3.content == "Third"


class TestUserPromptManagerPauseResume:
    """Tests for pause/resume functionality."""
    
    def test_pause(self):
        """Test pausing the manager."""
        pm = UserPromptManager()
        
        assert not pm.is_paused
        pm.pause("Test reason")
        assert pm.is_paused
        assert pm.pause_reason == "Test reason"
    
    def test_resume(self):
        """Test resuming from pause."""
        pm = UserPromptManager()
        
        pm.pause()
        assert pm.is_paused
        
        pm.resume()
        assert not pm.is_paused
        assert pm.pause_reason == ""
    
    @pytest.mark.asyncio
    async def test_enqueue_auto_resumes(self):
        """Test that enqueuing a prompt auto-resumes."""
        pm = UserPromptManager()
        
        pm.pause()
        assert pm.is_paused
        
        await pm.enqueue("Resume me")
        assert not pm.is_paused
    
    @pytest.mark.asyncio
    async def test_wait_for_resume_with_timeout(self):
        """Test wait_for_resume times out correctly."""
        pm = UserPromptManager()
        
        pm.pause()
        
        start = time.time()
        resumed = await pm.wait_for_resume(timeout=0.1)
        elapsed = time.time() - start
        
        assert not resumed
        assert elapsed >= 0.1
        assert elapsed < 0.5  # Shouldn't take too long
    
    @pytest.mark.asyncio
    async def test_wait_for_resume_with_prompt(self):
        """Test wait_for_resume returns when prompt is enqueued."""
        pm = UserPromptManager()
        
        pm.pause()
        
        async def send_prompt_after_delay():
            await asyncio.sleep(0.05)
            await pm.enqueue("User message")
        
        # Start the delayed enqueue
        asyncio.create_task(send_prompt_after_delay())
        
        start = time.time()
        resumed = await pm.wait_for_resume(timeout=1.0)
        elapsed = time.time() - start
        
        assert resumed
        assert elapsed < 0.5  # Should resume quickly, not wait full timeout
        assert pm.has_pending


class TestUserPromptManagerConcurrency:
    """Tests for concurrent access patterns."""
    
    @pytest.mark.asyncio
    async def test_concurrent_enqueue(self):
        """Test concurrent enqueuing."""
        pm = UserPromptManager()
        
        async def enqueue_batch(prefix: str, count: int):
            for i in range(count):
                await pm.enqueue(f"{prefix}-{i}")
                await asyncio.sleep(0.001)
        
        # Run multiple concurrent enqueuers
        await asyncio.gather(
            enqueue_batch("A", 5),
            enqueue_batch("B", 5),
            enqueue_batch("C", 5),
        )
        
        assert pm.queue_size == 15
        
        # Drain the queue
        prompts = []
        while pm.has_pending:
            p = await pm.get_pending_prompt()
            if p:
                prompts.append(p.content)
        
        assert len(prompts) == 15


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
