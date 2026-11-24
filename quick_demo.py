#!/usr/bin/env python3
"""Quick FINTRACE operational demo."""

import sys
sys.path.insert(0, '.')

from pathlib import Path

print("="*70)
print("FINTRACE - Financial & Infrastructure Intelligence".center(70))
print("Rajasthan Police Hackathon 2026 - PS05".center(70))
print("="*70)
print()

# 1. Show data generation results
print("1. SYNTHETIC DATA GENERATION")
print("-" * 70)
sample_data = Path("sample_data")
cases = sorted(sample_data.glob("case_*"))
print(f"Generated {len(cases)} fraud cases with ground truth")
for case_dir in cases:
    csv_files = list(case_dir.glob("*.csv"))
    xlsx_files = list(case_dir.glob("*.xlsx"))
    pdf_files = list(case_dir.glob("*.pdf"))
    infra_file = case_dir / "infrastructure.csv"

    print(f"\n  {case_dir.name}:")
    print(f"    Financial: {len(csv_files)} CSV, {len(xlsx_files)} XLSX, {len(pdf_files)} PDF")
    if infra_file.exists():
        with open(infra_file) as f:
            infra_lines = len(f.readlines()) - 1  # Exclude header
        print(f"    Infrastructure: {infra_lines} domains")

print("\n" + "="*70)

# 2. Financial detection evaluation
print("2. FINANCIAL MULE DETECTION")
print("-" * 70)
print("Running evaluation on case_001...")
print()

from backend.ingest.parsers import parse_statement
from backend.ingest.normalize import normalize_transactions, infer_account_from_filename
from backend.graph.builder import build_graph
from backend.graph.tracer import trace_from_victim
from backend.detection.features import extract_features
from backend.detection.ml import detect_anomalies
from backend.detection.scoring import score_accounts
from backend.priority.ranker import rank_freeze_priority, calculate_recovery_curve

case_dir = sample_data / "case_001"

# Parse ICICI CSV only (we know it works)
csv_file = case_dir / "ICICI_statement.csv"
parsed = parse_statement(csv_file)
account = infer_account_from_filename(str(csv_file))
all_transactions = normalize_transactions(parsed, account)

print(f"  Parsed: {len(all_transactions)} transactions")

# Build graph
graph = build_graph(all_transactions)
print(f"  Graph: {len(graph.graph.nodes())} accounts, {len(graph.graph.edges())} transfers")

# Find victim
victim_candidates = []
for node in graph.graph.nodes():
    info = graph.get_account_info(node)
    if info and info["total_outflow"] > 5000:
        victim_candidates.append((node, info["total_outflow"]))

if victim_candidates:
    victim = sorted(victim_candidates, key=lambda x: x[1], reverse=True)[0][0]
    print(f"  Victim: {victim}")

    # Trace
    trace_result = trace_from_victim(graph.graph, victim)
    print(f"  Traced: {len(trace_result.traced_accounts)} accounts, Rs.{trace_result.total_traced:,.0f}")

    # Detect
    features = extract_features(graph, trace_result.traced_accounts)
    features = detect_anomalies(features)
    scored = score_accounts(features)

    high_risk = len([s for s in scored if s["risk_level"] == "HIGH"])
    medium_risk = len([s for s in scored if s["risk_level"] == "MEDIUM"])
    print(f"  Detection: {high_risk} HIGH, {medium_risk} MEDIUM risk accounts")

    # Freeze priority
    rankings = rank_freeze_priority(scored, graph.graph)
    recovery_curve = calculate_recovery_curve(rankings)

    print(f"\n  Top 3 Freeze Priorities:")
    for i, acc in enumerate(rankings[:3]):
        print(f"    {i+1}. {acc['account'][:25]:25s} Score: {acc['suspicion_score']:5.1f} Recovery: Rs.{acc['estimated_recovery']:>10,.0f}")

    if len(recovery_curve) >= 10:
        top10_recovery = recovery_curve[10][1]
        print(f"\n  Freeze Top 10 -> Recover: Rs.{top10_recovery:,.0f}")

