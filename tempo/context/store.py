"""
Context store for managing the agent's context tree.

Provides operations for message management, checkpointing,
branching, and context rendering.
"""

import uuid
from datetime import datetime

from tempo.context.frame import (
    AgentState,
    ContextFrame,
    Message,
    MessageRole,
    ToolCall,
)
from tempo.context.persistence import (
    ContextTreeData,
    load_context_tree,
    save_context_tree,
)


class ContextStore:
    """
    Manages the context tree and provides operations for
    checkpointing, branching, and context rendering.
    """
    
    def __init__(
        self,
        persistence_dir: str = "./contexts",
        session_id: str | None = None,
    ):
        """
        Initialize a new context store.
        
        Args:
            persistence_dir: Directory for saving context files
            session_id: Optional ID to resume an existing session
        """
        self._persistence_dir = persistence_dir
        self._session_id = session_id or str(uuid.uuid4())
        self._frames: dict[str, ContextFrame] = {}
        self._current_frame_id: str | None = None
        
        # Create root frame
        root = ContextFrame()
        self._frames[root.id] = root
        self._current_frame_id = root.id
    
    # === Core Properties ===
    
    @property
    def current_frame(self) -> ContextFrame:
        """Get the current (active) frame."""
        if self._current_frame_id is None:
            raise RuntimeError("No current frame")
        return self._frames[self._current_frame_id]
    
    @property
    def session_id(self) -> str:
        """Get the session ID for this context tree."""
        return self._session_id
    
    # === Message Management ===
    
    def add_message(self, role: MessageRole, content: str, **metadata) -> None:
        """
        Add a message to the current frame.
        
        Args:
            role: Message role (SYSTEM, USER, ASSISTANT, TOOL_RESULT)
            content: Message content
            **metadata: Optional metadata to attach
        """
        message = Message(role=role, content=content, metadata=metadata)
        self.current_frame.messages.append(message)
    
    def add_tool_call(self, tool_call: ToolCall) -> None:
        """
        Record a tool call in the current frame.
        
        Args:
            tool_call: The tool call to record
        """
        self.current_frame.tool_calls.append(tool_call)
    
    def summarize_tool_call(self, tool_call_id: str, summary: str) -> None:
        """
        Replace a tool call's raw output with a summary.
        The raw output is preserved but won't be included in rendered context.
        
        Args:
            tool_call_id: ID of the tool call to summarize
            summary: The summary text
            
        Raises:
            KeyError: If tool call not found
        """
        # Search in current frame and ancestors
        frame_id = self._current_frame_id
        while frame_id is not None:
            frame = self._frames[frame_id]
            for tc in frame.tool_calls:
                if tc.id == tool_call_id:
                    tc.summary = summary
                    return
            frame_id = frame.parent_id
        
        raise KeyError(f"Tool call not found: {tool_call_id}")
    
    def replace_messages_with_summary(
        self,
        start_index: int,
        end_index: int,
        summary: str,
    ) -> None:
        """
        Replace a range of messages with a single summary message.
        
        Used after REFLECT phase to replace the previous cycle's context
        with a concise summary, saving tokens for long runs.
        
        Args:
            start_index: First message index to replace (inclusive)
            end_index: Last message index to replace (exclusive)
            summary: The summary text to insert
        """
        messages = self.current_frame.messages
        
        # Validate indices
        if start_index < 0 or end_index > len(messages) or start_index >= end_index:
            return  # Nothing to replace
        
        # Keep messages before start_index
        before = messages[:start_index]
        # Keep messages after end_index
        after = messages[end_index:]
        
        # Create summary message
        summary_msg = Message(
            role=MessageRole.SYSTEM,
            content=f"[Previous Cycle Summary]\n{summary}",
        )
        
        # Rebuild message list
        self.current_frame.messages = list(before) + [summary_msg] + list(after)
        
        # Also clear tool calls from the replaced range (they're summarized now)
        # We keep tool calls as they may be referenced, but mark them as summarized
        for tc in self.current_frame.tool_calls:
            if tc.summary is None:
                tc.summary = "[Included in cycle summary]"
    
    # === State Management ===
    
    def update_state(self, **kwargs) -> None:
        """
        Update the agent state in the current frame.
        
        Args:
            **kwargs: State fields to update (current_phase, hypotheses, 
                      findings, notes, custom)
        """
        state = self.current_frame.state
        for key, value in kwargs.items():
            if hasattr(state, key):
                setattr(state, key, value)
    
    def get_state(self) -> AgentState:
        """Get the current agent state."""
        return self.current_frame.state
    
    # === Checkpointing ===
    
    def checkpoint(self, label: str = "") -> str:
        """
        Create a checkpoint of the current state.
        
        Args:
            label: Optional human-readable label for the checkpoint
            
        Returns:
            The frame ID that can be used for revert
        """
        self.current_frame.is_checkpoint = True
        self.current_frame.label = label
        return self.current_frame.id
    
    def revert(self, frame_id: str) -> None:
        """
        Revert to a previous checkpoint.
        Creates a new frame branching from the checkpoint.
        
        Args:
            frame_id: ID of the checkpoint to revert to
            
        Raises:
            KeyError: If frame not found
        """
        if frame_id not in self._frames:
            raise KeyError(f"Frame not found: {frame_id}")
        
        # Create a new frame branching from the checkpoint
        new_frame = ContextFrame(parent_id=frame_id)
        new_frame.state = AgentState.from_dict(self._frames[frame_id].state.to_dict())
        
        self._frames[new_frame.id] = new_frame
        self._current_frame_id = new_frame.id
    
    def list_checkpoints(self) -> list[tuple[str, str, datetime]]:
        """
        List all checkpoints as (frame_id, label, timestamp) tuples.
        
        Returns:
            List of checkpoint info, sorted by timestamp
        """
        checkpoints = [
            (frame.id, frame.label, frame.created_at)
            for frame in self._frames.values()
            if frame.is_checkpoint
        ]
        return sorted(checkpoints, key=lambda x: x[2])
    
    # === Branching ===
    
    def branch(self, n: int, objectives: list[str] | None = None) -> list[str]:
        """
        Create n branches from the current frame.
        
        Args:
            n: Number of branches to create
            objectives: Optional list of objectives for each branch
            
        Returns:
            List of frame IDs for the new branches
        """
        if objectives and len(objectives) != n:
            raise ValueError(f"Expected {n} objectives, got {len(objectives)}")
        
        # Mark current frame as branch point
        self.current_frame.is_branch_point = True
        parent_id = self.current_frame.id
        
        branch_ids = []
        for i in range(n):
            new_frame = ContextFrame(
                parent_id=parent_id,
                branch_objective=objectives[i] if objectives else None,
            )
            # Copy state from parent
            new_frame.state = AgentState.from_dict(self.current_frame.state.to_dict())
            
            self._frames[new_frame.id] = new_frame
            branch_ids.append(new_frame.id)
        
        return branch_ids
    
    def switch_to_branch(self, frame_id: str) -> None:
        """
        Switch the active context to a specific branch.
        
        Args:
            frame_id: ID of the branch frame to switch to
            
        Raises:
            KeyError: If frame not found
        """
        if frame_id not in self._frames:
            raise KeyError(f"Frame not found: {frame_id}")
        self._current_frame_id = frame_id
    
    def get_branch_ids(self) -> list[str]:
        """
        Get frame IDs of all branches from the current branch point.
        
        Returns:
            List of frame IDs for sibling branches
        """
        parent_id = self.current_frame.parent_id
        if parent_id is None:
            return [self.current_frame.id]
        
        return [
            frame.id
            for frame in self._frames.values()
            if frame.parent_id == parent_id
        ]
    
    def merge_branches(
        self,
        branch_ids: list[str],
        summaries: list[str],
    ) -> None:
        """
        Merge branch results back into the parent context.
        Creates a new frame with summaries injected as messages.
        
        Args:
            branch_ids: IDs of the branches to merge
            summaries: Summary of each branch's results
        """
        if len(branch_ids) != len(summaries):
            raise ValueError("Number of branch IDs must match number of summaries")
        
        # Find common parent
        parents = set()
        for bid in branch_ids:
            if bid in self._frames:
                parents.add(self._frames[bid].parent_id)
        
        if len(parents) != 1:
            raise ValueError("All branches must share the same parent")
        
        parent_id = parents.pop()
        if parent_id is None:
            raise ValueError("Cannot merge root branches")
        
        # Create merge frame
        merge_frame = ContextFrame(parent_id=parent_id)
        merge_frame.state = AgentState.from_dict(self._frames[parent_id].state.to_dict())
        
        # Add summaries as messages
        for i, (bid, summary) in enumerate(zip(branch_ids, summaries)):
            branch = self._frames.get(bid)
            objective = branch.branch_objective if branch else f"Branch {i+1}"
            merge_frame.messages.append(Message(
                role=MessageRole.ASSISTANT,
                content=f"**Branch Result ({objective}):**\n{summary}",
            ))
        
        self._frames[merge_frame.id] = merge_frame
        self._current_frame_id = merge_frame.id
    
    # === Context Rendering ===
    
    def _get_frame_path(self) -> list[ContextFrame]:
        """Get the path from root to current frame."""
        path = []
        frame_id = self._current_frame_id
        
        while frame_id is not None:
            frame = self._frames[frame_id]
            path.append(frame)
            frame_id = frame.parent_id
        
        return list(reversed(path))
    
    def render_messages(
        self,
        include_system: bool = True,
        max_tokens: int | None = None,
        max_output_chars: int = 10000,
    ) -> list[dict[str, str]]:
        """
        Render the context as a list of messages for the LLM.
        
        Walks the frame tree from root to current, assembling messages.
        Uses summaries instead of raw outputs where available.
        Truncates large outputs to prevent context overflow.
        
        Args:
            include_system: Whether to include system messages
            max_tokens: Optional token limit (triggers truncation strategy)
            max_output_chars: Max chars per tool output (default 10000)
            
        Returns:
            List of {"role": str, "content": str} dicts
        """
        messages = []
        
        for frame in self._get_frame_path():
            for msg in frame.messages:
                if not include_system and msg.role == MessageRole.SYSTEM:
                    continue
                messages.append({
                    "role": msg.role.value if msg.role != MessageRole.TOOL_RESULT else "user",
                    "content": msg.content,
                })
            
            # Add tool call results as messages
            for tc in frame.tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": f"[Tool: {tc.tool_name}]\nInput: {tc.input}",
                })
                messages.append({
                    "role": "user",
                    "content": f"[Tool Result: {tc.tool_name}]\n{tc.get_truncated_output(max_output_chars)}",
                })
        
        # Apply token limit if specified
        if max_tokens is not None:
            messages = self._truncate_to_token_limit(messages, max_tokens)
        
        return messages
    
    def _truncate_to_token_limit(
        self,
        messages: list[dict[str, str]],
        max_tokens: int,
    ) -> list[dict[str, str]]:
        """
        Truncate messages to fit within token limit.
        Keeps system message and most recent messages.
        """
        # Rough estimate: 4 chars per token
        total_tokens = sum(len(m["content"]) // 4 for m in messages)
        
        if total_tokens <= max_tokens:
            return messages
        
        # Keep first message if system, then take from end
        result = []
        if messages and messages[0]["role"] == "system":
            result.append(messages[0])
            messages = messages[1:]
        
        # Add messages from the end until we hit limit
        remaining_tokens = max_tokens - sum(len(m["content"]) // 4 for m in result)
        for msg in reversed(messages):
            msg_tokens = len(msg["content"]) // 4
            if msg_tokens <= remaining_tokens:
                result.insert(len(result) - len(result) + 1 if result else 0, msg)
                remaining_tokens -= msg_tokens
            else:
                break
        
        return result
    
    def estimate_tokens(self) -> int:
        """
        Estimate the current context size in tokens.
        
        Returns:
            Approximate token count
        """
        messages = self.render_messages()
        return sum(len(m["content"]) // 4 for m in messages)
    
    # === Persistence ===
    
    def save(self) -> str:
        """
        Save the entire context tree to disk.
        
        Returns:
            The path to the saved file
        """
        return save_context_tree(
            session_id=self._session_id,
            frames=self._frames,
            current_frame_id=self._current_frame_id,
            persistence_dir=self._persistence_dir,
        )
    
    @classmethod
    def load(cls, path: str) -> "ContextStore":
        """
        Load a context tree from disk.
        
        Args:
            path: Path to the saved context file
            
        Returns:
            ContextStore instance with loaded data
        """
        frames, current_frame_id, tree_data = load_context_tree(path)
        
        # Create store and populate
        store = cls.__new__(cls)
        store._persistence_dir = str(path).rsplit("/", 1)[0]
        store._session_id = tree_data.session_id
        store._frames = frames
        store._current_frame_id = current_frame_id
        
        return store
