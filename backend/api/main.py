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
    GraphResponse, SuspectsResponse, FreezePriorityResponse, LinkedCasesResponse,
    AskRequest, AskResponse
)
from backend.db.operations import CaseDB
from backend.db.models import Transaction
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
allowed_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001,http://localhost:5173").split(",")

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
        # Parse all statements (exclude infrastructure.csv)
        all_transactions = []
        statement_files = [f for f in case_dir.glob("*.csv") if f.name != "infrastructure.csv"] + \
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

        # Annotate each scored account with its hop from victim
        for s in scored:
            acc = s.get("account", "")
            if acc in trace_result.hops:
                s["hop"] = trace_result.hops[acc]
            elif any(acc.startswith(p) for p in ("ATM", "CRYPTO", "EXTERNAL")):
                s["hop"] = max(trace_result.hops.values(), default=0) + 1
            else:
                s["hop"] = -1

        # Rank freeze priority (exclude victim/exits, cap at victim loss)
        freeze_rankings = rank_freeze_priority(scored, graph.graph, victim_loss=500000.0)

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

    # Calculate recovery curve (capped at victim loss)
    recovery_curve = calculate_recovery_curve(case.freeze_rankings, victim_loss=500000.0)

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

@app.post("/cases/{case_id}/ask")
async def ask_assistant(case_id: str, request: AskRequest):
    """Ask AI assistant a question about the case."""
    from backend.assistant.parser import parse_query_rule_based
    from backend.assistant.intents import Intent
    from backend.assistant.audit import log_query

    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not case.analyzed_at:
        raise HTTPException(status_code=400, detail="Case not analyzed yet")

    # Parse query intent
    intent, params = parse_query_rule_based(request.query)

    # Execute based on intent
    answer = ""
    evidence = []

    if intent == Intent.FREEZE_PRIORITY:
        top_n = params.get("top_n", 3)
        rankings = (case.freeze_rankings or [])[:top_n]

        answer = f"Top {top_n} accounts to freeze (by priority score):\n\n"
        for i, rank in enumerate(rankings, 1):
            answer += f"{i}. **{rank['account']}** (Score: {rank['freeze_priority_score']:.1f})\n"
            answer += f"   - Est. Recovery: ₹{rank['estimated_recovery']:,.0f}\n"
            answer += f"   - Downstream flow: ₹{rank.get('downstream_reach', 0):,.0f}\n\n"
            evidence.append(rank['account'])

        if rankings:
            total_recovery = sum(r['estimated_recovery'] for r in rankings)
            answer += f"**Total estimated recovery: ₹{total_recovery:,.0f}**"

    elif intent == Intent.FIND_CROSS_LINKS:
        domain = params.get("domain")
        upi = params.get("upi_id")

        # Try to load infrastructure clusters
        infra_file = UPLOAD_DIR / case_id / "infrastructure.csv"
        if infra_file.exists():
            from backend.infra.parser import parse_infra_csv
            domains = parse_infra_csv(infra_file)

            if domain:
                target_domain = next((d for d in domains if d.domain == domain), None)
                if target_domain and target_domain.upi_ids:
                    upis = target_domain.upi_ids.split(',')
                    answer = f"Domain **{domain}** is linked to:\n\n"
                    for u in upis:
                        answer += f"- UPI: {u.strip()}\n"
                        evidence.append(u.strip())
                else:
                    answer = f"No UPI links found for domain {domain}"

            elif upi:
                linked_domains = [d for d in domains if upi in (d.upi_ids or "")]
                if linked_domains:
                    answer = f"UPI **{upi}** is linked to:\n\n"
                    for d in linked_domains:
                        answer += f"- Domain: {d.domain}\n"
                        answer += f"  IP: {d.ip_addresses}\n"
                        evidence.append(d.domain)
                else:
                    answer = f"No domains found linked to UPI {upi}"
        else:
            answer = "No infrastructure data uploaded for this case"

    elif intent == Intent.TRACE_MONEY:
        source = params.get("source", case.victim_account)
        if source and source.lower() == "victim":
            source = case.victim_account
        graph_data = case.graph_data or {}
        edges = graph_data.get("edges", [])
        suspects = case.suspects_data or []
        suspect_map = {s["account"]: s for s in suspects}

        # Find direct recipients from source (Hop 1)
        direct_edges = [e for e in edges if e["source"].lower() == (source or "").lower()]
        if direct_edges:
            total_out = sum(e["amount"] for e in direct_edges)
            answer = f"Money trail from **{source}** ({len(direct_edges)} direct transfers totaling ₹{total_out:,.0f}):\n\n"
            for e in direct_edges:
                tgt = e["target"]
                s_info = suspect_map.get(tgt, {})
                score = s_info.get("suspicion_score", 0)
                risk = s_info.get("risk_level", "UNKNOWN")
                answer += f"- **{tgt}**: ₹{e['amount']:,.0f} (Score: {score:.1f}, {risk})\n"
                evidence.append(tgt)
        else:
            answer = f"No outgoing transfers found from {source}."

    elif intent == Intent.PATH_BETWEEN:
        source = params.get("source")
        target = params.get("target")

        if source and target:
            import networkx as nx
            graph_data = case.graph_data
            if graph_data:
                G = nx.DiGraph()
                node_lookup = {}
                for node in graph_data.get("nodes", []):
                    nid = node["id"]
                    node_lookup[nid.lower()] = nid
                for edge in graph_data.get("edges", []):
                    G.add_edge(edge["source"], edge["target"], amount=edge["amount"])
                    node_lookup[edge["source"].lower()] = edge["source"]
                    node_lookup[edge["target"].lower()] = edge["target"]

                if source.lower() == "victim" and case.victim_account:
                    source_resolved = case.victim_account
                else:
                    source_resolved = node_lookup.get(source.lower(), source)

                if target.lower() == "victim" and case.victim_account:
                    target_resolved = case.victim_account
                else:
                    target_resolved = node_lookup.get(target.lower(), target)

                try:
                    path = nx.shortest_path(G, source_resolved, target_resolved)
                    answer = f"Shortest path from **{source_resolved}** to **{target_resolved}** ({len(path)-1} hops):\n\n"
                    for i, node in enumerate(path):
                        if i < len(path) - 1:
                            amt = G[node][path[i+1]].get("amount", 0)
                            answer += f"{i+1}. **{node}** → ₹{amt:,.0f}\n"
                        else:
                            answer += f"{i+1}. **{node}** (Exit)\n"
                        evidence.append(node)
                except nx.NetworkXNoPath:
                    answer = f"No path found between {source_resolved} and {target_resolved}"
                except nx.NodeNotFound as e:
                    answer = f"Node not found: {e}"
            else:
                answer = "Graph data not available"
        else:
            answer = "Please specify both source and target entities"

    else:
        answer = "I understand your question, but I need more specific information to answer it. Try asking about:\n- Top accounts to freeze\n- Domains on same IP\n- Money trail from victim\n- Path between two accounts"
        evidence = []

    # Log query
    log_query(request.query, intent.value if hasattr(intent, 'value') else str(intent), case_id)

    return {
        "query": request.query,
        "intent": str(intent),
        "answer": answer,
        "evidence": evidence
    }

