"""Tests for tempo/findings/document.py."""

import tempfile
from pathlib import Path

import pytest

from tempo.findings.document import FindingsDocument
from tempo.findings.schema import FindingStatus, Severity


class TestFindingsDocumentInit:
    """Tests for FindingsDocument initialization."""

    def test_create_new_document(self):
        """Test creating a new findings document."""
        doc = FindingsDocument(target="https://example.com")

        assert doc._data.target == "https://example.com"
        assert doc._data.version == "1.0"
        assert len(doc._data.attack_surfaces) == 0
        assert len(doc._data.findings) == 0

    def test_create_with_file_path(self):
        """Test creating document with file path."""
        doc = FindingsDocument(
            target="https://example.com",
            file_path="/tmp/findings.yaml"
        )

        assert doc.file_path == "/tmp/findings.yaml"


class TestFindingsDocumentPersistence:
    """Tests for save/load operations."""

    def test_save_and_load(self):
        """Test saving and loading a document."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "findings.yaml")

            # Create and save
            doc = FindingsDocument(target="https://example.com")
            doc.add_attack_surface(
                surface_id="surf-1",
                surface_type="endpoint",
                url="https://example.com/api",
                description="API endpoint",
                discovered_by="recon",
            )
            doc.save(path)

            # Load
            loaded = FindingsDocument.load(path)

            assert loaded._data.target == "https://example.com"
            assert len(loaded._data.attack_surfaces) == 1
            assert loaded._data.attack_surfaces[0].id == "surf-1"

    def test_save_without_path_raises(self):
        """Test that saving without path raises ValueError."""
        doc = FindingsDocument(target="https://example.com")

        with pytest.raises(ValueError, match="No file path"):
            doc.save()

    def test_save_updates_timestamp(self):
        """Test that save updates the updated_at timestamp."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "findings.yaml")

            doc = FindingsDocument(target="https://example.com", file_path=path)
            original_time = doc._data.updated_at

            # Small delay to ensure timestamp changes
            import time
            time.sleep(0.01)

            doc.save()

            assert doc._data.updated_at > original_time


class TestQueryMethods:
    """Tests for query methods."""

    def test_get_untested_surfaces(self):
        """Test getting untested attack surfaces."""
        doc = FindingsDocument(target="https://example.com")

        # Add tested surface
        doc.add_attack_surface(
            surface_id="surf-1",
            surface_type="endpoint",
            url="https://example.com/api1",
            description="Tested endpoint",
            discovered_by="recon",
        )
        doc.mark_surface_tested("surf-1")

        # Add untested surface
        doc.add_attack_surface(
            surface_id="surf-2",
            surface_type="endpoint",
            url="https://example.com/api2",
            description="Untested endpoint",
            discovered_by="recon",
        )

        untested = doc.get_untested_surfaces()

        assert len(untested) == 1
        assert untested[0].id == "surf-2"

    def test_get_findings_by_severity(self):
        """Test filtering findings by severity."""
        doc = FindingsDocument(target="https://example.com")

        doc.add_finding(
            finding_id="find-1",
            title="Critical Issue",
            severity=Severity.CRITICAL,
            status=FindingStatus.CONFIRMED,
            description="Bad",
            evidence="proof",
            discovered_by="tester",
        )

        doc.add_finding(
            finding_id="find-2",
            title="Info Issue",
            severity=Severity.INFO,
            status=FindingStatus.CONFIRMED,
            description="FYI",
            evidence="proof",
            discovered_by="tester",
        )

        critical = doc.get_findings_by_severity(Severity.CRITICAL)
        info = doc.get_findings_by_severity(Severity.INFO)

        assert len(critical) == 1
        assert critical[0].title == "Critical Issue"
        assert len(info) == 1
        assert info[0].title == "Info Issue"

    def test_get_summary(self):
        """Test getting document summary."""
        doc = FindingsDocument(target="https://example.com")

        doc.add_attack_surface(
            surface_id="surf-1",
            surface_type="endpoint",
            url="https://example.com/api",
            description="Test",
            discovered_by="recon",
        )

        doc.add_finding(
            finding_id="find-1",
            title="Issue",
            severity=Severity.HIGH,
            status=FindingStatus.CONFIRMED,
            description="Problem",
            evidence="proof",
            discovered_by="tester",
        )

        summary = doc.get_summary()

        assert summary["target"] == "https://example.com"
        assert summary["total_surfaces"] == 1
        assert summary["untested_surfaces"] == 1
        assert summary["total_findings"] == 1
        assert summary["findings_by_severity"]["high"] == 1


