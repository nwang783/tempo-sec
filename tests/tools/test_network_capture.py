"""Tests for NetworkRequestCapture functionality."""

import pytest
from unittest.mock import MagicMock, AsyncMock
import asyncio

from tempo.tools.network_capture import NetworkRequest, NetworkRequestCapture


class TestNetworkRequest:
    """Tests for NetworkRequest dataclass."""

    def test_create_network_request(self):
        """Test creating a NetworkRequest."""
        req = NetworkRequest(
            request_id="123",
            url="https://api.example.com/users",
            method="GET",
            resource_type="XHR",
        )
        assert req.request_id == "123"
        assert req.url == "https://api.example.com/users"
        assert req.method == "GET"
        assert req.resource_type == "XHR"
        assert req.completed is False
        assert req.response_status is None

    def test_to_dict(self):
        """Test converting NetworkRequest to dict."""
        req = NetworkRequest(
            request_id="456",
            url="https://api.example.com/data",
            method="POST",
            resource_type="Fetch",
            request_body='{"key": "value"}',
            response_status=200,
        )
        data = req.to_dict()
        assert data["request_id"] == "456"
        assert data["method"] == "POST"
        assert data["request_body"] == '{"key": "value"}'
        assert data["response_status"] == 200

    def test_format_summary_basic(self):
        """Test basic summary formatting."""
        req = NetworkRequest(
            request_id="789",
            url="https://api.example.com/endpoint",
            method="GET",
            resource_type="XHR",
            response_status=200,
        )
        summary = req.format_summary()
        assert "[GET]" in summary
        assert "https://api.example.com/endpoint" in summary
        assert "Status: 200" in summary

    def test_format_summary_with_headers(self):
        """Test summary includes interesting headers."""
        req = NetworkRequest(
            request_id="abc",
            url="https://api.example.com/secure",
            method="POST",
            resource_type="XHR",
            request_headers={
                "authorization": "Bearer token123",
                "content-type": "application/json",
            },
        )
        summary = req.format_summary()
        assert "authorization:" in summary
        assert "Bearer token123" in summary
        assert "content-type:" in summary

    def test_format_summary_with_body(self):
        """Test summary includes body when requested."""
        req = NetworkRequest(
            request_id="def",
            url="https://api.example.com/data",
            method="POST",
            resource_type="Fetch",
            request_body='{"username": "test"}',
            response_body='{"success": true}',
        )
        summary = req.format_summary(include_body=True)
        assert "Request Body:" in summary
        assert "username" in summary
        assert "Response Body:" in summary
        assert "success" in summary


