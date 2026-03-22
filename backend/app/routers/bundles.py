from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import shutil
import tarfile
import uuid
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from app.analyzers.ai_analyzer import AIAnalyzer
from app.analyzers.chat import BundleChat
from app.analyzers.heuristic import HeuristicAnalyzer
from app.analyzers.log_correlator import LogCorrelator
from app.analyzers.preflight_generator import PreflightGenerator
from app.bundle_parser import BundleParser
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
    ResourceHealthDot,
    Severity,
    TopologyEdge,
    TopologyNode,
)
from app.persistence import delete_bundle as db_delete_bundle
from app.persistence import is_db_available, load_latest_analysis, save_analysis, save_bundle
from app.persistence import load_all_bundles as db_load_bundles
from app.persistence import load_analysis_history as db_load_history
from app.rag.chunker import chunk_bundle
from app.rag.vector_store import delete_bundle_chunks, get_chunk_count, index_chunks

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


router = APIRouter(prefix="/api/bundles", tags=["Bundles"])

# In-memory stores
_bundles: dict[str, BundleInfo] = {}
_analyses: dict[str, AnalysisResult] = {}

MAX_PARSED_CACHE = 10  # Keep at most 10 bundles' parsed data in memory


class _LRUCache(OrderedDict):
    """Simple LRU cache using OrderedDict."""

    def __init__(self, maxsize: int = MAX_PARSED_CACHE):
        super().__init__()
        self.maxsize = maxsize

    def __getitem__(self, key):
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value

    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        while len(self) > self.maxsize:
            oldest = next(iter(self))
            logger.info("Evicting parsed data for bundle %s (LRU)", oldest)
            del self[oldest]

    def __contains__(self, key):
        if super().__contains__(key):
            self.move_to_end(key)
            return True
        return False


_parsed_data: _LRUCache = _LRUCache()

# Content-hash based analysis cache
_bundle_hashes: dict[str, str] = {}  # bundle_id -> file hash
_hash_to_analysis: dict[str, str] = {}  # file hash -> bundle_id with analysis

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


