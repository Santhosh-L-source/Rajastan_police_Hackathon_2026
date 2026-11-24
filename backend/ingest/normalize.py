"""
Transaction normalization to unified schema.
"""

from typing import List, Dict, Optional
from datetime import datetime
import re
import uuid

def extract_account_from_description(desc: str) -> Optional[str]:
    """Extract account number or UPI ID from transaction description."""
    # UPI pattern: xxx@bank or UPI/xxx@bank
    upi_match = re.search(r"[\w.]+@\w+", desc)
    if upi_match:
        return upi_match.group(0)

    # Account number pattern: 10-16 digits
    acc_match = re.search(r"\b\d{10,16}\b", desc)
    if acc_match:
        return acc_match.group(0)

    # Return description fragment as fallback
    return None

def infer_mode(description: str, txn_id: str = "") -> str:
    """Infer transaction mode from description."""
    desc_upper = description.upper()

    if "UPI" in desc_upper or "@" in description:
        return "UPI"
    elif "IMPS" in desc_upper:
        return "IMPS"
    elif "NEFT" in desc_upper:
        return "NEFT"
    elif "RTGS" in desc_upper:
        return "RTGS"
    elif "ATM" in desc_upper or "WITHDRAWAL" in desc_upper:
        return "ATM"
    elif "CASH" in desc_upper:
        return "CASH"
    elif "DEBIT" in desc_upper or "CARD" in desc_upper:
        return "DEBIT_CARD"
    elif "SALARY" in desc_upper:
        return "SALARY"
    else:
        return "OTHER"

def normalize_transaction(parsed: Dict, file_account: str) -> Dict:
    """
    Normalize a single parsed transaction to unified schema.

    Args:
        parsed: Parsed transaction dict (from parser)
        file_account: Account number this statement belongs to

    Returns:
        Normalized transaction with schema:
        {
            "txn_id": str,
            "timestamp": datetime,
            "from_account": str,
            "to_account": str,
            "amount": float,
            "mode": str (UPI/IMPS/NEFT/RTGS/ATM/CASH/OTHER),
            "bank": str,
            "balance_after": float | None,
            "narration": str,
            "direction": str (credit/debit)
        }
    """
    # Extract or generate transaction ID
    txn_id = parsed.get("txn_id", "")
    if not txn_id or txn_id == "":
        txn_id = f"GEN_{uuid.uuid4().hex[:12]}"

    # Extract other account from description
    description = parsed.get("description", "")
    other_account = extract_account_from_description(description)

    # Determine from/to based on direction
    direction = parsed.get("direction", "debit")
    if direction == "debit":
        from_account = file_account
        to_account = other_account or "EXTERNAL"
    else:  # credit
        from_account = other_account or "EXTERNAL"
        to_account = file_account

    # Infer mode
    mode = infer_mode(description, txn_id)

    return {
        "txn_id": txn_id,
        "timestamp": parsed["timestamp"],
        "from_account": from_account,
        "to_account": to_account,
        "amount": parsed["amount"],
        "mode": mode,
        "bank": parsed.get("bank", "UNKNOWN"),
        "balance_after": parsed.get("balance"),
        "narration": description,
        "direction": direction
    }

def normalize_transactions(parsed_list: List[Dict], file_account: str) -> List[Dict]:
    """
    Normalize a list of parsed transactions.

    Args:
        parsed_list: List of parsed transaction dicts
        file_account: Account number this statement belongs to

    Returns:
        List of normalized transactions
    """
    return [normalize_transaction(p, file_account) for p in parsed_list]

def infer_account_from_filename(filepath: str) -> str:
    """
    Try to infer account number from filename.
    Fallback to generating a unique identifier.
    """
    # Look for account-like pattern in filename
    match = re.search(r"(\d{10,16})", filepath)
    if match:
        return match.group(1)

    # Extract bank and use as prefix
    for bank in ["SBI", "HDFC", "ICICI", "AXIS"]:
        if bank in filepath.upper():
            return f"{bank}_ACCOUNT_{uuid.uuid4().hex[:8].upper()}"

    return f"ACCOUNT_{uuid.uuid4().hex[:8].upper()}"
