#!/usr/bin/env python3
"""
Tempo Sec - Recon Script

Runs the reconnaissance phase and produces a structured target_manifest.json.
This script is designed for standalone recon that produces a manifest file
which can then be consumed by the test_cycle.py script.

Usage:
    python -m tempo.scripts.recon --config config.toml --target example.com
    python -m tempo.scripts.recon --target example.com --output ./manifests/example.json
"""

import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Tempo Sec Recon - Produce a structured target manifest"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default="config.toml",
        help="Path to configuration file (default: config.toml)",
    )
    
    parser.add_argument(
        "--target",
        type=str,
        required=True,
        help="Target domain or URL to perform reconnaissance on",
    )
    
    parser.add_argument(
        "--output",
        type=str,
        help="Output path for manifest JSON (default: ./manifests/<target>_manifest.json)",
    )
    
    parser.add_argument(
        "--local",
        action="store_true",
        help="Run in local mode (no docker sandbox)",
    )
    
    parser.add_argument(
        "--max-steps",
        type=int,
        default=50,
        help="Maximum steps for recon (default: 50)",
    )
    
    parser.add_argument(
        "--no-viz",
        action="store_true",
        help="Disable visualization server",
    )
    
    return parser.parse_args()


async def main() -> None:
    """Main entry point for recon script."""
    args = parse_args()
    
    # Load environment
    load_dotenv()
    
    # Import after dotenv to pick up API keys
    from tempo import AgentConfig, Agent, ContextStore, LiteLLMClient, WorkflowManager
    from tempo.infra.container import ContainerConfig, ContainerManager
    from tempo.tools.registry import ToolRegistry
    from tempo.tools.shell import ShellTool
    from tempo.tools.filesystem import FileReadTool, FileWriteTool
    from tempo.tools.browser_tools import (
        BrowserSession,
        BrowserNavigateTool,
        BrowserSnapshotTool,
        BrowserClickTool,
        BrowserTypeTool,
        BrowserFillFormTool,
    )
    from tempo.tools.meta import SummarizeOutputTool
    from tempo.tools.manifest_tools import CompleteReconTool
    from tempo.tools.view_output import ViewToolOutputTool
    from tempo.prompts.phases import Phase
    from tempo.context.frame import MessageRole
    
    try:
        from tempo.visualization import VisualizationCollector, VisualizationServer
    except ImportError:
        VisualizationServer = None
        VisualizationCollector = None
    
    # Load config
    try:
        config = AgentConfig.from_toml(args.config)
    except FileNotFoundError:
        print(f"Config file not found: {args.config}")
        if args.config == "config.toml":
            print("Using default configuration.")
            config = AgentConfig()
        else:
            sys.exit(1)
    
    # Validate API keys
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY")):
        print("Error: No API key found in environment variables.")
        sys.exit(1)
    
    # Determine output path
    target_domain = args.target.replace("https://", "").replace("http://", "").split("/")[0]
    if args.output:
        output_path = args.output
    else:
        manifest_dir = getattr(config, "manifest_output_dir", "./manifests")
        output_path = str(Path(manifest_dir) / f"{target_domain.replace('.', '_')}_manifest.json")
    
    print(f"🎯 Target: {args.target}")
    print(f"📄 Output: {output_path}")
    
    # Setup Context
    session_id = str(uuid.uuid4())
    context = ContextStore(
        persistence_dir=config.persistence_dir,
        session_id=session_id,
    )
    
    # Setup LLM
    llm = LiteLLMClient(model=config.model)
    
    # Setup Visualization
    viz_server = None
    viz_collector = None
    
    if not args.no_viz and config.enable_visualization and VisualizationServer:
        print(f"Starting visualization server on {config.visualization_host}:{config.visualization_port}")
        viz_server = VisualizationServer(
            host=config.visualization_host,
            port=config.visualization_port,
            auto_open=config.auto_open_browser,
        )
        await viz_server.start()
        viz_collector = VisualizationCollector(viz_server)
    
    # Create tools registry for recon
    def create_recon_tools(container=None) -> ToolRegistry:
        """Create recon-specific tool registry."""
        tools = ToolRegistry()
        
        # Core tools
        if container:
            tools.register(ShellTool(container_manager=container))
            tools.register(FileReadTool(container_manager=container))
            tools.register(FileWriteTool(container_manager=container))
            
            # Playwright-style browser tools
            browser_session = BrowserSession(container_manager=container)
        else:
            tools.register(ShellTool())
            tools.register(FileReadTool())
            tools.register(FileWriteTool())
            
            # Playwright-style browser tools (local)
            browser_session = BrowserSession()
        
        # Register browser tools
        tools.register(BrowserNavigateTool(browser_session))
        tools.register(BrowserSnapshotTool(browser_session))
        tools.register(BrowserClickTool(browser_session))
        tools.register(BrowserTypeTool(browser_session))
        tools.register(BrowserFillFormTool(browser_session))
        
        # Meta tools
        tools.register(SummarizeOutputTool(context_store=context))
        tools.register(ViewToolOutputTool(context_store=context))
        
        # Recon completion tool
        tools.register(CompleteReconTool(
            output_path=output_path,
            target_domain=target_domain,
            agent_model=config.model,
            session_id=session_id,
            context_store=context,
        ))
        
        return tools
    
    # Runner function
    async def run_recon_agent(tools: ToolRegistry, workflow: WorkflowManager) -> None:
        """Run the recon agent with custom recon-only prompt."""
        from tempo.prompts.builder import PromptBuilder
        from tempo.context.frame import MessageRole
        
        prompts = PromptBuilder()
        
        # Build recon-specific system prompt (no phase transitions)
        recon_objective = f"Perform comprehensive reconnaissance on {args.target}"
        system_prompt = prompts.build_recon_prompt(
            objective=recon_objective,
            tool_schemas=tools.get_schemas(),
            scope_description=config.scope or "No specific scope defined.",
        )
        
        # Inject system prompt into context before agent starts
        context.add_message(MessageRole.SYSTEM, system_prompt)
        
        # Add user objective
        user_objective = f"""Target: {args.target}

Tasks:
1. Crawl the website to discover endpoints and pages
2. Fingerprint technologies (web server, frameworks, libraries)
3. Identify forms, APIs, and input points
4. Note authentication mechanisms
5. Look for misconfigurations or exposed resources

When you have gathered sufficient information, call `complete_recon` to save the manifest."""
        
        context.add_message(MessageRole.USER, user_objective)
        
        agent = Agent(
            config=config,
            llm=llm,
            tools=tools,
            context=context,
            prompts=prompts,
            workflow=workflow,
            visualization_collector=viz_collector,
        )
        
        # Run with a dummy objective since we already injected prompts
        # Set start_step > 0 to skip Agent's default prompt injection
        result = await agent.run(
            objective="",  # Empty - we already injected
            initial_phase=Phase.RECON,
            max_steps=args.max_steps,
            start_step=1,  # Skip initial prompt building
        )
        
        print(f"\n{'='*50}")
        if result.success:
            print("✅ Recon completed successfully")
        else:
            print(f"❌ Recon failed: {result.error}")
        print(f"Steps taken: {result.steps_taken}")
        
        # Check if manifest was created
        if Path(output_path).exists():
            print(f"📄 Manifest saved to: {output_path}")
        else:
            print(f"⚠️  Warning: Manifest file not found at {output_path}")
            print("   The agent may not have called complete_recon.")
    
    # Execute with appropriate container setup
    use_container = not args.local and os.getenv("TEMPO_LOCAL_MODE", "").lower() != "true"
    
    try:
        if use_container:
            print("🐳 Initializing container sandbox...")
            container_config = ContainerConfig(
                image=config.container_image,
                timeout=config.container_timeout,
            )
            container = ContainerManager(container_config)
            async with container:
                workflow = WorkflowManager(config, initial_phase=Phase.RECON)
                # Prevent transitions out of RECON (except via complete_recon)
                tools = create_recon_tools(container)
                await run_recon_agent(tools, workflow)
        else:
            print("⚠️  Running in LOCAL mode (no sandbox)...")
            workflow = WorkflowManager(config, initial_phase=Phase.RECON)
            tools = create_recon_tools()
            await run_recon_agent(tools, workflow)
        
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


def main_sync() -> None:
    """Synchronous entry point for CLI."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nRecon cancelled by user.")
        sys.exit(0)


if __name__ == "__main__":
    main_sync()
