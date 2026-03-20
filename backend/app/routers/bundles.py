from __future__ import annotations

import json
import logging
import shutil
import tarfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from fastapi.responses import JSONResponse, PlainTextResponse

logger = logging.getLogger(__name__)

from app.models import (
    AIExplanation,
    AnalysisHistoryEntry,
    AnalysisResult,
    BundleInfo,
    BundleStatus,
    ClusterHealth,
    CompareRequest,
    CompareResponse,
    Issue,
    LogEntry,
    LogSnippet,
    ProposedFix,
    Severity,
)
from app.bundle_parser import BundleParser
from app.analyzers.heuristic import HeuristicAnalyzer
from app.analyzers.ai_analyzer import AIAnalyzer
from app.analyzers.log_correlator import LogCorrelator
from app.analyzers.chat import BundleChat
from app.analyzers.preflight_generator import PreflightGenerator
from app.persistence import save_bundle, update_bundle_status, save_analysis, load_all_bundles as db_load_bundles, load_latest_analysis, load_analysis_history as db_load_history, delete_bundle as db_delete_bundle, is_db_available


# --- Chat models ---

class ChatMessage(BaseModel):
    """A single message in a chat conversation."""

    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    """Request body for the chat endpoint."""

    question: str
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    """Response body from the chat endpoint."""

    answer: str
    sources: list[str] = []

router = APIRouter(prefix="/api/bundles", tags=["bundles"])

# In-memory stores
_bundles: dict[str, BundleInfo] = {}
_analyses: dict[str, AnalysisResult] = {}
_parsed_data: dict[str, dict] = {}

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "bundles"


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _save_bundle_info(bundle_id: str, info: BundleInfo) -> None:
    """Persist BundleInfo to disk."""
    bundle_dir = DATA_DIR / bundle_id
    bundle_dir.mkdir(parents=True, exist_ok=True)
    data = info.model_dump(mode="json")
    data["file_path"] = info.file_path  # file_path is excluded from serialization
    with open(bundle_dir / "bundle_info.json", "w") as f:
        json.dump(data, f, indent=2)


def _save_analysis(bundle_id: str, result: AnalysisResult) -> None:
    """Persist AnalysisResult to disk (latest + timestamped history)."""
    bundle_dir = DATA_DIR / bundle_id
    bundle_dir.mkdir(parents=True, exist_ok=True)
    analyses_dir = bundle_dir / "analyses"
    analyses_dir.mkdir(exist_ok=True)

    data = result.model_dump(mode="json")

    # Save as latest
    with open(bundle_dir / "latest_analysis.json", "w") as f:
        json.dump(data, f, indent=2)

    # Save timestamped copy for history
    ts = result.analyzed_at.strftime("%Y-%m-%dT%H-%M-%S")
    with open(analyses_dir / f"{ts}.json", "w") as f:
        json.dump(data, f, indent=2)


def _load_all_bundles() -> None:
    """Scan DATA_DIR and load all persisted BundleInfo into memory."""
    if not DATA_DIR.exists():
        return
    for bundle_dir in DATA_DIR.iterdir():
        if not bundle_dir.is_dir():
            continue
        info_path = bundle_dir / "bundle_info.json"
        if not info_path.exists():
            continue
        try:
            with open(info_path) as f:
                data = json.load(f)
            # Reconstruct file_path from directory structure
            extract_dir = bundle_dir / "extracted"
            data["file_path"] = str(extract_dir) if extract_dir.exists() else ""
            info = BundleInfo.model_validate(data)
            _bundles[info.id] = info
            logger.info("Loaded persisted bundle: %s", info.id)
        except Exception as e:
            logger.warning("Failed to load bundle from %s: %s", bundle_dir, e)

    # Also load from database if available
    if is_db_available():
        db_bundles = db_load_bundles()
        for b in db_bundles:
            if b["id"] not in _bundles:
                try:
                    info = BundleInfo.model_validate(b)
                    _bundles[info.id] = info
                    logger.info("Loaded bundle from DB: %s", info.id)
                except Exception as e:
                    logger.warning("Failed to load bundle from DB: %s", e)


