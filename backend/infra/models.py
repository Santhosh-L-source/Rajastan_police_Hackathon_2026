"""Infrastructure intelligence data models."""

from dataclasses import dataclass
from typing import List, Optional, Set
from datetime import datetime

@dataclass
class Domain:
    """Represents a domain with WHOIS/DNS data."""
    domain: str
    ip: Optional[str] = None
    registrar: Optional[str] = None
    creation_date: Optional[datetime] = None
    name_servers: List[str] = None
    hosting_provider: Optional[str] = None
    asn: Optional[str] = None
    linked_upi_id: Optional[str] = None
    linked_phone: Optional[str] = None
    is_scam: bool = False  # Ground truth
    case_id: Optional[str] = None

    def __post_init__(self):
        if self.name_servers is None:
            self.name_servers = []

@dataclass
class InfraCluster:
    """Represents a cluster of related infrastructure entities."""
    cluster_id: str
    domains: List[Domain]
    shared_features: dict
    score: float
    explanation: str
    is_true_cluster: bool = False  # Ground truth
