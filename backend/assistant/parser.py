"""
Natural language query parser and executor.
Rule-based intent detection with optional Claude API fallback.
"""

import re
import os
from typing import Dict, List, Optional, Tuple
from .intents import Intent, QueryResult

def parse_query_rule_based(query: str) -> Tuple[Intent, Dict]:
    """
    Parse query using rule-based patterns.

    Returns:
        (intent, extracted_params)
    """
    query_lower = query.lower().strip()

    # Trace money (check before list accounts to avoid "money" keyword conflict)
    if any(keyword in query_lower for keyword in ["trace money", "follow money", "money trail", "trace from"]):
        params = {}
        # Extract account/entity after "from"
        match = re.search(r"from ([a-z0-9_@.]+)", query_lower)
        if match:
            params["source"] = match.group(1)
        return Intent.TRACE_MONEY, params

    # List accounts
    if any(keyword in query_lower for keyword in ["list accounts", "show accounts", "which accounts", "list all"]):
        params = {}
        # Extract filters
        if "suspicious" in query_lower or "mule" in query_lower:
            params["filter"] = "suspicious"
        if "received from" in query_lower:
            # Extract entity after "from"
            match = re.search(r"received from ([^\s,]+)", query_lower)
            if match:
                params["received_from"] = match.group(1)
        return Intent.LIST_ACCOUNTS, params

    # Freeze priority
    if any(keyword in query_lower for keyword in ["freeze", "priority", "which accounts to freeze", "top accounts"]):
        params = {}
        # Extract number
        match = re.search(r"top (\d+)", query_lower)
        if match:
            params["top_n"] = int(match.group(1))
        else:
            params["top_n"] = 10
        return Intent.FREEZE_PRIORITY, params

    # Domain clusters
    if any(keyword in query_lower for keyword in ["domain cluster", "scam domains", "infrastructure cluster", "related domains"]):
        params = {}
        return Intent.DOMAIN_CLUSTER, params

    # Path between entities
    if any(keyword in query_lower for keyword in ["path between", "connect", "link between", "how are", "related to"]):
        params = {}
        # Extract two entities
        # Pattern: "path between X and Y" or "how are X and Y connected"
        match = re.search(r"(?:between|are) ([a-z0-9_@.-]+) (?:and|to) ([a-z0-9_@.-]+)", query_lower)
        if match:
            params["source"] = match.group(1)
            params["target"] = match.group(2)
        return Intent.PATH_BETWEEN, params

    # Cross-case links
    if any(keyword in query_lower for keyword in ["cross case", "other cases", "repeat", "multiple cases"]):
        params = {}
        # Extract entity
        words = query_lower.split()
        for word in words:
            if "@" in word or len(word) > 10:  # Likely account/UPI
                params["entity"] = word
                break
        return Intent.CROSS_CASE_LINKS, params

    # Find cross-links (financial <-> digital)
    if any(keyword in query_lower for keyword in ["cross link", "upi", "domain", "phishing site"]):
        params = {}
        # Extract UPI or domain
        if "@" in query_lower:
            match = re.search(r"([a-z0-9_.]+@[a-z0-9_.]+)", query_lower)
            if match:
                params["upi_id"] = match.group(1)
        if ".com" in query_lower or ".net" in query_lower:
            match = re.search(r"([a-z0-9-]+\.(com|net|org|in))", query_lower)
            if match:
                params["domain"] = match.group(1)
        return Intent.FIND_CROSS_LINKS, params

    # Get neighbors
    if any(keyword in query_lower for keyword in ["neighbors", "connected to", "linked to", "associated with"]):
        params = {}
        # Extract entity
        words = query_lower.split()
        for i, word in enumerate(words):
            if word in ["of", "to", "with"] and i + 1 < len(words):
                params["entity"] = words[i + 1]
                break
        return Intent.GET_NEIGHBORS, params

    # Show suspicious accounts
    if any(keyword in query_lower for keyword in ["suspicious", "mules", "high risk"]):
        params = {}
        match = re.search(r"(\d+)", query_lower)
        if match:
            params["top_n"] = int(match.group(1))
        return Intent.SHOW_SUSPICIOUS, params

    return Intent.UNKNOWN, {}

