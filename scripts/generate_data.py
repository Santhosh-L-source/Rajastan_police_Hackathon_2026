#!/usr/bin/env python3
"""
Synthetic fraud data generator for TraceFreeze.
Generates realistic fraud scenarios with ground truth.
"""

import random
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import json
import csv
from typing import List, Dict, Tuple
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import io

# Shared mule pool for cross-case linking
SHARED_MULES = []

class Account:
    def __init__(self, acc_id: str, bank: str, is_mule: bool = False, is_victim: bool = False):
        self.id = acc_id
        self.bank = bank
        self.is_mule = is_mule
        self.is_victim = is_victim
        self.balance = random.randint(5000, 50000) if not is_mule else random.randint(100, 5000)
        self.transactions = []
        self.created_days_ago = random.randint(1, 30) if is_mule else random.randint(90, 1000)

class Transaction:
    def __init__(self, txn_id: str, timestamp: datetime, from_acc: str, to_acc: str,
                 amount: float, mode: str, bank: str, narration: str = ""):
        self.txn_id = txn_id
        self.timestamp = timestamp
        self.from_acc = from_acc
        self.to_acc = to_acc
        self.amount = amount
        self.mode = mode
        self.bank = bank
        self.narration = narration

def generate_account_number(bank: str, idx: int) -> str:
    """Generate realistic account number by bank."""
    if bank == "SBI":
        return f"3{random.randint(1000000000, 9999999999)}"
    elif bank == "HDFC":
        return f"5{random.randint(100000000000, 999999999999)}"
    elif bank == "ICICI":
        return f"0{random.randint(10000000000, 99999999999)}"
    elif bank == "AXIS":
        return f"9{random.randint(1000000000000, 9999999999999)}"
    return f"{random.randint(100000000, 999999999)}"

def generate_upi_id(acc_num: str, bank: str) -> str:
    """Generate UPI ID."""
    names = ["amit", "raj", "priya", "rahul", "neha", "sunil", "pooja", "vijay"]
    return f"{random.choice(names)}.{acc_num[-4:]}@{bank.lower()}"