class TestUpdateMethods:
    """Tests for update methods."""

    def test_add_attack_surface(self):
        """Test adding attack surface."""
        doc = FindingsDocument(target="https://example.com")

        surface = doc.add_attack_surface(
            surface_id="surf-1",
            surface_type="form",
            url="https://example.com/upload",
            description="File upload",
            discovered_by="recon",
            parameters=["file", "description"],
            technology_hints=["PHP"],
            priority="high",
        )

        assert surface.id == "surf-1"
        assert surface.surface_type == "form"
        assert surface.url == "https://example.com/upload"
        assert surface.parameters == ["file", "description"]
        assert surface.technology_hints == ["PHP"]
        assert surface.priority == "high"
        assert len(doc._data.attack_surfaces) == 1

    def test_add_finding(self):
        """Test adding finding."""
        doc = FindingsDocument(target="https://example.com")

        finding = doc.add_finding(
            finding_id="find-1",
            title="SQL Injection",
            severity=Severity.CRITICAL,
            status=FindingStatus.CONFIRMED,
            description="SQL injection vulnerability",
            evidence="Error messages reveal DB structure",
            discovered_by="sqli_scanner",
            attack_surface_id="surf-1",
            reproduction_steps=["Step 1", "Step 2"],
            remediation="Use parameterized queries",
            validated_by="manual_tester",
        )

        assert finding.id == "find-1"
        assert finding.title == "SQL Injection"
        assert finding.severity == Severity.CRITICAL
        assert finding.status == FindingStatus.CONFIRMED
        assert finding.attack_surface_id == "surf-1"
        assert len(finding.reproduction_steps) == 2
        assert finding.remediation == "Use parameterized queries"
        assert finding.validated_by == "manual_tester"
        assert len(doc._data.findings) == 1

    def test_mark_surface_tested(self):
        """Test marking surface as tested."""
        doc = FindingsDocument(target="https://example.com")

        doc.add_attack_surface(
            surface_id="surf-1",
            surface_type="endpoint",
            url="https://example.com/api",
            description="Test",
            discovered_by="recon",
        )

        assert doc._data.attack_surfaces[0].tested is False

        success = doc.mark_surface_tested("surf-1")

        assert success is True
        assert doc._data.attack_surfaces[0].tested is True

    def test_mark_surface_tested_not_found(self):
        """Test marking non-existent surface returns False."""
        doc = FindingsDocument(target="https://example.com")

        success = doc.mark_surface_tested("nonexistent")

        assert success is False

    def test_update_recon_summary(self):
        """Test updating recon summary."""
        doc = FindingsDocument(target="https://example.com")

        summary = doc.update_recon_summary(
            total_endpoints=10,
            total_forms=3,
            total_apis=5,
            technologies_detected=["React", "Express"],
            authentication_mechanisms=["JWT"],
            notes="Modern web app",
        )

        assert summary.total_endpoints == 10
        assert summary.total_forms == 3
        assert summary.total_apis == 5
        assert len(summary.technologies_detected) == 2
        assert len(summary.authentication_mechanisms) == 1
        assert summary.notes == "Modern web app"

    def test_update_recon_summary_partial(self):
        """Test partial update of recon summary."""
        doc = FindingsDocument(target="https://example.com")

        # Initial update
        doc.update_recon_summary(total_endpoints=10, notes="Initial")

        # Partial update
        doc.update_recon_summary(total_forms=5)

        summary = doc._data.recon_summary

        assert summary.total_endpoints == 10  # Unchanged
        assert summary.total_forms == 5  # Updated
        assert summary.notes == "Initial"  # Unchanged


class TestMetadataMethods:
    """Tests for metadata methods."""

    def test_add_agent_invocation(self):
        """Test recording agent invocations."""
        doc = FindingsDocument(target="https://example.com")

        doc.add_agent_invocation("recon_agent")
        doc.add_agent_invocation("test_agent")
        doc.add_agent_invocation("recon_agent")  # Duplicate

        assert len(doc._data.agents_invoked) == 2
        assert "recon_agent" in doc._data.agents_invoked
        assert "test_agent" in doc._data.agents_invoked

    def test_increment_steps(self):
        """Test incrementing step counter."""
        doc = FindingsDocument(target="https://example.com")

        assert doc._data.total_steps_taken == 0

        doc.increment_steps()
        assert doc._data.total_steps_taken == 1

        doc.increment_steps(5)
        assert doc._data.total_steps_taken == 6

    def test_data_property(self):
        """Test accessing underlying data."""
        doc = FindingsDocument(target="https://example.com")

        data = doc.data

        assert data.target == "https://example.com"
        assert data.version == "1.0"