def _load_all_analyses() -> None:
    """Load latest_analysis.json for each bundle into memory."""
    if not DATA_DIR.exists():
        return
    for bundle_dir in DATA_DIR.iterdir():
        if not bundle_dir.is_dir():
            continue
        analysis_path = bundle_dir / "latest_analysis.json"
        if not analysis_path.exists():
            continue
        try:
            with open(analysis_path) as f:
                data = json.load(f)
            result = AnalysisResult.model_validate(data)
            _analyses[result.bundle_id] = result
            logger.info("Loaded persisted analysis for bundle: %s", result.bundle_id)
        except Exception as e:
            logger.warning("Failed to load analysis from %s: %s", bundle_dir, e)

    # Also load from database if available
    if is_db_available():
        for bundle_id in list(_bundles.keys()):
            if bundle_id not in _analyses:
                db_analysis = load_latest_analysis(bundle_id)
                if db_analysis:
                    try:
                        result = AnalysisResult.model_validate(db_analysis)
                        _analyses[result.bundle_id] = result
                        logger.info("Loaded analysis from DB for: %s", bundle_id)
                    except Exception as e:
                        logger.warning("Failed to load analysis from DB: %s", e)


def _ensure_parsed_data(bundle_id: str) -> dict:
    """Lazy re-parse bundle data if not in memory (e.g. after restart)."""
    if bundle_id in _parsed_data:
        return _parsed_data[bundle_id]
    if bundle_id not in _bundles:
        return {}
    bundle = _bundles[bundle_id]
    if not bundle.file_path or not Path(bundle.file_path).exists():
        return {}
    try:
        parser = BundleParser(bundle.file_path)
        parsed = parser.parse()
        _parsed_data[bundle_id] = parsed
        logger.info("Re-parsed bundle data for %s", bundle_id)
        return parsed
    except Exception as e:
        logger.warning("Failed to re-parse bundle %s: %s", bundle_id, e)
        return {}


