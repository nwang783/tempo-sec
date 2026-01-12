"""
Unified Agent Runner.

Single entry point for running any modular agent definition.
Usage:
    python -m tempo.scripts.run --agent <name> [options]
"""

import argparse
import asyncio
import os
import sys
import uuid
from typing import NoReturn
import logging

from dotenv import load_dotenv

# Set logging to only show ERROR messages to suppress third-party logs
logging.basicConfig(level=logging.ERROR)

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Tempo Sec - Unified Agent Runner"
    )
    
    # Core arguments
    parser.add_argument(
        "--agent",
        type=str,
        required=True,
        help="Name of the agent to run (e.g., 'recon', 'test_cycle')",
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default="config.toml",
        help="Path to configuration file",
    )
    
    parser.add_argument(
        "--model",
        type=str,
        help="Override LLM model (defaults to agent's preference)",
    )
    
    # Runtime options
    parser.add_argument(
        "--max-steps",
        type=int,
        help="Maximum total steps",
    )
    
    parser.add_argument(
        "--local",
        action="store_true",
        help="Run in local mode (no docker sandbox)",
    )
    
    parser.add_argument(
        "--no-viz",
        action="store_true",
        help="Disable visualization server",
    )
    
    # Agent-specific arguments (passed to agent constructor/methods)
    parser.add_argument(
        "--scope-file",
        type=str,
        help="Path to scope file containing target(s) and constraints (required for orchestrator)",
    )
    
    parser.add_argument(
        "--manifest",
        type=str,
        help="Path to manifest file (for test_cycle)",
    )
    
    parser.add_argument(
        "--context",
        type=str,
        help="Path to context file to resume from",
    )
    
    parser.add_argument(
        "--output",
        type=str,
        help="Output path (for recon manifest, etc.)",
    )

    parser.add_argument(
        "--findings",
        type=str,
        help="Path to findings document (for orchestrator)",
    )

    parser.add_argument(
        "--max-iterations",
        type=int,
        help="Maximum iterations for orchestrator",
    )

    # --scope-file is defined above with agent-specific arguments

    # Parse known args first to allow agents to add their own?
    # For now, we take all args and pass relevant ones
    return parser.parse_args()


def load_config(path: str) -> "AgentConfig":
    """Load configuration with fallback."""
    from tempo import AgentConfig
    
    try:
        return AgentConfig.from_toml(path)
    except FileNotFoundError:
        if path == "config.toml":
            print("Notice: using default configuration.")
            return AgentConfig()
        print(f"Error: Config file not found: {path}")
        sys.exit(1)


