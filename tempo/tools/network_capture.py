"""
Network Request Capture for Browser Agent.

Captures XHR/fetch requests via CDP Network domain events,
providing visibility into API calls made by web pages.
"""

import asyncio
import json
import os
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from browser_use.browser.session import BrowserSession


@dataclass
class NetworkRequest:
    """Captured network request/response data."""

    request_id: str
    url: str
    method: str
    resource_type: str  # XHR, Fetch, Document, Script, etc.
    request_headers: dict[str, str] = field(default_factory=dict)
    request_body: str | None = None  # POST body if available
    response_status: int | None = None
    response_headers: dict[str, str] | None = None
    response_body: str | None = None  # Body if captured
    timestamp: float = 0.0
    completed: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "request_id": self.request_id,
            "url": self.url,
            "method": self.method,
            "resource_type": self.resource_type,
            "request_headers": self.request_headers,
            "request_body": self.request_body,
            "response_status": self.response_status,
            "response_headers": self.response_headers,
            "response_body": self.response_body,
            "timestamp": self.timestamp,
            "completed": self.completed,
            "error": self.error,
        }

    def format_summary(self, include_body: bool = False) -> str:
        """Format request as a human-readable summary."""
        lines = [
            f"[{self.method}] {self.url}",
            f"  Type: {self.resource_type}",
        ]

        if self.response_status:
            lines.append(f"  Status: {self.response_status}")

        if self.error:
            lines.append(f"  Error: {self.error}")

        # Show key headers
        interesting_headers = [
            "authorization",
            "x-api-key",
            "cookie",
            "content-type",
            "x-csrf-token",
            "x-requested-with",
        ]
        for header in interesting_headers:
            if header in self.request_headers:
                value = self.request_headers[header]
                # Truncate long values
                if len(value) > 100:
                    value = value[:100] + "..."
                lines.append(f"  {header}: {value}")

        if include_body and self.request_body:
            body_preview = self.request_body[:500]
            if len(self.request_body) > 500:
                body_preview += f"... ({len(self.request_body)} chars total)"
            lines.append(f"  Request Body: {body_preview}")

        if include_body and self.response_body:
            body_preview = self.response_body[:500]
            if len(self.response_body) > 500:
                body_preview += f"... ({len(self.response_body)} chars total)"
            lines.append(f"  Response Body: {body_preview}")

        return "\n".join(lines)


