"""Tests for PDF report generation."""

import pytest
import tempfile
import os
from pathlib import Path
from backend.reports.generator import generate_report
from backend.db.models import Case


@pytest.fixture
def sample_case():
    """Create a sample case for testing."""
    case = Case(
        case_id="test_001",
        title="Test Fraud Case",
        description="Sample fraud investigation",
        victim_account="VICTIM_ACC_123"
    )
    case.analyzed_at = "2024-01-01 12:00:00"
    case.graph_data = {
        "nodes": [
            {"id": "VICTIM_ACC_123", "type": "account"},
            {"id": "MULE_1", "type": "account"},
            {"id": "EXIT", "type": "account"}
        ],
        "edges": [
            {"source": "VICTIM_ACC_123", "target": "MULE_1", "amount": 10000},
            {"source": "MULE_1", "target": "EXIT", "amount": 9000}
        ]
    }
    case.suspects_data = [
        {
            "account": "MULE_1",
            "suspicion_score": 75.0,
            "risk_level": "HIGH",
            "explanation": "High pass-through ratio with rapid movement"
        }
    ]
    case.freeze_rankings = [
        {
            "account": "MULE_1",
            "freeze_priority_score": 80.0,
            "estimated_recovery": 9000.0,
            "suspicion_score": 75.0
        }
    ]
    return case


def test_generate_report_creates_file(sample_case):
    """Test that report generation creates a PDF file."""
    report_path = generate_report(sample_case)

    assert report_path is not None
    assert os.path.exists(report_path)
    assert report_path.endswith(".pdf")

    # Cleanup
    if os.path.exists(report_path):
        os.unlink(report_path)


def test_generate_report_with_no_analysis():
    """Test report generation for case without analysis."""
    case = Case(
        case_id="test_002",
        title="Unanalyzed Case",
        description="No analysis yet",
        victim_account="VICTIM"
    )
    case.analyzed_at = None
    case.graph_data = None
    case.suspects_data = None
    case.freeze_rankings = None

    report_path = generate_report(case)

    assert report_path is not None
    assert os.path.exists(report_path)

    # Cleanup
    if os.path.exists(report_path):
        os.unlink(report_path)


def test_report_contains_case_info(sample_case):
    """Test that generated report contains case information."""
    report_path = generate_report(sample_case)

    # PDF exists
    assert os.path.exists(report_path)

    # Has content (file size > 0)
    assert os.path.getsize(report_path) > 0

    # Cleanup
    if os.path.exists(report_path):
        os.unlink(report_path)


def test_report_with_suspects(sample_case):
    """Test report generation with suspect data."""
    report_path = generate_report(sample_case)

    assert os.path.exists(report_path)
    assert os.path.getsize(report_path) > 1000  # Has substantial content

    # Cleanup
    if os.path.exists(report_path):
        os.unlink(report_path)


def test_report_with_freeze_rankings(sample_case):
    """Test report generation with freeze priority data."""
    sample_case.freeze_rankings = [
        {"account": "MULE_1", "freeze_priority_score": 90, "estimated_recovery": 50000},
        {"account": "MULE_2", "freeze_priority_score": 80, "estimated_recovery": 30000},
    ]

    report_path = generate_report(sample_case)

    assert os.path.exists(report_path)
    assert os.path.getsize(report_path) > 1000

    # Cleanup
    if os.path.exists(report_path):
        os.unlink(report_path)


def test_report_filename_format(sample_case):
    """Test that report filename follows expected format."""
    report_path = generate_report(sample_case)

    filename = os.path.basename(report_path)
    assert sample_case.case_id in filename
    assert filename.endswith(".pdf")

    # Cleanup
    if os.path.exists(report_path):
        os.unlink(report_path)


def test_multiple_reports_different_cases():
    """Test generating reports for multiple cases."""
    case1 = Case(case_id="case_001", title="Case 1", description="Desc 1", victim_account="V1")
    case1.analyzed_at = "2024-01-01"

    case2 = Case(case_id="case_002", title="Case 2", description="Desc 2", victim_account="V2")
    case2.analyzed_at = "2024-01-02"

    report1 = generate_report(case1)
    report2 = generate_report(case2)

    assert report1 != report2
    assert os.path.exists(report1)
    assert os.path.exists(report2)

    # Cleanup
    for path in [report1, report2]:
        if os.path.exists(path):
            os.unlink(path)


def test_report_overwrites_existing():
    """Test that regenerating a report overwrites the old one."""
    case = Case(case_id="test_overwrite", title="Test", description="Desc", victim_account="V")
    case.analyzed_at = "2024-01-01"

    # Generate first report
    report1 = generate_report(case)
    mtime1 = os.path.getmtime(report1)

    # Generate second report (should overwrite)
    report2 = generate_report(case)

    assert report1 == report2
    assert os.path.exists(report2)

    # Cleanup
    if os.path.exists(report2):
        os.unlink(report2)
