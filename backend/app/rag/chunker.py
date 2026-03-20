"""Chunk parsed bundle data into retrieval-friendly documents."""
from __future__ import annotations

import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Target ~600 tokens per chunk, ~100 token overlap for log chunks
MAX_CHUNK_LINES = 30
OVERLAP_LINES = 5


def chunk_bundle(bundle_id: str, parsed_data: dict[str, Any]) -> list[dict]:
    """Chunk all parsed bundle data into documents with metadata.

    Returns list of dicts with keys:
      id, bundle_id, chunk_type, content, metadata (dict with namespace, pod, node, etc.)
    """
    chunks: list[dict] = []

    # 1. Pod status chunks — one per pod
    for pod in parsed_data.get("pods", []):
        meta = pod.get("metadata", {})
        name = meta.get("name", "unknown")
        ns = meta.get("namespace", "unknown")
        status = pod.get("status", {})
        phase = status.get("phase", "Unknown")

        # Build readable content
        lines = [f"Pod: {ns}/{name}", f"Phase: {phase}"]
        for cs in status.get("containerStatuses", []) or []:
            c_name = cs.get("name", "?")
            restarts = cs.get("restartCount", 0)
            waiting = cs.get("state", {}).get("waiting", {})
            terminated = cs.get("lastState", {}).get("terminated", {})
            lines.append(f"Container {c_name}: restarts={restarts}")
            if waiting.get("reason"):
                lines.append(f"  Waiting: {waiting['reason']} - {waiting.get('message', '')}")
            if terminated.get("reason"):
                lines.append(f"  Last terminated: {terminated['reason']} exitCode={terminated.get('exitCode', '?')}")

        for c in status.get("conditions", []) or []:
            if c.get("status") != "True":
                lines.append(f"  Condition {c.get('type')}: {c.get('status')} - {c.get('message', '')}")

        chunks.append(_make_chunk(
            bundle_id=bundle_id,
            chunk_type="pod_status",
            content="\n".join(lines),
            namespace=ns,
            pod=name,
            resource_kind="Pod",
            resource_name=name,
            severity=_pod_severity(phase, status),
        ))

    # 2. Node chunks — one per node
    for node in parsed_data.get("nodes", []):
        name = node.get("metadata", {}).get("name", "unknown")
        conditions = node.get("status", {}).get("conditions", []) or []
        lines = [f"Node: {name}"]
        for c in conditions:
            lines.append(f"  {c.get('type')}: {c.get('status')} - {c.get('reason', '')} {c.get('message', '')}")

        chunks.append(_make_chunk(
            bundle_id=bundle_id,
            chunk_type="node_status",
            content="\n".join(lines),
            node=name,
            resource_kind="Node",
            resource_name=name,
            severity="critical" if any(c.get("type") == "Ready" and c.get("status") != "True" for c in conditions) else "healthy",
        ))

    # 3. Event chunks — group warning events by resource
    events = parsed_data.get("events", [])
    warning_events = [e for e in events if e.get("type") == "Warning"]
    # Group by involved object
    event_groups: dict[str, list[dict]] = {}
    for ev in warning_events:
        involved = ev.get("involvedObject", {})
        key = f"{involved.get('kind', '?')}/{involved.get('name', '?')}"
        event_groups.setdefault(key, []).append(ev)

    for resource_key, group in event_groups.items():
        lines = [f"Warning events for {resource_key} ({len(group)} events):"]
        for ev in group[:15]:
            reason = ev.get("reason", "?")
            msg = ev.get("message", "")[:200]
            count = ev.get("count", 1)
            lines.append(f"  [{reason}] (x{count}) {msg}")

        involved = group[0].get("involvedObject", {})
        chunks.append(_make_chunk(
            bundle_id=bundle_id,
            chunk_type="warning_events",
            content="\n".join(lines),
            namespace=involved.get("namespace"),
            resource_kind=involved.get("kind"),
            resource_name=involved.get("name"),
            severity="warning",
        ))

    # 4. Log chunks — window-based chunking per source
    logs = parsed_data.get("logs", [])
    # Group by source
    log_groups: dict[str, list[dict]] = {}
    for log in logs:
        src = log.get("source", "unknown")
        log_groups.setdefault(src, []).append(log)

    for source, source_logs in log_groups.items():
        # Split into chunks with overlap
        for i in range(0, len(source_logs), MAX_CHUNK_LINES - OVERLAP_LINES):
            window = source_logs[i:i + MAX_CHUNK_LINES]
            if not window:
                break

            lines = [f"Logs from {source}:"]
            has_errors = False
            for log in window:
                level = log.get("level", "info")
                msg = log.get("message", "")[:200]
                ts = log.get("timestamp", "")
                prefix = f"[{ts}] " if ts else ""
                lines.append(f"  {prefix}[{level.upper()}] {msg}")
                if level in ("error", "warn"):
                    has_errors = True

            parts = source.split("/")
            ns = parts[0] if len(parts) > 0 else None
            pod = parts[1] if len(parts) > 1 else None

            chunks.append(_make_chunk(
                bundle_id=bundle_id,
                chunk_type="pod_log",
                content="\n".join(lines),
                namespace=ns,
                pod=pod,
                source_path=source,
                severity="error" if has_errors else "info",
            ))

    # 5. Cluster summary chunk
    nodes = parsed_data.get("nodes", [])
    pods = parsed_data.get("pods", [])
    namespaces = parsed_data.get("namespaces", [])
    cv = parsed_data.get("cluster_version")
    version_str = ""
    if isinstance(cv, dict):
        version_str = cv.get("gitVersion", str(cv))
    elif cv:
        version_str = str(cv)

    running = sum(1 for p in pods if p.get("status", {}).get("phase") == "Running")
    summary_lines = [
        "Cluster Summary:",
        f"  Version: {version_str}" if version_str else "  Version: unknown",
        f"  Nodes: {len(nodes)}",
        f"  Pods: {len(pods)} ({running} running)",
        f"  Namespaces: {len(namespaces)}",
        f"  Warning events: {len(warning_events)}",
    ]
    chunks.append(_make_chunk(
        bundle_id=bundle_id,
        chunk_type="cluster_summary",
        content="\n".join(summary_lines),
    ))

    logger.info("Chunked bundle %s into %d chunks", bundle_id, len(chunks))
    return chunks


