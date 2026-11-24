"""Intent definitions for natural language query parsing."""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from enum import Enum

class Intent(Enum):
    """Query intent types."""
    LIST_ACCOUNTS = "list_accounts"
    TRACE_MONEY = "trace_money"
    FREEZE_PRIORITY = "freeze_priority"
    DOMAIN_CLUSTER = "domain_cluster"
    PATH_BETWEEN = "path_between"
    CROSS_CASE_LINKS = "cross_case_links"
    SHOW_SUSPICIOUS = "show_suspicious"
    FIND_CROSS_LINKS = "find_cross_links"
    GET_NEIGHBORS = "get_neighbors"
    UNKNOWN = "unknown"

@dataclass
class QueryResult:
    """Result of executing a query."""
    intent: Intent
    success: bool
    data: Any
    explanation: str
    evidence: List[Dict]  # Grounded evidence (node/edge IDs, scores, etc.)
    sql_query: Optional[str] = None  # For audit log

    def to_dict(self) -> Dict:
        return {
            "intent": self.intent.value,
            "success": self.success,
            "data": self.data,
            "explanation": self.explanation,
            "evidence": self.evidence,
            "sql_query": self.sql_query
        }