class NetworkRequestCapture:
    """
    Captures network requests via CDP Network domain events.

    Attaches to a browser session and listens for XHR/fetch requests.
    On navigation, saves full history to file and clears in-memory buffer.
    """

    # Resource types to capture by default (XHR and Fetch for API calls)
    DEFAULT_RESOURCE_TYPES = {"XHR", "Fetch"}

    # Maximum requests to keep in memory
    MAX_REQUESTS = 100

    # Character limit for displayed output
    DISPLAY_CHAR_LIMIT = 45000

    # Maximum response body size to capture (1MB limit to prevent memory issues)
    MAX_BODY_SIZE = 1024 * 1024

    # Content types worth capturing (skip images, fonts, etc.)
    CAPTURABLE_CONTENT_TYPES = {
        "application/json",
        "application/xml",
        "text/html",
        "text/plain",
        "text/xml",
        "application/javascript",
        "text/javascript",
    }

    def __init__(
        self,
        output_dir: str = "/workspace",
        capture_response_bodies: bool = False,
        resource_types: set[str] | None = None,
    ):
        """
        Initialize network request capture.

        Args:
            output_dir: Directory for saving full request logs
            capture_response_bodies: Whether to capture response bodies (memory intensive)
            resource_types: Resource types to capture (default: XHR, Fetch)
        """
        self._requests: deque[NetworkRequest] = deque(maxlen=self.MAX_REQUESTS)
        self._request_map: dict[str, NetworkRequest] = {}  # request_id -> request
        self._pending_body_requests: set[str] = set()  # request_ids needing body fetch
        self._output_dir = output_dir
        self._capture_response_bodies = capture_response_bodies
        self._resource_types = resource_types or self.DEFAULT_RESOURCE_TYPES
        self._navigation_count = 0
        self._session: "BrowserSession | None" = None
        self._attached = False

    async def attach(self, browser_session: "BrowserSession") -> None:
        """
        Attach to a browser session to capture network requests.

        Args:
            browser_session: The browser-use BrowserSession instance
        """
        if self._attached:
            return

        self._session = browser_session

        # Get the CDP client from session
        cdp_client = browser_session._cdp_client_root
        if not cdp_client:
            return

        # Register handlers for network events
        cdp_client.register.Network.requestWillBeSent(self._on_request_will_be_sent)
        cdp_client.register.Network.responseReceived(self._on_response_received)
        cdp_client.register.Network.loadingFinished(self._on_loading_finished)
        cdp_client.register.Network.loadingFailed(self._on_loading_failed)

        # Register handler for navigation (to clear/save requests)
        cdp_client.register.Page.frameNavigated(self._on_frame_navigated)

        self._attached = True

    def _on_request_will_be_sent(
        self, event: dict[str, Any], session_id: str | None = None
    ) -> None:
        """Handle Network.requestWillBeSent event."""
        request_id = event.get("requestId", "")
        request = event.get("request", {})
        resource_type = event.get("type", "Other")

        # Filter by resource type
        if resource_type not in self._resource_types:
            return

        url = request.get("url", "")
        method = request.get("method", "GET")
        headers = request.get("headers", {})
        post_data = request.get("postData")

        # Normalize headers to lowercase keys
        normalized_headers = {k.lower(): v for k, v in headers.items()}

        network_request = NetworkRequest(
            request_id=request_id,
            url=url,
            method=method,
            resource_type=resource_type,
            request_headers=normalized_headers,
            request_body=post_data,
            timestamp=datetime.now(timezone.utc).timestamp(),
        )

        self._requests.append(network_request)
        self._request_map[request_id] = network_request

    def _on_response_received(
        self, event: dict[str, Any], session_id: str | None = None
    ) -> None:
        """Handle Network.responseReceived event."""
        request_id = event.get("requestId", "")

        if request_id not in self._request_map:
            return

        network_request = self._request_map[request_id]
        response = event.get("response", {})

        network_request.response_status = response.get("status")

        # Capture response headers
        headers = response.get("headers", {})
        network_request.response_headers = {k.lower(): v for k, v in headers.items()}

    def _on_loading_finished(
        self, event: dict[str, Any], session_id: str | None = None
    ) -> None:
        """Handle Network.loadingFinished event."""
        request_id = event.get("requestId", "")

        if request_id not in self._request_map:
            return

        network_request = self._request_map[request_id]
        network_request.completed = True

        # Queue for body capture if enabled and content type is worth capturing
        if self._capture_response_bodies and network_request.response_headers:
            content_type = network_request.response_headers.get("content-type", "")
            # Check if content type starts with any capturable type
            if any(ct in content_type for ct in self.CAPTURABLE_CONTENT_TYPES):
                self._pending_body_requests.add(request_id)

    def _on_loading_failed(
        self, event: dict[str, Any], session_id: str | None = None
    ) -> None:
        """Handle Network.loadingFailed event."""
        request_id = event.get("requestId", "")

        if request_id not in self._request_map:
            return

        network_request = self._request_map[request_id]
        network_request.completed = True
        network_request.error = event.get("errorText", "Unknown error")

    def _on_frame_navigated(
        self, event: dict[str, Any], session_id: str | None = None
    ) -> None:
        """Handle Page.frameNavigated event - save and clear requests."""
        # Only act on main frame navigations
        frame = event.get("frame", {})
        if frame.get("parentId"):
            # This is an iframe navigation, ignore
            return

        # Save current requests to file before clearing
        if self._requests:
            self._save_requests_to_file()

        # Clear in-memory state
        self._requests.clear()
        self._request_map.clear()
        self._pending_body_requests.clear()
        self._navigation_count += 1

    async def fetch_pending_bodies(self) -> int:
        """
        Fetch response bodies for pending requests via CDP.

        This is called on-demand when include_bodies=True is requested.
        Bodies are fetched asynchronously via Network.getResponseBody.

        Returns:
            Number of bodies successfully fetched
        """
        if not self._session or not self._pending_body_requests:
            return 0

        cdp_client = getattr(self._session, "_cdp_client_root", None)
        if not cdp_client:
            return 0

        fetched = 0
        to_remove = set()

        for request_id in list(self._pending_body_requests):
            if request_id not in self._request_map:
                to_remove.add(request_id)
                continue

            network_request = self._request_map[request_id]
            if network_request.response_body is not None:
                # Already fetched
                to_remove.add(request_id)
                continue

            try:
                # Call CDP command to get response body
                result = await cdp_client.send(
                    "Network.getResponseBody",
                    {"requestId": request_id},
                )

                body = result.get("body", "")
                is_base64 = result.get("base64Encoded", False)

                if is_base64:
                    # Skip binary content (images, etc.)
                    network_request.response_body = "[Binary content - base64 encoded]"
                elif len(body) > self.MAX_BODY_SIZE:
                    network_request.response_body = (
                        body[: self.MAX_BODY_SIZE]
                        + f"\n[TRUNCATED - response was {len(body)} bytes]"
                    )
                else:
                    network_request.response_body = body

                fetched += 1
                to_remove.add(request_id)

            except Exception:
                # Request may have been cleaned up by browser, skip it
                to_remove.add(request_id)

        # Clean up processed requests
        self._pending_body_requests -= to_remove

        return fetched

    def _save_requests_to_file(self) -> str | None:
        """Save all captured requests to a JSON file."""
        if not self._requests:
            return None

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"network_requests_{timestamp}.json"
        filepath = os.path.join(self._output_dir, filename)

        try:
            data = {
                "captured_at": timestamp,
                "navigation_count": self._navigation_count,
                "request_count": len(self._requests),
                "requests": [r.to_dict() for r in self._requests],
            }

            os.makedirs(self._output_dir, exist_ok=True)
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)

            return filepath
        except Exception:
            return None

    def get_requests(
        self,
        include_bodies: bool = False,
        max_requests: int = 50,
    ) -> tuple[str, str | None]:
        """
        Get formatted summary of captured requests.

        Args:
            include_bodies: Include request/response bodies
            max_requests: Maximum number of requests to return

        Returns:
            Tuple of (formatted output, file path if truncated)
        """
        # Determine which requests to include
        requests_to_show = list(self._requests)

        # Limit to max_requests (most recent)
        if len(requests_to_show) > max_requests:
            requests_to_show = requests_to_show[-max_requests:]

        if not requests_to_show:
            return "No network requests captured.", None

        # Format output
        lines = [
            f"Captured {len(requests_to_show)} network requests "
            f"(showing {min(len(requests_to_show), max_requests)}):",
            "",
        ]

        for i, req in enumerate(requests_to_show, 1):
            lines.append(f"--- Request {i} ---")
            lines.append(req.format_summary(include_body=include_bodies))
            lines.append("")

        full_output = "\n".join(lines)

        # Check if we need to truncate and save to file
        saved_file = None
        if len(full_output) > self.DISPLAY_CHAR_LIMIT:
            saved_file = self._save_requests_to_file()
            truncated_output = full_output[: self.DISPLAY_CHAR_LIMIT]
            truncated_output += (
                f"\n\n[OUTPUT TRUNCATED - {len(full_output)} chars total]\n"
            )
            if saved_file:
                truncated_output += (
                    f"Full output saved to: {saved_file}\n"
                    f"Use file_read tool to view complete data."
                )
            return truncated_output, saved_file

        return full_output, None

    async def get_requests_async(
        self,
        include_bodies: bool = False,
        max_requests: int = 50,
    ) -> tuple[str, str | None]:
        """
        Async version of get_requests that fetches response bodies on-demand.

        When include_bodies=True, this will fetch any pending response bodies
        via CDP before formatting the output.

        Args:
            include_bodies: Include request/response bodies (triggers async fetch)
            max_requests: Maximum number of requests to return

        Returns:
            Tuple of (formatted output, file path if truncated)
        """
        # Fetch pending bodies if requested
        if include_bodies and self._pending_body_requests:
            await self.fetch_pending_bodies()

        # Delegate to sync method for formatting
        return self.get_requests(
            include_bodies=include_bodies,
            max_requests=max_requests,
        )

    def get_request_count(self) -> int:
        """Get the number of captured requests."""
        return len(self._requests)

    def clear(self) -> None:
        """Clear all captured requests."""
        self._requests.clear()
        self._request_map.clear()
        self._pending_body_requests.clear()