@router.post("/upload", response_model=BundleInfo)
async def upload_bundle(file: UploadFile = File(...)):
    """Upload a support bundle tar.gz file."""
    _ensure_data_dir()

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    if not file.filename.endswith((".tar.gz", ".tgz")):
        raise HTTPException(
            status_code=400,
            detail="File must be a .tar.gz or .tgz archive",
        )

    bundle_id = str(uuid.uuid4())
    bundle_dir = DATA_DIR / bundle_id
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # Save the uploaded file - sanitize filename to prevent path traversal
    safe_filename = Path(file.filename).name
    if not safe_filename or safe_filename in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    archive_path = bundle_dir / safe_filename
    try:
        content = await file.read()
        with open(archive_path, "wb") as f:
            f.write(content)
        logger.info("Saved bundle archive: %s (%d bytes)", archive_path, len(content))
    except Exception as e:
        shutil.rmtree(bundle_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    # Extract the archive
    extract_dir = bundle_dir / "extracted"
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            # Security: check for path traversal
            for member in tar.getmembers():
                if member.name.startswith("/") or ".." in member.name:
                    raise HTTPException(
                        status_code=400,
                        detail="Archive contains unsafe paths",
                    )
            tar.extractall(path=extract_dir)
        logger.info("Extracted bundle to %s", extract_dir)
    except tarfile.TarError as e:
        shutil.rmtree(bundle_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Invalid tar.gz file: {e}")

    bundle_info = BundleInfo(
        id=bundle_id,
        filename=file.filename,
        upload_time=datetime.now(timezone.utc),
        status=BundleStatus.uploaded,
        file_path=str(extract_dir),
    )
    _bundles[bundle_id] = bundle_info
    _save_bundle_info(bundle_id, bundle_info)
    save_bundle(bundle_id, bundle_info.filename, bundle_info.status.value, bundle_info.file_path)

    return bundle_info


@router.get("/", response_model=list[BundleInfo])
async def list_bundles():
    """List all uploaded bundles."""
    return list(_bundles.values())


@router.get("/{bundle_id}", response_model=BundleInfo)
async def get_bundle(bundle_id: str):
    """Get info about a specific bundle."""
    if bundle_id not in _bundles:
        raise HTTPException(status_code=404, detail="Bundle not found")
    return _bundles[bundle_id]


@router.post("/{bundle_id}/analyze", response_model=AnalysisResult)
async def analyze_bundle(bundle_id: str):
    """Run analysis on an uploaded bundle."""
    if bundle_id not in _bundles:
        raise HTTPException(status_code=404, detail="Bundle not found")

    bundle = _bundles[bundle_id]
    bundle.status = BundleStatus.analyzing

    try:
        # Step 1: Parse the bundle
        logger.info("Starting analysis of bundle %s", bundle_id)
        parser = BundleParser(bundle.file_path)
        parsed_data = parser.parse()

        # Store parsed data for chat
        _parsed_data[bundle_id] = parsed_data

        # Step 2: Run heuristic analysis
        heuristic = HeuristicAnalyzer(parsed_data)
        heuristic_issues = heuristic.analyze()

        # Step 3: Run AI analysis (in thread to avoid blocking event loop)
        import asyncio
        ai_analyzer = AIAnalyzer()
        ai_result = await asyncio.to_thread(ai_analyzer.analyze, parsed_data, heuristic_issues)

        # Step 4: Merge AI additional issues into the issues list
        all_issues = list(heuristic_issues)
        for ai_issue_data in ai_result.get("additional_issues", []):
            try:
                severity_val = ai_issue_data.get("severity", "info").lower()
                if severity_val not in ("critical", "warning", "info"):
                    severity_val = "info"
                all_issues.append(Issue(
                    severity=Severity(severity_val),
                    title=ai_issue_data.get("title", "AI-detected issue"),
                    category=ai_issue_data.get("category", "configuration"),
                    description=ai_issue_data.get("description", ""),
                    evidence=ai_issue_data.get("evidence", []),
                    remediation=ai_issue_data.get("remediation", ""),
                    ai_confidence=0.75,
                ))
            except Exception as e:
                logger.warning("Could not parse AI issue: %s", e)

        # Step 5: Enrich each issue with proposed_fixes, relevant_log_snippets, ai_explanation
        all_logs = parsed_data.get("logs", [])
        for issue in all_issues:
            # Generate proposed_fixes from remediation text if not already set
            if not issue.proposed_fixes and issue.remediation:
                fix_steps = [
                    s.strip()
                    for s in issue.remediation.replace(". ", ".\n").split("\n")
                    if s.strip()
                ]
                for step in fix_steps:
                    command = None
                    is_automated = False
                    if "kubectl" in step:
                        cmd_start = step.find("kubectl")
                        command = step[cmd_start:].strip().rstrip(".")
                        is_automated = True
                    issue.proposed_fixes.append(ProposedFix(
                        description=step,
                        command=command,
                        is_automated=is_automated,
                    ))

            # Attach relevant_log_snippets by matching log entries to the issue's namespace/pod/resource
            if not issue.relevant_log_snippets:
                matching_logs: list[dict] = []
                for log in all_logs:
                    if log.get("level") not in ("error", "warn"):
                        continue
                    match = False
                    if issue.namespace and log.get("namespace") == issue.namespace:
                        match = True
                    if issue.resource and log.get("pod") and issue.resource in log.get("pod", ""):
                        match = True
                    if match:
                        matching_logs.append(log)

                # Group matching logs by source and create snippets
                source_logs: dict[str, list[str]] = {}
                for ml in matching_logs[:50]:
                    src = ml.get("source", "unknown")
                    source_logs.setdefault(src, []).append(ml.get("message", "")[:300])

                for src, lines in source_logs.items():
                    highlight = [i for i, line in enumerate(lines) if "error" in line.lower()]
                    issue.relevant_log_snippets.append(LogSnippet(
                        source=src,
                        lines=lines[:20],
                        highlight_indices=highlight[:10],
                        level="error",
                    ))

            # Generate ai_explanation if not already set
            if not issue.ai_explanation:
                severity_impact = {
                    "critical": "This issue can cause service outages or data loss",
                    "warning": "This issue may degrade performance or reliability",
                    "info": "This is an informational finding worth reviewing",
                }
                issue.ai_explanation = AIExplanation(
                    root_cause=issue.description,
                    impact=severity_impact.get(issue.severity.value, "Unknown impact"),
                    related_issues=[],
                )

        # Step 6: Run log correlation
        correlator = LogCorrelator()
        timeline_events = correlator.correlate(
            parsed_data.get("events", []),
            parsed_data.get("logs", []),
            all_issues,
        )
        topology_nodes, topology_edges = correlator.build_topology(parsed_data)

        # Step 7: Build correlation groups and resource health
        correlation_groups = correlator.build_correlation_groups(
            timeline_events,
            parsed_data.get("logs", []),
            all_issues,
        )
        resource_health = correlator.build_resource_health(parsed_data)

        # Step 8: Build cluster health summary
        cluster_health = _compute_cluster_health(parsed_data, all_issues)

        # Step 9: Extract top log entries (most relevant - errors/warnings first)
        log_entries = _extract_top_logs(parsed_data.get("logs", []), limit=200)

        # Step 10: Build raw events list
        raw_events = []
        for te in timeline_events[:500]:
            raw_events.append(te.model_dump())

        # Step 11: Collect AI insights
        ai_insights = ai_result.get("insights", [])

        # Step 12: Assemble result
        result = AnalysisResult(
            bundle_id=bundle_id,
            status=BundleStatus.completed,
            cluster_health=cluster_health,
            issues=all_issues,
            log_entries=log_entries,
            topology_nodes=topology_nodes,
            topology_edges=topology_edges,
            summary=ai_result.get("summary", "Analysis complete."),
            analyzed_at=datetime.now(timezone.utc),
            raw_events=raw_events,
            correlations=correlation_groups,
            resource_health=resource_health,
            ai_insights=ai_insights,
        )

        _analyses[bundle_id] = result
        _save_analysis(bundle_id, result)
        save_analysis(bundle_id, result.model_dump(mode="json"))
        _save_bundle_info(bundle_id, bundle)
        bundle.status = BundleStatus.completed
        logger.info("Analysis complete for bundle %s: %d issues found", bundle_id, len(all_issues))

        return result

    except Exception as e:
        bundle.status = BundleStatus.failed
        logger.error("Analysis failed for bundle %s: %s", bundle_id, e)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")


@router.get("/{bundle_id}/analysis", response_model=AnalysisResult)
async def get_analysis(bundle_id: str):
    """Get the stored analysis result for a bundle."""
    if bundle_id not in _bundles:
        raise HTTPException(status_code=404, detail="Bundle not found")
    if bundle_id not in _analyses:
        raise HTTPException(
            status_code=404,
            detail="Analysis not found. Run POST /{bundle_id}/analyze first.",
        )
    return _analyses[bundle_id]


@router.delete("/{bundle_id}")
async def delete_bundle(bundle_id: str):
    """Delete a bundle and its analysis."""
    if bundle_id not in _bundles:
        raise HTTPException(status_code=404, detail="Bundle not found")

    bundle = _bundles[bundle_id]

    # Remove files from disk
    bundle_dir = DATA_DIR / bundle_id
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir, ignore_errors=True)
        logger.info("Deleted bundle files at %s", bundle_dir)

    db_delete_bundle(bundle_id)

    # Remove from in-memory stores
    del _bundles[bundle_id]
    _analyses.pop(bundle_id, None)
    _parsed_data.pop(bundle_id, None)

    return {"detail": "Bundle deleted", "id": bundle_id}


@router.post("/{bundle_id}/reanalyze", response_model=AnalysisResult)
async def reanalyze_bundle(bundle_id: str):
    """Re-run analysis on an already uploaded bundle."""
    if bundle_id not in _bundles:
        raise HTTPException(status_code=404, detail="Bundle not found")

    # Remove any existing analysis so it runs fresh
    _analyses.pop(bundle_id, None)

    # Re-run the full analysis pipeline
    return await analyze_bundle(bundle_id)


@router.get("/{bundle_id}/export")
async def export_analysis(bundle_id: str):
    """Export the analysis result as a JSON download."""
    if bundle_id not in _bundles:
        raise HTTPException(status_code=404, detail="Bundle not found")
    if bundle_id not in _analyses:
        raise HTTPException(
            status_code=404,
            detail="Analysis not found. Run POST /{bundle_id}/analyze first.",
        )

    analysis = _analyses[bundle_id]
    return JSONResponse(
        content=analysis.model_dump(mode="json"),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="report-{bundle_id}.json"',
        },
    )


