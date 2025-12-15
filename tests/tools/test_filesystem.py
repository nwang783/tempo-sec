"""Tests for tempo/tools/filesystem.py."""

import os
import tempfile

import pytest

from tempo.tools.filesystem import FileReadTool, FileWriteTool


class TestFileReadTool:
    """Tests for FileReadTool class."""
    
    def test_name_and_category(self):
        """Test tool name and category are set."""
        tool = FileReadTool()
        assert tool.name == "file_read"
        assert tool.category.value == "filesystem"
    
    def test_get_schema(self):
        """Test schema generation."""
        tool = FileReadTool()
        schema = tool.get_schema().to_openai_format()
        
        assert schema["function"]["name"] == "file_read"
        assert "path" in schema["function"]["parameters"]["properties"]
    
    @pytest.mark.asyncio
    async def test_read_file(self):
        """Test reading a file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test content")
            path = f.name
        
        try:
            tool = FileReadTool(container_manager=None)
            result = await tool.execute(path=path, purpose="Test read")
            
            assert result.success is True
            assert result.output == "test content"
        finally:
            os.unlink(path)
    
    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self):
        """Test reading a nonexistent file."""
        tool = FileReadTool(container_manager=None)
        result = await tool.execute(path="/nonexistent/file.txt", purpose="Test")
        
        assert result.success is False
        assert "not found" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_read_with_max_bytes(self):
        """Test reading with max_bytes limit."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("A" * 100)
            path = f.name
        
        try:
            tool = FileReadTool(container_manager=None)
            result = await tool.execute(path=path, max_bytes=10, purpose="Test")
            
            assert result.success is True
            assert len(result.output) == 10
        finally:
            os.unlink(path)


class TestFileWriteTool:
    """Tests for FileWriteTool class."""
    
    def test_name_and_category(self):
        """Test tool name and category are set."""
        tool = FileWriteTool()
        assert tool.name == "file_write"
        assert tool.category.value == "filesystem"
    
    def test_get_schema(self):
        """Test schema generation."""
        tool = FileWriteTool()
        schema = tool.get_schema().to_openai_format()
        
        assert schema["function"]["name"] == "file_write"
        assert "path" in schema["function"]["parameters"]["properties"]
        assert "content" in schema["function"]["parameters"]["properties"]
    
    @pytest.mark.asyncio
    async def test_write_file(self):
        """Test writing a file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            tool = FileWriteTool(container_manager=None)
            
            result = await tool.execute(
                path=path,
                content="hello world",
                purpose="Test write",
            )
            
            assert result.success is True
            with open(path) as f:
                assert f.read() == "hello world"
    
    @pytest.mark.asyncio
    async def test_append_to_file(self):
        """Test appending to a file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            
            # Write initial content
            with open(path, "w") as f:
                f.write("first ")
            
            tool = FileWriteTool(container_manager=None)
            result = await tool.execute(
                path=path,
                content="second",
                append=True,
                purpose="Test append",
            )
            
            assert result.success is True
            with open(path) as f:
                assert f.read() == "first second"
