"""Tests for AI assistant."""

import pytest
from backend.assistant.parser import parse_query_rule_based, execute_query
from backend.assistant.intents import Intent

def test_parse_list_accounts():
    """Test parsing list accounts queries."""
    intent, params = parse_query_rule_based("List all suspicious accounts")
    assert intent == Intent.LIST_ACCOUNTS
    assert params.get("filter") == "suspicious"

def test_parse_trace_money():
    """Test parsing trace money queries."""
    intent, params = parse_query_rule_based("Trace money from ACC001")
    assert intent == Intent.TRACE_MONEY
    assert params.get("source") == "acc001"

def test_parse_freeze_priority():
    """Test parsing freeze priority queries."""
    intent, params = parse_query_rule_based("Show me the top 5 accounts to freeze")
    assert intent == Intent.FREEZE_PRIORITY
    assert params.get("top_n") == 5

def test_parse_domain_cluster():
    """Test parsing domain cluster queries."""
    intent, params = parse_query_rule_based("Show scam domains")
    assert intent == Intent.DOMAIN_CLUSTER

def test_parse_path_between():
    """Test parsing path queries."""
    intent, params = parse_query_rule_based("What is the path between ACC001 and scam.com")
    assert intent == Intent.PATH_BETWEEN
    assert params.get("source") == "acc001"
    assert params.get("target") == "scam.com"

def test_execute_freeze_priority():
    """Test executing freeze priority query."""
    case_data = {
        "freeze_rankings": [
            {"account": "ACC001", "suspicion_score": 85, "estimated_recovery": 50000},
            {"account": "ACC002", "suspicion_score": 75, "estimated_recovery": 30000},
        ]
    }

    result = execute_query("Show top 2 accounts to freeze", case_data)

    assert result.success
    assert len(result.data) == 2
    assert len(result.evidence) == 2
    assert result.evidence[0]["type"] == "freeze_priority"

def test_execute_domain_cluster():
    """Test executing domain cluster query."""
    from backend.infra.models import Domain, InfraCluster

    clusters = [
        InfraCluster(
            cluster_id="C1",
            domains=[Domain(domain="a.com", is_scam=True), Domain(domain="b.com", is_scam=True)],
            shared_features={},
            score=90.0,
            explanation="Test cluster"
        )
    ]

    case_data = {"clusters": clusters}

    result = execute_query("Show infrastructure clusters", case_data)

    assert result.success
    assert len(result.data) > 0
    assert result.evidence[0]["type"] == "infrastructure_cluster"

def test_execute_list_accounts():
    """Test executing list accounts query."""
    case_data = {
        "suspects": [
            {"account": "ACC001", "suspicion_score": 85, "risk_level": "HIGH"},
            {"account": "ACC002", "suspicion_score": 65, "risk_level": "MEDIUM"},
            {"account": "ACC003", "suspicion_score": 20, "risk_level": "LOW"},
        ]
    }

    result = execute_query("List all suspicious accounts", case_data)

    assert result.success
    # Should filter to HIGH and MEDIUM
    assert len(result.data) == 2