def _make_chunk(
    bundle_id: str,
    chunk_type: str,
    content: str,
    namespace: str | None = None,
    pod: str | None = None,
    node: str | None = None,
    resource_kind: str | None = None,
    resource_name: str | None = None,
    severity: str | None = None,
    source_path: str | None = None,
) -> dict:
    """Create a chunk dict with deterministic ID."""
    chunk_id = hashlib.sha256(f"{bundle_id}:{chunk_type}:{content[:200]}".encode()).hexdigest()[:16]
    return {
        "id": f"{bundle_id[:8]}-{chunk_id}",
        "bundle_id": bundle_id,
        "chunk_type": chunk_type,
        "content": content,
        "metadata": {
            "bundle_id": bundle_id,
            "chunk_type": chunk_type,
            "namespace": namespace,
            "pod": pod,
            "node": node,
            "resource_kind": resource_kind,
            "resource_name": resource_name,
            "severity": severity,
            "source_path": source_path,
        },
    }


def _pod_severity(phase: str, status: dict) -> str:
    """Determine severity from pod status."""
    if phase in ("Failed",):
        return "critical"
    for cs in status.get("containerStatuses", []) or []:
        waiting = cs.get("state", {}).get("waiting", {}).get("reason", "")
        if waiting in ("CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull"):
            return "critical"
        terminated = cs.get("lastState", {}).get("terminated", {}).get("reason", "")
        if terminated == "OOMKilled":
            return "critical"
    if phase == "Pending":
        return "warning"
    return "healthy"
