#!/usr/bin/env python3
"""
Evaluate mule detection against ground truth.
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.ingest.parsers import parse_statement
from backend.ingest.normalize import normalize_transactions, infer_account_from_filename
from backend.graph.builder import build_graph
from backend.graph.tracer import trace_from_victim
from backend.detection.features import extract_features
from backend.detection.ml import detect_anomalies
from backend.detection.scoring import score_accounts

def normalize_account_name(account: str) -> str:
    """Extract raw account number from prefixed account names."""
    # Remove bank prefixes: SBI_ACCOUNT_, ICICI_ACCOUNT_, etc.
    for prefix in ["SBI_ACCOUNT_", "ICICI_ACCOUNT_", "HDFC_ACCOUNT_", "AXIS_ACCOUNT_"]:
        if account.startswith(prefix):
            return account[len(prefix):]
    # Also handle UPI IDs - keep as-is
    if "@" in account:
        return account
    # Return as-is if no prefix
    return account

def evaluate_case(case_dir: Path, threshold: float = 50.0):
    """Evaluate detection for one case."""
    # Load ground truth
    with open(case_dir / "ground_truth.json") as f:
        gt = json.load(f)

    victim = gt["victim_account"]
    true_mules = set(gt["mule_accounts"])
    true_normals = set(gt["normal_accounts"])

    print(f"\nEvaluating {case_dir.name}")
    print(f"  Victim: {victim}")
    print(f"  True mules: {len(true_mules)}")
    print(f"  True normals: {len(true_normals)}")

    # Parse all statements
    all_transactions = []
    for statement_file in case_dir.glob("*.csv"):
        try:
            parsed = parse_statement(statement_file)
            account = infer_account_from_filename(str(statement_file))
            normalized = normalize_transactions(parsed, account)
            all_transactions.extend(normalized)
        except Exception as e:
            print(f"  Warning: Failed to parse {statement_file.name}: {e}")

    for statement_file in case_dir.glob("*.xlsx"):
        try:
            parsed = parse_statement(statement_file)
            account = infer_account_from_filename(str(statement_file))
            normalized = normalize_transactions(parsed, account)
            all_transactions.extend(normalized)
        except Exception as e:
            print(f"  Warning: Failed to parse {statement_file.name}: {e}")

    print(f"  Parsed {len(all_transactions)} transactions")

    # Build graph
    graph = build_graph(all_transactions)

    # Find victim in graph (may be under different ID)
    # Victim is the account with large initial outflow
    victim_candidates = []
    for node in graph.graph.nodes():
        info = graph.get_account_info(node)
        if info["num_outgoing"] > 0 and info["total_outflow"] > 50000:
            victim_candidates.append((node, info["total_outflow"]))

    if victim_candidates:
        victim_candidates.sort(key=lambda x: x[1], reverse=True)
        actual_victim = victim_candidates[0][0]
        print(f"  Using {actual_victim} as victim (highest outflow)")
    else:
        actual_victim = victim

    # Trace from victim
    trace_result = trace_from_victim(graph.graph, actual_victim)
    print(f"  Traced to {len(trace_result.traced_accounts)} accounts")

    # Extract features
    features_list = extract_features(graph, trace_result.traced_accounts)

    # ML anomaly detection
    features_list = detect_anomalies(features_list)

    # Score accounts
    scored = score_accounts(features_list)

    # Evaluate - normalize account names for comparison
    predicted_mules_raw = set()
    predicted_mules_full = {}  # Map normalized -> full name for display
    for features in scored:
        if features["suspicion_score"] >= threshold:
            full_name = features["account"]
            # Skip special nodes
            if any(x in full_name for x in ["ATM", "CRYPTO", "EXTERNAL"]):
                continue
            normalized = normalize_account_name(full_name)
            # Skip victim
            if normalized != victim:
                predicted_mules_raw.add(normalized)
                predicted_mules_full[normalized] = full_name

    # Calculate metrics using normalized names
    tp = len(predicted_mules_raw & true_mules)
    fp = len(predicted_mules_raw - true_mules)
    fn = len(true_mules - predicted_mules_raw)
    tn = len(true_normals - predicted_mules_raw)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    print(f"\n  Metrics (threshold={threshold}):")
    print(f"    Precision: {precision:.2%} ({tp} TP, {fp} FP)")
    print(f"    Recall:    {recall:.2%} ({tp} TP, {fn} FN)")
    print(f"    F1 Score:  {f1:.2%}")

    # Show top 5 predictions
    print(f"\n  Top 5 suspicious accounts:")
    for i, features in enumerate(scored[:5]):
        acc = features["account"]
        score = features["suspicion_score"]
        normalized = normalize_account_name(acc)
        is_mule = "[MULE]" if normalized in true_mules else "[NORMAL]"
        print(f"    {i+1}. {acc[:20]:20s} Score: {score:5.1f} {is_mule}")
        # Avoid unicode characters in explanation
        explanation = features['explanation'].replace('₹', 'Rs.')
        print(f"       {explanation}")

    return {
        "case": case_dir.name,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }

def main():
    sample_data = Path(__file__).parent.parent / "sample_data"

    results = []
    for case_dir in sorted(sample_data.glob("case_*")):
        if case_dir.is_dir():
            result = evaluate_case(case_dir, threshold=50.0)
            results.append(result)

    # Aggregate metrics
    if results:
        print("\n" + "="*60)
        print("AGGREGATE METRICS")
        print("="*60)

        total_tp = sum(r["tp"] for r in results)
        total_fp = sum(r["fp"] for r in results)
        total_fn = sum(r["fn"] for r in results)

        avg_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
        avg_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
        avg_f1 = 2 * avg_precision * avg_recall / (avg_precision + avg_recall) if (avg_precision + avg_recall) > 0 else 0

        print(f"Precision: {avg_precision:.2%}")
        print(f"Recall:    {avg_recall:.2%}")
        print(f"F1 Score:  {avg_f1:.2%}")

if __name__ == "__main__":
    main()