def generate_fraud_scenario(case_id: str, start_date: datetime, seed: int = None,
                           use_shared_mules: bool = False) -> Tuple[List[Account], List[Transaction]]:
    """Generate one fraud scenario with layering, fan-out, fan-in."""
    if seed:
        random.seed(seed)

    banks = ["SBI", "HDFC", "ICICI", "AXIS"]
    modes = ["UPI", "IMPS", "NEFT", "RTGS"]

    # Victim account
    victim_bank = random.choice(banks)
    victim = Account(generate_account_number(victim_bank, 0), victim_bank, is_victim=True)

    # Mule accounts (3-5 layers, 25-60 total)
    num_layers = random.randint(3, 5)
    mules_per_layer = [random.randint(5, 15) for _ in range(num_layers)]

    accounts = [victim]
    all_mules = []

    # Create mule accounts
    for layer_idx, num_mules in enumerate(mules_per_layer):
        layer_mules = []
        for i in range(num_mules):
            # Use shared mule occasionally
            if use_shared_mules and random.random() < 0.1 and SHARED_MULES:
                mule = random.choice(SHARED_MULES)
            else:
                bank = random.choice(banks)
                mule = Account(generate_account_number(bank, len(accounts)), bank, is_mule=True)
                # Add to shared pool occasionally
                if random.random() < 0.05:
                    SHARED_MULES.append(mule)
            layer_mules.append(mule)
            if mule not in accounts:
                accounts.append(mule)
        all_mules.append(layer_mules)

    # Normal accounts (noise)
    num_normal = random.randint(5, 10)
    for i in range(num_normal):
        bank = random.choice(banks)
        normal = Account(generate_account_number(bank, len(accounts)), bank)
        accounts.append(normal)

    # Generate transactions
    transactions = []
    txn_counter = 1
    current_time = start_date

    # Initial fraud transaction from victim
    fraud_amount = random.randint(50000, 500000)
    first_layer = all_mules[0]

    # Fan-out from victim to first layer
    split_amounts = []
    remaining = fraud_amount
    for i in range(len(first_layer) - 1):
        amt = random.randint(5000, remaining // 2)
        split_amounts.append(amt)
        remaining -= amt
    split_amounts.append(remaining)

    for mule, amt in zip(first_layer, split_amounts):
        current_time += timedelta(seconds=random.randint(10, 120))
        txn = Transaction(
            f"TXN{case_id}{txn_counter:06d}",
            current_time,
            victim.id,
            mule.id,
            amt,
            random.choice(modes),
            victim.bank,
            f"UPI/{generate_upi_id(mule.id, mule.bank)}/Fraud txn"
        )
        transactions.append(txn)
        mule.balance += amt
        txn_counter += 1

    # Layer-to-layer transfers (rapid pass-through)
    for layer_idx in range(len(all_mules) - 1):
        current_layer = all_mules[layer_idx]
        next_layer = all_mules[layer_idx + 1]

        for mule in current_layer:
            # Pass through 95-100% of balance
            pass_through = mule.balance * random.uniform(0.95, 1.0)
            if pass_through < 100:
                continue

            # Fan-out to 1-3 accounts in next layer
            num_targets = min(random.randint(1, 3), len(next_layer))
            targets = random.sample(next_layer, num_targets)

            split = []
            rem = pass_through
            for i in range(num_targets - 1):
                amt = rem * random.uniform(0.2, 0.5)
                split.append(amt)
                rem -= amt
            split.append(rem)

            for target, amt in zip(targets, split):
                # Rapid transfer (1-15 minutes holding time)
                current_time += timedelta(minutes=random.randint(1, 15))
                txn = Transaction(
                    f"TXN{case_id}{txn_counter:06d}",
                    current_time,
                    mule.id,
                    target.id,
                    amt,
                    random.choice(modes),
                    mule.bank,
                    f"Transfer/{generate_upi_id(target.id, target.bank)}"
                )
                transactions.append(txn)
                mule.balance -= amt
                target.balance += amt
                txn_counter += 1

    # Final layer: cash out or crypto
    final_layer = all_mules[-1]
    for mule in final_layer:
        if mule.balance > 500:
            # 60% ATM, 30% crypto, 10% stay in account
            exit_type = random.choices(["ATM", "CRYPTO", "HOLD"], weights=[0.6, 0.3, 0.1])[0]
            if exit_type == "ATM":
                # Multiple ATM withdrawals
                remaining = mule.balance
                while remaining > 10000:
                    amt = random.randint(10000, 25000)
                    if amt > remaining:
                        amt = remaining
                    current_time += timedelta(hours=random.randint(1, 6))
                    txn = Transaction(
                        f"TXN{case_id}{txn_counter:06d}",
                        current_time,
                        mule.id,
                        "ATM_WITHDRAWAL",
                        amt,
                        "ATM",
                        mule.bank,
                        f"ATM WD/{random.randint(100000, 999999)}"
                    )
                    transactions.append(txn)
                    remaining -= amt
                    txn_counter += 1
            elif exit_type == "CRYPTO":
                current_time += timedelta(hours=random.randint(1, 12))
                txn = Transaction(
                    f"TXN{case_id}{txn_counter:06d}",
                    current_time,
                    mule.id,
                    "CRYPTO_EXCHANGE",
                    mule.balance,
                    "NEFT",
                    mule.bank,
                    f"To WAZIRX/BINANCE"
                )
                transactions.append(txn)
                txn_counter += 1

    # Add normal transaction noise
    normal_accounts = [a for a in accounts if not a.is_mule and not a.is_victim]
    for _ in range(random.randint(20, 50)):
        acc = random.choice(accounts)
        noise_time = start_date + timedelta(hours=random.randint(-48, 72))

        if random.random() < 0.5:  # Incoming
            txn = Transaction(
                f"TXN{case_id}{txn_counter:06d}",
                noise_time,
                f"EXT{random.randint(10000, 99999)}",
                acc.id,
                random.randint(500, 15000),
                random.choice(["UPI", "SALARY", "NEFT"]),
                acc.bank,
                random.choice(["Salary credit", "UPI/merchant", "Transfer from friend"])
            )
        else:  # Outgoing
            txn = Transaction(
                f"TXN{case_id}{txn_counter:06d}",
                noise_time,
                acc.id,
                f"EXT{random.randint(10000, 99999)}",
                random.randint(100, 5000),
                random.choice(["UPI", "IMPS", "DEBIT_CARD"]),
                acc.bank,
                random.choice(["Amazon purchase", "Swiggy order", "Electricity bill", "UPI/shop"])
            )
        transactions.append(txn)
        txn_counter += 1

    return accounts, transactions

def save_as_sbi_csv(transactions: List[Transaction], accounts: List[Account], filepath: Path):
    """Save in SBI CSV format."""
    rows = []
    for txn in transactions:
        # Find account to get balance
        acc = next((a for a in accounts if a.id == txn.from_acc or a.id == txn.to_acc), None)
        rows.append({
            "Txn Date": txn.timestamp.strftime("%d-%m-%Y"),
            "Value Date": txn.timestamp.strftime("%d-%m-%Y"),
            "Description": txn.narration,
            "Ref No.": txn.txn_id,
            "Debit": f"{txn.amount:.2f}" if any(a.id == txn.from_acc for a in accounts) else "",
            "Credit": f"{txn.amount:.2f}" if any(a.id == txn.to_acc for a in accounts) else "",
            "Balance": f"{acc.balance:.2f}" if acc else "",
        })
    df = pd.DataFrame(rows)
    df.to_csv(filepath, index=False)

def save_as_hdfc_excel(transactions: List[Transaction], accounts: List[Account], filepath: Path):
    """Save in HDFC Excel format."""
    rows = []
    for txn in transactions:
        acc = next((a for a in accounts if a.id == txn.from_acc or a.id == txn.to_acc), None)
        is_debit = any(a.id == txn.from_acc for a in accounts)
        rows.append({
            "Date": txn.timestamp.strftime("%d/%m/%y"),
            "Narration": txn.narration,
            "Chq./Ref.No.": txn.txn_id,
            "Value Dt": txn.timestamp.strftime("%d/%m/%y"),
            "Withdrawal Amt.": txn.amount if is_debit else 0,
            "Deposit Amt.": txn.amount if not is_debit else 0,
            "Closing Balance": acc.balance if acc else 0,
        })
    df = pd.DataFrame(rows)
    df.to_excel(filepath, index=False, engine='openpyxl')

def save_as_pdf_statement(transactions: List[Transaction], accounts: List[Account], filepath: Path):
    """Save as text-based PDF (mimics scanned/printed statements)."""
    buffer = io.BytesIO()
    c = canvas.Canvas(str(filepath), pagesize=A4)
    width, height = A4

    # Header
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 50, "ICICI BANK LIMITED")
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 70, "Account Statement")

    # Transactions
    y = height - 120
    c.setFont("Courier", 8)
    c.drawString(50, y, "Date       Description                      Ref No.        Debit     Credit    Balance")
    y -= 20

    for txn in transactions[:30]:  # Limit to fit on page
        acc = next((a for a in accounts if a.id == txn.from_acc or a.id == txn.to_acc), None)
        is_debit = any(a.id == txn.from_acc for a in accounts)
        date_str = txn.timestamp.strftime("%d-%m-%Y")
        desc = txn.narration[:25].ljust(25)
        ref = txn.txn_id[:12].ljust(12)
        debit = f"{txn.amount:10.2f}" if is_debit else " " * 10
        credit = f"{txn.amount:10.2f}" if not is_debit else " " * 10
        balance = f"{acc.balance:10.2f}" if acc else " " * 10

        line = f"{date_str} {desc} {ref} {debit} {credit} {balance}"
        c.drawString(50, y, line)
        y -= 15

        if y < 50:
            c.showPage()
            y = height - 50
            c.setFont("Courier", 8)

    c.save()

