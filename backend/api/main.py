"""
FINTRACE FastAPI application.
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import List
from pathlib import Path
import shutil
import tempfile

from .models import (
    CaseCreate, CaseResponse, AnalyzeRequest, AnalyzeResponse,
    GraphResponse, SuspectsResponse, FreezePriorityResponse, LinkedCasesResponse
)
from backend.db.operations import CaseDB
from backend.ingest.parsers import parse_statement
from backend.ingest.normalize import normalize_transactions, infer_account_from_filename
from backend.graph.builder import build_graph
from backend.graph.tracer import trace_from_victim
from backend.detection.features import extract_features
from backend.detection.ml import detect_anomalies
from backend.detection.scoring import score_accounts
from backend.priority.ranker import rank_freeze_priority, calculate_recovery_curve

app = FastAPI(
    title="FINTRACE API",
    description="Money-trail analysis and freeze priority engine",
    version="1.0.0"
)

# CORS - restrict to frontend origin
# For production, set environment variable: ALLOWED_ORIGINS="https://fintrace.police.gov.in"
import os
allowed_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database
db = CaseDB()

# Temporary upload directory
UPLOAD_DIR = Path("./uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

@app.get("/")
def read_root():
    return {"message": "FINTRACE API", "version": "1.0.0"}

@app.post("/cases", response_model=CaseResponse)
def create_case(case: CaseCreate):
    """Create a new case."""
    try:
        db_case = db.create_case(
            case_id=case.case_id,
            title=case.title,
            description=case.description,
            victim_account=case.victim_account
        )
        return db_case
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/cases", response_model=List[CaseResponse])
def list_cases():
    """List all cases."""
    return db.list_cases()

@app.get("/cases/{case_id}", response_model=CaseResponse)
def get_case(case_id: str):
    """Get case details."""
    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case

@app.post("/cases/{case_id}/upload")
async def upload_statements(case_id: str, files: List[UploadFile] = File(...)):
    """Upload bank statement files for a case."""
    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Validate case_id format
    import re
    if not re.match(r'^[a-zA-Z0-9_-]+$', case_id):
        raise HTTPException(status_code=400, detail="Invalid case ID format")

    # Save uploaded files
    case_dir = UPLOAD_DIR / case_id
    case_dir.mkdir(exist_ok=True)

    # Allowed file types
    ALLOWED_EXTENSIONS = {'.csv', '.xlsx', '.pdf'}
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

    uploaded = []
    for file in files:
        # Validate file type
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"File type {file_ext} not allowed. Allowed: {ALLOWED_EXTENSIONS}")

        # Sanitize filename to prevent path traversal
        import os
        safe_filename = os.path.basename(file.filename)

        # Additional check: ensure no path separators
        if '/' in safe_filename or '\\' in safe_filename or '..' in safe_filename:
            raise HTTPException(status_code=400, detail="Invalid filename")

        file_path = case_dir / safe_filename

        # Check file size
        file.file.seek(0, 2)  # Seek to end
        file_size = file.file.tell()
        file.file.seek(0)  # Seek back to start

        if file_size > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"File {safe_filename} exceeds maximum size of {MAX_FILE_SIZE/(1024*1024)}MB")

        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        uploaded.append(safe_filename)

    return {
        "case_id": case_id,
        "uploaded_files": uploaded,
        "count": len(uploaded)
    }

@app.post("/cases/{case_id}/analyze", response_model=AnalyzeResponse)
async def analyze_case(case_id: str, request: AnalyzeRequest):
    """Analyze a case: parse statements, build graph, detect mules, rank freeze priority."""
    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    case_dir = UPLOAD_DIR / case_id
    if not case_dir.exists():
        raise HTTPException(status_code=400, detail="No files uploaded for this case")

    try:
        # Parse all statements
        all_transactions = []
        statement_files = list(case_dir.glob("*.csv")) + \
                         list(case_dir.glob("*.xlsx")) + \
                         list(case_dir.glob("*.pdf"))

        for statement_file in statement_files:
            parsed = parse_statement(statement_file)
            account = infer_account_from_filename(str(statement_file))
            normalized = normalize_transactions(parsed, account)
            all_transactions.extend(normalized)

        if not all_transactions:
            raise HTTPException(status_code=400, detail="No transactions parsed from uploaded files")

        # Build graph
        graph = build_graph(all_transactions)

        # Find victim if not provided
        victim_account = request.victim_account
        if not victim_account:
            # Auto-detect: account with largest outflow
            candidates = []
            for node in graph.graph.nodes():
                info = graph.get_account_info(node)
                if info["total_outflow"] > 50000:
                    candidates.append((node, info["total_outflow"]))

            if candidates:
                candidates.sort(key=lambda x: x[1], reverse=True)
                victim_account = candidates[0][0]
            else:
                victim_account = list(graph.graph.nodes())[0]  # Fallback

        # Trace from victim
        trace_result = trace_from_victim(graph.graph, victim_account)

        # Extract features
        features_list = extract_features(graph, trace_result.traced_accounts)

        # ML anomaly detection
        features_list = detect_anomalies(features_list)

        # Score accounts
        scored = score_accounts(features_list)

        # Rank freeze priority
        freeze_rankings = rank_freeze_priority(scored, graph.graph)

        # Save to database
        graph_json = graph.to_json()
        db.save_analysis(
            case_id=case_id,
            graph_data=graph_json,
            trace_data=trace_result,
            suspects=scored,
            freeze_rankings=freeze_rankings
        )
        db.save_transactions(case_id, all_transactions)

        return AnalyzeResponse(
            case_id=case_id,
            status="success",
            message="Analysis complete",
            stats={
                "num_transactions": len(all_transactions),
                "num_accounts": len(graph.graph.nodes()),
                "num_traced": len(trace_result.traced_accounts),
                "total_traced_amount": trace_result.total_traced,
                "num_suspects": len([s for s in scored if s["risk_level"] in ["HIGH", "MEDIUM"]]),
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.get("/cases/{case_id}/graph", response_model=GraphResponse)
def get_graph(case_id: str):
    """Get transaction graph for a case."""
    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not case.graph_data:
        raise HTTPException(status_code=400, detail="Case not analyzed yet")

    return case.graph_data

@app.get("/cases/{case_id}/suspects", response_model=SuspectsResponse)
def get_suspects(case_id: str, min_score: float = 0, risk_level: str = None):
    """Get suspicious accounts for a case."""
    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not case.suspects_data:
        raise HTTPException(status_code=400, detail="Case not analyzed yet")

    suspects = case.suspects_data

    # Filter by score
    if min_score > 0:
        suspects = [s for s in suspects if s.get("suspicion_score", 0) >= min_score]

    # Filter by risk level
    if risk_level:
        suspects = [s for s in suspects if s.get("risk_level") == risk_level.upper()]

    return SuspectsResponse(
        suspects=suspects,
        total_count=len(suspects)
    )

@app.get("/cases/{case_id}/freeze-priority", response_model=FreezePriorityResponse)
def get_freeze_priority(case_id: str, top_n: int = None):
    """Get freeze priority rankings for a case."""
    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not case.freeze_rankings:
        raise HTTPException(status_code=400, detail="Case not analyzed yet")

    rankings = case.freeze_rankings

    if top_n:
        rankings = rankings[:top_n]

    # Calculate recovery curve
    recovery_curve = calculate_recovery_curve(case.freeze_rankings)

    return FreezePriorityResponse(
        rankings=rankings,
        recovery_curve=[[n, amt] for n, amt in recovery_curve],
        total_estimated_recovery=recovery_curve[-1][1] if recovery_curve else 0.0
    )

@app.get("/cases/{case_id}/report")
async def download_report(case_id: str):
    """Download PDF report for a case."""
    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not case.analyzed_at:
        raise HTTPException(status_code=400, detail="Case not analyzed yet")

    # Generate PDF report (placeholder - will implement in phase 8)
    from backend.reports.generator import generate_report

    report_path = generate_report(case)

    return FileResponse(
        report_path,
        media_type="application/pdf",
        filename=f"{case_id}_report.pdf"
    )

@app.get("/accounts/{account}/linked-cases", response_model=LinkedCasesResponse)
def get_linked_cases(account: str):
    """Get cases linked to an account (cross-case analysis)."""
    linked = db.find_linked_cases(account)

    return LinkedCasesResponse(
        account=account,
        linked_cases=linked,
        is_repeat_offender=len(linked) > 1
    )

@app.get("/repeat-mules")
def get_repeat_mules(min_cases: int = 2):
    """Get accounts appearing in multiple cases."""
    return db.get_repeat_mules(min_cases=min_cases)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
