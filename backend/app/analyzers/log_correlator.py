from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

from app.models import (
    CorrelationGroup,
    Issue,
    ResourceHealthDot,
    TimelineEvent,
    TopologyEdge,
    TopologyNode,
)


class LogCorrelator:
    """Correlates events and logs into a timeline and builds cluster topology."""

    def correlate(
        self,
        events: list[dict],
        logs: list[dict],
        issues: list[Issue],
    ) -> list[TimelineEvent]:
        """
        Merge K8s events and error/warning logs into a unified timeline,
        sorted by timestamp.
        """
        timeline: list[TimelineEvent] = []

        # Add K8s events to timeline
        for event in events:
            ts = (
                event.get("lastTimestamp")
                or event.get("eventTime")
                or event.get("metadata", {}).get("creationTimestamp", "")
            )
            if not ts:
                continue

            involved = event.get("involvedObject", {})
            resource = ""
            if involved.get("kind") and involved.get("name"):
                resource = f"{involved['kind']}/{involved['name']}"

            event_type = event.get("type", "Normal")
            severity = "info"
            if event_type == "Warning":
                severity = "warning"
                reason = event.get("reason", "").lower()
                if any(kw in reason for kw in ("failed", "error", "oom", "crash", "backoff")):
                    severity = "critical"

            timeline.append(
                TimelineEvent(
                    timestamp=ts,
                    type=f"event/{event.get('reason', 'Unknown')}",
                    message=event.get("message", "")[:500],
                    severity=severity,
                    resource=resource or None,
                )
            )

        # Add error/warning log entries to timeline
        error_logs = [l for l in logs if l.get("level") in ("error", "warn")]
        for log in error_logs[-200:]:  # limit to recent entries
            ts = log.get("timestamp", "")
            if not ts:
                continue

            source = log.get("source", "")
            pod = log.get("pod")
            log.get("namespace")
            resource = f"pod/{pod}" if pod else None

            severity = "warning" if log.get("level") == "warn" else "critical"

            timeline.append(
                TimelineEvent(
                    timestamp=ts,
                    type=f"log/{log.get('level', 'unknown')}",
                    message=f"[{source}] {log.get('message', '')[:400]}",
                    severity=severity,
                    resource=resource,
                )
            )

        # Sort by timestamp
        timeline.sort(key=lambda e: e.timestamp)

        return timeline

    def build_topology(self, parsed_data: dict[str, Any]) -> tuple[list[TopologyNode], list[TopologyEdge]]:
        """
        Build a graph of cluster resources with health status.

        Returns (nodes, edges) where:
        - nodes are K8s nodes, namespaces, deployments, pods, services
        - edges represent scheduling, ownership, and selection relationships
        """
        topo_nodes: list[TopologyNode] = []
        topo_edges: list[TopologyEdge] = []
        seen_ids: set[str] = set()

        # Add K8s nodes
        for node in parsed_data.get("nodes", []):
            node_name = node.get("metadata", {}).get("name", "unknown")
            node_id = f"node/{node_name}"
            if node_id in seen_ids:
                continue
            seen_ids.add(node_id)

            status = self._node_health(node)
            topo_nodes.append(
                TopologyNode(
                    id=node_id,
                    label=node_name,
                    type="node",
                    status=status,
                    metadata={
                        "kubeletVersion": node.get("status", {}).get("nodeInfo", {}).get("kubeletVersion", ""),
                        "os": node.get("status", {}).get("nodeInfo", {}).get("osImage", ""),
                    },
                )
            )

        # Add namespaces
        namespaces_seen: set[str] = set()
        for ns in parsed_data.get("namespaces", []):
            ns_name = ns.get("metadata", {}).get("name", "unknown")
            namespaces_seen.add(ns_name)

        # Also collect namespaces from pods
        for pod in parsed_data.get("pods", []):
            ns = pod.get("metadata", {}).get("namespace", "")
            if ns:
                namespaces_seen.add(ns)

        for ns_name in namespaces_seen:
            ns_id = f"namespace/{ns_name}"
            if ns_id in seen_ids:
                continue
            seen_ids.add(ns_id)
            topo_nodes.append(
                TopologyNode(
                    id=ns_id,
                    label=ns_name,
                    type="namespace",
                    status="healthy",
                    namespace=ns_name,
                )
            )

        # Add deployments
        for deploy in parsed_data.get("deployments", []):
            meta = deploy.get("metadata", {})
            name = meta.get("name", "unknown")
            ns = meta.get("namespace", "default")
            deploy_id = f"deployment/{ns}/{name}"
            if deploy_id in seen_ids:
                continue
            seen_ids.add(deploy_id)

            # Determine health
            status_obj = deploy.get("status", {})
            ready = status_obj.get("readyReplicas", 0) or 0
            desired = status_obj.get("replicas", 0) or 0
            deploy_status = "healthy"
            if desired > 0 and ready == 0:
                deploy_status = "critical"
            elif ready < desired:
                deploy_status = "warning"

            topo_nodes.append(
                TopologyNode(
                    id=deploy_id,
                    label=name,
                    type="deployment",
                    status=deploy_status,
                    namespace=ns,
                    metadata={
                        "replicas": desired,
                        "readyReplicas": ready,
                    },
                )
            )

        # Add services
        for svc in parsed_data.get("services", []):
            meta = svc.get("metadata", {})
            name = meta.get("name", "unknown")
            ns = meta.get("namespace", "default")
            svc_id = f"service/{ns}/{name}"
            if svc_id in seen_ids:
                continue
            seen_ids.add(svc_id)

            topo_nodes.append(
                TopologyNode(
                    id=svc_id,
                    label=name,
                    type="service",
                    status="healthy",
                    namespace=ns,
                    metadata={
                        "type": svc.get("spec", {}).get("type", "ClusterIP"),
                        "clusterIP": svc.get("spec", {}).get("clusterIP", ""),
                    },
                )
            )

        # Add StatefulSets
        for sts in parsed_data.get("statefulsets", []):
            meta = sts.get("metadata", {})
            name = meta.get("name", "unknown")
            ns = meta.get("namespace", "default")
            sts_id = f"statefulset/{ns}/{name}"
            if sts_id in seen_ids:
                continue
            seen_ids.add(sts_id)

            desired = sts.get("spec", {}).get("replicas", 0) or 0
            ready = sts.get("status", {}).get("readyReplicas", 0) or 0
            sts_status = "healthy"
            if desired > 0 and ready == 0:
                sts_status = "critical"
            elif ready < desired:
                sts_status = "warning"

            topo_nodes.append(
                TopologyNode(
                    id=sts_id,
                    label=name,
                    type="statefulset",
                    status=sts_status,
                    namespace=ns,
                    metadata={"replicas": desired, "readyReplicas": ready},
                )
            )

        # Add DaemonSets
        for ds in parsed_data.get("daemonsets", []):
            meta = ds.get("metadata", {})
            name = meta.get("name", "unknown")
            ns = meta.get("namespace", "default")
            ds_id = f"daemonset/{ns}/{name}"
            if ds_id in seen_ids:
                continue
            seen_ids.add(ds_id)

            desired = ds.get("status", {}).get("desiredNumberScheduled", 0) or 0
            ready = ds.get("status", {}).get("numberReady", 0) or 0
            ds_status = "healthy"
            if desired > 0 and ready == 0:
                ds_status = "critical"
            elif ready < desired:
                ds_status = "warning"

            topo_nodes.append(
                TopologyNode(
                    id=ds_id,
                    label=name,
                    type="daemonset",
                    status=ds_status,
                    namespace=ns,
                    metadata={"desired": desired, "ready": ready},
                )
            )

        # Add Jobs
        for job in parsed_data.get("jobs", []):
            meta = job.get("metadata", {})
            name = meta.get("name", "unknown")
            ns = meta.get("namespace", "default")
            job_id = f"job/{ns}/{name}"
            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            failed = job.get("status", {}).get("failed", 0) or 0
            succeeded = job.get("status", {}).get("succeeded", 0) or 0
            job_status = "healthy"
            if failed > 0:
                job_status = "critical"
            elif succeeded == 0:
                job_status = "warning"

            topo_nodes.append(
                TopologyNode(
                    id=job_id,
                    label=name,
                    type="job",
                    status=job_status,
                    namespace=ns,
                    metadata={"succeeded": succeeded, "failed": failed},
                )
            )

        # Add Ingresses
        for ing in parsed_data.get("ingresses", []):
            meta = ing.get("metadata", {})
            name = meta.get("name", "unknown")
            ns = meta.get("namespace", "default")
            ing_id = f"ingress/{ns}/{name}"
            if ing_id in seen_ids:
                continue
            seen_ids.add(ing_id)

            topo_nodes.append(
                TopologyNode(
                    id=ing_id,
                    label=name,
                    type="ingress",
                    status="healthy",
                    namespace=ns,
                    metadata={},
                )
            )

        # Add pods and create edges
        for pod in parsed_data.get("pods", []):
            meta = pod.get("metadata", {})
            name = meta.get("name", "unknown")
            ns = meta.get("namespace", "default")
            pod_id = f"pod/{ns}/{name}"
            if pod_id in seen_ids:
                continue
            seen_ids.add(pod_id)

            pod_status = self._pod_health(pod)
            topo_nodes.append(
                TopologyNode(
                    id=pod_id,
                    label=name,
                    type="pod",
                    status=pod_status,
                    namespace=ns,
                    metadata={
                        "phase": pod.get("status", {}).get("phase", "Unknown"),
                        "nodeName": pod.get("spec", {}).get("nodeName", ""),
                    },
                )
            )

            # Edge: node -> pod (scheduled on)
            node_name = pod.get("spec", {}).get("nodeName", "")
            if node_name:
                node_id = f"node/{node_name}"
                topo_edges.append(
                    TopologyEdge(
                        source=node_id,
                        target=pod_id,
                        label="runs",
                    )
                )

            # Edge: deployment -> pod (ownership)
            owner_refs = meta.get("ownerReferences", []) or []
            for owner in owner_refs:
                owner_kind = owner.get("kind", "")
                owner_name = owner.get("name", "")
                if owner_kind == "ReplicaSet":
                    # Try to find the parent deployment from the ReplicaSet name
                    # ReplicaSet names are typically <deployment-name>-<hash>
                    parts = owner_name.rsplit("-", 1)
                    if len(parts) == 2:
                        deploy_candidate = parts[0]
                        deploy_id = f"deployment/{ns}/{deploy_candidate}"
                        if deploy_id in seen_ids:
                            topo_edges.append(
                                TopologyEdge(
                                    source=deploy_id,
                                    target=pod_id,
                                    label="owns",
                                )
                            )
                elif owner_kind == "StatefulSet":
                    sts_id = f"statefulset/{ns}/{owner_name}"
                    if sts_id in seen_ids:
                        topo_edges.append(
                            TopologyEdge(
                                source=sts_id,
                                target=pod_id,
                                label="owns",
                            )
                        )
                elif owner_kind == "DaemonSet":
                    ds_id = f"daemonset/{ns}/{owner_name}"
                    if ds_id in seen_ids:
                        topo_edges.append(
                            TopologyEdge(
                                source=ds_id,
                                target=pod_id,
                                label="owns",
                            )
                        )
                elif owner_kind == "Job":
                    job_id = f"job/{ns}/{owner_name}"
                    if job_id in seen_ids:
                        topo_edges.append(
                            TopologyEdge(
                                source=job_id,
                                target=pod_id,
                                label="owns",
                            )
                        )

        # Edge: service -> pod (selector matching)
        for svc in parsed_data.get("services", []):
            svc_meta = svc.get("metadata", {})
            svc_name = svc_meta.get("name", "unknown")
            svc_ns = svc_meta.get("namespace", "default")
            svc_id = f"service/{svc_ns}/{svc_name}"

            selector = svc.get("spec", {}).get("selector") or {}
            if not selector:
                continue

            # Match pods by labels
            for pod in parsed_data.get("pods", []):
                pod_meta = pod.get("metadata", {})
                pod_ns = pod_meta.get("namespace", "default")
                if pod_ns != svc_ns:
                    continue
                pod_labels = pod_meta.get("labels", {}) or {}
                if all(pod_labels.get(k) == v for k, v in selector.items()):
                    pod_name = pod_meta.get("name", "unknown")
                    pod_id = f"pod/{pod_ns}/{pod_name}"
                    topo_edges.append(
                        TopologyEdge(
                            source=svc_id,
                            target=pod_id,
                            label="selects",
                        )
                    )

        # Edge: ingress -> service (backend)
        for ing in parsed_data.get("ingresses", []):
            ing_meta = ing.get("metadata", {})
            ing_name = ing_meta.get("name", "unknown")
            ing_ns = ing_meta.get("namespace", "default")
            ing_id = f"ingress/{ing_ns}/{ing_name}"

            for rule in ing.get("spec", {}).get("rules", []) or []:
                for path_entry in (rule.get("http", {}) or {}).get("paths", []) or []:
                    backend = path_entry.get("backend", {})
                    svc_name = backend.get("service", {}).get("name", backend.get("serviceName", ""))
                    if svc_name:
                        svc_id = f"service/{ing_ns}/{svc_name}"
                        topo_edges.append(
                            TopologyEdge(
                                source=ing_id,
                                target=svc_id,
                                label="routes",
                            )
                        )

        logger.info("Built topology: %d nodes, %d edges", len(topo_nodes), len(topo_edges))
        return topo_nodes, topo_edges

    def build_correlation_groups(
        self,
        events: list[TimelineEvent],
        logs: list[dict],
        issues: list[Issue],
    ) -> list[CorrelationGroup]:
        """
        Group timeline events by resource and build correlation groups
        with sparkline data for time-bucketed event counts.
        """
        # Group events by resource (pod name or node name)
        resource_events: dict[str, list[TimelineEvent]] = {}
        for event in events:
            key = event.resource or "cluster"
            resource_events.setdefault(key, []).append(event)

        groups: list[CorrelationGroup] = []
        for resource, res_events in resource_events.items():
            if len(res_events) < 2:
                continue

            # Sort events by timestamp
            sorted_events = sorted(res_events, key=lambda e: e.timestamp)

            # Build sparkline data by bucketing timestamps into intervals
            sparkline_data = self._build_sparkline(sorted_events)

            # Build explanation from event types and severities
            event_types = list({e.type for e in sorted_events})
            severity_counts: dict[str, int] = {}
            for e in sorted_events:
                severity_counts[e.severity] = severity_counts.get(e.severity, 0) + 1

            severity_summary = ", ".join(f"{count} {sev}" for sev, count in severity_counts.items())
            explanation = (
                f"Resource '{resource}' has {len(sorted_events)} correlated events "
                f"({severity_summary}). Event types: {', '.join(event_types[:5])}."
            )

            groups.append(
                CorrelationGroup(
                    title=f"Events on {resource}",
                    events=sorted_events,
                    explanation=explanation,
                    sparkline_data=sparkline_data,
                )
            )

        logger.info("Built %d correlation groups", len(groups))
        return groups

    def build_resource_health(self, parsed_data: dict[str, Any]) -> list[ResourceHealthDot]:
        """
        Extract all pods, nodes, deployments, and services from parsed_data
        and create a ResourceHealthDot for each with appropriate status.
        """
        dots: list[ResourceHealthDot] = []

        # Pods: check containerStatuses for running/waiting/terminated
        for pod in parsed_data.get("pods", []):
            meta = pod.get("metadata", {})
            name = meta.get("name", "unknown")
            ns = meta.get("namespace", "default")
            pod_id = f"pod/{ns}/{name}"

            phase = pod.get("status", {}).get("phase", "Unknown")
            status = "unknown"
            if phase == "Running":
                status = "healthy"
                for cs in pod.get("status", {}).get("containerStatuses", []) or []:
                    waiting = cs.get("state", {}).get("waiting", {})
                    if waiting.get("reason") in ("CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull"):
                        status = "critical"
                        break
                    if not cs.get("ready", False):
                        status = "warning"
                    if cs.get("restartCount", 0) > 5:
                        status = "warning"
            elif phase == "Succeeded":
                status = "healthy"
            elif phase == "Pending":
                status = "warning"
            elif phase == "Failed":
                status = "critical"

            dots.append(
                ResourceHealthDot(
                    id=pod_id,
                    name=name,
                    type="pod",
                    namespace=ns,
                    status=status,
                )
            )

        # Nodes: check conditions for Ready
        for node in parsed_data.get("nodes", []):
            node_name = node.get("metadata", {}).get("name", "unknown")
            node_id = f"node/{node_name}"

            conditions = node.get("status", {}).get("conditions", []) or []
            status = "unknown"
            for cond in conditions:
                if cond.get("type") == "Ready":
                    if cond.get("status") == "True":
                        status = "healthy"
                        # Check for pressure conditions
                        for c in conditions:
                            if c.get("type") in ("DiskPressure", "MemoryPressure", "PIDPressure"):
                                if c.get("status") == "True":
                                    status = "warning"
                                    break
                    else:
                        status = "critical"
                    break

            dots.append(
                ResourceHealthDot(
                    id=node_id,
                    name=node_name,
                    type="node",
                    namespace="",
                    status=status,
                )
            )

        # Deployments
        for deploy in parsed_data.get("deployments", []):
            meta = deploy.get("metadata", {})
            name = meta.get("name", "unknown")
            ns = meta.get("namespace", "default")
            deploy_id = f"deployment/{ns}/{name}"

            status_obj = deploy.get("status", {})
            ready = status_obj.get("readyReplicas", 0) or 0
            desired = status_obj.get("replicas", 0) or 0
            status = "healthy"
            if desired > 0 and ready == 0:
                status = "critical"
            elif ready < desired:
                status = "warning"

            dots.append(
                ResourceHealthDot(
                    id=deploy_id,
                    name=name,
                    type="deployment",
                    namespace=ns,
                    status=status,
                )
            )

        # Services
        for svc in parsed_data.get("services", []):
            meta = svc.get("metadata", {})
            name = meta.get("name", "unknown")
            ns = meta.get("namespace", "default")
            svc_id = f"service/{ns}/{name}"

            dots.append(
                ResourceHealthDot(
                    id=svc_id,
                    name=name,
                    type="service",
                    namespace=ns,
                    status="healthy",
                )
            )

        # StatefulSets
        for sts in parsed_data.get("statefulsets", []):
            meta = sts.get("metadata", {})
            name = meta.get("name", "unknown")
            ns = meta.get("namespace", "default")
            sts_id = f"statefulset/{ns}/{name}"
            desired = sts.get("spec", {}).get("replicas", 0) or 0
            ready = sts.get("status", {}).get("readyReplicas", 0) or 0
            status = "healthy"
            if desired > 0 and ready == 0:
                status = "critical"
            elif ready < desired:
                status = "warning"
            dots.append(
                ResourceHealthDot(
                    id=sts_id,
                    name=name,
                    type="statefulset",
                    namespace=ns,
                    status=status,
                )
            )

        # DaemonSets
        for ds in parsed_data.get("daemonsets", []):
            meta = ds.get("metadata", {})
            name = meta.get("name", "unknown")
            ns = meta.get("namespace", "default")
            ds_id = f"daemonset/{ns}/{name}"
            desired = ds.get("status", {}).get("desiredNumberScheduled", 0) or 0
            ready = ds.get("status", {}).get("numberReady", 0) or 0
            status = "healthy"
            if desired > 0 and ready == 0:
                status = "critical"
            elif ready < desired:
                status = "warning"
            dots.append(
                ResourceHealthDot(
                    id=ds_id,
                    name=name,
                    type="daemonset",
                    namespace=ns,
                    status=status,
                )
            )

        # Jobs
        for job in parsed_data.get("jobs", []):
            meta = job.get("metadata", {})
            name = meta.get("name", "unknown")
            ns = meta.get("namespace", "default")
            job_id = f"job/{ns}/{name}"
            failed = job.get("status", {}).get("failed", 0) or 0
            succeeded = job.get("status", {}).get("succeeded", 0) or 0
            status = "healthy"
            if failed > 0:
                status = "critical"
            elif succeeded == 0:
                status = "warning"
            dots.append(
                ResourceHealthDot(
                    id=job_id,
                    name=name,
                    type="job",
                    namespace=ns,
                    status=status,
                )
            )

        logger.info("Built %d resource health dots", len(dots))
        return dots

    @staticmethod
    def _build_sparkline(events: list[TimelineEvent]) -> list[dict]:
        """Bucket event timestamps into time intervals for sparkline visualization."""
        if not events:
            return []

        timestamps = [e.timestamp for e in events]
        timestamps.sort()

        # Create up to 20 buckets between first and last timestamp
        num_buckets = min(20, len(events))
        if num_buckets < 2:
            return [{"bucket": 0, "count": len(events), "start": timestamps[0], "end": timestamps[-1]}]

        # Simple character-based bucketing (timestamps are ISO strings, so lexicographic sort works)
        bucket_size = max(1, len(timestamps) // num_buckets)
        sparkline: list[dict] = []
        for i in range(0, len(timestamps), bucket_size):
            chunk = timestamps[i : i + bucket_size]
            sparkline.append(
                {
                    "bucket": len(sparkline),
                    "count": len(chunk),
                    "start": chunk[0],
                    "end": chunk[-1],
                }
            )

        return sparkline

    @staticmethod
    def _node_health(node: dict) -> str:
        """Determine node health from conditions."""
        conditions = node.get("status", {}).get("conditions", []) or []
        for cond in conditions:
            if cond.get("type") == "Ready":
                if cond.get("status") == "True":
                    # Check for pressure conditions
                    for c in conditions:
                        if c.get("type") in ("DiskPressure", "MemoryPressure", "PIDPressure"):
                            if c.get("status") == "True":
                                return "warning"
                    return "healthy"
                return "critical"
        return "unknown"

    @staticmethod
    def _pod_health(pod: dict) -> str:
        """Determine pod health from status."""
        phase = pod.get("status", {}).get("phase", "Unknown")
        if phase == "Running":
            # Check container statuses for issues
            for cs in pod.get("status", {}).get("containerStatuses", []) or []:
                if not cs.get("ready", False):
                    return "warning"
                waiting = cs.get("state", {}).get("waiting", {})
                if waiting.get("reason") in ("CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull"):
                    return "critical"
                if cs.get("restartCount", 0) > 5:
                    return "warning"
            return "healthy"
        elif phase == "Succeeded":
            return "healthy"
        elif phase == "Pending":
            return "warning"
        elif phase == "Failed":
            return "critical"
        return "unknown"