@router.post("/demo", response_model=AnalysisResult, tags=["Demo"])
async def create_demo_bundle():
    """Create a demo bundle with sample analysis data for first-time users."""
    demo_id = "demo-" + str(uuid.uuid4())[:8]

    demo_issues = [
        Issue(
            severity=Severity.critical,
            title="CrashLoopBackOff: payment-gateway/payment-api",
            category="pod-health",
            resource="pod/payment-gateway-7f8d9c4b5-x2k9l",
            namespace="payments",
            description="Container 'payment-api' in pod 'payment-gateway-7f8d9c4b5-x2k9l' is in CrashLoopBackOff with 42 restarts. The container is repeatedly crashing.",
            evidence=[
                "Container state: CrashLoopBackOff",
                "Restart count: 42",
                "Message: back-off 5m0s restarting failed container",
            ],
            remediation="Check container logs: kubectl logs payment-gateway-7f8d9c4b5-x2k9l -c payment-api -n payments --previous. Common causes: missing config/secrets, insufficient resources.",
            ai_confidence=0.95,
            ai_explanation=AIExplanation(
                root_cause="Redis connection timeout causing crash loop. The payment-api container depends on redis-master which is not resolving.",
                impact="Payment processing is completely down. All transactions will fail.",
                related_issues=["Service has no endpoints: redis-master"],
            ),
        ),
        Issue(
            severity=Severity.critical,
            title="Node not ready: worker-3",
            category="pod-health",
            resource="node/worker-3",
            description="Node 'worker-3' is not in Ready state. Reason: KubeletNotReady. container runtime network not ready.",
            evidence=["Condition: Ready=False", "Reason: KubeletNotReady"],
            remediation="Check node 'worker-3' for kubelet issues: kubectl describe node worker-3",
            ai_confidence=0.95,
        ),
        Issue(
            severity=Severity.warning,
            title="StatefulSet degraded: postgres-cluster (1/3 ready)",
            category="pod-health",
            resource="statefulset/postgres-cluster",
            namespace="database",
            description="StatefulSet 'postgres-cluster' in namespace 'database' has 1/3 ready replicas.",
            evidence=["Desired: 3", "Ready: 1", "Current: 2"],
            remediation="Check StatefulSet pods: kubectl get pods -l app=postgres-cluster -n database. StatefulSet rollouts are sequential — a stuck pod blocks the rest.",
            ai_confidence=0.90,
        ),
        Issue(
            severity=Severity.warning,
            title="HPA scaling issue: api-hpa",
            category="resource-usage",
            resource="hpa/api-hpa",
            namespace="production",
            description="HPA 'api-hpa' in namespace 'production' has scaling concerns: Running at max replicas (10/10); ScalingLimited.",
            evidence=[
                "Running at max replicas (10/10)",
                "ScalingLimited: the desired replica count is more than the maximum replica count",
            ],
            remediation="Review HPA status: kubectl describe hpa api-hpa -n production. Consider increasing maxReplicas or adding node capacity.",
            ai_confidence=0.85,
        ),
        Issue(
            severity=Severity.warning,
            title="Service has no endpoints: redis-master",
            category="networking",
            resource="service/redis-master",
            namespace="payments",
            description="Service 'redis-master' in namespace 'payments' selector (app=redis, role=master) matches 0 pods. Traffic to this service will fail.",
            evidence=["Selector: app=redis, role=master", "Matching pods: 0"],
            remediation="Check that pods with labels matching app=redis,role=master exist in namespace 'payments'.",
            ai_confidence=0.90,
        ),
        Issue(
            severity=Severity.warning,
            title="Probe failure: api-server-abc123",
            category="pod-health",
            resource="pod/api-server-abc123",
            namespace="production",
            description="Pod 'api-server-abc123' has failing health probes. Total occurrences: 47.",
            evidence=["Unhealthy: Liveness probe failed: HTTP probe failed with statuscode: 503"],
            remediation="Review the probe configuration. Check if the application starts slowly and needs a higher initialDelaySeconds.",
            ai_confidence=0.90,
        ),
        Issue(
            severity=Severity.warning,
            title="Missing resource limits (8 container(s))",
            category="configuration",
            description="8 container(s) have no resource requests or limits set. This can lead to resource contention and OOM kills.",
            evidence=[
                "production/api-server/api",
                "payments/payment-gateway/payment-api",
                "monitoring/prometheus/prometheus",
            ],
            remediation="Add resource requests and limits to all containers.",
            ai_confidence=0.85,
        ),
        Issue(
            severity=Severity.info,
            title="Deprecated API versions in use",
            category="configuration",
            description="Some resources use deprecated Kubernetes API versions that may stop working after cluster upgrades.",
            evidence=["deployments/legacy-app uses deprecated extensions/v1beta1"],
            remediation="Update manifests to use current API versions.",
            ai_confidence=0.90,
        ),
    ]

    demo_topology_nodes = [
        TopologyNode(id="node/worker-1", label="worker-1", type="node", status="healthy"),
        TopologyNode(id="node/worker-2", label="worker-2", type="node", status="healthy"),
        TopologyNode(id="node/worker-3", label="worker-3", type="node", status="critical"),
        TopologyNode(
            id="deployment/production/api-server",
            label="api-server",
            type="deployment",
            status="warning",
            namespace="production",
            metadata={"replicas": 3, "readyReplicas": 2},
        ),
        TopologyNode(
            id="deployment/payments/payment-gateway",
            label="payment-gateway",
            type="deployment",
            status="critical",
            namespace="payments",
            metadata={"replicas": 2, "readyReplicas": 0},
        ),
        TopologyNode(
            id="statefulset/database/postgres-cluster",
            label="postgres-cluster",
            type="statefulset",
            status="warning",
            namespace="database",
            metadata={"replicas": 3, "readyReplicas": 1},
        ),
        TopologyNode(
            id="daemonset/monitoring/node-exporter",
            label="node-exporter",
            type="daemonset",
            status="healthy",
            namespace="monitoring",
            metadata={"desired": 3, "ready": 3},
        ),
        TopologyNode(
            id="service/production/api-svc", label="api-svc", type="service", status="healthy", namespace="production"
        ),
        TopologyNode(
            id="service/payments/redis-master",
            label="redis-master",
            type="service",
            status="warning",
            namespace="payments",
        ),
        TopologyNode(
            id="ingress/production/main-ingress",
            label="main-ingress",
            type="ingress",
            status="healthy",
            namespace="production",
        ),
        TopologyNode(
            id="pod/production/api-server-abc123",
            label="api-server-abc123",
            type="pod",
            status="warning",
            namespace="production",
            metadata={"phase": "Running", "nodeName": "worker-1"},
        ),
        TopologyNode(
            id="pod/production/api-server-def456",
            label="api-server-def456",
            type="pod",
            status="healthy",
            namespace="production",
            metadata={"phase": "Running", "nodeName": "worker-2"},
        ),
        TopologyNode(
            id="pod/payments/payment-gateway-xyz",
            label="payment-gateway-xyz",
            type="pod",
            status="critical",
            namespace="payments",
            metadata={"phase": "Running", "nodeName": "worker-1"},
        ),
        TopologyNode(
            id="pod/database/postgres-0",
            label="postgres-0",
            type="pod",
            status="healthy",
            namespace="database",
            metadata={"phase": "Running", "nodeName": "worker-1"},
        ),
        TopologyNode(
            id="pod/database/postgres-1",
            label="postgres-1",
            type="pod",
            status="warning",
            namespace="database",
            metadata={"phase": "Pending", "nodeName": ""},
        ),
        TopologyNode(
            id="job/batch/data-migration",
            label="data-migration",
            type="job",
            status="critical",
            namespace="batch",
            metadata={"succeeded": 0, "failed": 3},
        ),
    ]

    demo_topology_edges = [
        TopologyEdge(source="node/worker-1", target="pod/production/api-server-abc123", label="runs"),
        TopologyEdge(source="node/worker-2", target="pod/production/api-server-def456", label="runs"),
        TopologyEdge(source="node/worker-1", target="pod/payments/payment-gateway-xyz", label="runs"),
        TopologyEdge(source="node/worker-1", target="pod/database/postgres-0", label="runs"),
        TopologyEdge(
            source="deployment/production/api-server", target="pod/production/api-server-abc123", label="owns"
        ),
        TopologyEdge(
            source="deployment/production/api-server", target="pod/production/api-server-def456", label="owns"
        ),
        TopologyEdge(
            source="deployment/payments/payment-gateway", target="pod/payments/payment-gateway-xyz", label="owns"
        ),
        TopologyEdge(source="statefulset/database/postgres-cluster", target="pod/database/postgres-0", label="owns"),
        TopologyEdge(source="statefulset/database/postgres-cluster", target="pod/database/postgres-1", label="owns"),
        TopologyEdge(source="service/production/api-svc", target="pod/production/api-server-abc123", label="selects"),
        TopologyEdge(source="service/production/api-svc", target="pod/production/api-server-def456", label="selects"),
        TopologyEdge(source="ingress/production/main-ingress", target="service/production/api-svc", label="routes"),
    ]

    demo_resource_health = [
        ResourceHealthDot(id="node/worker-1", name="worker-1", type="node", status="healthy"),
        ResourceHealthDot(id="node/worker-2", name="worker-2", type="node", status="healthy"),
        ResourceHealthDot(id="node/worker-3", name="worker-3", type="node", status="critical"),
        ResourceHealthDot(
            id="deployment/production/api-server",
            name="api-server",
            type="deployment",
            namespace="production",
            status="warning",
        ),
        ResourceHealthDot(
            id="deployment/payments/payment-gateway",
            name="payment-gateway",
            type="deployment",
            namespace="payments",
            status="critical",
        ),
        ResourceHealthDot(
            id="statefulset/database/postgres-cluster",
            name="postgres-cluster",
            type="statefulset",
            namespace="database",
            status="warning",
        ),
        ResourceHealthDot(
            id="pod/production/api-server-abc123",
            name="api-server-abc123",
            type="pod",
            namespace="production",
            status="warning",
        ),
        ResourceHealthDot(
            id="pod/production/api-server-def456",
            name="api-server-def456",
            type="pod",
            namespace="production",
            status="healthy",
        ),
        ResourceHealthDot(
            id="pod/payments/payment-gateway-xyz",
            name="payment-gateway-xyz",
            type="pod",
            namespace="payments",
            status="critical",
        ),
        ResourceHealthDot(
            id="pod/database/postgres-0", name="postgres-0", type="pod", namespace="database", status="healthy"
        ),
        ResourceHealthDot(
            id="pod/database/postgres-1", name="postgres-1", type="pod", namespace="database", status="warning"
        ),
        ResourceHealthDot(
            id="pod/monitoring/prometheus-0", name="prometheus-0", type="pod", namespace="monitoring", status="healthy"
        ),
        ResourceHealthDot(
            id="pod/monitoring/grafana-abc", name="grafana-abc", type="pod", namespace="monitoring", status="healthy"
        ),
        ResourceHealthDot(
            id="service/production/api-svc", name="api-svc", type="service", namespace="production", status="healthy"
        ),
        ResourceHealthDot(
            id="service/payments/redis-master",
            name="redis-master",
            type="service",
            namespace="payments",
            status="warning",
        ),
        ResourceHealthDot(
            id="job/batch/data-migration", name="data-migration", type="job", namespace="batch", status="critical"
        ),
    ]

    result = AnalysisResult(
        bundle_id=demo_id,
        status=BundleStatus.completed,
        cluster_health=ClusterHealth(
            score=52, node_count=3, pod_count=16, namespace_count=5, critical_count=3, warning_count=5, info_count=1
        ),
        issues=demo_issues,
        log_entries=[
            LogEntry(
                timestamp="2024-01-15T10:28:00Z",
                source="payments/payment-gateway/payment-api",
                level="error",
                message="Failed to connect to redis-master:6379 - Connection refused",
                namespace="payments",
                pod="payment-gateway-xyz",
            ),
            LogEntry(
                timestamp="2024-01-15T10:28:05Z",
                source="payments/payment-gateway/payment-api",
                level="error",
                message="FATAL: Redis connection timeout after 30s, shutting down",
                namespace="payments",
                pod="payment-gateway-xyz",
            ),
            LogEntry(
                timestamp="2024-01-15T10:29:00Z",
                source="production/api-server/api",
                level="warn",
                message="High latency detected on /api/checkout: p99=4200ms",
                namespace="production",
                pod="api-server-abc123",
            ),
            LogEntry(
                timestamp="2024-01-15T10:29:15Z",
                source="database/postgres-0/postgres",
                level="warn",
                message="replication lag exceeding 30s for standby postgres-1",
                namespace="database",
                pod="postgres-0",
            ),
            LogEntry(
                timestamp="2024-01-15T10:30:00Z",
                source="production/api-server/api",
                level="error",
                message="upstream connect error: connection refused to payments.svc.cluster.local:8080",
                namespace="production",
                pod="api-server-abc123",
            ),
        ],
        topology_nodes=demo_topology_nodes,
        topology_edges=demo_topology_edges,
        summary="Cluster is experiencing cascading failures originating from a missing Redis service in the payments namespace. The payment-gateway deployment is in CrashLoopBackOff due to Redis connection timeouts, causing upstream API errors. Node worker-3 is NotReady, further reducing cluster capacity. The postgres StatefulSet has a stuck rollout with only 1 of 3 replicas ready.",
        analyzed_at=datetime.now(UTC),
        raw_events=[],
        correlations=[],
        resource_health=demo_resource_health,
        ai_insights=[
            "Root cause chain: redis-master service has no endpoints -> payment-gateway crashes -> cascading API failures.",
            "Node worker-3 being NotReady reduces scheduling capacity by 33%, compounding the StatefulSet rollout issue.",
            "8 containers lack resource limits -- in a resource-constrained cluster, this increases OOM kill risk.",
            "The HPA for api-server is at max replicas (10/10), indicating the application cannot scale further under current load.",
            "Consider prioritizing: 1) Fix redis-master selector, 2) Investigate worker-3, 3) Add resource limits.",
        ],
    )

    # Store in memory so the analysis page + chat work
    demo_bundle = BundleInfo(id=demo_id, filename="demo-support-bundle.tar.gz", status=BundleStatus.completed)
    _bundles[demo_id] = demo_bundle
    _analyses[demo_id] = result

    # Store minimal parsed data so chat can answer questions
    _parsed_data[demo_id] = {
        "pods": [
            {
                "metadata": {"name": "payment-gateway-7f8d9c4b5-x2k9l", "namespace": "payments"},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [
                        {
                            "name": "payment-api",
                            "restartCount": 42,
                            "state": {"waiting": {"reason": "CrashLoopBackOff"}},
                        }
                    ],
                },
            },
            {
                "metadata": {"name": "api-server-abc123", "namespace": "production"},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [{"name": "api", "restartCount": 8, "ready": False}],
                },
            },
        ],
        "nodes": [
            {"metadata": {"name": "worker-1"}, "status": {"conditions": [{"type": "Ready", "status": "True"}]}},
            {
                "metadata": {"name": "worker-3"},
                "status": {"conditions": [{"type": "Ready", "status": "False", "reason": "KubeletNotReady"}]},
            },
        ],
        "events": [],
        "logs": [
            {
                "source": "payments/payment-gateway/payment-api",
                "message": "Failed to connect to redis-master:6379 - Connection refused",
                "level": "error",
                "namespace": "payments",
                "pod": "payment-gateway-7f8d9c4b5-x2k9l",
            },
            {
                "source": "production/api-server/api",
                "message": "High latency on /api/checkout: p99=4200ms",
                "level": "warn",
                "namespace": "production",
                "pod": "api-server-abc123",
            },
        ],
        "deployments": [],
        "services": [],
        "namespaces": [{"metadata": {"name": "payments"}}, {"metadata": {"name": "production"}}],
        "statefulsets": [],
        "daemonsets": [],
        "jobs": [],
        "cronjobs": [],
        "ingresses": [],
        "hpas": [],
        "cluster_version": {"gitVersion": "v1.28.4"},
        "host_info": {},
        "analysis_json": None,
        "pvs": [],
        "storage_classes": [],
    }

    return result


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

    # Compute content hash for cache deduplication
    file_hash = hashlib.sha256(content).hexdigest()
    _bundle_hashes[bundle_id] = file_hash

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
        upload_time=datetime.now(UTC),
        status=BundleStatus.uploaded,
        file_path=str(extract_dir),
    )
    _bundles[bundle_id] = bundle_info

    # Check cache — if identical bundle was already analyzed, note it
    if file_hash in _hash_to_analysis:
        cached_id = _hash_to_analysis[file_hash]
        if cached_id in _analyses:
            bundle_info.status = BundleStatus.completed

    _save_bundle_info(bundle_id, bundle_info)
    save_bundle(bundle_id, bundle_info.filename, bundle_info.status.value, bundle_info.file_path)

    return bundle_info