def parse_query_with_claude(query: str, api_key: str) -> Tuple[Intent, Dict]:
    """
    Parse query using Claude API (optional fallback).

    Returns:
        (intent, extracted_params)
    """
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)

        prompt = f"""You are a query parser for a fraud investigation system. Parse this natural language query into a structured intent.

Query: "{query}"

Available intents:
- LIST_ACCOUNTS: List bank accounts (optionally filtered)
- TRACE_MONEY: Trace money flow from a source
- FREEZE_PRIORITY: Get freeze priority rankings
- DOMAIN_CLUSTER: Show infrastructure clusters
- PATH_BETWEEN: Find path between two entities
- CROSS_CASE_LINKS: Find cross-case connections
- FIND_CROSS_LINKS: Find links between financial and digital entities
- GET_NEIGHBORS: Get neighbors of an entity
- SHOW_SUSPICIOUS: Show suspicious accounts

Respond with JSON only:
{{
    "intent": "INTENT_NAME",
    "params": {{"key": "value"}}
}}"""

        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text.strip()

        # Extract JSON
        import json
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]

        parsed = json.loads(response_text)

        intent = Intent[parsed["intent"]]
        params = parsed.get("params", {})

        return intent, params

    except Exception as e:
        # Fall back to rule-based
        return parse_query_rule_based(query)

def parse_query(query: str) -> Tuple[Intent, Dict]:
    """
    Main query parser. Uses Claude API if available, else rule-based.

    Args:
        query: Natural language query

    Returns:
        (intent, extracted_params)
    """
    # Check for Claude API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if api_key:
        try:
            return parse_query_with_claude(query, api_key)
        except:
            pass  # Fall back to rule-based

    return parse_query_rule_based(query)

def execute_query(
    query: str,
    case_data: Dict,
    unified_graph = None,
    db_session = None
) -> QueryResult:
    """
    Execute a natural language query against case data.

    Args:
        query: Natural language query
        case_data: Dict with keys: graph, trace_result, suspects, freeze_rankings, domains, clusters
        unified_graph: Optional UnifiedGraph instance
        db_session: Optional database session for cross-case queries

    Returns:
        QueryResult with grounded evidence
    """
    intent, params = parse_query(query)

    if intent == Intent.LIST_ACCOUNTS:
        return _execute_list_accounts(case_data, params)

    elif intent == Intent.TRACE_MONEY:
        return _execute_trace_money(case_data, params)

    elif intent == Intent.FREEZE_PRIORITY:
        return _execute_freeze_priority(case_data, params)

    elif intent == Intent.DOMAIN_CLUSTER:
        return _execute_domain_cluster(case_data, params)

    elif intent == Intent.PATH_BETWEEN:
        return _execute_path_between(case_data, unified_graph, params)

    elif intent == Intent.FIND_CROSS_LINKS:
        return _execute_find_cross_links(unified_graph, params)

    elif intent == Intent.GET_NEIGHBORS:
        return _execute_get_neighbors(unified_graph, params)

    elif intent == Intent.SHOW_SUSPICIOUS:
        return _execute_show_suspicious(case_data, params)

    elif intent == Intent.CROSS_CASE_LINKS:
        return _execute_cross_case_links(db_session, params)

    else:
        return QueryResult(
            intent=Intent.UNKNOWN,
            success=False,
            data=None,
            explanation="I don't understand that query. Try asking about accounts, money trails, freeze priority, or infrastructure clusters.",
            evidence=[]
        )

def _execute_list_accounts(case_data: Dict, params: Dict) -> QueryResult:
    """Execute LIST_ACCOUNTS intent."""
    suspects = case_data.get("suspects", [])

    # Apply filters
    if params.get("filter") == "suspicious":
        accounts = [s for s in suspects if s.get("risk_level") in ["HIGH", "MEDIUM"]]
    else:
        accounts = suspects

    # Filter by source if specified
    if "received_from" in params:
        source = params["received_from"]
        # Would need transaction data to filter
        # For now, return all
        pass

    data = accounts[:10]  # Limit to 10

    evidence = [
        {
            "type": "account",
            "account": acc["account"],
            "suspicion_score": acc.get("suspicion_score", 0),
            "risk_level": acc.get("risk_level", "LOW")
        }
        for acc in data
    ]

    explanation = f"Found {len(data)} accounts"
    if params.get("filter") == "suspicious":
        explanation += " (filtered to suspicious accounts)"

    return QueryResult(
        intent=Intent.LIST_ACCOUNTS,
        success=True,
        data=data,
        explanation=explanation,
        evidence=evidence
    )

