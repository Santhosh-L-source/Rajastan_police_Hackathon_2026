"""
Unified Investigation Graph: connects financial and digital infrastructure entities.

Node types:
- account: Bank account
- upi_id: UPI ID
- phone: Phone number
- domain: Scam domain
- ip: IP address
- name_server: DNS name server
- hosting: Hosting provider/ASN

Edge types:
- received_from / sent_to: Financial transfers
- collects_to: Domain collects payments to UPI/account
- listed_on: Phone/UPI listed on domain
- resolves_to: Domain resolves to IP
- hosted_by: IP hosted by ASN/provider
- same_ns: Domains share name server
"""

import networkx as nx
from typing import List, Dict, Set, Tuple, Optional
from datetime import datetime

class UnifiedGraph:
    """Unified graph connecting financial and digital entities."""

    def __init__(self):
        # Use MultiDiGraph to handle multiple edges between same nodes
        self.graph = nx.MultiDiGraph()

    def add_financial_data(self, transactions: List[Dict], accounts_info: Dict = None):
        """
        Add financial transactions to the graph.

        Args:
            transactions: List of normalized transactions
            accounts_info: Optional dict of account metadata
        """
        for txn in transactions:
            from_acc = txn["from_account"]
            to_acc = txn["to_account"]

            # Add account nodes
            if not self.graph.has_node(from_acc):
                self.graph.add_node(from_acc, node_type="account", label=from_acc)
            if not self.graph.has_node(to_acc):
                self.graph.add_node(to_acc, node_type="account", label=to_acc)

            # Add transfer edge
            self.graph.add_edge(
                from_acc,
                to_acc,
                edge_type="sent_to",
                amount=txn["amount"],
                timestamp=txn["timestamp"],
                mode=txn["mode"],
                txn_id=txn.get("txn_id", "")
            )

            # Extract UPI IDs from narration
            narration = txn.get("narration", "")
            if "@" in narration:
                # Try to extract UPI ID
                parts = narration.split("/")
                for part in parts:
                    if "@" in part:
                        upi_id = part.strip()
                        # Add UPI node
                        if not self.graph.has_node(upi_id):
                            self.graph.add_node(upi_id, node_type="upi_id", label=upi_id)

                        # Link UPI to accounts
                        self.graph.add_edge(upi_id, to_acc, edge_type="collects_to")

        # Add account metadata
        if accounts_info:
            for account, info in accounts_info.items():
                if self.graph.has_node(account):
                    self.graph.nodes[account].update(info)

    def add_infrastructure_data(self, domains: List, clusters: List = None):
        """
        Add digital infrastructure entities to the graph.

        Args:
            domains: List of Domain objects
            clusters: Optional list of InfraCluster objects
        """
        for domain_obj in domains:
            domain = domain_obj.domain

            # Add domain node
            if not self.graph.has_node(domain):
                self.graph.add_node(
                    domain,
                    node_type="domain",
                    label=domain,
                    is_scam=domain_obj.is_scam,
                    registrar=domain_obj.registrar,
                    creation_date=domain_obj.creation_date.isoformat() if domain_obj.creation_date else None
                )

            # Add IP node and edge
            if domain_obj.ip:
                ip = domain_obj.ip
                if not self.graph.has_node(ip):
                    self.graph.add_node(ip, node_type="ip", label=ip)
                self.graph.add_edge(domain, ip, edge_type="resolves_to")

            # Add name server nodes and edges
            for ns in domain_obj.name_servers:
                if ns:
                    if not self.graph.has_node(ns):
                        self.graph.add_node(ns, node_type="name_server", label=ns)
                    self.graph.add_edge(domain, ns, edge_type="same_ns")

            # Add hosting/ASN node
            if domain_obj.asn:
                asn = domain_obj.asn
                hosting_label = f"{domain_obj.hosting_provider} ({asn})" if domain_obj.hosting_provider else asn
                if not self.graph.has_node(asn):
                    self.graph.add_node(asn, node_type="hosting", label=hosting_label)

                if domain_obj.ip:
                    self.graph.add_edge(domain_obj.ip, asn, edge_type="hosted_by")

            # Cross-link: UPI ID on domain
            if domain_obj.linked_upi_id:
                upi_id = domain_obj.linked_upi_id
                if not self.graph.has_node(upi_id):
                    self.graph.add_node(upi_id, node_type="upi_id", label=upi_id)
                self.graph.add_edge(domain, upi_id, edge_type="collects_to")

            # Cross-link: Phone on domain
            if domain_obj.linked_phone:
                phone = domain_obj.linked_phone
                if not self.graph.has_node(phone):
                    self.graph.add_node(phone, node_type="phone", label=phone)
                self.graph.add_edge(domain, phone, edge_type="listed_on")

    def find_shortest_path(self, source: str, target: str, max_length: int = 10) -> Optional[List]:
        """
        Find shortest path between two entities.

        Args:
            source: Source node ID
            target: Target node ID
            max_length: Maximum path length

        Returns:
            List of nodes in path, or None if no path found
        """
        try:
            path = nx.shortest_path(self.graph, source, target)
            if len(path) <= max_length:
                return path
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            pass

        return None

    def get_neighbors(self, node: str, edge_type: Optional[str] = None, direction: str = "both") -> List[Tuple[str, Dict]]:
        """
        Get neighbors of a node.

        Args:
            node: Node ID
            edge_type: Filter by edge type (optional)
            direction: "in", "out", or "both"

        Returns:
            List of (neighbor_id, edge_data) tuples
        """
        if not self.graph.has_node(node):
            return []

        neighbors = []

        if direction in ["out", "both"]:
            for _, target, data in self.graph.out_edges(node, data=True):
                if edge_type is None or data.get("edge_type") == edge_type:
                    neighbors.append((target, data))

        if direction in ["in", "both"]:
            for source, _, data in self.graph.in_edges(node, data=True):
                if edge_type is None or data.get("edge_type") == edge_type:
                    neighbors.append((source, data))

        return neighbors

    def get_subgraph_around_node(self, node: str, max_hops: int = 2) -> nx.DiGraph:
        """
        Get subgraph centered around a node (k-hop neighborhood).

        Args:
            node: Center node ID
            max_hops: Number of hops to include

        Returns:
            NetworkX DiGraph of subgraph
        """
        if not self.graph.has_node(node):
            return nx.DiGraph()

        # BFS to find all nodes within max_hops
        visited = {node}
        current_layer = {node}

        for _ in range(max_hops):
            next_layer = set()
            for n in current_layer:
                # Get all neighbors
                neighbors = [target for _, target in self.graph.out_edges(n)]
                neighbors += [source for source, _ in self.graph.in_edges(n)]
                next_layer.update(neighbors)

            visited.update(next_layer)
            current_layer = next_layer

        # Extract subgraph
        return self.graph.subgraph(visited).copy()

    def get_nodes_by_type(self, node_type: str) -> List[str]:
        """Get all nodes of a specific type."""
        return [n for n, data in self.graph.nodes(data=True) if data.get("node_type") == node_type]

    def to_json(self, include_node_types: Optional[List[str]] = None) -> Dict:
        """
        Export graph to JSON format for frontend.

        Args:
            include_node_types: Optional list of node types to include (filter)

        Returns:
            Dict with nodes and edges arrays
        """
        nodes = []
        edges = []

        # Nodes
        for node_id, data in self.graph.nodes(data=True):
            node_type = data.get("node_type", "unknown")

            # Filter by type if specified
            if include_node_types and node_type not in include_node_types:
                continue

            nodes.append({
                "id": node_id,
                "label": data.get("label", node_id),
                "type": node_type,
                **{k: v for k, v in data.items() if k not in ["label", "node_type"]}
            })

        # Only include edges between included nodes
        included_node_ids = {n["id"] for n in nodes}

        # Edges
        for source, target, data in self.graph.edges(data=True):
            if source in included_node_ids and target in included_node_ids:
                edges.append({
                    "source": source,
                    "target": target,
                    "type": data.get("edge_type", "unknown"),
                    **{k: v for k, v in data.items() if k != "edge_type"}
                })

        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "num_nodes": len(nodes),
                "num_edges": len(edges),
                "node_types": {nt: len([n for n in nodes if n["type"] == nt])
                             for nt in set(n["type"] for n in nodes)}
            }
        }

    def find_cross_links(self) -> List[Dict]:
        """
        Find cross-links between financial and digital subgraphs.

        Returns:
            List of cross-link connections with metadata
        """
        cross_links = []

        # Find UPI IDs that connect to both accounts and domains
        upi_nodes = self.get_nodes_by_type("upi_id")

        for upi in upi_nodes:
            # Find connected accounts
            accounts = []
            for neighbor, data in self.get_neighbors(upi, edge_type="collects_to"):
                if self.graph.nodes[neighbor].get("node_type") == "account":
                    accounts.append(neighbor)

            # Find connected domains
            domains = []
            for source, data in self.get_neighbors(upi, direction="in"):
                if self.graph.nodes[source].get("node_type") == "domain":
                    domains.append(source)

            if accounts and domains:
                cross_links.append({
                    "type": "upi_cross_link",
                    "upi_id": upi,
                    "accounts": accounts,
                    "domains": domains,
                    "explanation": f"UPI {upi} collects from {len(domains)} domains to {len(accounts)} accounts"
                })

        # Find phone numbers that connect domains and might be associated with accounts
        phone_nodes = self.get_nodes_by_type("phone")

        for phone in phone_nodes:
            domains = []
            for source, data in self.get_neighbors(phone, direction="in"):
                if self.graph.nodes[source].get("node_type") == "domain":
                    domains.append(source)

            if len(domains) > 1:
                cross_links.append({
                    "type": "phone_cross_link",
                    "phone": phone,
                    "domains": domains,
                    "explanation": f"Phone {phone} listed on {len(domains)} domains"
                })

        return cross_links
