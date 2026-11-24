"""
Freeze priority ranking: which accounts to freeze first to maximize recovery.

Rules
─────
  • Exclude victim accounts and cash-out exit nodes (ATM*, CRYPTO*, EXTERNAL)
    from the freeze list – they appear in a separate "cash-out points" note.
  • Cap total estimated recovery at victim_loss to prevent double-counting.
  • Add bank column extracted from graph node data.
"""

from typing import List, Dict, Tuple
import networkx as nx

EXIT_PREFIXES = ("ATM", "CRYPTO", "EXTERNAL")


def _is_exit_node(account: str) -> bool:
    return any(account.startswith(p) for p in EXIT_PREFIXES)


def _is_victim(account: str) -> bool:
    return account.startswith("VICTIM")


def calculate_time_criticality(features: Dict) -> float:
    holding_time = features.get("median_holding_time", 0)
    pass_through = features.get("pass_through_ratio", 0)

    if holding_time == 0:
        time_score = 0.5
    elif holding_time < 60:
        time_score = 1.0
    elif holding_time < 360:
        time_score = 0.8
    elif holding_time < 1440:
        time_score = 0.5
    else:
        time_score = 0.2

    return (time_score + pass_through) / 2


def calculate_downstream_reach(account: str, graph: nx.MultiDiGraph) -> float:
    if not graph.has_node(account):
        return 0.0
    try:
        descendants = nx.descendants(graph, account)
    except Exception:
        descendants = set()

    total_downstream = 0.0
    for node in descendants:
        out_edges = graph.out_edges(node, data=True)
        total_downstream += sum(e[2]["amount"] for e in out_edges)
    return total_downstream


def _infer_bank(account: str) -> str:
    """Guess a bank name from the account string for the demo."""
    a = account.upper()
    if "ICICI" in a:
        return "ICICI Bank"
    if "HDFC" in a:
        return "HDFC Bank"
    if "MULE_L1" in a:
        return "Paytm Payments Bank"
    if "SBI" in a:
        return "SBI"
    if "VICTIM" in a:
        return "Victim Bank"
    if a.startswith("ATM"):
        return "ATM Cash-out"
    if a.startswith("CRYPTO"):
        return "Crypto Exchange"
    return "Unknown"


def calculate_freeze_priority_score(features: Dict, graph: nx.MultiDiGraph = None) -> Dict:
    account = features["account"]
    remaining_balance = max(features.get("net_balance", 0), 0)
    suspicion = features.get("suspicion_score", 0) / 100.0
    time_criticality = calculate_time_criticality(features)

    if graph:
        downstream = calculate_downstream_reach(account, graph)
    else:
        downstream = 0.0

    downstream_recoverable = downstream * suspicion * 0.5
    estimated_recovery = remaining_balance + downstream_recoverable

    recovery_score = min(estimated_recovery / 100000, 1.0) * 40
    suspicion_score = suspicion * 30
    time_score = time_criticality * 20
    downstream_score = min(downstream / 500000, 1.0) * 10

    priority_score = recovery_score + suspicion_score + time_score + downstream_score

    return {
        "account": account,
        "bank": _infer_bank(account),
        "freeze_priority_score": priority_score,
        "estimated_recovery": estimated_recovery,
        "remaining_balance": remaining_balance,
        "time_criticality": time_criticality,
        "downstream_reach": downstream,
        "suspicion_score": features.get("suspicion_score", 0),
    }


def rank_freeze_priority(
    scored_accounts: List[Dict],
    graph: nx.MultiDiGraph = None,
    victim_loss: float = 500000.0,
) -> List[Dict]:
    """
    Rank accounts by freeze priority.

    • Excludes victim and exit nodes.
    • Caps cumulative estimated_recovery at victim_loss to avoid double-counting.
    """
    freeze_rankings = []

    for features in scored_accounts:
        account = features.get("account", "")
        if _is_victim(account) or _is_exit_node(account):
            continue

        priority_info = calculate_freeze_priority_score(features, graph)
        ranking = {**features, **priority_info}
        freeze_rankings.append(ranking)

    freeze_rankings.sort(key=lambda x: x["freeze_priority_score"], reverse=True)

    # ── Cap total recovery at victim_loss ──
    cumulative = 0.0
    for r in freeze_rankings:
        room = max(victim_loss - cumulative, 0)
        r["estimated_recovery"] = min(r["estimated_recovery"], room)
        cumulative += r["estimated_recovery"]

    return freeze_rankings


def calculate_recovery_curve(
    freeze_rankings: List[Dict],
    victim_loss: float = 500000.0,
) -> List[Tuple[int, float]]:
    """
    Cumulative recovery curve, capped at victim_loss.
    """
    curve = [(0, 0.0)]
    cumulative = 0.0

    for i, ranking in enumerate(freeze_rankings):
        cumulative += ranking["estimated_recovery"]
        cumulative = min(cumulative, victim_loss)
        curve.append((i + 1, cumulative))

    return curve