def generate_case(case_id: str, output_dir: Path, seed: int = None, use_shared: bool = False):
    """Generate one complete case with multiple bank formats."""
    start_date = datetime.now() - timedelta(days=random.randint(7, 30))
    accounts, transactions = generate_fraud_scenario(case_id, start_date, seed, use_shared)

    case_dir = output_dir / case_id
    case_dir.mkdir(exist_ok=True)

    # Group transactions by bank
    banks_data = {}
    for txn in transactions:
        if txn.bank not in banks_data:
            banks_data[txn.bank] = []
        banks_data[txn.bank].append(txn)

    # Save in different formats
    for idx, (bank, txns) in enumerate(banks_data.items()):
        format_choice = idx % 3
        if format_choice == 0:
            save_as_sbi_csv(txns, accounts, case_dir / f"{bank}_statement.csv")
        elif format_choice == 1:
            save_as_hdfc_excel(txns, accounts, case_dir / f"{bank}_statement.xlsx")
        else:
            save_as_pdf_statement(txns, accounts, case_dir / f"{bank}_statement.pdf")

    # Ground truth
    ground_truth = {
        "case_id": case_id,
        "victim_account": next(a.id for a in accounts if a.is_victim),
        "mule_accounts": [a.id for a in accounts if a.is_mule],
        "normal_accounts": [a.id for a in accounts if not a.is_mule and not a.is_victim],
        "total_fraud_amount": sum(txn.amount for txn in transactions if any(a.id == txn.from_acc for a in accounts if a.is_victim)),
        "num_layers": len([a for a in accounts if a.is_mule]) // 10,
    }

    with open(case_dir / "ground_truth.json", "w") as f:
        json.dump(ground_truth, f, indent=2)

    print(f"Generated {case_id}: {len(accounts)} accounts, {len(transactions)} transactions, {len([a for a in accounts if a.is_mule])} mules")
    return ground_truth

