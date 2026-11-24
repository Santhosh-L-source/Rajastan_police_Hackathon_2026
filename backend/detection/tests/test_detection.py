"""Tests for mule detection features, ML, and scoring."""

import pytest
from backend.graph.builder import GraphBuilder, build_graph
from backend.detection.features import extract_features
from backend.detection.ml import detect_anomalies
from backend.detection.scoring import score_accounts


@pytest.fixture
def simple_graph():
    """Create a simple test graph."""
    # Use GraphBuilder instead of TransactionGraph
    transactions = [
        {"txn_id": "1", "from_account": "victim", "to_account": "mule1", "amount": 10000, "timestamp": "2024-01-01 10:00"},
        {"txn_id": "2", "from_account": "mule1", "to_account": "mule2", "amount": 10000, "timestamp": "2024-01-01 10:01"},
        {"txn_id": "3", "from_account": "mule2", "to_account": "exit", "amount": 10000, "timestamp": "2024-01-01 10:02"}
    ]
    graph = build_graph(transactions)
    return graph

    # Victim -> Mule1 -> Mule2 -> Exit
    graph.add_transaction("victim", "mule1", 10000, "2024-01-01 10:00")
    graph.add_transaction("mule1", "mule2", 10000, "2024-01-01 10:01")
    graph.add_transaction("mule2", "exit", 10000, "2024-01-01 10:02")

    return graph


def test_extract_features_basic(simple_graph):
    """Test basic feature extraction."""
    accounts = ["victim", "mule1", "mule2", "exit"]
    features = extract_features(simple_graph, accounts)

    assert len(features) == 4
    assert all("account" in f for f in features)
    assert all("pass_through_ratio" in f for f in features)
    assert all("fan_in" in f for f in features)
    assert all("fan_out" in f for f in features)


def test_pass_through_ratio():
    """Test pass-through ratio calculation."""
    transactions = [
        {"txn_id": "1", "from_account": "A", "to_account": "B", "amount": 1000, "timestamp": "2024-01-01 10:00"},
        {"txn_id": "2", "from_account": "B", "to_account": "C", "amount": 1000, "timestamp": "2024-01-01 10:01"}
    ]
    graph = build_graph(transactions)

    features = extract_features(graph, ["B"])
    assert len(features) == 1
    assert features[0]["pass_through_ratio"] == 1.0


def test_fan_in_fan_out():
    """Test fan-in and fan-out counting."""
    transactions = [
        {"txn_id": "3", "from_account": "A1", "to_account": "hub", "amount": 100, "timestamp": "2024-01-01 10:00"},
        {"txn_id": "4", "from_account": "A2", "to_account": "hub", "amount": 100, "timestamp": "2024-01-01 10:00"},
        {"txn_id": "5", "from_account": "hub", "to_account": "B1", "amount": 50, "timestamp": "2024-01-01 10:01"},
        {"txn_id": "6", "from_account": "hub", "to_account": "B2", "amount": 50, "timestamp": "2024-01-01 10:01"},
        {"txn_id": "7", "from_account": "hub", "to_account": "B3", "amount": 50, "timestamp": "2024-01-01 10:01"}
    ]
    graph = build_graph(transactions)

    features = extract_features(graph, ["hub"])
    assert features[0]["fan_in"] == 2
    assert features[0]["fan_out"] == 3


def test_velocity_calculation():
    """Test transaction velocity."""
    transactions = [
        {"txn_id": "8", "from_account": "A", "to_account": "B", "amount": 10000, "timestamp": "2024-01-01 10:00"},
        {"txn_id": "9", "from_account": "B", "to_account": "C", "amount": 10000, "timestamp": "2024-01-01 11:00"}
    ]
    graph = build_graph(transactions)

    features = extract_features(graph, ["B"])
    assert features[0]["velocity"] > 0


def test_cycle_detection():
    """Test cycle participation detection."""
    transactions = [
        {"txn_id": "10", "from_account": "A", "to_account": "B", "amount": 100, "timestamp": "2024-01-01 10:00"},
        {"txn_id": "11", "from_account": "B", "to_account": "C", "amount": 100, "timestamp": "2024-01-01 10:01"},
        {"txn_id": "12", "from_account": "C", "to_account": "A", "amount": 100, "timestamp": "2024-01-01 10:02"}
    ]
    graph = build_graph(transactions)

    features = extract_features(graph, ["A", "B", "C"])
    assert all(f["cycle_participation"] == 1.0 for f in features)


def test_ml_anomaly_detection(simple_graph):
    """Test ML-based anomaly detection."""
    accounts = ["victim", "mule1", "mule2", "exit"]
    features = extract_features(simple_graph, accounts)
    features_with_anomalies = detect_anomalies(features)

    assert len(features_with_anomalies) == 4
    assert all("anomaly_score" in f for f in features_with_anomalies)
    assert all("is_anomaly" in f for f in features_with_anomalies)
    assert all(0 <= f["anomaly_score"] <= 1 for f in features_with_anomalies)


def test_scoring_basic(simple_graph):
    """Test suspicion scoring."""
    accounts = ["victim", "mule1", "mule2", "exit"]
    features = extract_features(simple_graph, accounts)
    features = detect_anomalies(features)
    scored = score_accounts(features)

    assert len(scored) == 4
    assert all("suspicion_score" in s for s in scored)
    assert all("risk_level" in s for s in scored)
    assert all("explanation" in s for s in scored)
    assert all(0 <= s["suspicion_score"] <= 100 for s in scored)


def test_risk_level_thresholds():
    """Test risk level classification."""
    transactions = []
    # Create high-risk pattern: 100% pass-through with high fan-out
    for i in range(20):
        transactions.append({"txn_id": "13", "from_account": f"source{i}", "to_account": "hub", "amount": 1000, "timestamp": "2024-01-01 10:00"})
    for i in range(20):
        transactions.append({"txn_id": "14", "from_account": "hub", "to_account": f"dest{i}", "amount": 1000, "timestamp": "2024-01-01 10:01"})

    graph = build_graph(transactions)

    features = extract_features(graph, ["hub"])
    features = detect_anomalies(features)
    scored = score_accounts(features)

    # Hub should be high/medium risk
    assert scored[0]["risk_level"] in ["HIGH", "MEDIUM"]
    assert scored[0]["suspicion_score"] >= 50


def test_empty_features():
    """Test handling of empty feature list."""
    scored = score_accounts([])
    assert scored == []


def test_feature_extraction_no_transactions():
    """Test feature extraction with no transactions for account."""
    transactions = [
        {"txn_id": "15", "from_account": "A", "to_account": "B", "amount": 100, "timestamp": "2024-01-01 10:00"}
    ]
    graph = build_graph(transactions)

    # Try to extract features for non-existent account
    features = extract_features(graph, ["C"])
    assert len(features) == 1
    assert features[0]["account"] == "C"
    assert features[0]["total_inflow"] == 0
    assert features[0]["total_outflow"] == 0