@router.get("/{bundle_id}/preflight")
async def get_preflight_spec(bundle_id: str):
    """Generate a Troubleshoot preflight check YAML spec from detected issues."""
    if bundle_id not in _bundles:
        raise HTTPException(status_code=404, detail="Bundle not found")
    if bundle_id not in _analyses:
        raise HTTPException(
            status_code=404,
            detail="Analysis not found. Run POST /{bundle_id}/analyze first.",
        )

    analysis = _analyses[bundle_id]
    parsed = _ensure_parsed_data(bundle_id)

    generator = PreflightGenerator(analysis.issues, parsed)
    yaml_content = generator.generate()

    return PlainTextResponse(
        content=yaml_content,
        media_type="text/yaml",
        headers={
            "Content-Disposition": f'attachment; filename="preflight-spec-{bundle_id}.yaml"',
        },
    )


@router.post("/{bundle_id}/chat", response_model=ChatResponse)
async def chat_with_bundle(bundle_id: str, body: ChatRequest):
    """Ask a natural-language question about an analyzed bundle."""
    if bundle_id not in _bundles:
        raise HTTPException(status_code=404, detail="Bundle not found")
    if bundle_id not in _analyses:
        raise HTTPException(
            status_code=400,
            detail="Bundle has not been analyzed yet. Run POST /{bundle_id}/analyze first.",
        )
    parsed = _ensure_parsed_data(bundle_id)
    if not parsed:
        raise HTTPException(
            status_code=400,
            detail="Parsed data not available. Re-analyze the bundle with POST /{bundle_id}/analyze.",
        )

    analysis = _analyses[bundle_id]

    chat = BundleChat(parsed, analysis)
    history = [{"role": m.role, "content": m.content} for m in body.history]

    try:
        import asyncio
        answer = await asyncio.to_thread(chat.ask, body.question, history)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat failed: {exc}")

    # Report which data sources were consulted
    sources: list[str] = []
    if parsed.get("pods"):
        sources.append("pods")
    if parsed.get("nodes"):
        sources.append("nodes")
    if parsed.get("events"):
        sources.append("events")
    if parsed.get("logs"):
        sources.append("logs")
    if analysis.issues:
        sources.append("analysis_issues")

    return ChatResponse(answer=answer, sources=sources)


