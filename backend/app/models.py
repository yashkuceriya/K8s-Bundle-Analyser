from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


class BundleStatus(str, Enum):
    """Lifecycle status of an uploaded support bundle."""

    uploaded = "uploaded"
    analyzing = "analyzing"
    completed = "completed"
    failed = "failed"


class BundleInfo(BaseModel):
    """Metadata for an uploaded support bundle."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str
    upload_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: BundleStatus = BundleStatus.uploaded
    file_path: str = Field(exclude=True, default="")


class Severity(str, Enum):
    """Issue severity level."""

    critical = "critical"
    warning = "warning"
    info = "info"


class ProposedFix(BaseModel):
    """A suggested remediation step with an optional CLI command."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    command: str | None = None
    is_automated: bool = False


class AIExplanation(BaseModel):
    """AI-generated root-cause analysis for an issue."""

    root_cause: str
    impact: str
    related_issues: list[str] = []


class LogSnippet(BaseModel):
    """A snippet of log lines associated with an issue."""

    source: str
    lines: list[str]
    highlight_indices: list[int] = []
    level: str = "error"


class Issue(BaseModel):
    """A detected cluster issue with severity, evidence, and remediation."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    severity: Severity
    title: str
    category: str  # pod-health, networking, storage, configuration, security, resource-usage
    resource: str | None = None
    namespace: str | None = None
    description: str
    evidence: list[str] = Field(default_factory=list)
    remediation: str
    ai_confidence: float | None = None  # 0-1
    proposed_fixes: list[ProposedFix] = []
    ai_explanation: AIExplanation | None = None
    relevant_log_snippets: list[LogSnippet] = []


class ClusterHealth(BaseModel):
    """Aggregate cluster health metrics."""

    score: int = 100  # 0-100
    node_count: int = 0
    pod_count: int = 0
    namespace_count: int = 0
    critical_count: int = 0
    warning_count: int = 0
    info_count: int = 0


class LogEntry(BaseModel):
    """A single parsed log line from a pod container."""

    timestamp: str | None = None
    source: str
    level: str  # error, warn, info
    message: str
    namespace: str | None = None
    pod: str | None = None


class TopologyNode(BaseModel):
    """A node in the cluster resource topology graph."""

    id: str
    label: str
    type: str  # node, namespace, deployment, pod, service
    status: str = "unknown"  # healthy, warning, critical, unknown
    namespace: str | None = None
    metadata: dict = Field(default_factory=dict)


class TopologyEdge(BaseModel):
    """An edge connecting two topology nodes."""

    source: str
    target: str
    label: str | None = None


class TimelineEvent(BaseModel):
    """A single event on the cluster timeline."""

    timestamp: str
    type: str
    message: str
    severity: str
    resource: str | None = None


class CorrelationGroup(BaseModel):
    """A group of correlated timeline events for a single resource."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    events: list[TimelineEvent] = []
    explanation: str = ""
    sparkline_data: list[dict] = []


class ResourceHealthDot(BaseModel):
    """Health indicator for a single cluster resource."""

    id: str
    name: str
    type: str
    namespace: str = ""
    status: str = "unknown"


class AnalysisResult(BaseModel):
    """Complete analysis output for a support bundle."""

    bundle_id: str
    status: BundleStatus
    cluster_health: ClusterHealth = Field(default_factory=ClusterHealth)
    issues: list[Issue] = Field(default_factory=list)
    log_entries: list[LogEntry] = Field(default_factory=list)
    topology_nodes: list[TopologyNode] = Field(default_factory=list)
    topology_edges: list[TopologyEdge] = Field(default_factory=list)
    summary: str = ""
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw_events: list[dict] = Field(default_factory=list)
    correlations: list[CorrelationGroup] = []
    resource_health: list[ResourceHealthDot] = []
    ai_insights: list[str] = []


class AnalysisHistoryEntry(BaseModel):
    """Summary of a single analysis run for history listing."""

    analyzed_at: datetime
    health_score: int
    critical_count: int
    warning_count: int
    info_count: int
    issue_count: int


class CompareRequest(BaseModel):
    """Request body for comparing two analyses."""

    left_bundle_id: str
    left_timestamp: str | None = None
    right_bundle_id: str
    right_timestamp: str | None = None


class CompareResponse(BaseModel):
    """Response body with two analyses for comparison."""

    left: AnalysisResult
    right: AnalysisResult
