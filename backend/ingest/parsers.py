"""
Multi-format bank statement parsers with auto-detection.
Handles CSV, XLSX, and text-based PDF statements.
"""

import pandas as pd
import pdfplumber
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import re

class ParseError(Exception):
    """Raised when statement parsing fails."""
    pass

def detect_format(filepath: Path) -> str:
    """Auto-detect statement format: sbi_csv, hdfc_excel, icici_pdf, or unknown."""
    suffix = filepath.suffix.lower()

    if suffix == ".csv":
        try:
            df = pd.read_csv(filepath, nrows=1)
            if "Txn Date" in df.columns and "Ref No." in df.columns:
                return "sbi_csv"
            elif "Date" in df.columns and "Withdrawal Amt." in df.columns:
                return "hdfc_csv"
            return "generic_csv"
        except Exception:
            return "unknown"

    elif suffix in [".xlsx", ".xls"]:
        try:
            df = pd.read_excel(filepath, nrows=1)
            if "Withdrawal Amt." in df.columns and "Deposit Amt." in df.columns:
                return "hdfc_excel"
            return "generic_excel"
        except Exception:
            return "unknown"

    elif suffix == ".pdf":
        try:
            with pdfplumber.open(filepath) as pdf:
                if len(pdf.pages) > 0:
                    text = pdf.pages[0].extract_text()
                    if "ICICI BANK" in text:
                        return "icici_pdf"
                    elif "STATE BANK" in text or "SBI" in text:
                        return "sbi_pdf"
                    return "generic_pdf"
        except Exception:
            return "unknown"

    return "unknown"

def parse_sbi_csv(filepath: Path, bank_name: str = "SBI") -> List[Dict]:
    """Parse SBI-format CSV statement."""
    try:
        df = pd.read_csv(filepath)
        required = ["Txn Date", "Description", "Ref No."]
        if not all(col in df.columns for col in required):
            raise ParseError(f"Missing required columns in SBI CSV: {required}")

        transactions = []
        for _, row in df.iterrows():
            # Parse date
            try:
                txn_date = pd.to_datetime(row["Txn Date"], format="%d-%m-%Y", errors="coerce")
            except:
                txn_date = pd.to_datetime(row["Txn Date"], errors="coerce")

            if pd.isna(txn_date):
                continue

            # Determine direction and amount
            debit = row.get("Debit", "")
            credit = row.get("Credit", "")

            if pd.notna(debit) and str(debit).strip():
                amount = float(str(debit).replace(",", ""))
                direction = "debit"
            elif pd.notna(credit) and str(credit).strip():
                amount = float(str(credit).replace(",", ""))
                direction = "credit"
            else:
                continue

            transactions.append({
                "timestamp": txn_date,
                "txn_id": str(row["Ref No."]),
                "description": str(row["Description"]),
                "amount": amount,
                "direction": direction,
                "balance": float(str(row.get("Balance", "0")).replace(",", "")) if pd.notna(row.get("Balance")) else None,
                "bank": bank_name,
                "raw": row.to_dict()
            })

        return transactions

    except Exception as e:
        raise ParseError(f"Failed to parse SBI CSV: {str(e)}")

def parse_hdfc_excel(filepath: Path, bank_name: str = "HDFC") -> List[Dict]:
    """Parse HDFC-format Excel statement."""
    try:
        df = pd.read_excel(filepath)
        required = ["Date", "Narration"]
        if not all(col in df.columns for col in required):
            raise ParseError(f"Missing required columns in HDFC Excel: {required}")

        transactions = []
        for _, row in df.iterrows():
            # Parse date
            try:
                txn_date = pd.to_datetime(row["Date"], format="%d/%m/%y", errors="coerce")
            except:
                txn_date = pd.to_datetime(row["Date"], errors="coerce")

            if pd.isna(txn_date):
                continue

            # Determine direction and amount
            withdrawal = row.get("Withdrawal Amt.", 0)
            deposit = row.get("Deposit Amt.", 0)

            if pd.notna(withdrawal) and withdrawal > 0:
                amount = float(withdrawal)
                direction = "debit"
            elif pd.notna(deposit) and deposit > 0:
                amount = float(deposit)
                direction = "credit"
            else:
                continue

            transactions.append({
                "timestamp": txn_date,
                "txn_id": str(row.get("Chq./Ref.No.", "")),
                "description": str(row["Narration"]),
                "amount": amount,
                "direction": direction,
                "balance": float(row.get("Closing Balance", 0)) if pd.notna(row.get("Closing Balance")) else None,
                "bank": bank_name,
                "raw": row.to_dict()
            })

        return transactions

    except Exception as e:
        raise ParseError(f"Failed to parse HDFC Excel: {str(e)}")