def _execute_trace_money(case_data: Dict, params: Dict) -> QueryResult:
    """Execute TRACE_MONEY intent."""
    trace_result = case_data.get("trace_result")

    if not trace_result:
        return QueryResult(
            intent=Intent.TRACE_MONEY,
            success=False,
            data=None,
            explanation="No trace data available for this case",
            evidence=[]
        )

    source = params.get("source", trace_result.victim_account)

    traced_accounts = trace_result.traced_accounts

    # Get accounts and amounts
    trail = []
    for account, info in traced_accounts.items():
        trail.append({
            "account": account,
            "hop": info.get("hop", 0),
            "amount_traced": info.get("amount_traced", 0)
        })

    trail.sort(key=lambda x: x["hop"])

    evidence = [
        {
            "type": "traced_account",
            "account": t["account"],
            "hop": t["hop"],
            "amount": t["amount_traced"]
        }
        for t in trail[:10]
    ]

    explanation = f"Traced money from {source} through {len(trail)} accounts, total Rs.{trace_result.total_traced:,.0f}"

    return QueryResult(
        intent=Intent.TRACE_MONEY,
        success=True,
        data=trail[:10],
        explanation=explanation,
        evidence=evidence
    )

def _execute_freeze_priority(case_data: Dict, params: Dict) -> QueryResult:
    """Execute FREEZE_PRIORITY intent."""
    freeze_rankings = case_data.get("freeze_rankings", [])

    top_n = params.get("top_n", 10)
    top_accounts = freeze_rankings[:top_n]

    evidence = [
        {
            "type": "freeze_priority",
            "rank": i + 1,
            "account": acc["account"],
            "suspicion_score": acc.get("suspicion_score", 0),
            "estimated_recovery": acc.get("estimated_recovery", 0),
            "time_criticality": acc.get("time_criticality", 0)
        }
        for i, acc in enumerate(top_accounts)
    ]

    total_recovery = sum(acc.get("estimated_recovery", 0) for acc in top_accounts)

    explanation = f"Top {len(top_accounts)} accounts to freeze. Total estimated recovery: Rs.{total_recovery:,.0f}"

    return QueryResult(
        intent=Intent.FREEZE_PRIORITY,
        success=True,
        data=top_accounts,
        explanation=explanation,
        evidence=evidence
    )

def _execute_domain_cluster(case_data: Dict, params: Dict) -> QueryResult:
    """Execute DOMAIN_CLUSTER intent."""
    clusters = case_data.get("clusters", [])

    data = []
    for cluster in clusters[:5]:  # Top 5 clusters
        data.append({
            "cluster_id": cluster.cluster_id,
            "num_domains": len(cluster.domains),
            "score": cluster.score,
            "explanation": cluster.explanation,
            "domains": [d.domain for d in cluster.domains[:5]]
        })

    evidence = [
        {
            "type": "infrastructure_cluster",
            "cluster_id": c["cluster_id"],
            "score": c["score"],
            "num_domains": c["num_domains"]
        }
        for c in data
    ]

    explanation = f"Found {len(data)} infrastructure clusters"

    return QueryResult(
        intent=Intent.DOMAIN_CLUSTER,
        success=True,
        data=data,
        explanation=explanation,
        evidence=evidence
    )

def _execute_path_between(case_data: Dict, unified_graph, params: Dict) -> QueryResult:
    """Execute PATH_BETWEEN intent."""
    if not unified_graph:
        return QueryResult(
            intent=Intent.PATH_BETWEEN,
            success=False,
            data=None,
            explanation="Unified graph not available",
            evidence=[]
        )

    source = params.get("source")
    target = params.get("target")

    if not source or not target:
        return QueryResult(
            intent=Intent.PATH_BETWEEN,
            success=False,
            data=None,
            explanation="Please specify both source and target entities",
            evidence=[]
        )

    path = unified_graph.find_shortest_path(source, target)

    if not path:
        return QueryResult(
            intent=Intent.PATH_BETWEEN,
            success=True,
            data=[],
            explanation=f"No path found between {source} and {target}",
            evidence=[]
        )

    # Get edge types in path
    path_with_edges = []
    for i in range(len(path) - 1):
        edges = unified_graph.graph.get_edge_data(path[i], path[i + 1])
        edge_type = list(edges.values())[0].get("edge_type", "unknown") if edges else "unknown"
        path_with_edges.append({
            "from": path[i],
            "to": path[i + 1],
            "edge_type": edge_type
        })

    evidence = [
        {
            "type": "path_edge",
            "from": pe["from"],
            "to": pe["to"],
            "edge_type": pe["edge_type"]
        }
        for pe in path_with_edges
    ]

    explanation = f"Path from {source} to {target}: {len(path)} nodes, {len(path)-1} hops"

    return QueryResult(
        intent=Intent.PATH_BETWEEN,
        success=True,
        data=path_with_edges,
        explanation=explanation,
        evidence=evidence
    )