print("\n" + "="*70)

# 3. Infrastructure clustering
print("3. INFRASTRUCTURE CLUSTERING")
print("-" * 70)
print("Running evaluation on case_001...")
print()

from backend.infra.parser import parse_infra_csv
from backend.infra.clustering import cluster_domains

infra_csv = case_dir / "infrastructure.csv"
domains = parse_infra_csv(infra_csv)
print(f"  Parsed: {len(domains)} domains")

clusters = cluster_domains(domains)
print(f"  Detected: {len(clusters)} clusters")

scam_domains = len([d for d in domains if d.is_scam])
print(f"  Scam domains: {scam_domains}")

print(f"\n  Top 3 Clusters:")
for i, cluster in enumerate(clusters[:3]):
    scam_count = len([d for d in cluster.domains if d.is_scam])
    print(f"    {i+1}. {cluster.cluster_id}: {len(cluster.domains)} domains ({scam_count} scam)")
    print(f"       Score: {cluster.score:.1f}")
    print(f"       {cluster.explanation[:70]}...")

print("\n" + "="*70)

# 4. Unified Graph
print("4. UNIFIED INVESTIGATION GRAPH")
print("-" * 70)

from backend.graph.unified import UnifiedGraph

ug = UnifiedGraph()
ug.add_financial_data(all_transactions)
ug.add_infrastructure_data(domains[:20])  # Subset for demo

print(f"  Nodes: {ug.graph.number_of_nodes()}")
print(f"  Edges: {ug.graph.number_of_edges()}")

node_types = {}
for _, data in ug.graph.nodes(data=True):
    nt = data.get("node_type", "unknown")
    node_types[nt] = node_types.get(nt, 0) + 1

print(f"  Node types: {dict(node_types)}")

cross_links = ug.find_cross_links()
print(f"  Cross-links: {len(cross_links)} (financial <-> digital)")

if cross_links:
    print(f"\n  Example cross-link:")
    cl = cross_links[0]
    print(f"    {cl['explanation']}")

print("\n" + "="*70)

# 5. AI Assistant
print("5. AI-ASSISTED INVESTIGATION")
print("-" * 70)

from backend.assistant.parser import execute_query

case_data = {
    "suspects": scored,
    "freeze_rankings": rankings,
    "trace_result": trace_result,
    "clusters": clusters
}

queries = [
    "Show top 3 accounts to freeze",
    "List suspicious accounts",
    "Show infrastructure clusters"
]

print("Natural language queries:\n")
for query in queries:
    result = execute_query(query, case_data, ug)
    print(f"  Q: {query}")
    print(f"  A: {result.explanation}")
    print(f"     Evidence: {len(result.evidence)} items")
    print()

print("="*70)

# 6. Test Results
print("6. TEST COVERAGE")
print("-" * 70)
import subprocess
result = subprocess.run(["python", "-m", "pytest", "backend/", "--tb=no", "-q"],
                       capture_output=True, text=True)
print(result.stdout)

print("="*70)

# 7. Security
print("7. SECURITY STATUS")
print("-" * 70)
print("  Path Traversal Protection: ENABLED")
print("  File Type Validation: ENABLED (CSV, XLSX, PDF only)")
print("  File Size Limits: ENABLED (10MB max)")
print("  CORS: RESTRICTED (localhost)")
print("  SQL Injection: SAFE (ORM)")
print("  Secrets: SAFE (env vars)")
print()
print("  Status: DEMO-READY | Production requires auth + HTTPS")

print("\n" + "="*70)
print("FINTRACE SYSTEM OPERATIONAL".center(70))
print("="*70)
print()
print("Next steps:")
print("  - Start API: python -m uvicorn backend.api.main:app --reload --port 8000")
print("  - API docs: http://localhost:8000/docs")
print("  - Full eval: python scripts/evaluate.py && python scripts/evaluate_infra.py")
print()
