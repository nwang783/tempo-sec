"""
User Prompt Manager.

Manages user prompts received mid-run and pause/resume signaling for the agent.
This class is decoupled from both the visualization server and the agent,
allowing clean integration without tight coupling.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class UserPrompt:
    """A user prompt received mid-run."""
    content: str
    timestamp: float = field(default_factory=time.time)


class UserPromptManager:
    """
    Thread-safe manager for user prompts during agent execution.
    
    The agent polls this manager between steps to check for pending prompts.
    The visualization server enqueues prompts received via WebSocket.
    
    Usage:
        # In visualization server (producer):
        await prompt_manager.enqueue("User's message")
        
        # In agent loop (consumer):
        prompt = await prompt_manager.get_pending_prompt()
        if prompt:
            context.add_message(USER, prompt.content)
        
        # For pause/resume:
        prompt_manager.pause()  # Agent signals it's pausing
        await prompt_manager.wait_for_resume()  # Blocks until user sends prompt
    """
    
    def __init__(self):
        self._queue: asyncio.Queue[UserPrompt] = asyncio.Queue()
        self._paused = asyncio.Event()
        self._paused.set()  # Start in "running" (not paused) state
        self._pause_reason: str = ""
    
    async def enqueue(self, content: str) -> None:
        """
        Add a user prompt to the queue.
        
        If the agent is paused, this will also signal resume.
        
        Args:
            content: The prompt content from the user
        """
        prompt = UserPrompt(content=content)
        await self._queue.put(prompt)
        
        # If agent is paused, signal resume
        if not self._paused.is_set():
            self._paused.set()
    
    async def get_pending_prompt(self) -> Optional[UserPrompt]:
        """
        Get the next pending prompt, or None if queue is empty.
        
        This is non-blocking and returns immediately.
        
        Returns:
            UserPrompt if available, None otherwise
        """
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None
    
    def pause(self, reason: str = "") -> None:
        """
        Signal that the agent is paused.
        
        Args:
            reason: Optional reason for the pause (e.g., "Awaiting user decision")
        """
        self._pause_reason = reason
        self._paused.clear()
    
    def resume(self) -> None:
        """Signal that the agent should resume."""
        self._pause_reason = ""
        self._paused.set()
    
    async def wait_for_resume(self, timeout: Optional[float] = None) -> bool:
        """
        Block until resume signal or timeout.
        
        Call this after pause() to wait for user input.
        
        Args:
            timeout: Maximum seconds to wait (None = wait forever)
            
        Returns:
            True if resumed (user sent prompt), False if timed out
        """
        try:
            await asyncio.wait_for(self._paused.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
    
    @property
    def is_paused(self) -> bool:
        """Check if agent is currently paused."""
        return not self._paused.is_set()
    
    @property
    def pause_reason(self) -> str:
        """Get the reason for the current pause."""
        return self._pause_reason
    
    @property
    def has_pending(self) -> bool:
        """Check if there are pending prompts."""
        return not self._queue.empty()
    
    @property
    def queue_size(self) -> int:
        """Get the number of pending prompts."""
        return self._queue.qsize()