def _execute_find_cross_links(unified_graph, params: Dict) -> QueryResult:
    """Execute FIND_CROSS_LINKS intent."""
    if not unified_graph:
        return QueryResult(
            intent=Intent.FIND_CROSS_LINKS,
            success=False,
            data=None,
            explanation="Unified graph not available",
            evidence=[]
        )

    cross_links = unified_graph.find_cross_links()

    # Filter by params if specified
    if "upi_id" in params:
        cross_links = [cl for cl in cross_links if cl.get("upi_id") == params["upi_id"]]

    if "domain" in params:
        cross_links = [cl for cl in cross_links if params["domain"] in cl.get("domains", [])]

    evidence = [
        {
            "type": "cross_link",
            "link_type": cl["type"],
            **{k: v for k, v in cl.items() if k != "type"}
        }
        for cl in cross_links[:10]
    ]

    explanation = f"Found {len(cross_links)} cross-links between financial and digital entities"

    return QueryResult(
        intent=Intent.FIND_CROSS_LINKS,
        success=True,
        data=cross_links[:10],
        explanation=explanation,
        evidence=evidence
    )

def _execute_get_neighbors(unified_graph, params: Dict) -> QueryResult:
    """Execute GET_NEIGHBORS intent."""
    if not unified_graph:
        return QueryResult(
            intent=Intent.GET_NEIGHBORS,
            success=False,
            data=None,
            explanation="Unified graph not available",
            evidence=[]
        )

    entity = params.get("entity")
    if not entity:
        return QueryResult(
            intent=Intent.GET_NEIGHBORS,
            success=False,
            data=None,
            explanation="Please specify an entity",
            evidence=[]
        )

    neighbors = unified_graph.get_neighbors(entity)

    data = [
        {
            "neighbor": neighbor,
            "edge_type": edge_data.get("edge_type", "unknown")
        }
        for neighbor, edge_data in neighbors[:10]
    ]

    evidence = [
        {
            "type": "neighbor",
            "entity": entity,
            "neighbor": d["neighbor"],
            "edge_type": d["edge_type"]
        }
        for d in data
    ]

    explanation = f"Found {len(neighbors)} neighbors of {entity}"

    return QueryResult(
        intent=Intent.GET_NEIGHBORS,
        success=True,
        data=data,
        explanation=explanation,
        evidence=evidence
    )

def _execute_show_suspicious(case_data: Dict, params: Dict) -> QueryResult:
    """Execute SHOW_SUSPICIOUS intent."""
    suspects = case_data.get("suspects", [])

    # Filter to HIGH and MEDIUM risk
    suspicious = [s for s in suspects if s.get("risk_level") in ["HIGH", "MEDIUM"]]

    top_n = params.get("top_n", 10)
    data = suspicious[:top_n]

    evidence = [
        {
            "type": "suspicious_account",
            "account": acc["account"],
            "suspicion_score": acc.get("suspicion_score", 0),
            "risk_level": acc.get("risk_level"),
            "explanation": acc.get("explanation", "")
        }
        for acc in data
    ]

    explanation = f"Found {len(data)} suspicious accounts (HIGH/MEDIUM risk)"

    return QueryResult(
        intent=Intent.SHOW_SUSPICIOUS,
        success=True,
        data=data,
        explanation=explanation,
        evidence=evidence
    )

def _execute_cross_case_links(db_session, params: Dict) -> QueryResult:
    """Execute CROSS_CASE_LINKS intent."""
    if not db_session:
        return QueryResult(
            intent=Intent.CROSS_CASE_LINKS,
            success=False,
            data=None,
            explanation="Database not available for cross-case queries",
            evidence=[]
        )

    entity = params.get("entity")
    if not entity:
        return QueryResult(
            intent=Intent.CROSS_CASE_LINKS,
            success=False,
            data=None,
            explanation="Please specify an account or entity",
            evidence=[]
        )

    # This would query the database for linked cases
    # For now, return placeholder

    return QueryResult(
        intent=Intent.CROSS_CASE_LINKS,
        success=True,
        data=[],
        explanation=f"Cross-case linking for {entity} (database query needed)",
        evidence=[]
    )