def parse_icici_pdf(filepath: Path, bank_name: str = "ICICI") -> List[Dict]:
    """Parse ICICI-format PDF statement (text-based)."""
    try:
        transactions = []
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue

                # Parse lines looking for transaction pattern
                # Format: DD-MM-YYYY Description Ref Debit Credit Balance
                lines = text.split("\n")
                for line in lines:
                    # Skip headers and non-transaction lines
                    if not line or "Date" in line or "Description" in line:
                        continue

                    # Try to extract date at start (DD-MM-YYYY)
                    date_match = re.match(r"(\d{2}-\d{2}-\d{4})", line)
                    if not date_match:
                        continue

                    date_str = date_match.group(1)
                    try:
                        txn_date = datetime.strptime(date_str, "%d-%m-%Y")
                    except:
                        continue

                    # Extract amounts (last 3 numbers on the line)
                    amounts = re.findall(r"(\d+\.\d{2})", line)
                    if len(amounts) < 2:
                        continue

                    # Parse debit/credit (second-to-last and third-to-last)
                    if len(amounts) >= 3:
                        debit_str = amounts[-3]
                        credit_str = amounts[-2]
                        balance = float(amounts[-1])
                    else:
                        # Try heuristic
                        debit_str = amounts[0] if len(amounts) > 1 else "0.00"
                        credit_str = amounts[1] if len(amounts) > 1 else "0.00"
                        balance = None

                    # Determine direction
                    debit = float(debit_str)
                    credit = float(credit_str)

                    if debit > 0:
                        amount = debit
                        direction = "debit"
                    elif credit > 0:
                        amount = credit
                        direction = "credit"
                    else:
                        continue

                    # Extract reference number and description (heuristic)
                    # Remove date and amounts to get middle part
                    desc_part = line[len(date_str):].strip()
                    for amt in amounts:
                        desc_part = desc_part.replace(amt, "")
                    desc_part = desc_part.strip()

                    # Try to extract ref no (looks like TXNXXXXXX or similar)
                    ref_match = re.search(r"(TXN\w+|\d{6,})", desc_part)
                    ref_no = ref_match.group(1) if ref_match else f"PDF_{len(transactions)}"

                    transactions.append({
                        "timestamp": txn_date,
                        "txn_id": ref_no,
                        "description": desc_part[:100],
                        "amount": amount,
                        "direction": direction,
                        "balance": balance,
                        "bank": bank_name,
                        "raw": {"line": line}
                    })

        return transactions

    except Exception as e:
        raise ParseError(f"Failed to parse ICICI PDF: {str(e)}")

def parse_statement(filepath: Path, format_hint: Optional[str] = None) -> List[Dict]:
    """
    Parse a bank statement file into normalized transaction list.

    Args:
        filepath: Path to statement file
        format_hint: Optional format override (auto-detected if None)

    Returns:
        List of transaction dictionaries with keys:
        timestamp, txn_id, description, amount, direction, balance, bank, raw

    Raises:
        ParseError: If parsing fails
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise ParseError(f"File not found: {filepath}")

    # Detect format if not provided
    if format_hint is None:
        format_hint = detect_format(filepath)

    # Infer bank from filename if possible
    bank_name = "UNKNOWN"
    for bank in ["SBI", "HDFC", "ICICI", "AXIS"]:
        if bank in filepath.stem.upper():
            bank_name = bank
            break

    # Route to appropriate parser
    if format_hint == "sbi_csv":
        return parse_sbi_csv(filepath, bank_name)
    elif format_hint == "hdfc_excel" or format_hint == "hdfc_csv":
        return parse_hdfc_excel(filepath, bank_name)
    elif format_hint == "icici_pdf" or format_hint == "generic_pdf":
        return parse_icici_pdf(filepath, bank_name)
    elif format_hint == "generic_csv":
        return parse_sbi_csv(filepath, bank_name)  # Try SBI format as fallback
    elif format_hint == "generic_excel":
        return parse_hdfc_excel(filepath, bank_name)  # Try HDFC format as fallback
    else:
        raise ParseError(f"Unsupported format: {format_hint}")