def generate_infrastructure_data(case_id: str, seed: int = None) -> dict:
    """Generate synthetic digital infrastructure data with scam clusters."""
    if seed:
        random.seed(seed)

    # Create scam clusters (domains that are related)
    clusters = []

    # Cluster 1: Shared IP + registrar + near-simultaneous registration
    base_time = datetime.now() - timedelta(days=random.randint(30, 180))
    shared_ip1 = f"185.{random.randint(100, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}"
    registrar1 = random.choice(["NAMECHEAP", "GODADDY", "HOSTINGER"])
    ns1 = ["ns1.scamhost.com", "ns2.scamhost.com"]

    cluster1_domains = []
    bank_names = ["sbi", "hdfc", "icici", "axis", "paytm"]
    for i in range(random.randint(5, 8)):
        # Typosquat legitimate banks
        bank = random.choice(bank_names)
        typo_domain = f"{bank}-{random.choice(['secure', 'verify', 'login', 'update'])}{random.randint(1, 999)}.com"

        cluster1_domains.append({
            "domain": typo_domain,
            "ip": shared_ip1,
            "registrar": registrar1,
            "creation_date": (base_time + timedelta(hours=random.uniform(0, 2))).isoformat(),
            "name_servers": ",".join(ns1),
            "hosting_provider": "BulletproofHost LLC",
            "asn": "AS12345",
            "linked_upi_id": f"{random.choice(['amit', 'raj', 'sunil'])}@{random.choice(['paytm', 'phonepe'])}",
            "linked_phone": f"+91{random.randint(7000000000, 9999999999)}",
            "is_scam": "true",
            "case_id": case_id
        })

    clusters.append({"id": "cluster_1", "domains": cluster1_domains})

    # Cluster 2: Shared name servers + ASN
    shared_ip2 = f"192.{random.randint(100, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}"
    ns2 = ["ns3.shadyhost.net", "ns4.shadyhost.net"]

    cluster2_domains = []
    for i in range(random.randint(4, 6)):
        domain_name = f"customer-{random.choice(['support', 'service', 'help'])}-{random.randint(100, 999)}.com"
        cluster2_domains.append({
            "domain": domain_name,
            "ip": shared_ip2 if random.random() < 0.7 else f"192.{random.randint(100, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}",
            "registrar": "NAMECHEAP",
            "creation_date": (base_time + timedelta(days=random.randint(0, 7))).isoformat(),
            "name_servers": ",".join(ns2),
            "hosting_provider": "ShieldHost",
            "asn": "AS67890",
            "linked_upi_id": f"{random.choice(['neha', 'priya', 'pooja'])}@paytm",
            "linked_phone": f"+91{random.randint(7000000000, 9999999999)}",
            "is_scam": "true",
            "case_id": case_id
        })

    clusters.append({"id": "cluster_2", "domains": cluster2_domains})

    # Cluster 3: Typosquats (high string similarity)
    cluster3_domains = []
    base_domain = "statebank"
    variations = ["statebnak", "statebnk", "stat3bank", "statebank0nline", "statehank"]

    for var in variations[:random.randint(3, 5)]:
        cluster3_domains.append({
            "domain": f"{var}.com",
            "ip": f"203.{random.randint(100, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}",
            "registrar": "GODADDY",
            "creation_date": (base_time + timedelta(days=random.randint(0, 5))).isoformat(),
            "name_servers": f"ns{random.randint(1, 10)}.parkingcrew.net,ns{random.randint(1, 10)}.parkingcrew.net",
            "hosting_provider": "CloudFront",
            "asn": "AS13335",
            "linked_upi_id": f"merchant{random.randint(100, 999)}@paytm",
            "linked_phone": f"+91{random.randint(7000000000, 9999999999)}",
            "is_scam": "true",
            "case_id": case_id
        })

    clusters.append({"id": "cluster_3", "domains": cluster3_domains})

    # Add benign domains (noise)
    benign_domains = []
    for i in range(random.randint(10, 15)):
        benign_domains.append({
            "domain": f"{random.choice(['shop', 'store', 'market', 'deals'])}{random.randint(100, 999)}.com",
            "ip": f"{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}",
            "registrar": random.choice(["NAMECHEAP", "GODADDY", "HOSTINGER", "CLOUDFLARE"]),
            "creation_date": (datetime.now() - timedelta(days=random.randint(100, 1000))).isoformat(),
            "name_servers": f"ns1.{random.choice(['cloudflare', 'aws', 'google'])}.com,ns2.{random.choice(['cloudflare', 'aws', 'google'])}.com",
            "hosting_provider": random.choice(["AWS", "Google Cloud", "Azure"]),
            "asn": f"AS{random.randint(10000, 99999)}",
            "linked_upi_id": "",
            "linked_phone": "",
            "is_scam": "false",
            "case_id": case_id
        })

    # Combine all
    all_domains = []
    for cluster in clusters:
        all_domains.extend(cluster["domains"])
    all_domains.extend(benign_domains)

    # Shuffle
    random.shuffle(all_domains)

    return {
        "clusters": clusters,
        "all_domains": all_domains,
        "num_scam_domains": len([d for d in all_domains if d["is_scam"] == "true"]),
        "num_clusters": len(clusters)
    }