@app.post("/cases/{case_id}/infra/upload")
async def upload_infrastructure(case_id: str, file: UploadFile = File(...)):
    """Upload infrastructure CSV for a case."""
    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Validate file type
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files allowed for infrastructure data")

    # Save file
    case_dir = UPLOAD_DIR / case_id
    case_dir.mkdir(exist_ok=True)

    import os
    safe_filename = "infrastructure.csv"
    file_path = case_dir / safe_filename

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    return {"case_id": case_id, "uploaded": "infrastructure.csv"}

@app.get("/cases/{case_id}/infra/clusters")
async def get_infrastructure_clusters(case_id: str):
    """Get infrastructure clusters for a case."""
    from backend.infra.parser import parse_infra_csv
    from backend.infra.clustering import cluster_domains

    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Check if infrastructure file exists
    infra_file = UPLOAD_DIR / case_id / "infrastructure.csv"
    if not infra_file.exists():
        raise HTTPException(status_code=404, detail="No infrastructure data uploaded")

    # Parse and cluster
    domains = parse_infra_csv(infra_file)
    clusters = cluster_domains(domains)

    return {
        "case_id": case_id,
        "total_domains": len(domains),
        "total_clusters": len(clusters),
        "clusters": [
            {
                "cluster_id": c.cluster_id,
                "size": len(c.domains),
                "score": c.score,
                "explanation": c.explanation,
                "domains": [{"domain": d.domain, "is_scam": d.is_scam} for d in c.domains],
                "shared_ip": c.shared_features.get("shared_ips", ["–"])[0] if c.shared_features.get("shared_ips") else "–",
                "name_server": ", ".join(c.shared_features.get("shared_name_servers", [])[:2]),
                "registrar": ", ".join(c.shared_features.get("shared_registrars", [])),
                "creation_window": f"{c.shared_features.get('creation_time_span_hours', 0):.0f} hours",
                "asn": ", ".join(c.shared_features.get("shared_asns", [])),
                "linked_upis": c.shared_features.get("linked_upis", []),
                "linked_phones": c.shared_features.get("linked_phones", []),
                "typosquats": [
                    {"a": t[0], "b": t[1], "sim": round(t[2], 2)}
                    for t in c.shared_features.get("typosquats", [])
                ],
            }
            for c in clusters
        ],
    }

@app.get("/cases/{case_id}/unified-graph")
async def get_unified_graph(case_id: str):
    """Get unified graph (financial + infrastructure) for a case."""
    from backend.graph.unified import UnifiedGraph
    from backend.infra.parser import parse_infra_csv

    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not case.analyzed_at:
        raise HTTPException(status_code=400, detail="Case not analyzed yet")

    # Build unified graph
    ug = UnifiedGraph()

    # Add financial data from database
    transactions = db.session.query(Transaction).filter_by(case_id=case.id).all()
    financial_txns = [
        {
            "from_account": t.from_account,
            "to_account": t.to_account,
            "amount": t.amount,
            "timestamp": t.timestamp
        }
        for t in transactions
    ]
    ug.add_financial_data(financial_txns)

    # Add infrastructure data if available
    infra_file = UPLOAD_DIR / case_id / "infrastructure.csv"
    if infra_file.exists():
        try:
            domains = parse_infra_csv(infra_file)
            ug.add_infrastructure_data(domains)
        except:
            pass

    # Export to JSON
    graph_json = ug.to_json()

    return {
        "case_id": case_id,
        "nodes": graph_json["nodes"],
        "edges": graph_json["edges"],
        "stats": {
            "total_nodes": ug.graph.number_of_nodes(),
            "total_edges": ug.graph.number_of_edges(),
            "node_types": len(set(data["node_type"] for _, data in ug.graph.nodes(data=True)))
        }
    }

@app.get("/assistant/audit")
async def get_audit_log(limit: int = 100):
    """Get AI assistant audit log."""
    from backend.assistant.audit import get_audit_log

    logs = get_audit_log(limit=limit)
    return {"logs": logs, "total": len(logs)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
