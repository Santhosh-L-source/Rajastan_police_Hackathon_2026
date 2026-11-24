"""
Money-trail tracer using proportional FIFO (poison-spreading) model.
"""

from typing import Dict, List, Set, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import networkx as nx

@dataclass
class TraceResult:
    """Result of tracing from victim."""
    traced_accounts: Dict[str, Dict]  # account -> trace info
    traced_edges: List[Dict]  # edges in the trail
    hops: Dict[str, int]  # account -> hop number from victim
    total_traced: float  # total amount traced
    victim_account: str

class MoneyTracer:
    """
    Traces money flow from victim using proportional FIFO model.

    Assumption: Money is fungible. When account receives from multiple sources
    and sends to multiple destinations, we proportionally attribute outflows
    based on inflow sources (FIFO-like poison spreading).
    """

    def __init__(self, graph: nx.MultiDiGraph):
        self.graph = graph

    def trace_from_victim(self, victim_account: str, fraud_txn_ids: List[str] = None) -> TraceResult:
        """
        Trace money flow starting from victim account.

        Args:
            victim_account: Starting account
            fraud_txn_ids: Optional list of specific fraud transaction IDs to trace
                          If None, traces all outflows from victim

        Returns:
            TraceResult with traced accounts, edges, and metadata
        """
        if not self.graph.has_node(victim_account):
            return TraceResult({}, [], {}, 0.0, victim_account)

        # Get initial fraud outflows from victim
        victim_outflows = list(self.graph.out_edges(victim_account, data=True))

        if fraud_txn_ids:
            victim_outflows = [e for e in victim_outflows if e[2]["txn_id"] in fraud_txn_ids]

        if not victim_outflows:
            return TraceResult({}, [], {}, 0.0, victim_account)

        # Initialize tracing
        traced_accounts = {victim_account: {
            "account": victim_account,
            "hop": 0,
            "amount_traced": sum(e[2]["amount"] for e in victim_outflows),
            "source": "VICTIM",
            "first_seen": min(e[2]["timestamp"] for e in victim_outflows if isinstance(e[2]["timestamp"], datetime)),
        }}

        traced_edges = []
        hops = {victim_account: 0}

        # BFS-style tracing with proportional flow
        # Queue: (account, poisoned_amount, hop_number, entry_time)
        queue = []
        for _, target, data in victim_outflows:
            queue.append((target, data["amount"], 1, data["timestamp"]))
            traced_edges.append({
                "source": victim_account,
                "target": target,
                "amount": data["amount"],
                "traced_amount": data["amount"],
                "timestamp": data["timestamp"],
                "hop": 1,
                "txn_id": data["txn_id"],
            })

        visited = {victim_account}

        while queue:
            current_account, poisoned_amount, hop, entry_time = queue.pop(0)

            if current_account in visited:
                # Already traced, add to poisoned amount
                if current_account in traced_accounts:
                    traced_accounts[current_account]["amount_traced"] += poisoned_amount
                continue

            visited.add(current_account)
            hops[current_account] = hop

            # Get all inflows and outflows for this account
            inflows = list(self.graph.in_edges(current_account, data=True))
            outflows = list(self.graph.out_edges(current_account, data=True))

            # Calculate total inflow to this account
            total_inflow = sum(e[2]["amount"] for e in inflows)
            if total_inflow == 0:
                continue

            # Proportion of this account's funds that are poisoned
            poison_ratio = min(poisoned_amount / total_inflow, 1.0)

            # Calculate holding time
            in_times = [e[2]["timestamp"] for e in inflows if isinstance(e[2]["timestamp"], datetime)]
            out_times = [e[2]["timestamp"] for e in outflows if isinstance(e[2]["timestamp"], datetime)]

            avg_in_time = min(in_times) if in_times else entry_time
            avg_out_time = max(out_times) if out_times else entry_time

            if isinstance(avg_in_time, datetime) and isinstance(avg_out_time, datetime):
                holding_time = (avg_out_time - avg_in_time).total_seconds() / 60  # minutes
            else:
                holding_time = 0

            traced_accounts[current_account] = {
                "account": current_account,
                "hop": hop,
                "amount_traced": poisoned_amount,
                "poison_ratio": poison_ratio,
                "total_inflow": total_inflow,
                "total_outflow": sum(e[2]["amount"] for e in outflows),
                "holding_time_minutes": holding_time,
                "first_seen": entry_time,
                "num_incoming": len(inflows),
                "num_outgoing": len(outflows),
            }

            # Trace outflows proportionally
            for _, target, data in outflows:
                if target == "EXTERNAL" or target.startswith("ATM") or target.startswith("CRYPTO"):
                    # Exit node (cash out or external)
                    traced_edges.append({
                        "source": current_account,
                        "target": target,
                        "amount": data["amount"],
                        "traced_amount": data["amount"] * poison_ratio,
                        "timestamp": data["timestamp"],
                        "hop": hop + 1,
                        "txn_id": data["txn_id"],
                        "exit": True,
                    })
                    continue

                # Proportional poisoned amount for this outflow
                traced_outflow = data["amount"] * poison_ratio

                traced_edges.append({
                    "source": current_account,
                    "target": target,
                    "amount": data["amount"],
                    "traced_amount": traced_outflow,
                    "timestamp": data["timestamp"],
                    "hop": hop + 1,
                    "txn_id": data["txn_id"],
                })

                # Continue tracing if significant amount
                if traced_outflow > 100:  # Threshold to avoid tracing noise
                    queue.append((target, traced_outflow, hop + 1, data["timestamp"]))

        total_traced = sum(acc["amount_traced"] for acc in traced_accounts.values())

        return TraceResult(
            traced_accounts=traced_accounts,
            traced_edges=traced_edges,
            hops=hops,
            total_traced=total_traced,
            victim_account=victim_account
        )

def trace_from_victim(graph: nx.MultiDiGraph, victim_account: str,
                     fraud_txn_ids: List[str] = None) -> TraceResult:
    """
    Convenience function to trace from victim.

    Args:
        graph: Transaction graph
        victim_account: Victim account ID
        fraud_txn_ids: Optional specific fraud transactions to trace

    Returns:
        TraceResult
    """
    tracer = MoneyTracer(graph)
    return tracer.trace_from_victim(victim_account, fraud_txn_ids)
