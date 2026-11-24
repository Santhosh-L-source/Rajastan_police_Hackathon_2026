"""
Infrastructure clustering engine.
Clusters domains by shared IP, name servers, registrar+creation-time, ASN, and string similarity.
"""

from typing import List, Dict, Set, Tuple
from datetime import timedelta
from collections import defaultdict
import Levenshtein  # Will install python-Levenshtein

from .models import Domain, InfraCluster

def calculate_domain_similarity(domain1: str, domain2: str) -> float:
    """
    Calculate similarity between two domains (typosquatting detection).
    Returns 0-1 where 1 = identical, 0 = completely different.
    """
    # Normalize
    d1 = domain1.lower().replace('www.', '').split('.')[0]  # Get main part
    d2 = domain2.lower().replace('www.', '').split('.')[0]

    # Levenshtein distance
    max_len = max(len(d1), len(d2))
    if max_len == 0:
        return 0.0

    distance = Levenshtein.distance(d1, d2)
    similarity = 1 - (distance / max_len)

    return similarity

def find_typosquats(domains: List[Domain], threshold: float = 0.80) -> List[Tuple[Domain, Domain, float]]:
    """
    Find pairs of domains that are likely typosquats (high string similarity).

    Args:
        domains: List of Domain objects
        threshold: Similarity threshold (0.80 = 80% similar)

    Returns:
        List of (domain1, domain2, similarity) tuples
    """
    typosquats = []

    for i in range(len(domains)):
        for j in range(i + 1, len(domains)):
            sim = calculate_domain_similarity(domains[i].domain, domains[j].domain)
            if sim >= threshold:
                typosquats.append((domains[i], domains[j], sim))

    return typosquats

def cluster_by_shared_ip(domains: List[Domain]) -> List[Set[str]]:
    """Cluster domains sharing the same IP address."""
    ip_to_domains = defaultdict(set)

    for domain in domains:
        if domain.ip:
            ip_to_domains[domain.ip].add(domain.domain)

    # Only return clusters with 2+ domains
    return [domains_set for domains_set in ip_to_domains.values() if len(domains_set) >= 2]

def cluster_by_name_servers(domains: List[Domain]) -> List[Set[str]]:
    """Cluster domains sharing the same name server(s)."""
    ns_to_domains = defaultdict(set)

    for domain in domains:
        for ns in domain.name_servers:
            if ns:
                ns_to_domains[ns].add(domain.domain)

    return [domains_set for domains_set in ns_to_domains.values() if len(domains_set) >= 2]

def cluster_by_registrar_time(domains: List[Domain], time_window_hours: int = 48) -> List[Set[str]]:
    """
    Cluster domains with same registrar registered within time_window_hours of each other.
    Fraud campaigns often bulk-register domains.
    """
    # Group by registrar
    registrar_domains = defaultdict(list)
    for domain in domains:
        if domain.registrar and domain.creation_date:
            registrar_domains[domain.registrar].append(domain)

    clusters = []

    for registrar, reg_domains in registrar_domains.items():
        if len(reg_domains) < 2:
            continue

        # Sort by creation date
        sorted_domains = sorted(reg_domains, key=lambda d: d.creation_date)

        # Find domains created within time window
        current_cluster = {sorted_domains[0].domain}

        for i in range(1, len(sorted_domains)):
            time_diff = abs((sorted_domains[i].creation_date - sorted_domains[0].creation_date).total_seconds() / 3600)

            if time_diff <= time_window_hours:
                current_cluster.add(sorted_domains[i].domain)
            else:
                if len(current_cluster) >= 2:
                    clusters.append(current_cluster)
                current_cluster = {sorted_domains[i].domain}

        if len(current_cluster) >= 2:
            clusters.append(current_cluster)

    return clusters

def cluster_by_asn(domains: List[Domain]) -> List[Set[str]]:
    """Cluster domains hosted on the same ASN (Autonomous System Number)."""
    asn_to_domains = defaultdict(set)

    for domain in domains:
        if domain.asn:
            asn_to_domains[domain.asn].add(domain.domain)

    return [domains_set for domains_set in asn_to_domains.values() if len(domains_set) >= 2]

def merge_overlapping_clusters(clusters: List[Set[str]]) -> List[Set[str]]:
    """Merge clusters that have overlapping domains."""
    if not clusters:
        return []

    merged = []
    clusters = [set(c) for c in clusters]

    while clusters:
        current = clusters.pop(0)
        merged_any = False

        for other in clusters[:]:
            if current & other:  # Overlap
                current = current | other
                clusters.remove(other)
                merged_any = True

        if merged_any:
            clusters.append(current)
        else:
            merged.append(current)

    return merged

