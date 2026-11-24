"""Database operations for case management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime

from .models import Base, Case, Account, Transaction

class CaseDB:
    """Database manager for cases."""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = "sqlite:///tracefreeze.db"
        elif not db_path.startswith("sqlite"):
            db_path = f"sqlite:///{db_path}"

        self.engine = create_engine(db_path)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def create_case(self, case_id: str, title: str = None, description: str = None,
                   victim_account: str = None) -> Case:
        """Create a new case."""
        session = self.Session()
        try:
            case = Case(
                case_id=case_id,
                title=title or f"Case {case_id}",
                description=description,
                victim_account=victim_account
            )
            session.add(case)
            session.commit()
            session.refresh(case)
            return case
        finally:
            session.close()

    def get_case(self, case_id: str) -> Optional[Case]:
        """Get case by ID."""
        session = self.Session()
        try:
            return session.query(Case).filter(Case.case_id == case_id).first()
        finally:
            session.close()

    def list_cases(self) -> List[Case]:
        """List all cases."""
        session = self.Session()
        try:
            return session.query(Case).order_by(Case.created_at.desc()).all()
        finally:
            session.close()

    def save_analysis(self, case_id: str, graph_data: Dict, trace_data: Dict,
                     suspects: List[Dict], freeze_rankings: List[Dict]) -> Case:
        """Save analysis results to case."""
        session = self.Session()
        try:
            case = session.query(Case).filter(Case.case_id == case_id).first()
            if not case:
                raise ValueError(f"Case {case_id} not found")

            case.graph_data = graph_data
            case.trace_data = {
                "total_traced": trace_data.total_traced,
                "num_accounts": len(trace_data.traced_accounts),
                "victim": trace_data.victim_account
            }
            case.suspects_data = suspects
            case.freeze_rankings = freeze_rankings
            case.analyzed_at = datetime.utcnow()

            # Save accounts for cross-case linking
            for suspect in suspects:
                account = Account(
                    case_id=case.id,
                    account_number=suspect["account"],
                    bank=graph_data["nodes"][0].get("bank", "UNKNOWN") if graph_data["nodes"] else "UNKNOWN",
                    is_mule=1 if suspect.get("risk_level") in ["HIGH", "MEDIUM"] else 0,
                    suspicion_score=suspect.get("suspicion_score", 0),
                    risk_level=suspect.get("risk_level", "LOW")
                )
                session.add(account)

            session.commit()
            session.refresh(case)
            return case
        finally:
            session.close()

    def find_linked_cases(self, account_number: str) -> List[Dict]:
        """Find other cases involving this account (cross-case linking)."""
        session = self.Session()
        try:
            accounts = session.query(Account).filter(
                Account.account_number == account_number
            ).all()

            linked = []
            for acc in accounts:
                case = session.query(Case).filter(Case.id == acc.case_id).first()
                if case:
                    linked.append({
                        "case_id": case.case_id,
                        "title": case.title,
                        "created_at": case.created_at.isoformat() if case.created_at else None,
                        "suspicion_score": acc.suspicion_score,
                        "risk_level": acc.risk_level,
                    })

            return linked
        finally:
            session.close()

    def get_repeat_mules(self, min_cases: int = 2) -> List[Dict]:
        """Find accounts appearing in multiple cases (repeat offenders)."""
        session = self.Session()
        try:
            from sqlalchemy import func

            # Group by account_number and count cases
            results = session.query(
                Account.account_number,
                func.count(func.distinct(Account.case_id)).label("case_count"),
                func.avg(Account.suspicion_score).label("avg_score")
            ).group_by(Account.account_number).having(
                func.count(func.distinct(Account.case_id)) >= min_cases
            ).all()

            repeat_mules = []
            for acc_num, count, avg_score in results:
                linked_cases = self.find_linked_cases(acc_num)
                repeat_mules.append({
                    "account": acc_num,
                    "case_count": count,
                    "avg_suspicion_score": float(avg_score),
                    "linked_cases": linked_cases
                })

            return repeat_mules
        finally:
            session.close()

    def save_transactions(self, case_id: str, transactions: List[Dict]):
        """Save transactions for a case."""
        session = self.Session()
        try:
            case = session.query(Case).filter(Case.case_id == case_id).first()
            if not case:
                raise ValueError(f"Case {case_id} not found")

            for txn in transactions:
                transaction = Transaction(
                    case_id=case.id,
                    txn_id=txn["txn_id"],
                    timestamp=txn["timestamp"],
                    from_account=txn["from_account"],
                    to_account=txn["to_account"],
                    amount=txn["amount"],
                    mode=txn["mode"],
                    bank=txn.get("bank", "UNKNOWN"),
                    narration=txn.get("narration", "")
                )
                session.add(transaction)

            session.commit()
        finally:
            session.close()