def save_infrastructure_csv(domains: list, filepath: Path):
    """Save infrastructure data as CSV."""
    with open(filepath, 'w', newline='') as f:
        fieldnames = ["domain", "ip", "registrar", "creation_date", "name_servers",
                      "hosting_provider", "asn", "linked_upi_id", "linked_phone",
                      "is_scam", "case_id"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(domains)

def main():
    output_dir = Path(__file__).parent.parent / "sample_data"
    output_dir.mkdir(exist_ok=True)

    print("Generating synthetic fraud data...")

    # Generate multiple cases
    cases_meta = []
    all_infra_data = []

    for i in range(1, 4):  # 3 cases
        case_id = f"case_{i:03d}"
        use_shared = i > 1  # Case 2 and 3 can share mules
        gt = generate_case(case_id, output_dir, seed=42 + i, use_shared=use_shared)
        cases_meta.append(gt)

        # Generate infrastructure data for this case
        infra_data = generate_infrastructure_data(case_id, seed=100 + i)

        # Save infrastructure CSV
        case_dir = output_dir / case_id
        save_infrastructure_csv(infra_data["all_domains"], case_dir / "infrastructure.csv")

        # Save ground truth for clusters
        with open(case_dir / "infra_ground_truth.json", "w") as f:
            json.dump({
                "case_id": case_id,
                "clusters": infra_data["clusters"],
                "num_scam_domains": infra_data["num_scam_domains"],
                "num_clusters": infra_data["num_clusters"]
            }, f, indent=2)

        all_infra_data.append({
            "case_id": case_id,
            "num_scam_domains": infra_data["num_scam_domains"],
            "num_clusters": infra_data["num_clusters"]
        })

        print(f"Generated infrastructure for {case_id}: {infra_data['num_scam_domains']} scam domains, {infra_data['num_clusters']} clusters")

    # Save master metadata
    with open(output_dir / "cases_metadata.json", "w") as f:
        json.dump({
            "cases": cases_meta,
            "shared_mules": [m.id for m in SHARED_MULES],
            "infrastructure": all_infra_data,
            "generated_at": datetime.now().isoformat(),
        }, f, indent=2)

    print(f"\nGeneration complete!")
    print(f"Output: {output_dir}")
    print(f"Shared mules across cases: {len(SHARED_MULES)}")
    print(f"Total scam domains: {sum(i['num_scam_domains'] for i in all_infra_data)}")

if __name__ == "__main__":
    main()
