"""Audit logging for AI assistant queries."""

from datetime import datetime
from typing import Dict, Optional

class AuditLog:
    """In-memory audit log for assistant queries."""

    def __init__(self):
        self.logs = []

    def log_query(
        self,
        case_id: str,
        user: str,
        query: str,
        intent: str,
        result: Dict,
        timestamp: Optional[datetime] = None
    ):
        """
        Log a query execution.

        Args:
            case_id: Case ID
            user: User who made the query (default: "investigator")
            query: Natural language query
            intent: Detected intent
            result: Query result dict
            timestamp: Optional timestamp (defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.utcnow()

        log_entry = {
            "case_id": case_id,
            "user": user,
            "query": query,
            "intent": intent,
            "success": result.get("success", False),
            "num_results": len(result.get("data", [])) if result.get("data") else 0,
            "timestamp": timestamp.isoformat(),
            "explanation": result.get("explanation", "")
        }

        self.logs.append(log_entry)

    def get_logs(self, case_id: Optional[str] = None, limit: int = 100) -> list:
        """
        Get audit logs.

        Args:
            case_id: Optional filter by case ID
            limit: Max number of logs to return

        Returns:
            List of log entries
        """
        logs = self.logs

        if case_id:
            logs = [log for log in logs if log["case_id"] == case_id]

        return logs[-limit:]  # Most recent first

    def export_for_report(self, case_id: str) -> str:
        """
        Export audit log as text for PDF report.

        Args:
            case_id: Case ID

        Returns:
            Formatted audit log text
        """
        case_logs = self.get_logs(case_id)

        if not case_logs:
            return "No assistant queries logged for this case."

        lines = ["AI Assistant Query Log", "=" * 60, ""]

        for i, log in enumerate(case_logs, 1):
            lines.append(f"{i}. [{log['timestamp']}] {log['user']}")
            lines.append(f"   Query: {log['query']}")
            lines.append(f"   Intent: {log['intent']}")
            lines.append(f"   Result: {log['explanation']}")
            lines.append("")

        return "\n".join(lines)

# Global audit log instance
audit_log = AuditLog()

def log_query(query: str, intent: str, case_id: str, user: str = "investigator"):
    """Convenience function to log a query."""
    audit_log.log_query(
        case_id=case_id,
        user=user,
        query=query,
        intent=intent,
        result={"success": True, "explanation": f"Intent: {intent}"}
    )

def get_audit_log(limit: int = 100):
    """Convenience function to get audit logs."""
    return audit_log.get_logs(limit=limit)
