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
    
    def find_tool_call(self, tool_call_id: str) -> ToolCall | None:
        """
        Find a tool call by ID in the context history.
        
        Implements the ToolCallFinder protocol from infra.protocols.
        
        Args:
            tool_call_id: ID of the tool call to find
            
        Returns:
            The ToolCall if found, None otherwise
        """
        # Search in current frame and ancestors
        frame_id = self._current_frame_id
        while frame_id is not None:
            frame = self._frames.get(frame_id)
            if frame is None:
                break
            for tc in frame.tool_calls:
                if tc.id == tool_call_id:
                    return tc
            frame_id = frame.parent_id
        return None
    
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
        role: MessageRole = MessageRole.SYSTEM,
    ) -> None:
        """
        Replace a range of messages with a single summary message.
        
        Args:
            start_index: First message index to replace (inclusive)
            end_index: Last message index to replace (exclusive)
            summary: The summary text to insert
            role: Role for the summary message
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
            role=role,
            content=summary,
        )
        
        # Rebuild message list
        self.current_frame.messages = list(before) + [summary_msg] + list(after)
        
        # Remove tool calls that occurred within this message block's timeframe
        # This prevents "dangling" tool calls from being rendered after their context is summarized.
        if messages and start_index < len(messages) and end_index > 0:
            # We have a defined range of messages being removed.
            # We use the timestamps of the first and last message in that block to define the window.
            # safe access
            start_msg = messages[start_index]
            end_msg = messages[end_index - 1] if end_index <= len(messages) else messages[-1]
            
            time_start = start_msg.timestamp
            time_end = end_msg.timestamp
            
            # Filter out tool calls within this range
            self.current_frame.tool_calls = [
                tc for tc in self.current_frame.tool_calls
                if not (time_start <= tc.timestamp <= time_end)
            ]

    
    # === Semantic Summarization ===

    def identify_phase_blocks(self) -> list[dict]:
        """
        Identify blocks of messages corresponding to workflow phases.
        
        Returns:
            List of dicts with:
                - phase: Phase name (e.g., "RECON")
                - start_index: Start message index
                - end_index: End message index
                - content_tokens: Approx token count
        """
        blocks = []
        messages = self.current_frame.messages
        
        current_phase = "RECON" # Default start
        start_index = 0
        
        for i, msg in enumerate(messages):
            # Check for phase transition markers in System messages
            if msg.role == MessageRole.SYSTEM or msg.role == "system":
                content = msg.content
                # Patterns from runner.py and specialized tools
                lower_content = content.lower()
                if "transitioned to" in lower_content or "you are now back in" in lower_content or "you are now in" in lower_content:
                    # Found a transition point. 
                    # The PREVIOUS block ends at i (exclusive).
                    if i > start_index:
                        blocks.append({
                            "phase": current_phase,
                            "start_index": start_index,
                            "end_index": i,
                        })
                    
                    # Extract new phase name
                    # Simple heuristic: look for phase names
                    upper_content = content.upper()
                    new_phase = current_phase # fallback
                    for p in ["RECON", "HYPOTHESIZE", "TEST", "REFLECT"]:
                        if p in upper_content:
                            new_phase = p
                            break
                    
                    current_phase = new_phase
                    start_index = i # Start new block including this transition message
        
        # Add the final block (current phase)
        if start_index < len(messages):
            blocks.append({
                "phase": current_phase,
                "start_index": start_index,
                "end_index": len(messages),
            })
            
        return blocks

    async def optimize(
        self, 
        llm_client, 
        threshold: int = 100000, 
        recent_protection_tokens: int = 20000
    ) -> bool:
        """
        Optimize context by summarizing old phases if over threshold.
        
        Args:
            llm_client: Client to use for summarization
            threshold: Token limit to trigger optimization
            recent_protection_tokens: Number of recent tokens to protect
            
        Returns:
            True if optimization was performed
        """
        # 1. Check total size
        total_tokens = self.estimate_tokens()
        if total_tokens < threshold:
            return False
            
        # 2. Identify phase blocks
        blocks = self.identify_phase_blocks()
        if not blocks:
            return False
            
        # 3. Define protected window (indices)
        # We walk backwards summing tokens until we hit protection limit
        protected_start_index = len(self.current_frame.messages)
        content_tokens = 0
        
        for i in range(len(self.current_frame.messages) - 1, -1, -1):
            msg = self.current_frame.messages[i]
            # Rough estimate
            tokens = len(msg.content) // 4
            content_tokens += tokens
            protected_start_index = i
            if content_tokens >= recent_protection_tokens:
                break
        
        # 4. Find oldest *completed* phase that is fully before protected window
        # We start looking from index 1 (skipping potential initial system setup/objective block)
        target_block = None
        
        # Skip the very first block if it's uniquely small or just setup, 
        # but usually RECON is the first real block.
        # We also DON'T want to summarize the CURRENT phase (last block).
        
        summarizable_blocks = blocks[:-1] # Exclude current phase
        
        # Identify Preamble end to protect it
        # We detect the first ASSISTANT message as the start of "real work"
        preamble_end_index = 0
        for i, msg in enumerate(self.current_frame.messages):
             if msg.role == MessageRole.ASSISTANT:
                 preamble_end_index = i
                 break
        if preamble_end_index == 0 and len(self.current_frame.messages) > 0 and self.current_frame.messages[0].role != MessageRole.ASSISTANT:
             # If we never found an assistant message, but have history, maybe it's all preamble?
             # But for optimization, we assume we have phases.
             # If NO assistant message exists, we probably shouldn't summarize anything yet.
             # But let's safe-guard: if we found blocks, we assume we can summarize.
             # Let's default to preserving first 2 messages if no assistant found (System + User)
             preamble_end_index = 2
             
        for block in summarizable_blocks:
            # Check if block overlaps with protected window
            if block["end_index"] > protected_start_index:
                continue
                
            # Adjust start_index to preserve Preamble
            if block["start_index"] < preamble_end_index:
                block["start_index"] = preamble_end_index
            
            # If adjustment made block valid range empty or negative, skip
            if block["start_index"] >= block["end_index"]:
                continue
                
            # Check if block is long enough to be worth summarizing (> 1000 tokens)
            # Estimate size
            block_content = "".join([
                self.current_frame.messages[j].content 
                for j in range(block["start_index"], block["end_index"])
            ])
            if len(block_content) // 4 < 1000:
                continue
                
            # Found a candidate!
            target_block = block
            break
            
        if not target_block:
            return False
            
        # 5. Summarize
        from tempo.agent.summarizer import PhaseSummarizer
        summarizer = PhaseSummarizer(llm_client)
        
        import logging
        logging.info(f"Summarizing phase {target_block['phase']} (indices {target_block['start_index']}-{target_block['end_index']})")
        
        # Extract messages for summary
        msgs_to_summarize = [
            self.current_frame.messages[j].to_dict() 
            for j in range(target_block["start_index"], target_block["end_index"])
        ]
        
        try:
            summary = await summarizer.summarize_phase(
                target_block["phase"],
                msgs_to_summarize
            )
            
            # Format the replacement
            summary_text = (
                f"## Phase Summary: {target_block['phase']}\n"
                f"**Actions:**\n- " + "\n- ".join(summary.actions) + "\n\n"
                f"**Key Findings:**\n- " + "\n- ".join(summary.key_findings) + "\n\n"
                f"**Narrative:**\n{summary.narrative_summary}"
            )
            
            # 6. Replace
            self.replace_messages_with_summary(
                target_block["start_index"],
                target_block["end_index"],
                summary_text,
                role=MessageRole.SYSTEM 
            )
            return True
            
        except Exception as e:
            logging.error(f"Phase summarization failed: {e}")
            return False

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
    
    # === Test Plan Management (TestPlanManager protocol) ===
    
    def add_test_plan_item(
        self,
        description: str,
        priority: str = "medium",
    ) -> str:
        """
        Add a new item to the test plan.
        
        Args:
            description: What to investigate
            priority: high/medium/low
            
        Returns:
            ID of the created item
        """
        import uuid
        from datetime import datetime
        
        item = {
            "id": str(uuid.uuid4()),
            "description": description,
            "priority": priority,
            "status": "pending",
            "reason": None,
            "created_at": datetime.utcnow().isoformat(),
            "completed_at": None,
        }
        self.current_frame.state.test_plan.append(item)
        return item["id"]
    
    def complete_test_plan_item(
        self,
        item_id: str,
        status: str,
        reason: str,
    ) -> bool:
        """
        Mark a test plan item as completed or skipped.
        
        Args:
            item_id: ID of the item
            status: "completed" or "skipped"
            reason: Explanation of findings or why skipped
            
        Returns:
            True if item was found and updated
        """
        from datetime import datetime
        
        for item in self.current_frame.state.test_plan:
            if item["id"] == item_id:
                item["status"] = status
                item["reason"] = reason
                item["completed_at"] = datetime.utcnow().isoformat()
                return True
        return False
    
    def get_test_plan(self) -> list[dict]:
        """Get the current test plan items."""
        return self.current_frame.state.test_plan
    
    def set_test_plan(self, items: list[dict]) -> None:
        """Replace the entire test plan."""
        self.current_frame.state.test_plan = items
    
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
    
    def _get_preamble_end_index(self, messages: list[dict[str, str]]) -> int:
        """
        Find the index where the 'preamble' (System prompts + User Objective) ends.
        Heuristic: The preamble ends just before the first ASSISTANT message.
        """
        for i, msg in enumerate(messages):
            if msg["role"] == "assistant":
                return i
        
        # If no assistant message, potentially the whole thing is preamble 
        return len(messages)

    def _truncate_to_token_limit(
        self,
        messages: list[dict[str, str]],
        max_tokens: int,
    ) -> list[dict[str, str]]:
        """
        Truncate messages to fit within token limit.
        Prioritizes:
        1. System messages (always kept)
        2. First few messages (User Objective)
        3. Most recent messages (Immediate context)
        4. Drops middle history
        """
        # Rough estimate: 4 chars per token
        total_tokens = sum(len(m["content"]) // 4 for m in messages)
        
        if total_tokens <= max_tokens:
            return messages
        
        # 1. Identify Preamble (System messages + User Objective)
        # We protect everything up to the first Assistant message
        preamble_end = self._get_preamble_end_index(messages)
        kept_start = messages[:preamble_end]
        remaining_messages = messages[preamble_end:]
        
        # Calculate remaining budget
        current_tokens = sum(len(m["content"]) // 4 for m in kept_start)
        remaining_budget = max(0, max_tokens - current_tokens)
        
        # 2. Fill the rest with MOST RECENT messages from remaining_messages
        kept_end = []
        for msg in reversed(remaining_messages):
            msg_tokens = len(msg["content"]) // 4
            if msg_tokens <= remaining_budget:
                kept_end.insert(0, msg)
                remaining_budget -= msg_tokens
            else:
                # We can't fit this message, stop
                break
                
        # If we had to drop messages, insert a marker
        if len(kept_start) + len(kept_end) < len(kept_start) + len(messages):
             kept_start.append({
                 "role": "system",
                 "content": f"[... Context Truncated. Dropped {len(messages) - len(kept_end)} messages ...]"
             })
             
        return kept_start + kept_end
    
    def estimate_tokens(self) -> int:
        """
        Estimate the current context size in tokens.
        
        Returns:
            Approximate token count
        """
        messages = self.render_messages()
        return sum(len(m["content"]) // 4 for m in messages)
    
    def export_for_visualization(self) -> dict:
        """
        Export the context tree data for visualization purposes.
        
        Returns:
            Dictionary with session_id, current_frame_id, and serialized frames
        """
        frames = {}
        
        # Walk the frame path from current to root
        frame_id = self._current_frame_id
        while frame_id and frame_id in self._frames:
            frame = self._frames[frame_id]
            frames[frame_id] = frame.to_dict()
            frame_id = frame.parent_id
        
        return {
            "session_id": self._session_id,
            "current_frame_id": self._current_frame_id,
            "frames": frames,
        }
    
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
