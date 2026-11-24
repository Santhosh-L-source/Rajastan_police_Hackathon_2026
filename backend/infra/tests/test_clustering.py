"""Tests for infrastructure clustering."""

import pytest
from pathlib import Path
from datetime import datetime, timedelta

from backend.infra.models import Domain
from backend.infra.clustering import (
    cluster_by_shared_ip,
    cluster_by_name_servers,
    cluster_by_registrar_time,
    cluster_domains,
    calculate_domain_similarity
)
from backend.infra.parser import parse_infra_csv

SAMPLE_DATA = Path(__file__).parent.parent.parent.parent / "sample_data" / "case_001"

def test_domain_similarity():
    """Test typosquat detection."""
    assert calculate_domain_similarity("statebank.com", "statebnak.com") > 0.75
    assert calculate_domain_similarity("hdfc.com", "hdfcc.com") > 0.70
    assert calculate_domain_similarity("google.com", "amazon.com") < 0.50

def test_parse_infra_csv():
    """Test infrastructure CSV parsing."""
    csv_path = SAMPLE_DATA / "infrastructure.csv"
    if not csv_path.exists():
        pytest.skip("Infrastructure data not generated")

    domains = parse_infra_csv(csv_path)

    assert len(domains) > 0
    # Check required fields
    for domain in domains[:5]:
        assert domain.domain
        assert isinstance(domain.is_scam, bool)

def test_cluster_by_shared_ip():
    """Test IP-based clustering."""
    domains = [
        Domain(domain="a.com", ip="1.2.3.4"),
        Domain(domain="b.com", ip="1.2.3.4"),
        Domain(domain="c.com", ip="1.2.3.4"),
        Domain(domain="d.com", ip="5.6.7.8"),
    ]

    clusters = cluster_by_shared_ip(domains)

    assert len(clusters) == 1  # Only one cluster with 2+ domains
    assert len(clusters[0]) == 3  # a, b, c share IP

def test_cluster_by_name_servers():
    """Test name server clustering."""
    domains = [
        Domain(domain="a.com", name_servers=["ns1.example.com", "ns2.example.com"]),
        Domain(domain="b.com", name_servers=["ns1.example.com"]),
        Domain(domain="c.com", name_servers=["ns3.other.com"]),
    ]

    clusters = cluster_by_name_servers(domains)

    assert len(clusters) >= 1
    # Domains a and b should be in a cluster (share ns1)

def test_cluster_by_registrar_time():
    """Test registrar+time-window clustering."""
    base_time = datetime.now()

    domains = [
        Domain(domain="a.com", registrar="NAMECHEAP", creation_date=base_time),
        Domain(domain="b.com", registrar="NAMECHEAP", creation_date=base_time + timedelta(hours=1)),
        Domain(domain="c.com", registrar="NAMECHEAP", creation_date=base_time + timedelta(hours=100)),  # Too far
    ]

    clusters = cluster_by_registrar_time(domains, time_window_hours=48)

    assert len(clusters) >= 1
    # a and b should cluster (same registrar, within 48 hours)

def test_cluster_domains_full():
    """Integration test: full clustering pipeline."""
    csv_path = SAMPLE_DATA / "infrastructure.csv"
    if not csv_path.exists():
        pytest.skip("Infrastructure data not generated")

    domains = parse_infra_csv(csv_path)

    clusters = cluster_domains(domains)

    assert len(clusters) > 0  # Should find at least one cluster

    # Check cluster structure
    for cluster in clusters[:3]:
        assert cluster.cluster_id
        assert len(cluster.domains) >= 2
        assert cluster.score >= 0
        assert cluster.explanation

    # Print top cluster for debugging
    if clusters:
        top = clusters[0]
        print(f"\nTop cluster: {top.cluster_id}")
        print(f"  Score: {top.score:.1f}")
        print(f"  Domains: {[d.domain for d in top.domains[:5]]}")
        print(f"  Explanation: {top.explanation}")

def test_cluster_evaluation():
    """Test clustering accuracy against ground truth."""
    csv_path = SAMPLE_DATA / "infrastructure.csv"
    if not csv_path.exists():
        pytest.skip("Infrastructure data not generated")

    domains = parse_infra_csv(csv_path)
    clusters = cluster_domains(domains)

    # Count scam domains in top clusters
    scam_domains_clustered = set()
    for cluster in clusters[:5]:  # Top 5 clusters
        for domain in cluster.domains:
            if domain.is_scam:
                scam_domains_clustered.add(domain.domain)

    total_scam_domains = len([d for d in domains if d.is_scam])

    if total_scam_domains > 0:
        recall = len(scam_domains_clustered) / total_scam_domains
        print(f"\nClustering recall (top 5): {recall:.2%} ({len(scam_domains_clustered)}/{total_scam_domains} scam domains)")

        # At least 50% of scam domains should be in top 5 clusters
        assert recall >= 0.5, f"Clustering recall too low: {recall:.2%}"