@router.get("/{bundle_id}/history")
async def get_analysis_history(bundle_id: str):
    """List all historical analysis runs for a bundle."""
    if bundle_id not in _bundles:
        raise HTTPException(status_code=404, detail="Bundle not found")

    analyses_dir = DATA_DIR / bundle_id / "analyses"
    if not analyses_dir.exists():
        return []

    entries: list[AnalysisHistoryEntry] = []
    for f in sorted(analyses_dir.glob("*.json"), reverse=True):
        try:
            with open(f) as fh:
                data = json.load(fh)
            health = data.get("cluster_health", {})
            issues = data.get("issues", [])
            entries.append(AnalysisHistoryEntry(
                analyzed_at=data.get("analyzed_at", ""),
                health_score=health.get("score", 0),
                critical_count=health.get("critical_count", 0),
                warning_count=health.get("warning_count", 0),
                info_count=health.get("info_count", 0),
                issue_count=len(issues),
            ))
        except Exception as e:
            logger.warning("Failed to read history file %s: %s", f, e)

    # Supplement with DB history
    if is_db_available():
        db_history = db_load_history(bundle_id)
        # Merge — add DB entries that aren't already in file-based history
        existing_timestamps = {e.analyzed_at.isoformat() if hasattr(e, 'analyzed_at') else str(e.get('analyzed_at', '')) for e in entries}
        for entry in db_history:
            if entry["analyzed_at"] not in existing_timestamps:
                entries.append(AnalysisHistoryEntry.model_validate(entry))

    return entries


