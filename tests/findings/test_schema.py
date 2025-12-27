"""Tests for tempo/findings/schema.py."""

from datetime import datetime

import pytest

from tempo.findings.schema import (
    AttackSurface,
    Finding,
    FindingStatus,
    FindingsDocumentSchema,
    ReconSummary,
    Severity,
)


class TestSeverity:
    """Tests for Severity enum."""

    def test_all_severities_exist(self):
        """Test all expected severity levels exist."""
        assert Severity.CRITICAL == "critical"
        assert Severity.HIGH == "high"
        assert Severity.MEDIUM == "medium"
        assert Severity.LOW == "low"
        assert Severity.INFO == "info"


class TestFindingStatus:
    """Tests for FindingStatus enum."""

    def test_all_statuses_exist(self):
        """Test all expected status values exist."""
        assert FindingStatus.SUSPECTED == "suspected"
        assert FindingStatus.CONFIRMED == "confirmed"
        assert FindingStatus.FALSE_POSITIVE == "false_positive"
        assert FindingStatus.NEEDS_MANUAL == "needs_manual"


class TestAttackSurface:
    """Tests for AttackSurface model."""

    def test_basic_creation(self):
        """Test creating a basic attack surface."""
        surface = AttackSurface(
            id="test-id",
            surface_type="endpoint",
            url="https://example.com/api/login",
            description="Login endpoint",
            discovered_by="recon_agent",
        )

        assert surface.id == "test-id"
        assert surface.surface_type == "endpoint"
        assert surface.url == "https://example.com/api/login"
        assert surface.description == "Login endpoint"
        assert surface.discovered_by == "recon_agent"
        assert surface.tested is False
        assert surface.priority == "medium"
        assert surface.parameters == []
        assert surface.technology_hints == []

    def test_with_all_fields(self):
        """Test creating attack surface with all fields."""
        now = datetime.utcnow()
        surface = AttackSurface(
            id="test-id",
            surface_type="form",
            url="https://example.com/upload",
            description="File upload form",
            parameters=["file", "description"],
            technology_hints=["PHP", "nginx"],
            tested=True,
            priority="high",
            discovered_at=now,
            discovered_by="recon_agent",
        )

        assert surface.parameters == ["file", "description"]
        assert surface.technology_hints == ["PHP", "nginx"]
        assert surface.tested is True
        assert surface.priority == "high"
        assert surface.discovered_at == now


class TestFinding:
    """Tests for Finding model."""

    def test_basic_creation(self):
        """Test creating a basic finding."""
        finding = Finding(
            id="finding-id",
            title="SQL Injection",
            severity=Severity.HIGH,
            status=FindingStatus.CONFIRMED,
            description="SQL injection in login form",
            evidence="Error message reveals database structure",
            discovered_by="test_agent",
        )

        assert finding.id == "finding-id"
        assert finding.title == "SQL Injection"
        assert finding.severity == Severity.HIGH
        assert finding.status == FindingStatus.CONFIRMED
        assert finding.description == "SQL injection in login form"
        assert finding.evidence == "Error message reveals database structure"
        assert finding.discovered_by == "test_agent"
        assert finding.attack_surface_id is None
        assert finding.reproduction_steps == []
        assert finding.remediation == ""
        assert finding.validated_by is None

    def test_with_all_fields(self):
        """Test creating finding with all fields."""
        now = datetime.utcnow()
        finding = Finding(
            id="finding-id",
            title="XSS Vulnerability",
            severity=Severity.MEDIUM,
            status=FindingStatus.SUSPECTED,
            attack_surface_id="surface-id",
            description="Reflected XSS in search parameter",
            evidence="<script>alert(1)</script> executed",
            reproduction_steps=[
                "Navigate to /search",
                "Enter <script>alert(1)</script> in search box",
                "Submit form",
            ],
            remediation="Sanitize user input and encode output",
            discovered_at=now,
            discovered_by="xss_scanner",
            validated_by="manual_tester",
        )

        assert finding.attack_surface_id == "surface-id"
        assert len(finding.reproduction_steps) == 3
        assert finding.remediation == "Sanitize user input and encode output"
        assert finding.validated_by == "manual_tester"


class TestReconSummary:
    """Tests for ReconSummary model."""

    def test_default_creation(self):
        """Test creating recon summary with defaults."""
        summary = ReconSummary()

        assert summary.total_endpoints == 0
        assert summary.total_forms == 0
        assert summary.total_apis == 0
        assert summary.technologies_detected == []
        assert summary.authentication_mechanisms == []
        assert summary.notes == ""

    def test_with_data(self):
        """Test creating recon summary with data."""
        summary = ReconSummary(
            total_endpoints=25,
            total_forms=5,
            total_apis=10,
            technologies_detected=["React", "Express", "MongoDB"],
            authentication_mechanisms=["JWT", "Session Cookies"],
            notes="Application uses modern tech stack",
        )

        assert summary.total_endpoints == 25
        assert summary.total_forms == 5
        assert summary.total_apis == 10
        assert len(summary.technologies_detected) == 3
        assert len(summary.authentication_mechanisms) == 2
        assert "modern tech stack" in summary.notes


class TestFindingsDocumentSchema:
    """Tests for FindingsDocumentSchema model."""

    def test_minimal_creation(self):
        """Test creating document with minimal required fields."""
        doc = FindingsDocumentSchema(target="https://example.com")

        assert doc.version == "1.0"
        assert doc.target == "https://example.com"
        assert doc.recon_summary is None
        assert doc.attack_surfaces == []
        assert doc.findings == []
        assert doc.agents_invoked == []
        assert doc.total_steps_taken == 0
        assert isinstance(doc.created_at, datetime)
        assert isinstance(doc.updated_at, datetime)

    def test_with_full_data(self):
        """Test creating document with all data."""
        now = datetime.utcnow()

        recon_summary = ReconSummary(
            total_endpoints=10,
            technologies_detected=["nginx"],
        )

        surface = AttackSurface(
            id="surf-1",
            surface_type="endpoint",
            url="https://example.com/api",
            description="API endpoint",
            discovered_by="recon",
        )

        finding = Finding(
            id="find-1",
            title="IDOR",
            severity=Severity.HIGH,
            status=FindingStatus.CONFIRMED,
            description="Insecure Direct Object Reference",
            evidence="Can access other users' data",
            discovered_by="tester",
        )

        doc = FindingsDocumentSchema(
            version="1.0",
            target="https://example.com",
            created_at=now,
            updated_at=now,
            recon_summary=recon_summary,
            attack_surfaces=[surface],
            findings=[finding],
            agents_invoked=["recon", "tester"],
            total_steps_taken=42,
        )

        assert doc.target == "https://example.com"
        assert doc.recon_summary is not None
        assert len(doc.attack_surfaces) == 1
        assert len(doc.findings) == 1
        assert len(doc.agents_invoked) == 2
        assert doc.total_steps_taken == 42

    def test_model_validation(self):
        """Test that Pydantic validation works."""
        # Missing required field should raise ValidationError
        with pytest.raises(Exception):  # Pydantic ValidationError
            FindingsDocumentSchema()  # type: ignore
