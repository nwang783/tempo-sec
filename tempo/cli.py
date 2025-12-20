#!/usr/bin/env python3
"""
Tempo Sec CLI

Command-line interface for running the Tempo Sec agent.
Supports starting new runs, resuming from contexts, and traversing history.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import NoReturn

from dotenv import load_dotenv

from tempo import (
    Agent,
    AgentConfig,
    ContextStore,
    LiteLLMClient,
    ContainerManager,
    WorkflowManager,
    ToolCall,
)
from tempo.infra.container import ContainerConfig
from tempo.tools.tool_factory import create_sandboxed_tools, create_local_tools
try:
    from tempo.visualization import VisualizationCollector, VisualizationServer, UserPromptManager
except ImportError:
    VisualizationServer = None
    VisualizationCollector = None
    UserPromptManager = None


def log_tool_call(tool_call: ToolCall) -> None:
    """Log each tool call as it happens."""
    output_preview = tool_call.raw_output[:300] if tool_call.raw_output else "(no output)"
    if len(tool_call.raw_output or "") > 300:
        output_preview += "..."
    
    # Use different formatting for success/error
    status = "✓" if tool_call.success else "✗"
    print(f"\n  [{status} Tool: {tool_call.tool_name}]")
    print(f"    Input: {tool_call.input}")
    print(f"    Output: {output_preview}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tempo Sec - Context-Aware Cybersecurity Agent")
    
    parser.add_argument(
        "--config", 
        type=str, 
        default="config.toml",
        help="Path to configuration file (default: config.toml)"
    )
    
    parser.add_argument(
        "--context", 
        type=str,
        help="Path to existing context file to resume from"
    )
    
    parser.add_argument(
        "--restart-step", 
        type=int,
        help="Restart execution from a specific step number (requires --context)"
    )
    
    parser.add_argument(
        "--restart-phase", 
        type=str,
        help="Restart execution from the beginning of a specific phase (requires --context)"
    )
    
    parser.add_argument(
        "--prompt", 
        type=str,
        help="Initial objective/prompt (overrides config/interactive input)"
    )
    
    parser.add_argument(
        "--local", 
        action="store_true",
        help="Run in local mode (no docker sandbox)"
    )
    
    return parser.parse_args()


def restore_context(
    context_path: str, 
    restart_step: int | None = None, 
    restart_phase: str | None = None
) -> tuple[ContextStore, int]:
    """
    Load and optionally revert context.
    
    Returns:
        Tuple of (ContextStore, step_count)
    """
    print(f"Loading context from {context_path}...")
    try:
        context = ContextStore.load(context_path)
    except Exception as e:
        print(f"Error loading context: {e}")
        sys.exit(1)
        
    checkpoints = context.list_checkpoints()
    target_frame_id = None
    current_step = 0
    
    if restart_step is not None:
        print(f"Looking for checkpoint at step {restart_step}...")
        # Checkpoints are labeled "Step {n}: {phase}"
        for fid, label, _ in checkpoints:
            try:
                if label.startswith("Step "):
                    step_num = int(label.split(":")[0].replace("Step ", ""))
                    if step_num == restart_step:
                        target_frame_id = fid
                        current_step = step_num
                        print(f"Found checkpoint: {label}")
                        break
            except ValueError:
                continue
        
        if not target_frame_id:
            print(f"Error: No checkpoint found for step {restart_step}")
            print("Available checkpoints:")
            for _, label, _ in checkpoints[-5:]:
                print(f"  - {label}")
            sys.exit(1)
            
    elif restart_phase is not None:
        print(f"Looking for start of phase '{restart_phase}'...")
        # Find the LAST checkpoint that was in the PREVIOUS phase 
        # OR the FIRST checkpoint in this phase?
        # Let's find the most recent checkpoint where phase == restart_phase
        # Actually, user probably wants to restart the phase, so jump to the state BEFORE the phase started?
        # Or just resume from the latest point in that phase?
        # Let's assume restart FROM THE BEGINNING of the phase.
        # But phases are transitions.
        # Let's find the first checkpoint where the label contains the phase name.
        
        target_frame_id = None
        for fid, label, _ in checkpoints:
            if restart_phase.lower() in label.lower():
                target_frame_id = fid
                # Parse step count
                try:
                    current_step = int(label.split(":")[0].replace("Step ", ""))
                except:
                    pass
                print(f"Found checkpoint: {label}")
                break
        
        if not target_frame_id:
            print(f"Error: No checkpoint found for phase '{restart_phase}'")
            sys.exit(1)
            
    if target_frame_id:
        print(f"Reverting to checkpoint {target_frame_id}...")
        context.revert(target_frame_id)
    else:
        # Just resuming from end
        pass
        
            
    return context, current_step


async def replay_history(context: ContextStore, viz_collector: "VisualizationCollector") -> None:
    """
    Replay events from context history to the visualization collector.
    """
    print("Replaying history to visualization...")
    
    # Manually traverse history from root
    path = []
    frame_id = context._current_frame_id
    frames_map = context._frames
    
    while frame_id is not None:
        if frame_id in frames_map:
            frame = frames_map[frame_id]
            path.append(frame)
            frame_id = frame.parent_id
        else:
            break
            
    # Reverse to get chronological order
    path.reverse()
    
    last_phase = "recon"
    current_step_num = 0
    
    # Emit start event
    viz_collector.on_agent_start("Resumed Session", model_name="Resumed")

    for frame in path:
        # Try to infer step number from label "Step N: ..."
        if frame.label and frame.label.startswith("Step "):
            try:
                parts = frame.label.split(":")
                step_str = parts[0].replace("Step ", "")
                current_step_num = int(step_str)
            except ValueError:
                pass
                
        # Emit step event
        # We perform a sort of "virtual step" for each frame to ensure UI has a container
        # Use frame's state phase
        current_phase = frame.state.current_phase or last_phase
        
        step_data = {
            "step_number": current_step_num,
            "phase": current_phase if current_phase != last_phase else None,
            "error": None,
            "should_continue": True,
            "llm_content": None,
            "frame_id": frame.id
        }
        viz_collector.emit("step", step_data)
        
        last_phase = current_phase
        
        # Emit tool calls
        for tool_call in frame.tool_calls:
            viz_collector.on_tool_call(tool_call, frame.id)
            
    print(f"Replayed {len(path)} frames.")



async def main():
    args = parse_args()
    
    # Load env
    load_dotenv()
    
    # Load config
    try:
        config = AgentConfig.from_toml(args.config)
    except FileNotFoundError:
        print(f"Config file not found: {args.config}")
        # If no config provided and default missing, try to proceed with defaults but warn
        if args.config == "config.toml":
            print("Using default configuration.")
            config = AgentConfig()
        else:
            sys.exit(1)
    
    # Override local mode if flag set
    use_container = not args.local and os.getenv("TEMPO_LOCAL_MODE", "").lower() != "true"
    
    # Setup Context
    step_count = 0
    if args.context:
        context, step_count = restore_context(
            args.context, 
            args.restart_step, 
            args.restart_phase
        )
    else:
        context = ContextStore(persistence_dir=config.persistence_dir)
        if args.restart_step or args.restart_phase:
            print("Error: --restart arguments require --context")
            sys.exit(1)
    
    # Setup Infra
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY")):
        print("Error: No API key found in environment variables.")
        sys.exit(1)
        
    llm = LiteLLMClient(model=config.model)
    
    # Setup Visualization
    viz_server = None
    viz_collector = None
    prompt_manager = None
    stop_event = asyncio.Event()
    
    if config.enable_visualization and VisualizationServer:
        print(f"Starting visualization server on {config.visualization_host}:{config.visualization_port}")
        if UserPromptManager:
            prompt_manager = UserPromptManager()
            
        viz_server = VisualizationServer(
            host=config.visualization_host,
            port=config.visualization_port,
            auto_open=config.auto_open_browser,
            prompt_manager=prompt_manager,
            stop_event=stop_event,
        )
        await viz_server.start()
        viz_collector = VisualizationCollector(viz_server)
        
        # Replay history if context exists
        if args.context and context and context._current_frame_id:
            print("Waiting for visualization client to connect...")
            connected = await viz_server.wait_for_connection(timeout=15.0)
            if connected:
                await replay_history(context, viz_collector)
            else:
                print("No visualization client connected, skipping history replay.")
    
    # Determine Objective
    objective = args.prompt
    if not objective and not args.context:
        # If starting new and no prompt, try to get from config or interactive
        # For this PoC, we'll use a default if nothing provided
        domains = config.allowed_domains
        target = domains[0] if domains else "example.com"
        objective = f"Perform reconnaissance on {target}"
        print(f"No objective provided. Using default: {objective}")
    
    # Execution Wrapper
    async def run_agent_with_tools(tools, workflow):

        agent = Agent(
            config=config,
            llm=llm,
            tools=tools,
            context=context,
            workflow=workflow,
            on_tool_call=log_tool_call,
            visualization_collector=viz_collector,
            prompt_manager=prompt_manager,
            stop_event=stop_event,
        )
        
        # If restarting, manually set the step count
        # Accessing protected member for restart logic
        if step_count > 0:
            agent._step_count = step_count
            print(f"Resuming agent execution from step {step_count}")
        
        # Run
        # If we have an existing context, we might not need to pass objective if it's already in history?
        # But run() expects an objective.
        # If context is loaded, agent.run() normally resets workflow.
        # We need to be careful not to wipe state.
        # Agent.run calls workflow.reset(). 
        # If we are resuming, we should probably modify Agent.run to handle resumption better,
        # or use a new method `resume()`.
        # For now, let's call run() but rely on it not clearing context if we pass it in.
        # Check Agent.run implementation:
        #   self.workflow.reset(initial_phase) -> Resets phase to RECON or whatever passed.
        #   self.context.add_message... -> Adds system prompt again.
        
        # WE NEED TO FIX Agent.run FOR RESUMPTION or use a different entry point.
        # Let's adjust Agent.run in the next step to support resumption/skip initialization.
        
        return await agent.run(
            objective=objective if objective else "Resume execution",
            max_steps=config.max_total_steps,
        )

    # Resource Management
    try:
        if use_container:
            print("Initializing container sandbox...")
            container_config = ContainerConfig(
                image=config.container_image,
                timeout=config.container_timeout,
            )
            container = ContainerManager(container_config)
            async with container:
                workflow = WorkflowManager(config)
                # If resuming, we need to sync workflow state with context state?
                # The workflow manager tracks current_phase.
                # If we loaded context, we should set workflow.current_phase from context.state.current_phase
                if args.context:
                    state = context.get_state()
                    if state.current_phase:
                        from tempo.prompts.phases import Phase
                        try:
                            workflow.current_phase = Phase(state.current_phase)
                            print(f"Restored phase: {workflow.current_phase.value}")
                        except ValueError:
                            pass
                
                tools = create_sandboxed_tools(container, context, workflow)
                result = await run_agent_with_tools(tools, workflow)
        else:
            print("Running in LOCAL mode (unsafe)...")
            workflow = WorkflowManager(config)
            if args.context:
                state = context.get_state()
                if state.current_phase:
                    from tempo.prompts.phases import Phase
                    try:
                        workflow.current_phase = Phase(state.current_phase)
                    except ValueError:
                        pass
                        
            tools = create_local_tools(context, workflow)
            result = await run_agent_with_tools(tools, workflow)
            
        # Report
        print(f"\n{'='*20} Result {'='*20}")
        if result.success:
            print("SUCCESS")
        else:
            print(f"FAILED: {result.error}")
        
        print(f"Steps: {result.steps_taken}")
        if result.findings:
            print("Findings:")
            for f in result.findings:
                print(f" - {f}")

        # Save context
        save_path = context.save()
        print(f"Context saved to: {save_path}")

    finally:
        if viz_server:
            print("Press Enter to stop visualization server...")
            try:
                input()
            except:
                pass
            await viz_server.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
