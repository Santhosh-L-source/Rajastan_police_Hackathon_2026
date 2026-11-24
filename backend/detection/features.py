"""
Rule-based feature extraction for mule account detection.
"""

from typing import Dict, List
from datetime import datetime, timedelta
import numpy as np
from backend.graph.builder import GraphBuilder

def calculate_pass_through_ratio(account_info: Dict) -> float:
    """
    Pass-through ratio: outflow / inflow.
    Mules typically have 95-100% (money passes through quickly).
    """
    inflow = account_info["total_inflow"]
    outflow = account_info["total_outflow"]

    if inflow == 0:
        return 0.0

    return min(outflow / inflow, 1.0)

def calculate_holding_time(traced_info: Dict, graph: GraphBuilder) -> float:
    """
    Median holding time in minutes.
    Mules hold funds for minutes/hours, not days.
    """
    account = traced_info["account"]

    # Get all in and out edges for this account
    in_edges = list(graph.graph.in_edges(account, data=True))
    out_edges = list(graph.graph.out_edges(account, data=True))

    if not in_edges or not out_edges:
        return 0.0

    # Calculate holding time for each in-out pair
    holding_times = []
    for _, _, in_data in in_edges:
        in_time = in_data.get("timestamp")
        if not isinstance(in_time, datetime):
            continue

        # Find closest outflow after this inflow
        for _, _, out_data in out_edges:
            out_time = out_data.get("timestamp")
            if not isinstance(out_time, datetime):
                continue

            if out_time > in_time:
                delta_minutes = (out_time - in_time).total_seconds() / 60
                if delta_minutes < 24 * 60:  # Within 24 hours
                    holding_times.append(delta_minutes)

    if not holding_times:
        return 0.0

    return np.median(holding_times)

def calculate_velocity(account_info: Dict, traced_info: Dict) -> float:
    """
    Transaction velocity: total flow / time window (in hours).
    High velocity indicates rapid movement.
    """
    if "first_seen" not in traced_info or "last_out" not in account_info:
        return 0.0

    first_time = traced_info.get("first_seen")
    last_time = account_info.get("last_out")

    if not isinstance(first_time, datetime) or not isinstance(last_time, datetime):
        return 0.0

    time_window_hours = (last_time - first_time).total_seconds() / 3600
    if time_window_hours == 0:
        return 0.0

    total_flow = account_info["total_inflow"] + account_info["total_outflow"]
    return total_flow / time_window_hours

def calculate_round_number_ratio(graph: GraphBuilder, account: str) -> float:
    """
    Ratio of round-number transactions (amounts ending in 000).
    Fraud transactions often use round numbers.
    """
    out_edges = list(graph.graph.out_edges(account, data=True))

    if not out_edges:
        return 0.0

    round_count = 0
    for _, _, data in out_edges:
        amount = data["amount"]
        if amount % 1000 == 0 or amount % 5000 == 0:
            round_count += 1

    return round_count / len(out_edges)

def calculate_cash_out_exposure(graph: GraphBuilder, account: str) -> float:
    """
    Fraction of outflow to cash-out channels (ATM, crypto, external).
    """
    out_edges = list(graph.graph.out_edges(account, data=True))

    if not out_edges:
        return 0.0

    total_out = sum(e[2]["amount"] for e in out_edges)
    if total_out == 0:
        return 0.0

    cash_out = 0
    for _, target, data in out_edges:
        if any(x in target for x in ["ATM", "CRYPTO", "EXTERNAL"]):
            cash_out += data["amount"]

    return cash_out / total_out

def calculate_cycle_participation(graph: GraphBuilder, account: str) -> float:
    """
    Check if account is part of a cycle (round-tripping).
    Returns 1.0 if in a cycle, 0.0 otherwise.
    """
    try:
        # Check if there's a path from this account back to itself
        import networkx as nx
        if nx.has_path(graph.graph, account, account):
            return 1.0
    except:
        pass

    return 0.0

def is_dormant_then_active(traced_info: Dict, account_info: Dict) -> float:
    """
    Check if account was dormant then suddenly active.
    Mule accounts are often newly created or dormant.
    Returns 1.0 if pattern detected, 0.0 otherwise.
    """
    # Heuristic: very few transactions but high volume
    num_txns = account_info["num_incoming"] + account_info["num_outgoing"]
    total_flow = account_info["total_inflow"] + account_info["total_outflow"]

    if num_txns < 5 and total_flow > 50000:
        return 1.0

    return 0.0

def extract_account_features(account: str, graph: GraphBuilder, traced_info: Dict = None) -> Dict:
    """
    Extract all features for a single account.

    Returns dict with features:
    - pass_through_ratio: 0-1
    - median_holding_time: minutes
    - fan_in: count
    - fan_out: count
    - velocity: amount/hour
    - round_number_ratio: 0-1
    - cash_out_exposure: 0-1
    - cycle_participation: 0-1
    - dormant_then_active: 0-1
    - balance_ratio: remaining/total_in
    """
    account_info = graph.get_account_info(account)
    if account_info is None:
        return None

    # Use traced info if available, otherwise empty
    if traced_info is None:
        traced_info = {"account": account, "first_seen": account_info.get("first_in")}

    features = {
        "account": account,
        "pass_through_ratio": calculate_pass_through_ratio(account_info),
        "median_holding_time": calculate_holding_time(traced_info, graph),
        "fan_in": account_info["fan_in"],
        "fan_out": account_info["fan_out"],
        "velocity": calculate_velocity(account_info, traced_info),
        "round_number_ratio": calculate_round_number_ratio(graph, account),
        "cash_out_exposure": calculate_cash_out_exposure(graph, account),
        "cycle_participation": calculate_cycle_participation(graph, account),
        "dormant_then_active": is_dormant_then_active(traced_info, account_info),
        "balance_ratio": account_info["net_balance"] / account_info["total_inflow"] if account_info["total_inflow"] > 0 else 0,
        "total_inflow": account_info["total_inflow"],
        "total_outflow": account_info["total_outflow"],
        "net_balance": account_info["net_balance"],
    }

    return features

def extract_features(graph: GraphBuilder, traced_accounts: Dict = None) -> List[Dict]:
    """
    Extract features for all accounts in graph.

    Args:
        graph: GraphBuilder instance
        traced_accounts: Optional dict of traced account info (from tracer)

    Returns:
        List of feature dicts, one per account
    """
    features_list = []

    for account in graph.graph.nodes():
        traced_info = traced_accounts.get(account) if traced_accounts else None
        features = extract_account_features(account, graph, traced_info)

        if features:
            features_list.append(features)

    return features_list
