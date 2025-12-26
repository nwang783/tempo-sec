
import asyncio
import logging
from unittest.mock import MagicMock, AsyncMock, patch
from tempo.context.store import ContextStore
from tempo.context.frame import MessageRole
from tempo.agent.summarizer import PhaseSummary

async def test_semantic_summarization():
    """
    Test that phase blocks are correctly identified and summarized
    when the context threshold is exceeded.
    """
    store = ContextStore()
    
    # 1. Setup Mock LLM Client
    mock_llm = MagicMock()
    # Mock the complete_structured response
    mock_summary = PhaseSummary(
        phase_name="RECON",
        actions=["Ran nmap", "Found ports"],
        key_findings=["Port 80 open"],
        narrative_summary="We found stuff."
    )
    mock_llm.complete_structured = AsyncMock(return_value=mock_summary)
    
    # Patch LiteLLMClient in tempo.infra.llm because that is where it is imported from in summarizer.py
    with patch("tempo.infra.llm.LiteLLMClient") as MockLiteLLM:
        MockLiteLLM.return_value = mock_llm
        
        # 2. Build Context
        # Start
        store.add_message(MessageRole.SYSTEM, "System Prompt")
        store.add_message(MessageRole.USER, "Objective: Hack the planet")
        
        # Phase 1: RECON (Completed)
        from tempo.context.frame import ToolCall
        
        for i in range(10): 
            store.add_message(MessageRole.ASSISTANT, f"Recon action {i}")
            if i == 5:
                # Add a tool call in the middle of RECON
                tc = ToolCall(tool_name="recon_tool", raw_output="Output")
                store.add_tool_call(tc)
            store.add_message(MessageRole.USER, f"Recon result {i}")
            
        # Add bulky text to RECON to ensure it meets the 1000 token threshold for summarization
        # With accurate tokenizer: ~8000 chars = ~1200 tokens (varies by model)
        bulky_text = "A" * 8000
        store.add_message(MessageRole.ASSISTANT, f"Bulky Recon: {bulky_text}")
            
        # Transition Marker (Note: store.py is case-insensitive, but we use standard format here)
        store.add_message(MessageRole.SYSTEM, "[System] Automatically transitioned to HYPOTHESIZE due to step limit.")
        
        # Phase 2: HYPOTHESIZE (Current/Recent)
        for i in range(5):
             store.add_message(MessageRole.ASSISTANT, f"Hypothesis {i}")

        print(f"Total tokens before: {store.estimate_tokens()}")
        
        # 3. Trigger Optimize
        # Threshold 100 (low to force trigger), Protection 10 tokens (keep only very recent)
        did_optimize = await store.optimize(
            llm_client=mock_llm, 
            threshold=100, 
            recent_protection_tokens=10
        )
        
        print(f"Did optimize: {did_optimize}")
        
        if did_optimize:
            print("\nMessages after optimization:")
            msgs = store.render_messages(include_system=True)
            for m in msgs:
                print(f"[{m['role']}] {m['content'][:50]}...")

            # Check that Preamble is preserved
            if msgs[0]["content"] != "System Prompt":
                print(f"FAILURE: System prompt lost. Found: {msgs[0]['content']}")
                raise AssertionError("System prompt lost")
            
            if msgs[1]["content"] != "Objective: Hack the planet":
                 print(f"FAILURE: Objective lost. Found: {msgs[1]['content']}")
                 raise AssertionError("Objective lost")
                 
            # Check Tool Call cleanup
            # We added one tool call in RECON. It should be gone.
            recon_tcs = [tc for tc in store.current_frame.tool_calls if tc.tool_name == "recon_tool"]
            if len(recon_tcs) > 0:
                print(f"FAILURE: Tool calls from summarized phase were not cleaned up. Found: {len(recon_tcs)}")
                raise AssertionError("Tool calls not cleaned up")
            
            # Check for summary marker
            has_summary = any("Phase Summary: RECON" in m["content"] for m in msgs)
            if has_summary:
                print("\nSUCCESS: RECON phase was summarized, Preamble preserved, Tool calls cleaned.")
            else:
                print("\nFAILURE: Summary message not found.")
                raise AssertionError("Summary message missing")
        else:
            print("\nFAILURE: Optimization did not trigger.")
            raise AssertionError("Optimization failed to trigger")

if __name__ == "__main__":
    asyncio.run(test_semantic_summarization())
