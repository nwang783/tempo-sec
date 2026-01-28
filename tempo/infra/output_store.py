"""
File-backed output store for large tool outputs.

Stores full tool outputs on disk and returns opaque handles for lookup.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

_HANDLE_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


class OutputStore:
    """Persist and retrieve large tool outputs by handle."""

    def __init__(self, root_dir: str):
        self._root = Path(root_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def default(cls) -> "OutputStore":
        root = os.getenv("TEMPO_OUTPUT_STORE_DIR", "/tmp/tempo_output_store")
        return cls(root)

    def save(self, content: str, metadata: dict[str, Any] | None = None) -> str:
        handle = f"out_{uuid.uuid4().hex}"
        self._ensure_handle(handle)

        content_path = self._content_path(handle)
        meta_path = self._meta_path(handle)

        with content_path.open("w", encoding="utf-8", errors="replace") as f:
            f.write(content)

        meta = {
            "handle": handle,
            "created_at": int(time.time()),
            "chars": len(content),
            "metadata": metadata or {},
        }

        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=True, indent=2)

        return handle

    def read_range(self, handle: str, start: int, end: int) -> tuple[str, int]:
        self._ensure_handle(handle)
        content_path = self._content_path(handle)
        size = content_path.stat().st_size

        start = max(0, start)
        end = min(size, end)
        if start >= end:
            return "", size

        with content_path.open("rb") as f:
            f.seek(start)
            data = f.read(end - start)

        return data.decode("utf-8", errors="replace"), size

    def search(
        self,
        handle: str,
        query: str,
        *,
        regex: bool = False,
        case_sensitive: bool = False,
        max_hits: int = 20,
        context_chars: int = 60,
    ) -> dict[str, Any]:
        import re as _re

        self._ensure_handle(handle)
        if not query:
            return {"hits": [], "total_hits": 0, "scanned_bytes": 0}

        content_path = self._content_path(handle)
        hits: list[dict[str, Any]] = []
        total_hits = 0
        scanned = 0
        chunk_size = 64 * 1024

        flags = 0 if case_sensitive else _re.IGNORECASE
        pattern = _re.compile(query, flags) if regex else None

        tail = b""
        tail_keep = max(context_chars + 128, len(query))

        with content_path.open("rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break

                scanned += len(chunk)
                buffer = tail + chunk
                buffer_start = scanned - len(buffer)

                if regex:
                    text = buffer.decode("utf-8", errors="replace")
                    for match in pattern.finditer(text):
                        if total_hits >= max_hits:
                            break
                        start = buffer_start + match.start()
                        end = buffer_start + match.end()
                        context = _slice_context(text, match.start(), match.end(), context_chars)
                        hits.append(
                            {
                                "start": start,
                                "end": end,
                                "match": match.group(0),
                                "context": context,
                            }
                        )
                        total_hits += 1
                else:
                    hay = buffer if case_sensitive else buffer.lower()
                    needle = query.encode() if case_sensitive else query.encode().lower()
                    idx = 0
                    while True:
                        if total_hits >= max_hits:
                            break
                        found = hay.find(needle, idx)
                        if found == -1:
                            break
                        start = buffer_start + found
                        end = start + len(needle)
                        text = buffer.decode("utf-8", errors="replace")
                        context = _slice_context(text, found, found + len(needle), context_chars)
                        hits.append(
                            {
                                "start": start,
                                "end": end,
                                "match": text[found : found + len(needle)],
                                "context": context,
                            }
                        )
                        total_hits += 1
                        idx = found + len(needle)

                if total_hits >= max_hits:
                    break

                tail = buffer[-tail_keep:]

        return {
            "hits": hits,
            "total_hits": total_hits,
            "scanned_bytes": scanned,
        }

    def _content_path(self, handle: str) -> Path:
        return self._root / f"{handle}.txt"

    def _meta_path(self, handle: str) -> Path:
        return self._root / f"{handle}.json"

    def _ensure_handle(self, handle: str) -> None:
        if not _HANDLE_RE.match(handle):
            raise ValueError(f"Invalid handle: {handle}")


def _slice_context(text: str, start: int, end: int, context_chars: int) -> str:
    left = max(0, start - context_chars)
    right = min(len(text), end + context_chars)
    return text[left:right]