@router.get("/")
async def list_bundles():
    """List all uploaded bundles with analysis summary stats."""
    results = []
    for bundle in _bundles.values():
        data = bundle.model_dump(mode="json")
        data["file_path"] = ""  # Don't expose file paths
        # Attach analysis stats if available
        analysis = _analyses.get(bundle.id)
        if analysis:
            data["status"] = "completed"  # Fix stale status
            data["analysis"] = {
                "health_score": analysis.cluster_health.score,
                "issues": [{"severity": i.severity.value, "title": i.title} for i in analysis.issues],
            }
        results.append(data)
    return results


@router.get("/search/cross-bundle", tags=["Search"])
async def cross_bundle_search(q: str, n: int = 10):
    """Search across all bundles for similar issues/patterns."""
    from app.rag.vector_store import _get_collection

    collection = _get_collection()
    if not collection or collection.count() == 0:
        return {"results": [], "total_chunks": 0}

    try:
        results = collection.query(
            query_texts=[q],
            n_results=min(n, collection.count()),
        )

        hits = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                hits.append(
                    {
                        "content": doc[:500],
                        "bundle_id": meta.get("bundle_id", ""),
                        "chunk_type": meta.get("chunk_type", ""),
                        "namespace": meta.get("namespace", ""),
                        "severity": meta.get("severity", ""),
                        "distance": results["distances"][0][i] if results["distances"] else 0,
                    }
                )

        return {
            "query": q,
            "results": hits,
            "total_chunks": collection.count(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")


@router.get("/{bundle_id}/chunks", tags=["Search"])
async def get_bundle_chunks(bundle_id: str):
    """Get chunk/indexing stats for a bundle."""
    if bundle_id not in _bundles:
        raise HTTPException(status_code=404, detail="Bundle not found")

    from app.persistence import get_chunk_stats

    vector_count = get_chunk_count(bundle_id)
    db_stats = get_chunk_stats(bundle_id)

    return {
        "bundle_id": bundle_id,
        "vector_store_chunks": vector_count,
        "database_chunks": db_stats.get("total_chunks", 0),
        "by_type": db_stats.get("by_type", {}),
        "indexed": vector_count > 0,
    }


@router.get("/{bundle_id}", response_model=BundleInfo)
async def get_bundle(bundle_id: str):
    """Get info about a specific bundle."""
    if bundle_id not in _bundles:
        raise HTTPException(status_code=404, detail="Bundle not found")
    return _bundles[bundle_id]


@router.get("/{bundle_id}/analyze/stream", tags=["Analysis"])
async def analyze_bundle_stream(bundle_id: str):
    """Run analysis with live progress updates via Server-Sent Events."""
    from starlette.responses import StreamingResponse

    if bundle_id not in _bundles:
        raise HTTPException(status_code=404, detail="Bundle not found")

    bundle = _bundles[bundle_id]
    bundle.status = BundleStatus.analyzing

    async def event_stream():
        try:

            def send(step: str, detail: str, progress: int):
                data = json.dumps({"step": step, "detail": detail, "progress": progress})
                return f"data: {data}\n\n"

            # Step 1: Parse
            yield send("parsing", "Parsing support bundle...", 5)
            parser = BundleParser(bundle.file_path)
            parsed_data = await asyncio.to_thread(parser.parse)
            _parsed_data[bundle_id] = parsed_data

            pods = len(parsed_data.get("pods", []))
            nodes = len(parsed_data.get("nodes", []))
            events = len(parsed_data.get("events", []))
            yield send("parsing", f"Found {pods} pods, {nodes} nodes, {events} events", 15)

            # Step 2: Heuristic analysis
            yield send("heuristics", "Running 25 pattern detectors...", 25)
            heuristic = HeuristicAnalyzer(parsed_data)
            heuristic_issues = await asyncio.to_thread(heuristic.analyze)
            yield send("heuristics", f"Found {len(heuristic_issues)} issues", 40)

            # Step 3: AI analysis
            yield send("ai", "AI analyzing root causes...", 45)
            ai_analyzer = AIAnalyzer()
            ai_result = await asyncio.to_thread(ai_analyzer.analyze, parsed_data, heuristic_issues, bundle_id)
            ai_count = len(ai_result.get("additional_issues", []))
            yield send("ai", f"AI found {ai_count} additional insights", 65)

            # Step 4: Merge issues
            all_issues = list(heuristic_issues)
            for ai_issue_data in ai_result.get("additional_issues", []):
                try:
                    severity_val = ai_issue_data.get("severity", "info").lower()
                    if severity_val not in ("critical", "warning", "info"):
                        severity_val = "info"
                    all_issues.append(
                        Issue(
                            severity=Severity(severity_val),
                            title=ai_issue_data.get("title", "AI-detected issue"),
                            category=ai_issue_data.get("category", "configuration"),
                            description=ai_issue_data.get("description", ""),
                            evidence=ai_issue_data.get("evidence", []),
                            remediation=ai_issue_data.get("remediation", ""),
                            ai_confidence=0.75,
                        )
                    )
                except Exception:
                    pass

            # Step 5: Enrich issues
            yield send("enriching", "Enriching issues with fixes and log snippets...", 70)
            all_logs = parsed_data.get("logs", [])
            for issue in all_issues:
                if not issue.proposed_fixes and issue.remediation:
                    fix_steps = [s.strip() for s in issue.remediation.replace(". ", ".\n").split("\n") if s.strip()]
                    for step in fix_steps:
                        command = None
                        is_automated = False
                        if "kubectl" in step:
                            cmd_start = step.find("kubectl")
                            command = step[cmd_start:].strip().rstrip(".")
                            is_automated = True
                        issue.proposed_fixes.append(
                            ProposedFix(description=step, command=command, is_automated=is_automated)
                        )

                if not issue.relevant_log_snippets:
                    matching_logs = [
                        l
                        for l in all_logs
                        if l.get("level") in ("error", "warn")
                        and (
                            (issue.namespace and l.get("namespace") == issue.namespace)
                            or (issue.resource and l.get("pod") and issue.resource in l.get("pod", ""))
                        )
                    ][:50]
                    source_logs: dict[str, list[str]] = {}
                    for ml in matching_logs:
                        src = ml.get("source", "unknown")
                        source_logs.setdefault(src, []).append(ml.get("message", "")[:300])
                    for src, lines in source_logs.items():
                        highlight = [i for i, line in enumerate(lines) if "error" in line.lower()]
                        issue.relevant_log_snippets.append(
                            LogSnippet(source=src, lines=lines[:20], highlight_indices=highlight[:10], level="error")
                        )

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

            # Step 6: Build topology
            yield send("topology", "Building cluster topology graph...", 80)
            correlator = LogCorrelator()
            timeline_events = correlator.correlate(
                parsed_data.get("events", []), parsed_data.get("logs", []), all_issues
            )
            topology_nodes, topology_edges = correlator.build_topology(parsed_data)
            correlation_groups = correlator.build_correlation_groups(
                timeline_events, parsed_data.get("logs", []), all_issues
            )
            resource_health = correlator.build_resource_health(parsed_data)

            # Step 7: Finalize
            yield send("finalizing", "Computing health score...", 90)
            cluster_health = _compute_cluster_health(parsed_data, all_issues)
            log_entries = _extract_top_logs(parsed_data.get("logs", []), limit=200)
            raw_events = [te.model_dump() for te in timeline_events[:500]]

            result = AnalysisResult(
                bundle_id=bundle_id,
                status=BundleStatus.completed,
                cluster_health=cluster_health,
                issues=all_issues,
                log_entries=log_entries,
                topology_nodes=topology_nodes,
                topology_edges=topology_edges,
                summary=ai_result.get("summary", "Analysis complete."),
                analyzed_at=datetime.now(UTC),
                raw_events=raw_events,
                correlations=correlation_groups,
                resource_health=resource_health,
                ai_insights=ai_result.get("insights", []),
            )

            _analyses[bundle_id] = result
            _save_analysis(bundle_id, result)
            save_analysis(bundle_id, result.model_dump(mode="json"))

            # RAG indexing
            yield send("indexing", "Indexing for search...", 95)
            try:
                chunks = chunk_bundle(bundle_id, parsed_data)
                index_chunks(chunks)
                from app.persistence import save_chunks

                save_chunks(chunks)
            except Exception:
                pass

            bundle.status = BundleStatus.completed
            _save_bundle_info(bundle_id, bundle)

            # Register hash in cache
            bundle_hash = _bundle_hashes.get(bundle_id)
            if bundle_hash:
                _hash_to_analysis[bundle_hash] = bundle_id

            yield send("complete", f"Analysis complete — {len(all_issues)} issues found", 100)

        except Exception as e:
            bundle.status = BundleStatus.failed
            yield f"data: {json.dumps({'step': 'error', 'detail': str(e), 'progress': 0})}\n\n"

    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.post("/{bundle_id}/analyze", response_model=AnalysisResult, tags=["Analysis"])
async def analyze_bundle(bundle_id: str):
    """Run analysis on an uploaded bundle."""
    if bundle_id not in _bundles:
        raise HTTPException(status_code=404, detail="Bundle not found")

    bundle = _bundles[bundle_id]

    # Cache hit: if this exact bundle content was already analyzed, return cached
    bundle_hash = _bundle_hashes.get(bundle_id)
    if bundle_hash and bundle_hash in _hash_to_analysis:
        cached_id = _hash_to_analysis[bundle_hash]
        if cached_id in _analyses and cached_id != bundle_id:
            cached = _analyses[cached_id]
            # Clone result for this bundle_id
            result = cached.model_copy(update={"bundle_id": bundle_id, "analyzed_at": datetime.now(UTC)})
            _analyses[bundle_id] = result
            bundle.status = BundleStatus.completed
            return result

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
        ai_analyzer = AIAnalyzer()
        ai_result = await asyncio.to_thread(ai_analyzer.analyze, parsed_data, heuristic_issues, bundle_id)

        # Step 4: Merge AI additional issues into the issues list
        all_issues = list(heuristic_issues)
        for ai_issue_data in ai_result.get("additional_issues", []):
            try:
                severity_val = ai_issue_data.get("severity", "info").lower()
                if severity_val not in ("critical", "warning", "info"):
                    severity_val = "info"
                all_issues.append(
                    Issue(
                        severity=Severity(severity_val),
                        title=ai_issue_data.get("title", "AI-detected issue"),
                        category=ai_issue_data.get("category", "configuration"),
                        description=ai_issue_data.get("description", ""),
                        evidence=ai_issue_data.get("evidence", []),
                        remediation=ai_issue_data.get("remediation", ""),
                        ai_confidence=0.75,
                    )
                )
            except Exception as e:
                logger.warning("Could not parse AI issue: %s", e)

        # Step 5: Enrich each issue with proposed_fixes, relevant_log_snippets, ai_explanation
        all_logs = parsed_data.get("logs", [])
        for issue in all_issues:
            # Generate proposed_fixes from remediation text if not already set
            if not issue.proposed_fixes and issue.remediation:
                fix_steps = [s.strip() for s in issue.remediation.replace(". ", ".\n").split("\n") if s.strip()]
                for step in fix_steps:
                    command = None
                    is_automated = False
                    if "kubectl" in step:
                        cmd_start = step.find("kubectl")
                        command = step[cmd_start:].strip().rstrip(".")
                        is_automated = True
                    issue.proposed_fixes.append(
                        ProposedFix(
                            description=step,
                            command=command,
                            is_automated=is_automated,
                        )
                    )

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
                    issue.relevant_log_snippets.append(
                        LogSnippet(
                            source=src,
                            lines=lines[:20],
                            highlight_indices=highlight[:10],
                            level="error",
                        )
                    )

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
            analyzed_at=datetime.now(UTC),
            raw_events=raw_events,
            correlations=correlation_groups,
            resource_health=resource_health,
            ai_insights=ai_insights,
        )

        _analyses[bundle_id] = result
        _save_analysis(bundle_id, result)
        save_analysis(bundle_id, result.model_dump(mode="json"))

        # Step 13: Chunk and index for RAG
        try:
            chunks = chunk_bundle(bundle_id, parsed_data)
            indexed = index_chunks(chunks)
            logger.info("Indexed %d chunks for bundle %s", indexed, bundle_id)
            from app.persistence import save_chunks

            save_chunks(chunks)
        except Exception as e:
            logger.warning("RAG indexing failed (non-fatal): %s", e)

        _save_bundle_info(bundle_id, bundle)
        bundle.status = BundleStatus.completed
        logger.info("Analysis complete for bundle %s: %d issues found", bundle_id, len(all_issues))

        # Register hash in cache
        bundle_hash = _bundle_hashes.get(bundle_id)
        if bundle_hash:
            _hash_to_analysis[bundle_hash] = bundle_id

        return result

    except Exception as e:
        bundle.status = BundleStatus.failed
        logger.error("Analysis failed for bundle %s: %s", bundle_id, e)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")


@router.get("/{bundle_id}/analysis", response_model=AnalysisResult, tags=["Analysis"])
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

    _bundles[bundle_id]

    # Remove files from disk
    bundle_dir = DATA_DIR / bundle_id
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir, ignore_errors=True)
        logger.info("Deleted bundle files at %s", bundle_dir)

    db_delete_bundle(bundle_id)

    try:
        delete_bundle_chunks(bundle_id)
    except Exception:
        pass

    # Remove from in-memory stores
    del _bundles[bundle_id]
    _analyses.pop(bundle_id, None)
    _parsed_data.pop(bundle_id, None)

    return {"detail": "Bundle deleted", "id": bundle_id}


