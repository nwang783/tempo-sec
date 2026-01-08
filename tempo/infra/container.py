"""
Container manager for sandboxed tool execution.

Manages Docker container lifecycle for secure, isolated execution
of security testing tools.
"""

import asyncio
import io
import tarfile
from dataclasses import dataclass
from typing import Any

import docker
from docker.models.containers import Container


@dataclass
class ContainerConfig:
    """Configuration for the sandbox container."""
    image: str = "tempo-sec-base:latest"
    memory_limit: str = "2g"
    cpu_count: int = 2
    network_mode: str = "bridge"
    timeout: int = 300


class ContainerManager:
    """
    Manages Docker container lifecycle for sandboxed tool execution.
    
    Provides async methods for starting/stopping containers, executing
    commands, and transferring files.
    """
    
    def __init__(self, config: ContainerConfig | None = None):
        """
        Initialize the container manager.
        
        Args:
            config: Optional container configuration. Uses defaults if not provided.
        """
        self.config = config or ContainerConfig()
        self.client = docker.from_env()
        self._container: Container | None = None
    
    async def start(self) -> None:
        """
        Start the sandbox container.
        
        Creates and starts a new container with the configured settings.
        The container runs in detached mode with a long-running command.
        """
        if self._container is not None and self.is_running:
            return  # Already running
        
        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        self._container = await loop.run_in_executor(
            None,
            lambda: self.client.containers.run(
                self.config.image,
                command="tail -f /dev/null",  # Keep container running
                detach=True,
                mem_limit=self.config.memory_limit,
                cpu_count=self.config.cpu_count,
                network_mode=self.config.network_mode,
                working_dir="/workspace",
                remove=True,  # Auto-remove when stopped
            )
        )
    
    async def stop(self) -> None:
        """
        Stop and remove the container.
        
        Gracefully stops the container, waiting up to 10 seconds
        before force-killing.
        """
        if self._container is None:
            return
        
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                lambda: self._container.stop(timeout=10)
            )
        except docker.errors.NotFound:
            pass  # Container already removed
        finally:
            self._container = None
    
    async def exec(
        self,
        command: str,
        working_dir: str = "/workspace",
        timeout: int | None = None,
        environment: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        """
        Execute a command in the container.
        
        Args:
            command: Shell command to execute
            working_dir: Working directory for the command
            timeout: Command timeout in seconds (uses config default if None)
            environment: Optional environment variables
            
        Returns:
            Tuple of (exit_code, stdout, stderr)
            
        Raises:
            RuntimeError: If container is not running
        """
        if self._container is None or not self.is_running:
            raise RuntimeError("Container is not running")
        
        timeout = timeout or self.config.timeout
        
        loop = asyncio.get_event_loop()
        
        # Create exec instance
        exec_result = await loop.run_in_executor(
            None,
            lambda: self._container.exec_run(
                cmd=["bash", "-c", command],
                workdir=working_dir,
                environment=environment,
                demux=True,  # Separate stdout/stderr
            )
        )
        
        exit_code = exec_result.exit_code
        stdout, stderr = exec_result.output
        
        return (
            exit_code,
            stdout.decode("utf-8") if stdout else "",
            stderr.decode("utf-8") if stderr else "",
        )
    
    async def copy_to(self, local_path: str, container_path: str) -> None:
        """
        Copy a file from local filesystem into the container.
        
        Args:
            local_path: Path to local file
            container_path: Destination path in container
        """
        if self._container is None:
            raise RuntimeError("Container is not running")
        
        loop = asyncio.get_event_loop()
        
        # Create a tar archive in memory
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            tar.add(local_path, arcname=container_path.split("/")[-1])
        tar_stream.seek(0)
        
        # Get parent directory
        parent_dir = "/".join(container_path.split("/")[:-1]) or "/"
        
        await loop.run_in_executor(
            None,
            lambda: self._container.put_archive(parent_dir, tar_stream)
        )
    
    async def copy_from(self, container_path: str, local_path: str) -> None:
        """
        Copy a file from the container to local filesystem.
        
        Args:
            container_path: Path in container
            local_path: Destination path on local filesystem
        """
        if self._container is None:
            raise RuntimeError("Container is not running")
        
        loop = asyncio.get_event_loop()
        
        # Get archive from container
        bits, _ = await loop.run_in_executor(
            None,
            lambda: self._container.get_archive(container_path)
        )
        
        # Extract from tar
        tar_stream = io.BytesIO()
        for chunk in bits:
            tar_stream.write(chunk)
        tar_stream.seek(0)
        
        with tarfile.open(fileobj=tar_stream, mode="r") as tar:
            # Extract the first file
            for member in tar.getmembers():
                if member.isfile():
                    extracted = tar.extractfile(member)
                    if extracted:
                        with open(local_path, "wb") as f:
                            f.write(extracted.read())
                        break
    
    async def file_exists(self, path: str) -> bool:
        """
        Check if a file exists in the container.
        
        Args:
            path: Path to check in container
            
        Returns:
            True if file exists, False otherwise
        """
        exit_code, _, _ = await self.exec(f"test -e {path}")
        return exit_code == 0
    
    async def read_file(self, path: str) -> str:
        """
        Read a file from the container.
        
        Args:
            path: Path to file in container
            
        Returns:
            File contents as string
        """
        exit_code, stdout, stderr = await self.exec(f"cat {path}")
        if exit_code != 0:
            raise FileNotFoundError(f"File not found: {path}. Error: {stderr}")
        return stdout
    
    async def write_file(self, path: str, content: str) -> None:
        """
        Write content to a file in the container.
        
        Args:
            path: Path to file in container
            content: Content to write
        """
        # Escape content for shell
        escaped = content.replace("'", "'\"'\"'")
        exit_code, _, stderr = await self.exec(f"echo '{escaped}' > {path}")
        if exit_code != 0:
            raise IOError(f"Failed to write file: {path}. Error: {stderr}")
    
    @property
    def is_running(self) -> bool:
        """Check if the container is running."""
        if self._container is None:
            return False
        try:
            self._container.reload()
            return self._container.status == "running"
        except docker.errors.NotFound:
            self._container = None
            return False
    
    async def __aenter__(self) -> "ContainerManager":
        """Async context manager entry."""
        print(f"[DEBUG] Container __aenter__: starting container with image={self.config.image}")
        try:
            await self.start()
            print(f"[DEBUG] Container __aenter__: container started successfully")
        except Exception as e:
            print(f"[DEBUG] Container __aenter__: failed to start container: {e}")
            import traceback
            traceback.print_exc()
            raise
        return self
    
    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit - cleanup container."""
        await self.stop()
    
    def __enter__(self) -> "ContainerManager":
        """Sync context manager entry (starts container synchronously)."""
        asyncio.get_event_loop().run_until_complete(self.start())
        return self
    
    def __exit__(self, *args: Any) -> None:
        """Sync context manager exit - cleanup container."""
        asyncio.get_event_loop().run_until_complete(self.stop())
