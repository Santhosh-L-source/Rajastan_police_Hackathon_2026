"""Parser for infrastructure CSV/JSON data."""

import csv
import json
from pathlib import Path
from typing import List
from datetime import datetime

from .models import Domain

def parse_infra_csv(filepath: Path) -> List[Domain]:
    """
    Parse infrastructure CSV file.

    Expected columns:
    domain, ip, registrar, creation_date, name_servers, hosting_provider, asn, linked_upi_id, linked_phone

    Returns:
        List of Domain objects
    """
    domains = []

    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)

        for row in reader:
            # Parse name servers (comma-separated)
            name_servers = []
            if row.get('name_servers'):
                name_servers = [ns.strip() for ns in row['name_servers'].split(',')]

            # Parse creation date
            creation_date = None
            if row.get('creation_date'):
                try:
                    creation_date = datetime.fromisoformat(row['creation_date'])
                except:
                    try:
                        creation_date = datetime.strptime(row['creation_date'], "%Y-%m-%d")
                    except:
                        pass

            domain = Domain(
                domain=row['domain'],
                ip=row.get('ip') or row.get('ip_addresses') or None,
                registrar=row.get('registrar') or None,
                creation_date=creation_date,
                name_servers=name_servers,
                hosting_provider=row.get('hosting_provider') or None,
                asn=row.get('asn') or None,
                linked_upi_id=row.get('linked_upi_id') or row.get('upi_ids') or None,
                linked_phone=row.get('linked_phone') or row.get('phone_numbers') or None,
                is_scam=row.get('is_scam', '').lower() == 'true',
                case_id=row.get('case_id')
            )

            domains.append(domain)

    return domains

def parse_infra_json(filepath: Path) -> List[Domain]:
    """Parse infrastructure JSON file."""
    with open(filepath, 'r') as f:
        data = json.load(f)

    domains = []

    for item in data:
        creation_date = None
        if item.get('creation_date'):
            try:
                creation_date = datetime.fromisoformat(item['creation_date'])
            except:
                pass

        domain = Domain(
            domain=item['domain'],
            ip=item.get('ip'),
            registrar=item.get('registrar'),
            creation_date=creation_date,
            name_servers=item.get('name_servers', []),
            hosting_provider=item.get('hosting_provider'),
            asn=item.get('asn'),
            linked_upi_id=item.get('linked_upi_id'),
            linked_phone=item.get('linked_phone'),
            is_scam=item.get('is_scam', False),
            case_id=item.get('case_id')
        )

        domains.append(domain)

    return domains
