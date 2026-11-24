"""
ML-based anomaly detection using Isolation Forest.
"""

from typing import List, Dict
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

# Features to use for ML (exclude account identifier and raw amounts)
ML_FEATURES = [
    "pass_through_ratio",
    "median_holding_time",
    "fan_in",
    "fan_out",
    "velocity",
    "round_number_ratio",
    "cash_out_exposure",
    "cycle_participation",
    "dormant_then_active",
    "balance_ratio",
]

def detect_anomalies(features_list: List[Dict], contamination: float = 0.15) -> List[Dict]:
    """
    Use Isolation Forest to detect anomalous accounts.

    Args:
        features_list: List of feature dicts from extract_features()
        contamination: Expected proportion of mules (default 0.15 = 15%)

    Returns:
        features_list with added fields:
        - anomaly_score: -1 to 1 (higher = more anomalous)
        - is_anomaly: boolean (1 = anomaly, -1 = normal)
    """
    if len(features_list) < 2:
        # Not enough data for ML
        for f in features_list:
            f["anomaly_score"] = 0.0
            f["is_anomaly"] = 0
        return features_list

    # Prepare feature matrix
    X = []
    for features in features_list:
        row = [features.get(f, 0.0) for f in ML_FEATURES]
        X.append(row)

    X = np.array(X)

    # Handle missing/inf values
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    # Standardize features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Isolation Forest
    iso_forest = IsolationForest(
        contamination=contamination,
        random_state=42,
        n_estimators=100
    )

    predictions = iso_forest.fit_predict(X_scaled)
    scores = iso_forest.score_samples(X_scaled)

    # Normalize scores to [0, 1] where 1 = most anomalous
    # Isolation Forest scores are negative (more negative = more normal)
    # Flip and normalize
    scores_normalized = (scores - scores.min()) / (scores.max() - scores.min() + 1e-10)
    scores_normalized = 1 - scores_normalized  # Flip so high = anomalous

    # Add to features
    for i, features in enumerate(features_list):
        features["anomaly_score"] = float(scores_normalized[i])
        features["is_anomaly"] = int(predictions[i])  # -1 = normal, 1 = anomaly

    return features_list