async def main() -> None:
    """Main execution flow."""
    args = parse_args()
    
    # Load environment
    load_dotenv()
    
    # Imports
    from tempo import Agent, ContextStore, LiteLLMClient
    from tempo.infra.container import ContainerConfig, ContainerManager
    from tempo.prompts.builder import PromptBuilder
    from tempo.context.frame import MessageRole
    
    try:
        from tempo.agents import get_agent
    except ImportError:
        # Fallback for when installed as package vs source
        sys.path.append(os.getcwd())
        from tempo.agents import get_agent

    try:
        from tempo.visualization import VisualizationCollector, VisualizationServer, UserPromptManager
    except ImportError:
        VisualizationServer = None
        VisualizationCollector = None
        UserPromptManager = None

    # Load Config
    config = load_config(args.config)
    
    # Load Agent Definition
    try:
        # Build kwargs for agent constructor
        agent_kwargs = {
            "manifest_path": args.manifest,
            "output_path": args.output,
            "session_id": str(uuid.uuid4()),
        }

        # Add orchestrator-specific arguments
        if args.findings:
            agent_kwargs["findings_path"] = args.findings
        if args.max_iterations:
            agent_kwargs["max_iterations"] = args.max_iterations
        
        # Load scope file content if provided
        if args.scope_file:
            from pathlib import Path
            scope_path = Path(args.scope_file)
            if not scope_path.exists():
                print(f"Error: Scope file not found: {args.scope_file}")
                sys.exit(1)
            agent_kwargs["scope_content"] = scope_path.read_text().strip()

        agent_def = get_agent(args.agent, **agent_kwargs)
    except KeyError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error initializing agent '{args.agent}': {e}")
        # Hint at missing args
        if args.agent == "test_cycle" and not args.manifest:
            print("Hint: 'test_cycle' agent requires --manifest")
        if args.agent == "orchestrator" and not args.scope_file:
            print("Hint: 'orchestrator' agent requires --scope-file")
        sys.exit(1)

    # Resolve Model
    # Priority: CLI override > Agent definition
    model = args.model or agent_def.model
    config.model = model  # Update config with selected model
    
    # Validate API keys (provider specific checks could be added here)
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY")):
        print("Warning: No standard API keys found (ANTHROPIC/OPENAI/GEMINI). Ensure your provider is configured.")

    print(f"🚀 Starting {agent_def.name} agent")
    print(f"🤖 Model: {model}")
    print(f"📝 Description: {agent_def.description}")
    
    # Setup Context
    step_count = 0
    if args.context:
        print(f"📂 Resuming from context: {args.context}")
        context = ContextStore.load(args.context)
        # Estimate step count from tool calls
        if context.current_frame:
            step_count = len(context.current_frame.tool_calls)
    else:
        context = ContextStore(
            persistence_dir=config.persistence_dir,
            session_id=getattr(agent_def, "_session_id", str(uuid.uuid4())) # Best effort session ID
        )

    # Setup LLM
    llm = LiteLLMClient(model=model)
    
    # Setup Visualization
    viz_server = None
    viz_collector = None
    prompt_manager = None
    stop_event = asyncio.Event()
    
    if not args.no_viz and config.enable_visualization and VisualizationServer:
        print(f"📊 Visualization running on {config.visualization_host}:{config.visualization_port}")
        if UserPromptManager:
            prompt_manager = UserPromptManager()
        
        viz_server = VisualizationServer(
            host=config.visualization_host,
            port=config.visualization_port,
            auto_open=config.auto_open_browser,
            prompt_manager=prompt_manager,
            stop_event=stop_event,
            persistence_dir=config.persistence_dir,
        )
        viz_server.set_context_store(context)
        await viz_server.start()
        viz_collector = VisualizationCollector(viz_server)

    # Initialize PromptBuilder
    prompts = PromptBuilder()
    
    # Execution Wrapper
    async def run_agent(tools):

        # Build Objective
        try:
            # Pass args that might be relevant
            objective = agent_def.build_objective(
                manifest_path=args.manifest
            )

        except Exception as e:
            print(f"Error building objective: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
            
        # Build System Prompt if starting fresh
        if step_count == 0:

            system_prompt = agent_def.build_system_prompt(
                prompts, 
                tools.get_schemas(), 
                config.scope or "No specific scope defined."
            )

            # Inject system prompt
            context.add_message(MessageRole.SYSTEM, system_prompt)
            
            # Inject objective (User message)
            context.add_message(MessageRole.USER, objective)
            
            # Skip agent's internal prompt injection since we did it manually
            # This gives agent definitions full control
            run_start_step = 1
        else:
            run_start_step = step_count
            # Objective might be needed for restoring state or logging
            objective = "Resumed session" # Placeholder if resuming
        

        # Create Agent
        agent = Agent(
            config=config,
            llm=llm,
            tools=tools,
            context=context,
            prompts=prompts,
            visualization_collector=viz_collector,
            prompt_manager=prompt_manager,
            stop_event=stop_event,
        )
        

        # Run Agent
        result = await agent.run(
            objective=objective,
            max_steps=args.max_steps or config.max_total_steps,
            start_step=run_start_step,
        )
        

        return result

    # Setup Container & Run
    use_container = not args.local and os.getenv("TEMPO_LOCAL_MODE", "").lower() != "true"
    
    try:
        if use_container:
            print("🐳 Initializing container sandbox...")
            container_config = ContainerConfig(
                image=config.container_image,
                timeout=config.container_timeout,
            )
            container = ContainerManager(container_config)
            
            # Early Docker connectivity check
            try:
                container.client.ping()

            except Exception as docker_err:
                print(f"\n❌ Docker connection failed: {docker_err}")
                print("\nPossible fixes:")
                print("  1. Start Docker Desktop")
                print("  2. Run with --local flag to skip containerization")
                print("  3. Set TEMPO_LOCAL_MODE=true in environment")
                sys.exit(1)
            
            async with container:
                # Create tools with container
                tools = agent_def.create_tools(context, container, visualization=viz_collector, config=config)
                result = await run_agent(tools)
        else:
            print("⚠️  Running in LOCAL mode (no sandbox)...")
            # Create local tools
            tools = agent_def.create_tools(context, None, visualization=viz_collector, config=config)
            result = await run_agent(tools)
            
        # Final Report
        print(f"\n{'='*50}")
        if result.success:
            print("✅ Agent completed successfully")
        else:
            print(f"❌ Agent failed: {result.error}")
        print(f"Steps taken: {result.steps_taken}")
        
        if result.findings:
            print("\n📋 Findings:")
            for finding in result.findings:
                desc = finding.get('description', str(finding))
                print(f"  - {desc}")
        
        # Save Context
        save_path = context.save()
        print(f"\n💾 Context saved to: {save_path}")

    except Exception as e:

        import traceback
        traceback.print_exc()
        raise
    finally:
        if viz_server:
            print("\nPress Enter to stop visualization server...")
            try:
                input()
            except:
                pass
            await viz_server.stop()


def main_sync():
    """Synchronous entry point."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExecution cancelled by user.")
        sys.exit(0)


if __name__ == "__main__":
    main_sync()
