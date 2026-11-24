"""SQLAlchemy models for case storage."""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Case(Base):
    """Case record."""
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True)
    case_id = Column(String(100), unique=True, nullable=False, index=True)
    title = Column(String(200))
    description = Column(Text)
    victim_account = Column(String(100), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    analyzed_at = Column(DateTime)

    # Analysis results (JSON)
    graph_data = Column(JSON)  # Graph JSON from builder.to_json()
    trace_data = Column(JSON)  # Trace results
    suspects_data = Column(JSON)  # Scored suspects
    freeze_rankings = Column(JSON)  # Freeze priority list

    # Relationships
    accounts = relationship("Account", back_populates="case", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="case", cascade="all, delete-orphan")

class Account(Base):
    """Account record (for cross-case linking)."""
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False, index=True)
    account_number = Column(String(100), nullable=False, index=True)
    bank = Column(String(50))
    upi_id = Column(String(100), index=True)

    # Detection results
    is_mule = Column(Integer, default=0)  # 0 = unknown, 1 = suspected mule, -1 = normal
    suspicion_score = Column(Float, default=0.0)
    risk_level = Column(String(20))

    # Relationships
    case = relationship("Case", back_populates="accounts")

class Transaction(Base):
    """Transaction record."""
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False, index=True)
    txn_id = Column(String(100), nullable=False)
    timestamp = Column(DateTime)
    from_account = Column(String(100), index=True)
    to_account = Column(String(100), index=True)
    amount = Column(Float)
    mode = Column(String(20))
    bank = Column(String(50))
    narration = Column(Text)

    # Relationships
    case = relationship("Case", back_populates="transactions")
