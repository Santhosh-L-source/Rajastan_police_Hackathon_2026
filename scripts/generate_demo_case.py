#!/usr/bin/env python3
"""Generate polished demo case for hackathon presentation."""

import sys
sys.path.insert(0, '.')

import csv
import json
from pathlib import Path
import random
from datetime import datetime, timedelta

def generate_demo_case():
    """Generate Case 001 – Cyber Fraud Demo with realistic fraud pattern."""

    case_dir = Path("sample_data/case_001")
    case_dir.mkdir(parents=True, exist_ok=True)

    # Victim loses Rs 5,00,000
    victim_account = "VICTIM_9876543210"
    victim_amount = 500000

    # Layer 1: 5 primary mule accounts (receive from victim)
    layer1_mules = [f"MULE_L1_{i:02d}@paytm" for i in range(1, 6)]

    # Layer 2: 10 secondary mules (receive from layer 1)
    layer2_mules = [f"ICICI_ACC_{1000 + i}" for i in range(1, 11)]

    # Layer 3: 8 tertiary mules (receive from layer 2)
    layer3_mules = [f"HDFC_ACC_{2000 + i}" for i in range(1, 9)]

    # Exits: ATM and crypto
    exits = ["ATM_WITHDRAWAL", "CRYPTO_EXCHANGE", "ATM_WITHDRAWAL_2"]

    # Generate transactions over 2 days
    base_time = datetime(2024, 1, 15, 10, 0)
    transactions = []

    # Victim -> Layer 1 (within 1 hour)
    amounts_l1 = [100000, 120000, 80000, 110000, 90000]  # Total: 500,000
    for i, (mule, amt) in enumerate(zip(layer1_mules, amounts_l1)):
        txn_time = base_time + timedelta(minutes=i * 10)
        transactions.append({
            "txn_id": f"TXN_{len(transactions)+1:04d}",
            "from_account": victim_account,
            "to_account": mule,
            "amount": amt,
            "timestamp": txn_time.strftime("%Y-%m-%d %H:%M:%S"),
        })

    # Layer 1 -> Layer 2 (2-4 hours later)
    l1_to_l2_mapping = {0: [0, 1], 1: [2, 3], 2: [4, 5], 3: [6, 7], 4: [8, 9]}
    for l1_idx, l2_indices in l1_to_l2_mapping.items():
        l1_amount = amounts_l1[l1_idx]
        split = l1_amount // len(l2_indices)
        txn_time = base_time + timedelta(hours=2 + l1_idx * 0.5)
        for l2_idx in l2_indices:
            transactions.append({
                "txn_id": f"TXN_{len(transactions)+1:04d}",
                "from_account": layer1_mules[l1_idx],
                "to_account": layer2_mules[l2_idx],
                "amount": split - 1000,
                "timestamp": txn_time.strftime("%Y-%m-%d %H:%M:%S"),
            })

    # Layer 2 -> Layer 3 (8-12 hours later)
    l2_to_l3_mapping = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 7, 9: 6}
    for l2_idx, l3_idx in l2_to_l3_mapping.items():
        l2_amount = amounts_l1[l2_idx // 2] // 2 - 1000
        txn_time = base_time + timedelta(hours=10 + l2_idx * 0.3)
        transactions.append({
            "txn_id": f"TXN_{len(transactions)+1:04d}",
            "from_account": layer2_mules[l2_idx],
            "to_account": layer3_mules[l3_idx],
            "amount": int(l2_amount * 0.95),
            "timestamp": txn_time.strftime("%Y-%m-%d %H:%M:%S"),
        })

    # Layer 3 -> Exits (24-30 hours later)
    for i, l3_mule in enumerate(layer3_mules):
        exit_node = exits[i % len(exits)]
        txn_time = base_time + timedelta(hours=26 + i * 0.5)
        exit_amount = 45000 + random.randint(-5000, 5000)
        transactions.append({
            "txn_id": f"TXN_{len(transactions)+1:04d}",
            "from_account": l3_mule,
            "to_account": exit_node,
            "amount": exit_amount,
            "timestamp": txn_time.strftime("%Y-%m-%d %H:%M:%S"),
        })

    # Write CSV
    csv_path = case_dir / "DEMO_statement.csv"
    with open(csv_path, "w", newline="") as f:
        f.write("txn_id,from_account,to_account,amount,timestamp\n")
        for txn in transactions:
            f.write(f"{txn['txn_id']},{txn['from_account']},{txn['to_account']},{txn['amount']},{txn['timestamp']}\n")

    print(f"Generated {len(transactions)} transactions")

    # ─── Infrastructure: TWO scam clusters ───────────────────────
    # NO legitimate domains – only scam typosquats grouped in 2 clusters.
    # Each cluster has shared IP, NS, registrar, tight creation window,
    # hosting ASN, and a linked UPI that matches a mule in the graph.

    domains = []

    # ── Cluster 1: SBI typosquats (IP 103.21.244.15) ──
    cluster1_ip = "103.21.244.15"
    cluster1_ns = ["ns1.scamhost.com", "ns2.scamhost.com"]
    cluster1_registrar = "GoDaddy"
    cluster1_base_date = datetime(2024, 1, 10)
    cluster1_asn = "AS13335"
    cluster1_upi = layer1_mules[2]  # MULE_L1_03@paytm

    cluster1_domains = [
        "sbi-login.com",
        "sbionline-secure.com",
        "sbi-verify.com",
        "sbionlinebanking.net",
        "sbi-account.com",
    ]

    for i, domain in enumerate(cluster1_domains):
        creation = cluster1_base_date + timedelta(hours=i * 8)  # all within 2 days
        domains.append({
            "domain": domain,
            "ip_addresses": cluster1_ip,
            "name_servers": ",".join(cluster1_ns),
            "registrar": cluster1_registrar,
            "creation_date": creation.strftime("%Y-%m-%d"),
            "asn": cluster1_asn,
            "upi_ids": cluster1_upi if i == 0 else "",
            "phone_numbers": "+91-9876543210" if i == 0 else "",
            "is_scam": "true",
        })

    # ── Cluster 2: HDFC typosquats (IP 185.70.40.22) ──
    cluster2_ip = "185.70.40.22"
    cluster2_ns = ["ns1.bulletproof.xyz", "ns2.bulletproof.xyz"]
    cluster2_registrar = "Namecheap"
    cluster2_base_date = datetime(2024, 1, 12)
    cluster2_asn = "AS62904"
    cluster2_upi = layer1_mules[4]  # MULE_L1_05@paytm

    cluster2_domains = [
        "hdfc-netbanking.com",
        "hdfcbank-login.in",
        "secure-hdfc.com",
        "hdfc-otp-verify.com",
        "hdfconline-secure.net",
    ]

    for i, domain in enumerate(cluster2_domains):
        creation = cluster2_base_date + timedelta(hours=i * 6)
        domains.append({
            "domain": domain,
            "ip_addresses": cluster2_ip,
            "name_servers": ",".join(cluster2_ns),
            "registrar": cluster2_registrar,
            "creation_date": creation.strftime("%Y-%m-%d"),
            "asn": cluster2_asn,
            "upi_ids": cluster2_upi if i == 0 else "",
            "phone_numbers": "+91-8765432109" if i == 0 else "",
            "is_scam": "true",
        })

    # Write infrastructure CSV
    infra_path = case_dir / "infrastructure.csv"
    with open(infra_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "domain", "ip_addresses", "name_servers", "registrar",
            "creation_date", "asn", "upi_ids", "phone_numbers", "is_scam",
        ])
        for d in domains:
            writer.writerow([
                d["domain"], d["ip_addresses"], d["name_servers"],
                d["registrar"], d["creation_date"], d["asn"],
                d["upi_ids"], d["phone_numbers"], d["is_scam"],
            ])

    print(f"Generated {len(domains)} scam domains in 2 clusters")
    print(f"  Cluster 1  SBI-typosquats  UPI={cluster1_upi}")
    print(f"  Cluster 2  HDFC-typosquats UPI={cluster2_upi}")

    # Write metadata
    metadata = {
        "case_id": "case_001",
        "title": "Case 001 – Cyber Fraud Demo",
        "description": "Phishing scam with typosquat domains and layered money laundering",
        "victim_account": victim_account,
        "victim_loss": victim_amount,
        "num_mules": len(layer1_mules) + len(layer2_mules) + len(layer3_mules),
        "num_transactions": len(transactions),
        "num_domains": len(domains),
        "time_window": "30 hours",
        "case_date": "2024-01-15",
    }
    metadata_path = case_dir / "metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print("\nOK Demo case generated successfully")
    print(f"  - {metadata['num_transactions']} transactions")
    print(f"  - {metadata['num_mules']} mule accounts across 3 layers")
    print(f"  - {metadata['num_domains']} scam domains (0 legitimate)")


if __name__ == "__main__":
    generate_demo_case()
