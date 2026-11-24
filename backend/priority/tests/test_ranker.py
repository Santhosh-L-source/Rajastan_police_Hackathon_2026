"""Tests for freeze priority ranking."""

import pytest
import networkx as nx
from backend.priority.ranker import (
    rank_freeze_priority,
    calculate_recovery_curve,
    calculate_time_criticality,
    calculate_downstream_reach
)


@pytest.fixture
def sample_suspects():
    """Create sample suspect list."""
    return [
        {
            "account": "mule1",
            "suspicion_score": 80.0,
            "total_inflow": 10000,
            "total_outflow": 8000,
            "net_balance": 2000,
            "risk_level": "HIGH"
        },
        {
            "account": "mule2",
            "suspicion_score": 60.0,
            "total_inflow": 5000,
            "total_outflow": 5000,
            "net_balance": 0,
            "risk_level": "MEDIUM"
        },
        {
            "account": "mule3",
            "suspicion_score": 40.0,
            "total_inflow": 1000,
            "total_outflow": 500,
            "net_balance": 500,
            "risk_level": "LOW"
        }
    ]


@pytest.fixture
def sample_graph():
    """Create sample transaction graph."""
    G = nx.DiGraph()
    G.add_edge("victim", "mule1", amount=10000)
    G.add_edge("mule1", "mule2", amount=8000)
    G.add_edge("mule2", "exit", amount=5000)
    return G


def test_rank_freeze_priority_basic(sample_suspects, sample_graph):
    """Test basic freeze priority ranking."""
    rankings = rank_freeze_priority(sample_suspects, sample_graph)

    assert len(rankings) == 3
    assert all("freeze_priority_score" in r for r in rankings)
    assert all("estimated_recovery" in r for r in rankings)
    assert all("time_criticality" in r for r in rankings)


def test_rank_freeze_priority_ordering(sample_suspects, sample_graph):
    """Test that high-risk accounts are prioritized."""
    rankings = rank_freeze_priority(sample_suspects, sample_graph)

    # First ranked should be mule1 (highest suspicion + balance)
    assert rankings[0]["account"] == "mule1"
    assert rankings[0]["freeze_priority_score"] > rankings[1]["freeze_priority_score"]


def test_downstream_reach():
    """Test downstream reach calculation."""
    G = nx.MultiDiGraph()
    G.add_edge("A", "B", amount=1000)
    G.add_edge("B", "C", amount=500)
    G.add_edge("B", "D", amount=500)

    # B has downstream reach
    reach = calculate_downstream_reach("B", G)
    assert reach >= 0


def test_calculate_time_criticality():
    """Test time criticality calculation."""
    # Test with low holding time (high criticality)
    features_fast = {
        "median_holding_time": 0.5,  # 30 minutes
        "pass_through_ratio": 0.9
    }
    criticality_fast = calculate_time_criticality(features_fast)

    # Test with long holding time (low criticality)
    features_slow = {
        "median_holding_time": 48,  # 2 days
        "pass_through_ratio": 0.3
    }
    criticality_slow = calculate_time_criticality(features_slow)

    assert 0 <= criticality_fast <= 1
    assert 0 <= criticality_slow <= 1
    assert criticality_fast > criticality_slow  # Fast movement is more critical


def test_calculate_recovery_curve(sample_suspects, sample_graph):
    """Test recovery curve calculation."""
    rankings = rank_freeze_priority(sample_suspects, sample_graph)
    curve = calculate_recovery_curve(rankings)

    assert len(curve) == len(rankings) + 1
    assert curve[0] == (0, 0.0)  # Starts at origin
    assert all(curve[i][1] <= curve[i+1][1] for i in range(len(curve)-1))  # Monotonic


def test_empty_suspects():
    """Test ranking with empty suspects list."""
    rankings = rank_freeze_priority([], nx.DiGraph())
    assert rankings == []

    curve = calculate_recovery_curve([])
    assert curve == [(0, 0.0)]


def test_recovery_curve_cumulative():
    """Test that recovery curve is cumulative."""
    suspects = [
        {"account": "A", "suspicion_score": 90, "total_inflow": 1000, "total_outflow": 0, "net_balance": 1000, "risk_level": "HIGH"},
        {"account": "B", "suspicion_score": 80, "total_inflow": 2000, "total_outflow": 0, "net_balance": 2000, "risk_level": "HIGH"},
    ]

    rankings = rank_freeze_priority(suspects, nx.DiGraph())
    curve = calculate_recovery_curve(rankings)

    # Each point should be cumulative
    assert curve[1][1] > 0  # First account
    assert curve[2][1] > curve[1][1]  # Cumulative


def test_priority_score_components():
    """Test that priority score considers multiple factors."""
    G = nx.DiGraph()
    G.add_edge("victim", "mule", amount=10000)
    G.add_edge("mule", "exit", amount=5000)

    high_suspect = {
        "account": "mule",
        "suspicion_score": 90,
        "total_inflow": 10000,
        "total_outflow": 5000,
        "net_balance": 5000,
        "risk_level": "HIGH"
    }

    low_suspect = {
        "account": "other",
        "suspicion_score": 30,
        "total_inflow": 100,
        "total_outflow": 100,
        "net_balance": 0,
        "risk_level": "LOW"
    }

    rankings = rank_freeze_priority([high_suspect, low_suspect], G)

    # High suspect should rank first
    assert rankings[0]["account"] == "mule"
    assert rankings[0]["freeze_priority_score"] > rankings[1]["freeze_priority_score"]


def test_downstream_reach_calculation():
    """Test downstream reach in priority calculation."""
    G = nx.DiGraph()
    G.add_edge("victim", "hub", amount=10000)
    G.add_edge("hub", "exit1", amount=3000)
    G.add_edge("hub", "exit2", amount=3000)
    G.add_edge("hub", "exit3", amount=3000)

    suspect = {
        "account": "hub",
        "suspicion_score": 70,
        "total_inflow": 10000,
        "total_outflow": 9000,
        "net_balance": 1000,
        "risk_level": "MEDIUM"
    }

    rankings = rank_freeze_priority([suspect], G)
    assert "downstream_reach" in rankings[0]
    assert rankings[0]["downstream_reach"] > 0
