"""
Graph builder for transaction networks.
Creates directed weighted multigraph from normalized transactions.
"""

import networkx as nx
from typing import List, Dict
from datetime import datetime

class GraphBuilder:
    """Builds transaction graph from normalized transactions."""

    def __init__(self):
        # Use MultiDiGraph to handle multiple transfers between same accounts
        self.graph = nx.MultiDiGraph()
        self.transactions = []

    def add_transaction(self, txn: Dict):
        """Add a normalized transaction to the graph."""
        from_acc = txn["from_account"]
        to_acc = txn["to_account"]

        # Add nodes if not present
        if not self.graph.has_node(from_acc):
            self.graph.add_node(from_acc, account=from_acc, bank=txn.get("bank", "UNKNOWN"))
        if not self.graph.has_node(to_acc):
            self.graph.add_node(to_acc, account=to_acc, bank=txn.get("bank", "UNKNOWN"))

        # Add edge with transaction metadata
        self.graph.add_edge(
            from_acc,
            to_acc,
            txn_id=txn["txn_id"],
            amount=txn["amount"],
            timestamp=txn["timestamp"],
            mode=txn["mode"],
            narration=txn["narration"],
            bank=txn["bank"]
        )

        self.transactions.append(txn)

    def add_transactions(self, txns: List[Dict]):
        """Add multiple transactions."""
        for txn in txns:
            self.add_transaction(txn)

    def get_account_info(self, account: str) -> Dict:
        """Get summary info for an account."""
        if not self.graph.has_node(account):
            return None

        in_edges = list(self.graph.in_edges(account, data=True))
        out_edges = list(self.graph.out_edges(account, data=True))

        total_in = sum(e[2]["amount"] for e in in_edges)
        total_out = sum(e[2]["amount"] for e in out_edges)

        # Get timestamps for holding time calculation
        in_times = [e[2]["timestamp"] for e in in_edges if isinstance(e[2]["timestamp"], datetime)]
        out_times = [e[2]["timestamp"] for e in out_edges if isinstance(e[2]["timestamp"], datetime)]

        return {
            "account": account,
            "bank": self.graph.nodes[account].get("bank", "UNKNOWN"),
            "total_inflow": total_in,
            "total_outflow": total_out,
            "net_balance": total_in - total_out,
            "num_incoming": len(in_edges),
            "num_outgoing": len(out_edges),
            "fan_in": len(set(e[0] for e in in_edges)),
            "fan_out": len(set(e[1] for e in out_edges)),
            "first_in": min(in_times) if in_times else None,
            "last_out": max(out_times) if out_times else None,
        }

    def to_json(self) -> Dict:
        """Export graph to JSON format for frontend."""
        nodes = []
        for node in self.graph.nodes():
            info = self.get_account_info(node)
            nodes.append({
                "id": node,
                "account": node,
                "bank": info["bank"],
                "inflow": info["total_inflow"],
                "outflow": info["total_outflow"],
                "balance": info["net_balance"],
                "fan_in": info["fan_in"],
                "fan_out": info["fan_out"],
            })

        edges = []
        for u, v, data in self.graph.edges(data=True):
            edges.append({
                "source": u,
                "target": v,
                "amount": data["amount"],
                "timestamp": data["timestamp"].isoformat() if isinstance(data["timestamp"], datetime) else str(data["timestamp"]),
                "mode": data["mode"],
                "txn_id": data["txn_id"],
                "narration": data["narration"],
            })

        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "num_accounts": len(nodes),
                "num_transactions": len(edges),
                "total_flow": sum(e["amount"] for e in edges),
            }
        }

def build_graph(transactions: List[Dict]) -> GraphBuilder:
    """
    Build transaction graph from normalized transactions.

    Args:
        transactions: List of normalized transaction dicts

    Returns:
        GraphBuilder instance with populated graph
    """
    builder = GraphBuilder()
    builder.add_transactions(transactions)
    return builder