@router.post("/{bundle_id}/reanalyze", response_model=AnalysisResult, tags=["Analysis"])
async def reanalyze_bundle(bundle_id: str):
    """Re-run analysis on an already uploaded bundle."""
    if bundle_id not in _bundles:
        raise HTTPException(status_code=404, detail="Bundle not found")

    # Remove any existing analysis so it runs fresh
    _analyses.pop(bundle_id, None)

    # Re-run the full analysis pipeline
    return await analyze_bundle(bundle_id)


@router.get("/{bundle_id}/export", tags=["Export"])
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


@router.get("/{bundle_id}/preflight", tags=["Export"])
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


@router.post("/{bundle_id}/chat", response_model=ChatResponse, tags=["Chat"])
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

    chat = BundleChat(parsed, analysis, bundle_id=bundle_id)
    history = [{"role": m.role, "content": m.content} for m in body.history]

    try:
        result = await asyncio.to_thread(chat.ask, body.question, history)
        if isinstance(result, dict):
            answer = result.get("answer", "")
            retrieval_sources = result.get("sources", [])
        else:
            answer = result
            retrieval_sources = []
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

    # Add RAG retrieval sources
    for rs in retrieval_sources:
        src_desc = f"[RAG:{rs.get('type', '')}]"
        if rs.get("namespace"):
            src_desc += f" ns:{rs['namespace']}"
        if rs.get("pod"):
            src_desc += f" pod:{rs['pod']}"
        if rs.get("relevance"):
            src_desc += f" (relevance: {rs['relevance']})"
        sources.append(src_desc)

    return ChatResponse(answer=answer, sources=sources)