@router.get("/{bundle_id}/history/{timestamp}")
async def get_historical_analysis(bundle_id: str, timestamp: str):
    """Get a specific historical analysis result."""
    if bundle_id not in _bundles:
        raise HTTPException(status_code=404, detail="Bundle not found")

    analyses_dir = DATA_DIR / bundle_id / "analyses"
    analysis_path = analyses_dir / f"{timestamp}.json"
    if not analysis_path.exists():
        raise HTTPException(status_code=404, detail="Historical analysis not found")

    try:
        with open(analysis_path) as f:
            data = json.load(f)
        return AnalysisResult.model_validate(data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load analysis: {e}")


@router.post("/compare", response_model=CompareResponse)
async def compare_analyses(body: CompareRequest):
    """Compare two bundle analyses side by side."""
    def _load_analysis(bundle_id: str, timestamp: str | None) -> AnalysisResult:
        if timestamp:
            analysis_path = DATA_DIR / bundle_id / "analyses" / f"{timestamp}.json"
            if not analysis_path.exists():
                raise HTTPException(status_code=404, detail=f"Analysis not found for {bundle_id} at {timestamp}")
            with open(analysis_path) as f:
                return AnalysisResult.model_validate(json.load(f))
        if bundle_id in _analyses:
            return _analyses[bundle_id]
        raise HTTPException(status_code=404, detail=f"No analysis found for bundle {bundle_id}")

    if body.left_bundle_id not in _bundles:
        raise HTTPException(status_code=404, detail=f"Bundle {body.left_bundle_id} not found")
    if body.right_bundle_id not in _bundles:
        raise HTTPException(status_code=404, detail=f"Bundle {body.right_bundle_id} not found")

    left = _load_analysis(body.left_bundle_id, body.left_timestamp)
    right = _load_analysis(body.right_bundle_id, body.right_timestamp)

    return CompareResponse(left=left, right=right)


def _compute_cluster_health(parsed_data: dict[str, Any], issues: list[Issue]) -> ClusterHealth:
    """Compute a cluster health summary from parsed data and detected issues."""
    pods = parsed_data.get("pods", [])
    nodes = parsed_data.get("nodes", [])
    namespaces = parsed_data.get("namespaces", [])

    critical_count = sum(1 for i in issues if i.severity == Severity.critical)
    warning_count = sum(1 for i in issues if i.severity == Severity.warning)
    info_count = sum(1 for i in issues if i.severity == Severity.info)

    # Honest health score — reflects real cluster state
    total_pods = len(pods)
    running_pods = sum(
        1 for p in pods
        if p.get("status", {}).get("phase") in ("Running", "Succeeded")
    )

    # Node health: are all nodes Ready?
    ready_nodes = sum(
        1 for n in nodes
        if any(
            c.get("type") == "Ready" and c.get("status") == "True"
            for c in n.get("status", {}).get("conditions", [])
        )
    )
    node_health = (ready_nodes / len(nodes) * 100) if nodes else 100

    if total_pods > 0:
        # Pod health is the primary signal (60% weight)
        pod_ratio = running_pods / total_pods
        pod_score = pod_ratio * 60

        # Node health (20% weight)
        node_score = (node_health / 100) * 20

        # Issue penalty (20% weight) — critical issues hurt more
        max_penalty = 20
        penalty = min(max_penalty, critical_count * 5 + warning_count * 1.5)
        issue_score = max_penalty - penalty

        score = int(max(0, min(100, pod_score + node_score + issue_score)))
    else:
        score = 0 if critical_count > 0 else 50

    return ClusterHealth(
        score=score,
        node_count=len(nodes),
        pod_count=len(pods),
        namespace_count=len(namespaces),
        critical_count=critical_count,
        warning_count=warning_count,
        info_count=info_count,
    )


def _extract_top_logs(logs: list[dict], limit: int = 200) -> list[LogEntry]:
    """Extract the most relevant log entries, prioritizing errors and warnings."""
    # Separate by level
    errors = [l for l in logs if l.get("level") == "error"]
    warns = [l for l in logs if l.get("level") == "warn"]
    infos = [l for l in logs if l.get("level") == "info"]

    # Take most recent errors first, then warnings, then fill with info
    selected: list[dict] = []
    selected.extend(errors[-100:])
    remaining = limit - len(selected)
    if remaining > 0:
        selected.extend(warns[-remaining:])
    remaining = limit - len(selected)
    if remaining > 0:
        selected.extend(infos[-remaining:])

    return [
        LogEntry(
            timestamp=l.get("timestamp"),
            source=l.get("source", "unknown"),
            level=l.get("level", "info"),
            message=l.get("message", "")[:1000],
            namespace=l.get("namespace"),
            pod=l.get("pod"),
        )
        for l in selected[:limit]
    ]
