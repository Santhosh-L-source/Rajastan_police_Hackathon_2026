"""
Suspicion scoring with human-readable explanations.
"""

from typing import List, Dict

def generate_explanation(features: Dict) -> str:
    """Generate human-readable explanation for suspicion score."""
    explanations = []

    # Pass-through ratio
    ptr = features.get("pass_through_ratio", 0)
    if ptr > 0.95:
        explanations.append(f"Forwarded {ptr*100:.0f}% of received funds")
    elif ptr > 0.80:
        explanations.append(f"Forwarded {ptr*100:.0f}% of funds")

    # Holding time
    holding = features.get("median_holding_time", 0)
    if holding > 0 and holding < 60:
        explanations.append(f"Held funds for {holding:.0f} min on average")
    elif holding >= 60 and holding < 1440:
        explanations.append(f"Held funds for {holding/60:.1f} hours on average")

    # Fan-in/out
    fan_in = features.get("fan_in", 0)
    fan_out = features.get("fan_out", 0)
    if fan_in > 5:
        explanations.append(f"Received from {fan_in} different accounts")
    if fan_out > 5:
        explanations.append(f"Sent to {fan_out} different accounts")

    # Velocity
    velocity = features.get("velocity", 0)
    if velocity > 10000:
        explanations.append(f"High transaction velocity (₹{velocity:.0f}/hour)")

    # Round numbers
    round_ratio = features.get("round_number_ratio", 0)
    if round_ratio > 0.5:
        explanations.append(f"{round_ratio*100:.0f}% round-number amounts")

    # Cash out
    cash_out = features.get("cash_out_exposure", 0)
    if cash_out > 0.5:
        explanations.append(f"{cash_out*100:.0f}% withdrawn to ATM/crypto")

    # Dormant
    if features.get("dormant_then_active", 0) > 0:
        explanations.append("Dormant account suddenly active")

    # Cycle
    if features.get("cycle_participation", 0) > 0:
        explanations.append("Involved in round-tripping")

    # Anomaly score
    anomaly = features.get("anomaly_score", 0)
    if anomaly > 0.7:
        explanations.append(f"ML anomaly score: {anomaly:.2f}")

    if not explanations:
        explanations.append("Normal transaction pattern")

    return "; ".join(explanations)

def calculate_suspicion_score(features: Dict) -> float:
    """
    Calculate 0-100 suspicion score from features.

    Weights:
    - Pass-through ratio: 25 points
    - Holding time: 20 points (lower = more suspicious)
    - Fan-in/out: 15 points
    - Anomaly score: 20 points
    - Other features: 20 points
    """
    score = 0.0

    # Pass-through ratio (25 points)
    ptr = features.get("pass_through_ratio", 0)
    if ptr > 0.95:
        score += 25
    elif ptr > 0.85:
        score += 20
    elif ptr > 0.75:
        score += 15

    # Holding time (20 points) - lower is more suspicious
    holding = features.get("median_holding_time", 0)
    if holding > 0:
        if holding < 10:  # < 10 minutes
            score += 20
        elif holding < 60:  # < 1 hour
            score += 15
        elif holding < 360:  # < 6 hours
            score += 10
        elif holding < 1440:  # < 24 hours
            score += 5

    # Fan-in/out (15 points)
    fan_in = features.get("fan_in", 0)
    fan_out = features.get("fan_out", 0)
    if fan_in > 10 or fan_out > 10:
        score += 15
    elif fan_in > 5 or fan_out > 5:
        score += 10
    elif fan_in > 2 or fan_out > 2:
        score += 5

    # Anomaly score from ML (20 points)
    anomaly = features.get("anomaly_score", 0)
    score += anomaly * 20

    # Other features (20 points total)
    if features.get("round_number_ratio", 0) > 0.5:
        score += 5
    if features.get("cash_out_exposure", 0) > 0.5:
        score += 5
    if features.get("dormant_then_active", 0) > 0:
        score += 5
    if features.get("cycle_participation", 0) > 0:
        score += 5

    return min(score, 100.0)

def score_accounts(features_list: List[Dict]) -> List[Dict]:
    """
    Calculate suspicion scores and explanations for all accounts.

    Args:
        features_list: List of feature dicts (with anomaly_score from ML)

    Returns:
        features_list with added fields:
        - suspicion_score: 0-100
        - explanation: human-readable string
        - risk_level: "HIGH" / "MEDIUM" / "LOW"
    """
    for features in features_list:
        score = calculate_suspicion_score(features)
        explanation = generate_explanation(features)

        if score >= 70:
            risk_level = "HIGH"
        elif score >= 40:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        features["suspicion_score"] = score
        features["explanation"] = explanation
        features["risk_level"] = risk_level

    # Sort by suspicion score descending
    features_list.sort(key=lambda x: x.get("suspicion_score", 0), reverse=True)

    return features_list
