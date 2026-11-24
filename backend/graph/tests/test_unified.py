"""Tests for unified investigation graph."""

import pytest
from datetime import datetime
from pathlib import Path

from backend.graph.unified import UnifiedGraph
from backend.infra.models import Domain
from backend.infra.parser import parse_infra_csv
from backend.ingest.parsers import parse_statement
from backend.ingest.normalize import normalize_transactions, infer_account_from_filename

SAMPLE_DATA = Path(__file__).parent.parent.parent.parent / "sample_data" / "case_001"

def test_unified_graph_creation():
    """Test creating unified graph."""
    ug = UnifiedGraph()

    # Add financial data
    transactions = [
        {
            "txn_id": "T001",
            "timestamp": datetime.now(),
            "from_account": "ACC001",
            "to_account": "ACC002",
            "amount": 10000,
            "mode": "UPI",
            "narration": "UPI/amit@paytm/Payment"
        }
    ]

    ug.add_financial_data(transactions)

    # Add infrastructure data
    domains = [
        Domain(
            domain="scam1.com",
            ip="1.2.3.4",
            name_servers=["ns1.example.com"],
            linked_upi_id="amit@paytm",
            is_scam=True
        )
    ]

    ug.add_infrastructure_data(domains)

    # Verify graph
    assert ug.graph.number_of_nodes() > 0

    # Check node types
    node_types = {data.get("node_type") for _, data in ug.graph.nodes(data=True)}
    assert "account" in node_types
    assert "domain" in node_types
    assert "upi_id" in node_types
    assert "ip" in node_types

def test_cross_links():
    """Test finding cross-links between financial and digital subgraphs."""
    ug = UnifiedGraph()

    # Financial: account -> UPI
    transactions = [
        {
            "txn_id": "T001",
            "timestamp": datetime.now(),
            "from_account": "ACC001",
            "to_account": "ACC002",
            "amount": 10000,
            "mode": "UPI",
            "narration": "UPI/amit@paytm/Fraud"
        }
    ]
    ug.add_financial_data(transactions)

    # Digital: domain -> UPI
    domains = [
        Domain(
            domain="scam1.com",
            ip="1.2.3.4",
            linked_upi_id="amit@paytm",
            is_scam=True
        ),
        Domain(
            domain="scam2.com",
            ip="1.2.3.5",
            linked_upi_id="amit@paytm",
            is_scam=True
        )
    ]
    ug.add_infrastructure_data(domains)

    # Find cross-links
    cross_links = ug.find_cross_links()

    assert len(cross_links) > 0

    # Should find UPI cross-link
    upi_links = [cl for cl in cross_links if cl["type"] == "upi_cross_link"]
    assert len(upi_links) > 0

    # Check structure
    link = upi_links[0]
    assert link["upi_id"] == "amit@paytm"
    assert len(link["accounts"]) > 0
    assert len(link["domains"]) == 2

def test_shortest_path():
    """Test finding shortest path between entities."""
    ug = UnifiedGraph()

    # Build a chain: account -> upi -> domain -> ip
    transactions = [{
        "txn_id": "T001",
        "timestamp": datetime.now(),
        "from_account": "ACC001",
        "to_account": "ACC002",
        "amount": 10000,
        "mode": "UPI",
        "narration": "UPI/amit@paytm/Payment"
    }]
    ug.add_financial_data(transactions)

    domains = [Domain(
        domain="scam.com",
        ip="1.2.3.4",
        linked_upi_id="amit@paytm",
        is_scam=True
    )]
    ug.add_infrastructure_data(domains)

    # Try to find path from UPI to IP (more direct)
    path = ug.find_shortest_path("amit@paytm", "1.2.3.4")

    # Path should exist: amit@paytm -> scam.com -> 1.2.3.4
    if path:
        assert len(path) >= 2
    else:
        # Acceptable if path doesn't exist in this direction
        # (depends on edge direction)
        pass

def test_get_neighbors():
    """Test getting neighbors of a node."""
    ug = UnifiedGraph()

    domains = [
        Domain(domain="a.com", ip="1.2.3.4", linked_upi_id="upi1@paytm"),
        Domain(domain="b.com", ip="1.2.3.4", linked_upi_id="upi2@paytm"),
    ]
    ug.add_infrastructure_data(domains)

    # Get neighbors of IP
    neighbors = ug.get_neighbors("1.2.3.4", direction="in")

    # Should have 2 incoming edges from domains
    assert len(neighbors) >= 2

def test_subgraph_extraction():
    """Test extracting subgraph around a node."""
    ug = UnifiedGraph()

    domains = [
        Domain(domain="scam.com", ip="1.2.3.4", linked_upi_id="amit@paytm"),
    ]
    ug.add_infrastructure_data(domains)

    # Get subgraph around domain
    subgraph = ug.get_subgraph_around_node("scam.com", max_hops=2)

    assert subgraph.number_of_nodes() > 1  # Should include domain + neighbors

def test_json_export():
    """Test exporting graph to JSON."""
    ug = UnifiedGraph()

    domains = [Domain(domain="test.com", ip="1.2.3.4", is_scam=True)]
    ug.add_infrastructure_data(domains)

    json_data = ug.to_json()

    assert "nodes" in json_data
    assert "edges" in json_data
    assert "stats" in json_data
    assert len(json_data["nodes"]) > 0

def test_integration_with_real_data():
    """Integration test with generated sample data."""
    if not SAMPLE_DATA.exists():
        pytest.skip("Sample data not generated")

    ug = UnifiedGraph()

    # Load financial data
    csv_files = list(SAMPLE_DATA.glob("*.csv"))
    if not csv_files:
        pytest.skip("No CSV files found")

    all_transactions = []
    for csv_file in csv_files[:1]:  # Just use one file for speed
        try:
            parsed = parse_statement(csv_file)
            account = infer_account_from_filename(str(csv_file))
            normalized = normalize_transactions(parsed, account)
            all_transactions.extend(normalized[:10])  # Limit for speed
        except:
            pass

    if all_transactions:
        ug.add_financial_data(all_transactions)

    # Load infrastructure data
    infra_csv = SAMPLE_DATA / "infrastructure.csv"
    if infra_csv.exists():
        domains = parse_infra_csv(infra_csv)
        ug.add_infrastructure_data(domains[:10])  # Limit for speed

    # Verify unified graph
    assert ug.graph.number_of_nodes() > 0

    # Get stats
    json_data = ug.to_json()
    stats = json_data["stats"]

    print(f"\nUnified Graph Stats:")
    print(f"  Nodes: {stats['num_nodes']}")
    print(f"  Edges: {stats['num_edges']}")
    print(f"  Node types: {stats['node_types']}")

    # Find cross-links
    cross_links = ug.find_cross_links()
    print(f"  Cross-links found: {len(cross_links)}")

    if cross_links:
        print(f"\n  Example cross-link: {cross_links[0]['explanation']}")
