"""Tests for database operations and cross-case linking."""

import pytest
import tempfile
import os
from pathlib import Path
from backend.db.operations import CaseDB


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    db = CaseDB(db_path=path)
    yield db

    # Cleanup - close database connection first
    db.session.close()
    db.engine.dispose()

    # Give Windows time to release the file
    import time
    time.sleep(0.1)

    if os.path.exists(path):
        try:
            os.unlink(path)
        except PermissionError:
            pass  # File still locked, will be cleaned up eventually


def test_create_case(temp_db):
    """Test case creation."""
    case = temp_db.create_case(
        case_id="test_001",
        title="Test Case",
        description="Test description",
        victim_account="ACC_VICTIM"
    )

    assert case.case_id == "test_001"
    assert case.title == "Test Case"
    assert case.victim_account == "ACC_VICTIM"
    assert case.created_at is not None


def test_get_case(temp_db):
    """Test retrieving a case."""
    temp_db.create_case("test_001", "Test", "Desc", "VICTIM")
    case = temp_db.get_case("test_001")

    assert case is not None
    assert case.case_id == "test_001"


def test_get_nonexistent_case(temp_db):
    """Test retrieving non-existent case."""
    case = temp_db.get_case("nonexistent")
    assert case is None


def test_list_cases(temp_db):
    """Test listing all cases."""
    temp_db.create_case("case_001", "Case 1", "Desc 1", "V1")
    temp_db.create_case("case_002", "Case 2", "Desc 2", "V2")

    cases = temp_db.list_cases()
    assert len(cases) == 2
    assert cases[0].case_id == "case_001"
    assert cases[1].case_id == "case_002"


def test_save_transactions(temp_db):
    """Test saving transactions."""
    temp_db.create_case("test_001", "Test", "Desc", "VICTIM")

    transactions = [
        {
            "from_account": "A",
            "to_account": "B",
            "amount": 1000,
            "timestamp": "2024-01-01 10:00"
        },
        {
            "from_account": "B",
            "to_account": "C",
            "amount": 500,
            "timestamp": "2024-01-01 11:00"
        }
    ]

    temp_db.save_transactions("test_001", transactions)

    # Verify saved
    case = temp_db.get_case("test_001")
    assert case is not None


def test_find_linked_cases_single_account(temp_db):
    """Test finding cases linked to a single account."""
    # Create two cases
    temp_db.create_case("case_001", "Case 1", "Desc", "V1")
    temp_db.create_case("case_002", "Case 2", "Desc", "V2")

    # Save transactions with shared account
    temp_db.save_transactions("case_001", [
        {"from_account": "A", "to_account": "SHARED", "amount": 1000, "timestamp": "2024-01-01 10:00"}
    ])
    temp_db.save_transactions("case_002", [
        {"from_account": "B", "to_account": "SHARED", "amount": 2000, "timestamp": "2024-01-01 11:00"}
    ])

    # Find linked cases
    linked = temp_db.find_linked_cases("SHARED")

    assert len(linked) == 2
    assert any(c["case_id"] == "case_001" for c in linked)
    assert any(c["case_id"] == "case_002" for c in linked)


def test_find_linked_cases_no_links(temp_db):
    """Test finding cases for account that doesn't exist."""
    linked = temp_db.find_linked_cases("NONEXISTENT")
    assert len(linked) == 0


def test_get_repeat_mules(temp_db):
    """Test identifying repeat mule accounts."""
    # Create three cases
    temp_db.create_case("case_001", "Case 1", "Desc", "V1")
    temp_db.create_case("case_002", "Case 2", "Desc", "V2")
    temp_db.create_case("case_003", "Case 3", "Desc", "V3")

    # MULE1 appears in all three cases
    temp_db.save_transactions("case_001", [
        {"from_account": "V1", "to_account": "MULE1", "amount": 1000, "timestamp": "2024-01-01 10:00"}
    ])
    temp_db.save_transactions("case_002", [
        {"from_account": "V2", "to_account": "MULE1", "amount": 2000, "timestamp": "2024-01-02 10:00"}
    ])
    temp_db.save_transactions("case_003", [
        {"from_account": "V3", "to_account": "MULE1", "amount": 3000, "timestamp": "2024-01-03 10:00"}
    ])

    # Get repeat mules (min 2 cases)
    repeat_mules = temp_db.get_repeat_mules(min_cases=2)

    assert len(repeat_mules) > 0
    mule1_entry = next((m for m in repeat_mules if m["account"] == "MULE1"), None)
    assert mule1_entry is not None
    assert mule1_entry["case_count"] == 3
    assert len(mule1_entry["cases"]) == 3