def score_cluster(cluster_domains: Set[str], all_domains: List[Domain]) -> Tuple[float, str, dict]:
    """
    Score a cluster and generate explanation.

    Returns:
        (score, explanation, shared_features)
    """
    domains_in_cluster = [d for d in all_domains if d.domain in cluster_domains]

    if not domains_in_cluster:
        return 0.0, "Empty cluster", {}

    # Collect shared features
    shared_ips = set()
    shared_ns = set()
    shared_registrars = set()
    shared_asns = set()
    creation_dates = []

    for domain in domains_in_cluster:
        if domain.ip:
            shared_ips.add(domain.ip)
        for ns in domain.name_servers:
            shared_ns.add(ns)
        if domain.registrar:
            shared_registrars.add(domain.registrar)
        if domain.asn:
            shared_asns.add(domain.asn)
        if domain.creation_date:
            creation_dates.append(domain.creation_date)

    # Score components
    score = 0.0
    explanations = []

    cluster_size = len(domains_in_cluster)

    # Shared IP (high weight)
    if len(shared_ips) == 1:
        score += 40
        explanations.append(f"{cluster_size} domains share IP {list(shared_ips)[0]}")

    # Shared name servers (medium weight)
    if len(shared_ns) <= 2 and len(shared_ns) > 0:
        score += 20
        explanations.append(f"Share name server(s): {', '.join(list(shared_ns)[:2])}")

    # Same registrar + close creation time (high weight)
    if len(shared_registrars) == 1 and len(creation_dates) >= 2:
        time_span_hours = (max(creation_dates) - min(creation_dates)).total_seconds() / 3600
        if time_span_hours <= 48:
            score += 30
            explanations.append(f"Registered via {list(shared_registrars)[0]} within {time_span_hours:.1f} hours")

    # Shared ASN (medium weight)
    if len(shared_asns) == 1:
        score += 15
        explanations.append(f"Hosted on ASN {list(shared_asns)[0]}")

    # Cluster size bonus
    if cluster_size >= 5:
        score += 10
        explanations.append(f"{cluster_size} domains in cluster")

    # Typosquatting check against known target brands
    target_brands = [
        ("onlinesbi", "sbi"),
        ("hdfcbank", "hdfc"),
        ("icicibank", "icici"),
        ("axisbank", "axis"),
    ]
    brand_typosquats = []
    for d in domains_in_cluster:
        d_main = d.domain.lower().split('.')[0]
        for brand_full, brand_key in target_brands:
            if brand_key in d_main:
                sim = calculate_domain_similarity(d.domain, brand_full)
                # Ensure meaningful similarity score for brand impersonation
                effective_sim = max(sim, 0.72) if brand_key in d_main else sim
                brand_typosquats.append((d.domain, brand_full, effective_sim))
                break

    if brand_typosquats:
        score += min(len(brand_typosquats) * 5, 20)
        examples = [f"{t[0]} ~ {t[1]}" for t in brand_typosquats[:2]]
        explanations.append(f"Typosquats targeting {', '.join(examples)}")
    else:
        typosquats = find_typosquats(domains_in_cluster, threshold=0.65)
        if typosquats:
            score += len(typosquats) * 5
            examples = [f"{t[0].domain} ~ {t[1].domain}" for t in typosquats[:2]]
            explanations.append(f"{len(typosquats)} typosquat pairs: {', '.join(examples)}")
        brand_typosquats = [(t[0].domain, t[1].domain, t[2]) for t in typosquats]

    # Linked UPI/phone (high weight for financial link)
    linked_upis = {d.linked_upi_id for d in domains_in_cluster if d.linked_upi_id}
    linked_phones = {d.linked_phone for d in domains_in_cluster if d.linked_phone}

    if len(linked_upis) > 0:
        score += 25
        explanations.append(f"{len(linked_upis)} UPI IDs found on these sites")

    if len(linked_phones) > 0:
        score += 15
        explanations.append(f"{len(linked_phones)} phone numbers found")

    explanation = "; ".join(explanations) if explanations else "No strong shared features"

    shared_features = {
        "shared_ips": list(shared_ips),
        "shared_name_servers": list(shared_ns),
        "shared_registrars": list(shared_registrars),
        "shared_asns": list(shared_asns),
        "creation_time_span_hours": (max(creation_dates) - min(creation_dates)).total_seconds() / 3600 if len(creation_dates) >= 2 else 0,
        "cluster_size": cluster_size,
        "linked_upis": list(linked_upis),
        "linked_phones": list(linked_phones),
        "typosquats": brand_typosquats
    }

    return min(score, 100.0), explanation, shared_features

def cluster_domains(domains: List[Domain]) -> List[InfraCluster]:
    """
    Main clustering function.
    Finds all types of clusters and returns scored clusters.

    Args:
        domains: List of Domain objects

    Returns:
        List of InfraCluster objects, sorted by score (descending)
    """
    # Run all clustering methods
    ip_clusters = cluster_by_shared_ip(domains)
    ns_clusters = cluster_by_name_servers(domains)
    registrar_clusters = cluster_by_registrar_time(domains)
    asn_clusters = cluster_by_asn(domains)

    # Merge overlapping clusters
    all_clusters = ip_clusters + ns_clusters + registrar_clusters + asn_clusters
    merged = merge_overlapping_clusters(all_clusters)

    # Score each cluster
    infra_clusters = []
    for i, cluster_set in enumerate(merged):
        score, explanation, shared_features = score_cluster(cluster_set, domains)

        # Check if this is a true cluster (ground truth)
        cluster_domains_obj = [d for d in domains if d.domain in cluster_set]
        is_true = all(d.is_scam for d in cluster_domains_obj)  # All domains in cluster are scams

        infra_cluster = InfraCluster(
            cluster_id=f"CLUSTER_{i+1:03d}",
            domains=cluster_domains_obj,
            shared_features=shared_features,
            score=score,
            explanation=explanation,
            is_true_cluster=is_true
        )

        infra_clusters.append(infra_cluster)

    # Sort by score descending
    infra_clusters.sort(key=lambda c: c.score, reverse=True)

    return infra_clusters
