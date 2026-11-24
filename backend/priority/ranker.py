"""
Freeze priority ranking: which accounts to freeze first to maximize recovery.
"""

from typing import List, Dict, Tuple
import networkx as nx

def calculate_time_criticality(features: Dict) -> float:
    """
    Estimate likelihood funds will leave soon (0-1).
    Based on historical holding time and pass-through pattern.
    """
    holding_time = features.get("median_holding_time", 0)
    pass_through = features.get("pass_through_ratio", 0)

    # Shorter holding time = higher criticality
    if holding_time == 0:
        time_score = 0.5
    elif holding_time < 60:  # < 1 hour
        time_score = 1.0
    elif holding_time < 360:  # < 6 hours
        time_score = 0.8
    elif holding_time < 1440:  # < 24 hours
        time_score = 0.5
    else:
        time_score = 0.2

    # High pass-through = higher criticality
    pass_through_score = pass_through

    return (time_score + pass_through_score) / 2

def calculate_downstream_reach(account: str, graph: nx.MultiDiGraph) -> float:
    """
    Estimate how much more money flows through this account's downstream path.
    Uses sum of outflow amounts from descendants.
    """
    if not graph.has_node(account):
        return 0.0

    # Get all descendant nodes
    try:
        descendants = nx.descendants(graph, account)
    except:
        descendants = set()

    # Sum outflows from all descendants
    total_downstream = 0.0
    for node in descendants:
        out_edges = graph.out_edges(node, data=True)
        total_downstream += sum(e[2]["amount"] for e in out_edges)

    return total_downstream

def calculate_freeze_priority_score(features: Dict, graph: nx.MultiDiGraph = None) -> Dict:
    """
    Calculate freeze priority score for an account.

    Priority = f(remaining_balance, suspicion, time_criticality, downstream_reach)

    Returns dict with:
    - freeze_priority_score: 0-100
    - estimated_recovery: amount likely recoverable
    - time_criticality: 0-1
    - downstream_reach: amount
    """
    account = features["account"]
    remaining_balance = max(features.get("net_balance", 0), 0)
    suspicion = features.get("suspicion_score", 0) / 100.0  # Normalize to 0-1
    time_criticality = calculate_time_criticality(features)

    # Downstream reach (requires graph)
    if graph:
        downstream = calculate_downstream_reach(account, graph)
    else:
        downstream = 0.0

    # Estimated recoverable amount
    # Assumes we can recover balance + portion of downstream based on suspicion
    downstream_recoverable = downstream * suspicion * 0.5  # Conservative estimate
    estimated_recovery = remaining_balance + downstream_recoverable

    # Priority score (0-100)
    # Weights: recovery potential (40%), suspicion (30%), time criticality (20%), downstream (10%)
    recovery_score = min(estimated_recovery / 100000, 1.0) * 40  # Normalize by 100k
    suspicion_score = suspicion * 30
    time_score = time_criticality * 20
    downstream_score = min(downstream / 500000, 1.0) * 10  # Normalize by 500k

    priority_score = recovery_score + suspicion_score + time_score + downstream_score

    return {
        "account": account,
        "freeze_priority_score": priority_score,
        "estimated_recovery": estimated_recovery,
        "remaining_balance": remaining_balance,
        "time_criticality": time_criticality,
        "downstream_reach": downstream,
        "suspicion_score": features.get("suspicion_score", 0),
    }

def rank_freeze_priority(scored_accounts: List[Dict], graph: nx.MultiDiGraph = None) -> List[Dict]:
    """
    Rank accounts by freeze priority.

    Args:
        scored_accounts: List of accounts with suspicion scores
        graph: Optional graph for downstream reach calculation

    Returns:
        List of dicts with freeze priority info, sorted by priority (highest first)
    """
    freeze_rankings = []

    for features in scored_accounts:
        priority_info = calculate_freeze_priority_score(features, graph)

        # Merge with original features
        ranking = {**features, **priority_info}
        freeze_rankings.append(ranking)

    # Sort by freeze priority score descending
    freeze_rankings.sort(key=lambda x: x["freeze_priority_score"], reverse=True)

    return freeze_rankings

def calculate_recovery_curve(freeze_rankings: List[Dict]) -> List[Tuple[int, float]]:
    """
    Calculate cumulative recovery curve: (num_accounts_frozen, total_recovery).

    Args:
        freeze_rankings: Ranked list from rank_freeze_priority()

    Returns:
        List of (num_frozen, cumulative_recovery) tuples
    """
    curve = [(0, 0.0)]
    cumulative = 0.0

    for i, ranking in enumerate(freeze_rankings):
        cumulative += ranking["estimated_recovery"]
        curve.append((i + 1, cumulative))

    return curve