def test_get_repeat_mules_threshold(temp_db):
    """Test repeat mules with different thresholds."""
    temp_db.create_case("case_001", "Case 1", "Desc", "V1")
    temp_db.create_case("case_002", "Case 2", "Desc", "V2")

    # MULE_A in 2 cases, MULE_B in 1 case
    temp_db.save_transactions("case_001", [
        {"from_account": "V1", "to_account": "MULE_A", "amount": 1000, "timestamp": "2024-01-01 10:00"},
        {"from_account": "V1", "to_account": "MULE_B", "amount": 1000, "timestamp": "2024-01-01 10:00"}
    ])
    temp_db.save_transactions("case_002", [
        {"from_account": "V2", "to_account": "MULE_A", "amount": 2000, "timestamp": "2024-01-02 10:00"}
    ])

    # With min_cases=2, only MULE_A should appear
    repeat_mules = temp_db.get_repeat_mules(min_cases=2)
    accounts = [m["account"] for m in repeat_mules]
    assert "MULE_A" in accounts
    assert "MULE_B" not in accounts


def test_save_analysis(temp_db):
    """Test saving analysis results."""
    temp_db.create_case("test_001", "Test", "Desc", "VICTIM")

    graph_data = {"nodes": ["A", "B"], "edges": [["A", "B"]]}
    trace_data = {"traced_accounts": ["A", "B"], "total_traced": 1000}
    suspects = [{"account": "A", "suspicion_score": 70}]
    freeze_rankings = [{"account": "A", "freeze_priority_score": 60}]

    temp_db.save_analysis("test_001", graph_data, trace_data, suspects, freeze_rankings)

    # Verify saved
    case = temp_db.get_case("test_001")
    assert case.analyzed_at is not None
    assert case.graph_data == graph_data
    assert case.suspects_data == suspects


def test_cross_case_analysis(temp_db):
    """Test full cross-case analysis workflow."""
    # Create two fraud cases
    temp_db.create_case("fraud_001", "Fraud 1", "Phishing", "VICTIM1")
    temp_db.create_case("fraud_002", "Fraud 2", "Phishing", "VICTIM2")

    # Both cases use the same mule accounts
    shared_mule1 = "MULE_X_123"
    shared_mule2 = "MULE_Y_456"

    temp_db.save_transactions("fraud_001", [
        {"from_account": "VICTIM1", "to_account": shared_mule1, "amount": 50000, "timestamp": "2024-01-01 10:00"},
        {"from_account": shared_mule1, "to_account": shared_mule2, "amount": 45000, "timestamp": "2024-01-01 11:00"}
    ])

    temp_db.save_transactions("fraud_002", [
        {"from_account": "VICTIM2", "to_account": shared_mule1, "amount": 30000, "timestamp": "2024-01-05 14:00"},
        {"from_account": shared_mule1, "to_account": shared_mule2, "amount": 28000, "timestamp": "2024-01-05 15:00"}
    ])

    # Find linked cases for first mule
    linked1 = temp_db.find_linked_cases(shared_mule1)
    assert len(linked1) == 2

    # Find linked cases for second mule
    linked2 = temp_db.find_linked_cases(shared_mule2)
    assert len(linked2) == 2

    # Get repeat mules
    repeat = temp_db.get_repeat_mules(min_cases=2)
    assert len(repeat) >= 2
    assert any(m["account"] == shared_mule1 for m in repeat)
    assert any(m["account"] == shared_mule2 for m in repeat)
