"""Pydantic models for API."""

from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class CaseCreate(BaseModel):
    case_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    victim_account: Optional[str] = None

class CaseResponse(BaseModel):
    id: int
    case_id: str
    title: str
    description: Optional[str]
    victim_account: Optional[str]
    created_at: datetime
    analyzed_at: Optional[datetime]

    class Config:
        from_attributes = True

class AnalyzeRequest(BaseModel):
    victim_account: Optional[str] = None  # Auto-detect if not provided

class AnalyzeResponse(BaseModel):
    case_id: str
    status: str
    message: str
    stats: Dict[str, Any]

class GraphResponse(BaseModel):
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    stats: Dict[str, Any]

class SuspectsResponse(BaseModel):
    suspects: List[Dict[str, Any]]
    total_count: int

class FreezePriorityResponse(BaseModel):
    rankings: List[Dict[str, Any]]
    recovery_curve: List[List[float]]  # [[num_frozen, total_recovery], ...]
    total_estimated_recovery: float

class LinkedCasesResponse(BaseModel):
    account: str
    linked_cases: List[Dict[str, Any]]
    is_repeat_offender: bool
