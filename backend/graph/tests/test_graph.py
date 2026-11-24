"""Tests for graph engine."""

import pytest
from datetime import datetime, timedelta
from backend.graph.builder import build_graph
from backend.graph.tracer import trace_from_victim

def create_sample_transactions():
    """Create sample fraud scenario for testing."""
    base_time = datetime(2024, 1, 1, 10, 0)

    return [
        # Victim to mule1
        {
            "txn_id": "T001",
            "timestamp": base_time,
            "from_account": "VICTIM123",
            "to_account": "MULE001",
            "amount": 100000,
            "mode": "UPI",
            "bank": "SBI",
            "narration": "Fraud txn",
            "direction": "debit"
        },
        # Mule1 splits to mule2 and mule3
        {
            "txn_id": "T002",
            "timestamp": base_time + timedelta(minutes=5),
            "from_account": "MULE001",
            "to_account": "MULE002",
            "amount": 60000,
            "mode": "IMPS",
            "bank": "HDFC",
            "narration": "Transfer",
            "direction": "debit"
        },
        {
            "txn_id": "T003",
            "timestamp": base_time + timedelta(minutes=10),
            "from_account": "MULE001",
            "to_account": "MULE003",
            "amount": 39000,
            "mode": "NEFT",
            "bank": "ICICI",
            "narration": "Transfer",
            "direction": "debit"
        },
        # Mule2 to ATM
        {
            "txn_id": "T004",
            "timestamp": base_time + timedelta(hours=2),
            "from_account": "MULE002",
            "to_account": "ATM_WITHDRAWAL",
            "amount": 25000,
            "mode": "ATM",
            "bank": "HDFC",
            "narration": "ATM WD",
            "direction": "debit"
        },
        # Mule3 to crypto
        {
            "txn_id": "T005",
            "timestamp": base_time + timedelta(hours=3),
            "from_account": "MULE003",
            "to_account": "CRYPTO_EXCHANGE",
            "amount": 38000,
            "mode": "NEFT",
            "bank": "ICICI",
            "narration": "To exchange",
            "direction": "debit"
        },
    ]

def test_build_graph():
    """Test graph construction."""
    transactions = create_sample_transactions()
    builder = build_graph(transactions)

    # Check nodes created
    assert builder.graph.number_of_nodes() >= 5  # victim + 3 mules + exit nodes

    # Check edges
    assert builder.graph.number_of_edges() >= 5

    # Check victim info
    victim_info = builder.get_account_info("VICTIM123")
    assert victim_info is not None
    assert victim_info["total_outflow"] == 100000
    assert victim_info["num_outgoing"] == 1

def test_trace_from_victim():
    """Test money trail tracing."""
    transactions = create_sample_transactions()
    builder = build_graph(transactions)

    result = trace_from_victim(builder.graph, "VICTIM123")

    # Should trace all accounts
    assert "VICTIM123" in result.traced_accounts
    assert "MULE001" in result.traced_accounts
    assert "MULE002" in result.traced_accounts
    assert "MULE003" in result.traced_accounts

    # Check hops
    assert result.hops["VICTIM123"] == 0
    assert result.hops["MULE001"] == 1
    assert result.hops["MULE002"] == 2
    assert result.hops["MULE003"] == 2

    # Check traced amount close to original
    assert result.total_traced > 90000  # Some loss in proportional tracking

    # Check holding times calculated
    mule1 = result.traced_accounts["MULE001"]
    assert mule1["holding_time_minutes"] > 0

def test_account_info_extraction():
    """Test account info extraction."""
    transactions = create_sample_transactions()
    builder = build_graph(transactions)

    mule1_info = builder.get_account_info("MULE001")
    assert mule1_info["total_inflow"] == 100000
    assert mule1_info["total_outflow"] == 99000
    assert mule1_info["fan_in"] == 1
    assert mule1_info["fan_out"] == 2

def test_graph_json_export():
    """Test graph JSON export for frontend."""
    transactions = create_sample_transactions()
    builder = build_graph(transactions)

    graph_json = builder.to_json()

    assert "nodes" in graph_json
    assert "edges" in graph_json
    assert "stats" in graph_json

    assert len(graph_json["nodes"]) > 0
    assert len(graph_json["edges"]) > 0
    assert graph_json["stats"]["total_flow"] > 0

    # Check node structure
    node = graph_json["nodes"][0]
    assert "id" in node
    assert "inflow" in node
    assert "outflow" in node

    # Check edge structure
    edge = graph_json["edges"][0]
    assert "source" in edge
    assert "target" in edge
    assert "amount" in edge
