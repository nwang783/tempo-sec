"""
Tools for searching and retrieving stored tool outputs.
"""

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema
from tempo.infra.output_store import OutputStore


class SearchStoredOutputTool(Tool):
    """Search within a stored output by handle."""

    name = "search_stored_output"
    description = "Search a stored tool output by handle. Use to find endpoints/IDs without loading full output."
    category = ToolCategory.META

    def __init__(self, store: OutputStore):
        self._store = store

    async def execute(
        self,
        handle: str,
        query: str,
        regex: bool = False,
        case_sensitive: bool = False,
        max_hits: int = 20,
        context_chars: int = 60,
        purpose: str = "",
    ) -> ToolResult:
        try:
            result = self._store.search(
                handle=handle,
                query=query,
                regex=regex,
                case_sensitive=case_sensitive,
                max_hits=max_hits,
                context_chars=context_chars,
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

        hits = result.get("hits", [])
        total_hits = result.get("total_hits", 0)
        scanned = result.get("scanned_bytes", 0)

        lines = [f"[Search {handle}] hits={total_hits} scanned_bytes={scanned}"]
        for hit in hits:
            lines.append(
                f"- {hit['start']}:{hit['end']} {hit['match']}\n  {hit['context']}"
            )

        return ToolResult(
            success=True,
            output="\n".join(lines),
            metadata={
                "handle": handle,
                "total_hits": total_hits,
                "scanned_bytes": scanned,
            },
        )

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "handle": {
                        "type": "string",
                        "description": "Stored output handle returned by a tool",
                    },
                    "query": {
                        "type": "string",
                        "description": "Text or regex to search for",
                    },
                    "regex": {
                        "type": "boolean",
                        "description": "Treat query as regex",
                        "default": False,
                    },
                    "case_sensitive": {
                        "type": "boolean",
                        "description": "Case-sensitive search",
                        "default": False,
                    },
                    "max_hits": {
                        "type": "integer",
                        "description": "Maximum number of hits to return",
                        "default": 20,
                    },
                    "context_chars": {
                        "type": "integer",
                        "description": "Context chars around each hit",
                        "default": 60,
                    },
                    "purpose": {
                        "type": "string",
                        "description": "Why you are searching this output",
                    },
                },
                "required": ["handle", "query", "purpose"],
            },
        )


class GetStoredOutputRangeTool(Tool):
    """Return a byte range from a stored output."""

    name = "get_stored_output_range"
    description = "Fetch a byte range from a stored tool output by handle."
    category = ToolCategory.META

    def __init__(self, store: OutputStore):
        self._store = store

    async def execute(
        self,
        handle: str,
        start: int | str = 0,
        end: int | str = 10000,
        purpose: str = "",
    ) -> ToolResult:
        try:
            start = int(start)
            end = int(end)
            content, total = self._store.read_range(handle, start, end)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

        return ToolResult(
            success=True,
            output=f"[Showing bytes {start}-{end} of {total} total]\n{content}",
            metadata={
                "handle": handle,
                "start": start,
                "end": end,
                "total_bytes": total,
            },
        )

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "handle": {
                        "type": "string",
                        "description": "Stored output handle returned by a tool",
                    },
                    "start": {
                        "type": "integer",
                        "description": "Start byte offset (0-indexed)",
                        "default": 0,
                    },
                    "end": {
                        "type": "integer",
                        "description": "End byte offset (exclusive)",
                        "default": 10000,
                    },
                    "purpose": {
                        "type": "string",
                        "description": "Why you are fetching this range",
                    },
                },
                "required": ["handle", "purpose"],
            },
        )
