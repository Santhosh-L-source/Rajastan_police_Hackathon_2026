#!/usr/bin/env python3
"""
Evaluate infrastructure clustering against ground truth.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.infra.parser import parse_infra_csv
from backend.infra.clustering import cluster_domains

def evaluate_case(case_dir: Path):
    """Evaluate clustering for one case."""
    # Load ground truth
    with open(case_dir / "infra_ground_truth.json") as f:
        gt = json.load(f)

    print(f"\nEvaluating {case_dir.name}")
    print(f"  True clusters: {gt['num_clusters']}")
    print(f"  Scam domains: {gt['num_scam_domains']}")

    # Parse infrastructure data
    csv_path = case_dir / "infrastructure.csv"
    domains = parse_infra_csv(csv_path)

    print(f"  Total domains parsed: {len(domains)}")

    # Run clustering
    clusters = cluster_domains(domains)

    print(f"  Detected clusters: {len(clusters)}")

    # Evaluation metrics
    # Ground truth: build sets of scam domains per true cluster
    true_clusters = []
    for cluster_data in gt["clusters"]:
        cluster_domain_set = {d["domain"] for d in cluster_data["domains"]}
        true_clusters.append(cluster_domain_set)

    # Detected clusters (top N by score)
    detected_clusters = []
    for cluster in clusters[:10]:  # Evaluate top 10
        cluster_domain_set = {d.domain for d in cluster.domains if d.is_scam}
        if cluster_domain_set:  # Only count clusters with scam domains
            detected_clusters.append(cluster_domain_set)

    # Calculate precision and recall for clustering
    # Precision: % of detected clusters that match a true cluster
    # Recall: % of true clusters that were detected

    # Match detected to true clusters (best overlap)
    matched_true = set()
    true_positives = 0

    for detected in detected_clusters:
        # Find true cluster with best overlap
        best_overlap = 0
        best_true_idx = None

        for i, true_set in enumerate(true_clusters):
            overlap = len(detected & true_set)
            if overlap > best_overlap:
                best_overlap = overlap
                best_true_idx = i

        # Count as match if >50% overlap
        if best_true_idx is not None and best_overlap / len(detected) > 0.5:
            true_positives += 1
            matched_true.add(best_true_idx)

    precision = true_positives / len(detected_clusters) if detected_clusters else 0
    recall = len(matched_true) / len(true_clusters) if true_clusters else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    print(f"\n  Clustering Metrics:")
    print(f"    Precision: {precision:.2%} ({true_positives}/{len(detected_clusters)} detected clusters are true)")
    print(f"    Recall:    {recall:.2%} ({len(matched_true)}/{len(true_clusters)} true clusters detected)")
    print(f"    F1 Score:  {f1:.2%}")

    # Show top 3 clusters
    print(f"\n  Top 3 Detected Clusters:")
    for i, cluster in enumerate(clusters[:3]):
        scam_count = len([d for d in cluster.domains if d.is_scam])
        print(f"    {i+1}. {cluster.cluster_id}: {len(cluster.domains)} domains ({scam_count} scam)")
        print(f"       Score: {cluster.score:.1f}")
        print(f"       {cluster.explanation}")
        print(f"       Domains: {', '.join([d.domain for d in cluster.domains[:3]])}")

    return {
        "case": case_dir.name,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "true_positives": true_positives,
        "detected_clusters": len(detected_clusters),
        "true_clusters": len(true_clusters)
    }

def main():
    sample_data = Path(__file__).parent.parent / "sample_data"

    results = []
    for case_dir in sorted(sample_data.glob("case_*")):
        if case_dir.is_dir() and (case_dir / "infrastructure.csv").exists():
            result = evaluate_case(case_dir)
            results.append(result)

    # Aggregate metrics
    if results:
        print("\n" + "="*60)
        print("AGGREGATE CLUSTERING METRICS")
        print("="*60)

        avg_precision = sum(r["precision"] for r in results) / len(results)
        avg_recall = sum(r["recall"] for r in results) / len(results)
        avg_f1 = sum(r["f1"] for r in results) / len(results)

        print(f"Average Precision: {avg_precision:.2%}")
        print(f"Average Recall:    {avg_recall:.2%}")
        print(f"Average F1 Score:  {avg_f1:.2%}")

        total_tp = sum(r["true_positives"] for r in results)
        total_detected = sum(r["detected_clusters"] for r in results)
        total_true = sum(r["true_clusters"] for r in results)

        print(f"\nTotal: {total_tp} TP / {total_detected} detected / {total_true} true clusters")

if __name__ == "__main__":
    main()