@router.get("/{bundle_id}/history", tags=["History"])
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
            entries.append(
                AnalysisHistoryEntry(
                    analyzed_at=data.get("analyzed_at", ""),
                    health_score=health.get("score", 0),
                    critical_count=health.get("critical_count", 0),
                    warning_count=health.get("warning_count", 0),
                    info_count=health.get("info_count", 0),
                    issue_count=len(issues),
                )
            )
        except Exception as e:
            logger.warning("Failed to read history file %s: %s", f, e)

    # Supplement with DB history
    if is_db_available():
        db_history = db_load_history(bundle_id)
        # Merge — add DB entries that aren't already in file-based history
        existing_timestamps = {
            e.analyzed_at.isoformat() if hasattr(e, "analyzed_at") else str(e.get("analyzed_at", "")) for e in entries
        }
        for entry in db_history:
            if entry["analyzed_at"] not in existing_timestamps:
                entries.append(AnalysisHistoryEntry.model_validate(entry))

    return entries


@router.get("/{bundle_id}/history/{timestamp}", tags=["History"])
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


@router.post("/compare", response_model=CompareResponse, tags=["History"])
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

    total_pods = len(pods)
    running_pods = sum(1 for p in pods if p.get("status", {}).get("phase") in ("Running", "Succeeded"))

    # Node health
    ready_nodes = sum(
        1
        for n in nodes
        if any(
            c.get("type") == "Ready" and c.get("status") == "True" for c in n.get("status", {}).get("conditions", [])
        )
    )
    node_ratio = (ready_nodes / len(nodes)) if nodes else 1.0

    # Workload readiness: Deployments + StatefulSets + DaemonSets
    total_desired = 0
    total_ready = 0
    for deploy in parsed_data.get("deployments", []):
        d = deploy.get("status", {}).get("replicas", 0) or 0
        r = deploy.get("status", {}).get("readyReplicas", 0) or 0
        total_desired += d
        total_ready += r
    for sts in parsed_data.get("statefulsets", []):
        d = sts.get("spec", {}).get("replicas", 0) or 0
        r = sts.get("status", {}).get("readyReplicas", 0) or 0
        total_desired += d
        total_ready += r
    for ds in parsed_data.get("daemonsets", []):
        d = ds.get("status", {}).get("desiredNumberScheduled", 0) or 0
        r = ds.get("status", {}).get("numberReady", 0) or 0
        total_desired += d
        total_ready += r
    workload_ratio = (total_ready / total_desired) if total_desired > 0 else 1.0

    # Stability: restart velocity + warning event frequency
    total_restarts = 0
    for pod in pods:
        for cs in pod.get("status", {}).get("containerStatuses", []) or []:
            total_restarts += cs.get("restartCount", 0)
    events = parsed_data.get("events", [])
    warning_events = sum(1 for e in events if e.get("type") == "Warning")
    # Normalize: 0 restarts & 0 warnings = 1.0, scale down from there
    restart_penalty = min(1.0, total_restarts / max(total_pods * 10, 1))
    event_penalty = min(1.0, warning_events / max(total_pods * 5, 1))
    stability = 1.0 - (restart_penalty * 0.5 + event_penalty * 0.5)

    if total_pods > 0:
        # Count pods with known-good status
        known_pods = sum(
            1 for p in pods if p.get("status", {}).get("phase") in ("Running", "Succeeded", "Pending", "Failed")
        )
        # If all pods are synthesized (Unknown phase), use issue-based scoring instead
        if known_pods > 0:
            pod_ratio = running_pods / total_pods
        else:
            pod_ratio = 0.5  # Assume moderate health when phases are unknown

        # Weighted formula:
        # 40% pod health, 15% node health, 15% workload readiness,
        # 15% issue penalty, 15% stability
        pod_score = pod_ratio * 40
        node_score = node_ratio * 15
        workload_score = workload_ratio * 15

        # Issue penalty: critical issues hurt more
        max_issue_penalty = 15
        issue_penalty = min(max_issue_penalty, critical_count * 4 + warning_count * 1.5)
        issue_score = max_issue_penalty - issue_penalty

        stability_score = stability * 15

        score = int(max(0, min(100, pod_score + node_score + workload_score + issue_score + stability_score)))
    else:
        # No pods at all — score based purely on issues
        if critical_count > 0:
            score = max(10, 50 - critical_count * 10 - warning_count * 3)
        elif warning_count > 0:
            score = max(30, 70 - warning_count * 5)
        else:
            score = 50

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