class TestNetworkRequestCapture:
    """Tests for NetworkRequestCapture class."""

    def test_init_defaults(self):
        """Test default initialization."""
        capture = NetworkRequestCapture()
        assert capture.get_request_count() == 0
        assert capture._capture_response_bodies is False
        assert "XHR" in capture._resource_types
        assert "Fetch" in capture._resource_types

    def test_init_custom_settings(self):
        """Test custom initialization."""
        capture = NetworkRequestCapture(
            output_dir="/tmp/test",
            capture_response_bodies=True,
            resource_types={"Script", "Document"},
        )
        assert capture._output_dir == "/tmp/test"
        assert capture._capture_response_bodies is True
        assert "Script" in capture._resource_types
        assert "XHR" not in capture._resource_types

    def test_on_request_will_be_sent_xhr(self):
        """Test handling XHR request event."""
        capture = NetworkRequestCapture()
        
        event = {
            "requestId": "req-001",
            "type": "XHR",
            "request": {
                "url": "https://api.example.com/data",
                "method": "POST",
                "headers": {"Authorization": "Bearer xyz"},
                "postData": '{"test": true}',
            },
        }
        
        capture._on_request_will_be_sent(event)
        
        assert capture.get_request_count() == 1
        assert "req-001" in capture._request_map
        req = capture._request_map["req-001"]
        assert req.url == "https://api.example.com/data"
        assert req.method == "POST"
        assert req.request_body == '{"test": true}'
        assert "authorization" in req.request_headers

    def test_on_request_will_be_sent_filters_other_types(self):
        """Test that non-XHR/Fetch requests are filtered."""
        capture = NetworkRequestCapture()
        
        # Script request should be ignored
        event = {
            "requestId": "req-002",
            "type": "Script",
            "request": {
                "url": "https://example.com/app.js",
                "method": "GET",
                "headers": {},
            },
        }
        
        capture._on_request_will_be_sent(event)
        
        assert capture.get_request_count() == 0

    def test_on_response_received(self):
        """Test handling response event."""
        capture = NetworkRequestCapture()
        
        # First add a request
        capture._on_request_will_be_sent({
            "requestId": "req-003",
            "type": "Fetch",
            "request": {
                "url": "https://api.example.com/users",
                "method": "GET",
                "headers": {},
            },
        })
        
        # Then handle response
        capture._on_response_received({
            "requestId": "req-003",
            "response": {
                "status": 200,
                "headers": {"Content-Type": "application/json"},
            },
        })
        
        req = capture._request_map["req-003"]
        assert req.response_status == 200
        assert "content-type" in req.response_headers

    def test_on_loading_finished(self):
        """Test handling loading finished event."""
        capture = NetworkRequestCapture()
        
        # Add a request
        capture._on_request_will_be_sent({
            "requestId": "req-004",
            "type": "XHR",
            "request": {
                "url": "https://api.example.com/test",
                "method": "GET",
                "headers": {},
            },
        })
        
        assert capture._request_map["req-004"].completed is False
        
        # Mark as finished
        capture._on_loading_finished({"requestId": "req-004"})
        
        assert capture._request_map["req-004"].completed is True

    def test_on_loading_failed(self):
        """Test handling loading failed event."""
        capture = NetworkRequestCapture()
        
        # Add a request
        capture._on_request_will_be_sent({
            "requestId": "req-005",
            "type": "Fetch",
            "request": {
                "url": "https://api.example.com/fail",
                "method": "POST",
                "headers": {},
            },
        })
        
        # Mark as failed
        capture._on_loading_failed({
            "requestId": "req-005",
            "errorText": "net::ERR_CONNECTION_REFUSED",
        })
        
        req = capture._request_map["req-005"]
        assert req.completed is True
        assert req.error == "net::ERR_CONNECTION_REFUSED"

    def test_get_requests_empty(self):
        """Test get_requests with no captured requests."""
        capture = NetworkRequestCapture()
        output, saved_file = capture.get_requests()
        assert "No network requests captured" in output
        assert saved_file is None

    def test_get_requests_with_data(self):
        """Test get_requests returns formatted data."""
        capture = NetworkRequestCapture()
        
        # Add some requests
        capture._on_request_will_be_sent({
            "requestId": "req-006",
            "type": "XHR",
            "request": {
                "url": "https://api.example.com/users",
                "method": "GET",
                "headers": {},
            },
        })
        capture._on_response_received({
            "requestId": "req-006",
            "response": {"status": 200, "headers": {}},
        })
        
        output, saved_file = capture.get_requests()
        
        assert "Captured 1 network requests" in output
        assert "[GET]" in output
        assert "https://api.example.com/users" in output
        assert saved_file is None  # Small output shouldn't trigger file save

    def test_clear(self):
        """Test clearing captured requests."""
        capture = NetworkRequestCapture()
        
        # Add a request
        capture._on_request_will_be_sent({
            "requestId": "req-007",
            "type": "XHR",
            "request": {
                "url": "https://api.example.com/test",
                "method": "GET",
                "headers": {},
            },
        })
        
        assert capture.get_request_count() == 1
        
        capture.clear()
        
        assert capture.get_request_count() == 0
        assert len(capture._request_map) == 0

    def test_max_requests_limit(self):
        """Test that requests are limited by MAX_REQUESTS."""
        capture = NetworkRequestCapture()
        # Override MAX_REQUESTS for testing
        capture._requests = type(capture._requests)(maxlen=5)
        
        # Add more requests than the limit
        for i in range(10):
            capture._on_request_will_be_sent({
                "requestId": f"req-{i:03d}",
                "type": "XHR",
                "request": {
                    "url": f"https://api.example.com/item/{i}",
                    "method": "GET",
                    "headers": {},
                },
            })
        
        # Should only keep the most recent 5
        assert capture.get_request_count() == 5

    def test_pending_body_requests_queued_on_loading_finished(self):
        """Test that requests with capturable content types are queued for body fetch."""
        capture = NetworkRequestCapture(capture_response_bodies=True)

        # Add request with response headers
        capture._on_request_will_be_sent({
            "requestId": "req-body-001",
            "type": "XHR",
            "request": {
                "url": "https://api.example.com/data",
                "method": "GET",
                "headers": {},
            },
        })

        # Add response with JSON content type
        capture._on_response_received({
            "requestId": "req-body-001",
            "response": {
                "status": 200,
                "headers": {"Content-Type": "application/json; charset=utf-8"},
            },
        })

        # Loading finished should queue for body capture
        capture._on_loading_finished({"requestId": "req-body-001"})

        assert "req-body-001" in capture._pending_body_requests

    def test_pending_body_requests_not_queued_for_binary(self):
        """Test that binary content types are not queued for body fetch."""
        capture = NetworkRequestCapture(capture_response_bodies=True)

        capture._on_request_will_be_sent({
            "requestId": "req-img-001",
            "type": "XHR",
            "request": {
                "url": "https://api.example.com/image.png",
                "method": "GET",
                "headers": {},
            },
        })

        capture._on_response_received({
            "requestId": "req-img-001",
            "response": {
                "status": 200,
                "headers": {"Content-Type": "image/png"},
            },
        })

        capture._on_loading_finished({"requestId": "req-img-001"})

        # Should NOT be queued for body capture
        assert "req-img-001" not in capture._pending_body_requests

    def test_clear_also_clears_pending_body_requests(self):
        """Test that clear() also clears pending body requests."""
        capture = NetworkRequestCapture(capture_response_bodies=True)

        # Queue a pending body request
        capture._pending_body_requests.add("test-request-id")

        capture.clear()

        assert len(capture._pending_body_requests) == 0

    async def test_get_requests_async(self):
        """Test async get_requests_async method."""
        capture = NetworkRequestCapture()

        # Add a request
        capture._on_request_will_be_sent({
            "requestId": "async-001",
            "type": "Fetch",
            "request": {
                "url": "https://api.example.com/async",
                "method": "GET",
                "headers": {},
            },
        })

        output, saved_file = await capture.get_requests_async()

        assert "https://api.example.com/async" in output
        assert saved_file is None
