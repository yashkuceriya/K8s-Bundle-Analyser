from __future__ import annotations

import logging
import re
from typing import Any

from app.models import Issue, Severity

logger = logging.getLogger(__name__)


class HeuristicAnalyzer:
    """Detects common Kubernetes issues through pattern matching on parsed bundle data."""

    def __init__(self, parsed_data: dict[str, Any]):
        self.data = parsed_data
        self.issues: list[Issue] = []

    def analyze(self) -> list[Issue]:
        """Run all heuristic checks and return discovered issues."""
        logger.info("Running heuristic analysis...")
        self._check_crashloopbackoff()
        self._check_image_pull_errors()
        self._check_oom_killed()
        self._check_pending_pods()
        self._check_high_restart_counts()
        self._check_failed_events()
        self._check_node_not_ready()
        self._check_pvc_issues()
        self._check_certificate_expiration()
        self._check_resource_quota_exceeded()
        self._check_dns_failures()
        self._check_connection_errors()
        self._check_evicted_pods()
        self._check_node_pressure()
        self._check_deprecated_apis()
        logger.info("Heuristic analysis found %d issues", len(self.issues))
        return self.issues

    def _get_pod_id(self, pod: dict) -> tuple[str, str]:
        """Return (namespace, name) for a pod."""
        metadata = pod.get("metadata", {})
        name = metadata.get("name", "unknown")
        namespace = metadata.get("namespace", "unknown")
        return namespace, name

    def _get_container_statuses(self, pod: dict) -> list[dict]:
        """Get all container statuses from a pod (init + regular)."""
        status = pod.get("status", {})
        statuses = []
        for key in ("containerStatuses", "initContainerStatuses"):
            cs = status.get(key) or []
            statuses.extend(cs)
        return statuses

    # ---- Pod health checks ----

    def _check_crashloopbackoff(self) -> None:
        for pod in self.data.get("pods", []):
            ns, name = self._get_pod_id(pod)
            for cs in self._get_container_statuses(pod):
                waiting = cs.get("state", {}).get("waiting", {})
                reason = waiting.get("reason", "")
                if reason == "CrashLoopBackOff":
                    restart_count = cs.get("restartCount", 0)
                    container_name = cs.get("name", "unknown")
                    self.issues.append(Issue(
                        severity=Severity.critical,
                        title=f"CrashLoopBackOff: {name}/{container_name}",
                        category="pod-health",
                        resource=f"pod/{name}",
                        namespace=ns,
                        description=(
                            f"Container '{container_name}' in pod '{name}' is in CrashLoopBackOff "
                            f"with {restart_count} restarts. The container is repeatedly crashing."
                        ),
                        evidence=[
                            f"Container state: CrashLoopBackOff",
                            f"Restart count: {restart_count}",
                            f"Message: {waiting.get('message', 'N/A')}",
                        ],
                        remediation=(
                            "Check container logs for crash reason: "
                            f"kubectl logs {name} -c {container_name} -n {ns} --previous. "
                            "Common causes: application errors, missing config/secrets, "
                            "insufficient resources, or failed health checks."
                        ),
                        ai_confidence=0.95,
                    ))

    def _check_image_pull_errors(self) -> None:
        for pod in self.data.get("pods", []):
            ns, name = self._get_pod_id(pod)
            for cs in self._get_container_statuses(pod):
                waiting = cs.get("state", {}).get("waiting", {})
                reason = waiting.get("reason", "")
                if reason in ("ImagePullBackOff", "ErrImagePull"):
                    image = cs.get("image", "unknown")
                    container_name = cs.get("name", "unknown")
                    self.issues.append(Issue(
                        severity=Severity.critical,
                        title=f"Image pull failure: {name}/{container_name}",
                        category="pod-health",
                        resource=f"pod/{name}",
                        namespace=ns,
                        description=(
                            f"Container '{container_name}' in pod '{name}' cannot pull image '{image}'. "
                            f"Reason: {reason}."
                        ),
                        evidence=[
                            f"Image: {image}",
                            f"Reason: {reason}",
                            f"Message: {waiting.get('message', 'N/A')}",
                        ],
                        remediation=(
                            "Verify the image name and tag are correct. Check that image pull secrets "
                            "are configured if using a private registry. Ensure network connectivity "
                            "to the container registry. "
                            f"kubectl describe pod {name} -n {ns} for more details."
                        ),
                        ai_confidence=0.95,
                    ))

    def _check_oom_killed(self) -> None:
        for pod in self.data.get("pods", []):
            ns, name = self._get_pod_id(pod)
            for cs in self._get_container_statuses(pod):
                last_state = cs.get("lastState", {})
                terminated = last_state.get("terminated", {})
                reason = terminated.get("reason", "")
                if reason == "OOMKilled":
                    container_name = cs.get("name", "unknown")
                    self.issues.append(Issue(
                        severity=Severity.critical,
                        title=f"OOMKilled: {name}/{container_name}",
                        category="resource-usage",
                        resource=f"pod/{name}",
                        namespace=ns,
                        description=(
                            f"Container '{container_name}' in pod '{name}' was OOMKilled. "
                            "The container exceeded its memory limit and was terminated by the kernel."
                        ),
                        evidence=[
                            f"Termination reason: OOMKilled",
                            f"Exit code: {terminated.get('exitCode', 'N/A')}",
                            f"Finished at: {terminated.get('finishedAt', 'N/A')}",
                        ],
                        remediation=(
                            "Increase the container's memory limit in the pod spec. "
                            "Investigate the application's memory usage for leaks. "
                            "Consider setting appropriate memory requests and limits. "
                            f"Current container: {container_name} in pod {name} namespace {ns}."
                        ),
                        ai_confidence=0.95,
                    ))

    def _check_pending_pods(self) -> None:
        for pod in self.data.get("pods", []):
            ns, name = self._get_pod_id(pod)
            phase = pod.get("status", {}).get("phase", "")
            if phase == "Pending":
                conditions = pod.get("status", {}).get("conditions", []) or []
                condition_msgs = [
                    f"{c.get('type')}: {c.get('message', 'N/A')}"
                    for c in conditions
                    if c.get("status") != "True"
                ]
                self.issues.append(Issue(
                    severity=Severity.warning,
                    title=f"Pod pending: {name}",
                    category="pod-health",
                    resource=f"pod/{name}",
                    namespace=ns,
                    description=(
                        f"Pod '{name}' in namespace '{ns}' is stuck in Pending state. "
                        "This often indicates scheduling problems."
                    ),
                    evidence=condition_msgs or ["Phase: Pending"],
                    remediation=(
                        "Check if the cluster has sufficient resources (CPU, memory). "
                        "Verify node selectors, tolerations, and affinity rules. "
                        "Check for unbound PersistentVolumeClaims. "
                        f"kubectl describe pod {name} -n {ns}"
                    ),
                    ai_confidence=0.90,
                ))

    def _check_high_restart_counts(self) -> None:
        for pod in self.data.get("pods", []):
            ns, name = self._get_pod_id(pod)
            for cs in self._get_container_statuses(pod):
                restart_count = cs.get("restartCount", 0)
                if restart_count > 5:
                    container_name = cs.get("name", "unknown")
                    # Skip if we already flagged as CrashLoopBackOff
                    waiting = cs.get("state", {}).get("waiting", {})
                    if waiting.get("reason") == "CrashLoopBackOff":
                        continue
                    self.issues.append(Issue(
                        severity=Severity.warning,
                        title=f"High restart count: {name}/{container_name} ({restart_count})",
                        category="pod-health",
                        resource=f"pod/{name}",
                        namespace=ns,
                        description=(
                            f"Container '{container_name}' in pod '{name}' has restarted "
                            f"{restart_count} times, indicating instability."
                        ),
                        evidence=[
                            f"Restart count: {restart_count}",
                            f"Container: {container_name}",
                        ],
                        remediation=(
                            "Investigate the cause of frequent restarts. Check container logs "
                            "for errors, verify resource limits, and review liveness/readiness probes. "
                            f"kubectl logs {name} -c {container_name} -n {ns} --previous"
                        ),
                        ai_confidence=0.90,
                    ))

    def _check_failed_events(self) -> None:
        for event in self.data.get("events", []):
            event_type = event.get("type", "")
            reason = event.get("reason", "")
            if event_type != "Warning":
                continue
            # Check for significant failure patterns
            fail_patterns = ["Failed", "Error", "BackOff", "Unhealthy", "FailedScheduling",
                             "FailedMount", "FailedAttachVolume", "FailedCreate"]
            if not any(pat.lower() in reason.lower() for pat in fail_patterns):
                continue

            message = event.get("message", "")
            involved = event.get("involvedObject", {})
            resource_kind = involved.get("kind", "")
            resource_name = involved.get("name", "")
            ns = involved.get("namespace", "")
            count = event.get("count", 1)

            self.issues.append(Issue(
                severity=Severity.warning,
                title=f"Warning event: {reason} on {resource_kind}/{resource_name}",
                category="pod-health",
                resource=f"{resource_kind}/{resource_name}" if resource_kind else None,
                namespace=ns or None,
                description=f"Kubernetes warning event ({reason}) occurred {count} time(s): {message}",
                evidence=[
                    f"Reason: {reason}",
                    f"Message: {message}",
                    f"Count: {count}",
                    f"Last seen: {event.get('lastTimestamp', 'N/A')}",
                ],
                remediation=(
                    f"Investigate the {reason} event on {resource_kind}/{resource_name}. "
                    f"Check the resource status and logs for more details."
                ),
                ai_confidence=0.85,
            ))

    def _check_node_not_ready(self) -> None:
        for node in self.data.get("nodes", []):
            metadata = node.get("metadata", {})
            node_name = metadata.get("name", "unknown")
            conditions = node.get("status", {}).get("conditions", []) or []
            for cond in conditions:
                if cond.get("type") == "Ready" and cond.get("status") != "True":
                    self.issues.append(Issue(
                        severity=Severity.critical,
                        title=f"Node not ready: {node_name}",
                        category="pod-health",
                        resource=f"node/{node_name}",
                        description=(
                            f"Node '{node_name}' is not in Ready state. "
                            f"Reason: {cond.get('reason', 'N/A')}. "
                            f"Message: {cond.get('message', 'N/A')}."
                        ),
                        evidence=[
                            f"Condition: Ready={cond.get('status')}",
                            f"Reason: {cond.get('reason', 'N/A')}",
                            f"Message: {cond.get('message', 'N/A')}",
                            f"Last transition: {cond.get('lastTransitionTime', 'N/A')}",
                        ],
                        remediation=(
                            f"Check node '{node_name}' for kubelet issues, network problems, "
                            "or resource exhaustion. Run: kubectl describe node " + node_name
                        ),
                        ai_confidence=0.95,
                    ))

    def _check_pvc_issues(self) -> None:
        pvs = self.data.get("pvs") or []
        if isinstance(pvs, dict):
            pvs = pvs.get("items", []) if "items" in pvs else [pvs]
        for pv in pvs:
            phase = pv.get("status", {}).get("phase", "")
            pv_name = pv.get("metadata", {}).get("name", "unknown")
            if phase in ("Pending", "Lost"):
                self.issues.append(Issue(
                    severity=Severity.warning if phase == "Pending" else Severity.critical,
                    title=f"PV {phase}: {pv_name}",
                    category="storage",
                    resource=f"pv/{pv_name}",
                    description=f"PersistentVolume '{pv_name}' is in {phase} state.",
                    evidence=[f"PV phase: {phase}"],
                    remediation=(
                        f"Check PV '{pv_name}' configuration and the underlying storage backend. "
                        "Verify storage class provisioner is working correctly."
                    ),
                    ai_confidence=0.90,
                ))

    def _check_certificate_expiration(self) -> None:
        cert_pattern = re.compile(r"certific\w*.*expir", re.IGNORECASE)
        found_lines: list[str] = []
        for log in self.data.get("logs", []):
            msg = log.get("message", "")
            if cert_pattern.search(msg):
                found_lines.append(f"[{log.get('source', '')}] {msg[:200]}")
                if len(found_lines) >= 10:
                    break

        if found_lines:
            self.issues.append(Issue(
                severity=Severity.warning,
                title="Certificate expiration warnings detected",
                category="security",
                description=(
                    "Log entries mention certificate expiration. Expired or soon-to-expire "
                    "certificates can cause TLS failures and service disruptions."
                ),
                evidence=found_lines,
                remediation=(
                    "Review and renew expiring certificates. For Kubernetes-managed certificates, "
                    "check cert-manager or kubeadm certs. Run: kubeadm certs check-expiration"
                ),
                ai_confidence=0.85,
            ))

    def _check_resource_quota_exceeded(self) -> None:
        quota_pattern = re.compile(r"(exceed|forbidden).*quota", re.IGNORECASE)
        found: list[str] = []

        # Check events
        for event in self.data.get("events", []):
            msg = event.get("message", "")
            if quota_pattern.search(msg):
                found.append(f"Event: {msg[:200]}")
                if len(found) >= 5:
                    break

        # Check logs
        if len(found) < 5:
            for log in self.data.get("logs", []):
                msg = log.get("message", "")
                if quota_pattern.search(msg):
                    found.append(f"[{log.get('source', '')}] {msg[:200]}")
                    if len(found) >= 5:
                        break

        if found:
            self.issues.append(Issue(
                severity=Severity.warning,
                title="Resource quota exceeded",
                category="resource-usage",
                description="Resource quota limits have been exceeded, preventing resource creation.",
                evidence=found,
                remediation=(
                    "Review ResourceQuota objects and current resource usage. "
                    "Increase quotas or reduce resource requests. "
                    "kubectl get resourcequota --all-namespaces"
                ),
                ai_confidence=0.90,
            ))

    def _check_dns_failures(self) -> None:
        dns_pattern = re.compile(
            r"(dns|name resolution|resolve|nslookup).*(fail|error|timeout|refused)",
            re.IGNORECASE,
        )
        found: list[str] = []
        for log in self.data.get("logs", []):
            msg = log.get("message", "")
            if dns_pattern.search(msg):
                found.append(f"[{log.get('source', '')}] {msg[:200]}")
                if len(found) >= 10:
                    break

        if found:
            self.issues.append(Issue(
                severity=Severity.warning,
                title="DNS resolution failures detected",
                category="networking",
                description="Log entries indicate DNS resolution failures, which can cause service connectivity issues.",
                evidence=found,
                remediation=(
                    "Check CoreDNS pods are running: kubectl get pods -n kube-system -l k8s-app=kube-dns. "
                    "Verify DNS service: kubectl get svc -n kube-system kube-dns. "
                    "Test resolution from a pod: kubectl exec -it <pod> -- nslookup kubernetes.default"
                ),
                ai_confidence=0.85,
            ))

    def _check_connection_errors(self) -> None:
        conn_pattern = re.compile(
            r"(connection refused|connection timed? ?out|connect: connection refused|dial tcp.*refused|"
            r"i/o timeout|no route to host|network is unreachable)",
            re.IGNORECASE,
        )
        found: list[str] = []
        sources: set[str] = set()
        for log in self.data.get("logs", []):
            msg = log.get("message", "")
            if conn_pattern.search(msg):
                source = log.get("source", "")
                found.append(f"[{source}] {msg[:200]}")
                sources.add(source)
                if len(found) >= 15:
                    break

        if found:
            self.issues.append(Issue(
                severity=Severity.warning,
                title=f"Connection errors in {len(sources)} source(s)",
                category="networking",
                description=(
                    "Connection refused or timeout errors detected in logs. "
                    "This may indicate services are down, misconfigured, or network policies are blocking traffic."
                ),
                evidence=found[:10],
                remediation=(
                    "Verify target services are running and healthy. "
                    "Check network policies and firewall rules. "
                    "Ensure service endpoints are correct: kubectl get endpoints <service-name>"
                ),
                ai_confidence=0.85,
            ))

    def _check_evicted_pods(self) -> None:
        for pod in self.data.get("pods", []):
            ns, name = self._get_pod_id(pod)
            phase = pod.get("status", {}).get("phase", "")
            reason = pod.get("status", {}).get("reason", "")
            if phase == "Failed" and reason == "Evicted":
                message = pod.get("status", {}).get("message", "")
                self.issues.append(Issue(
                    severity=Severity.warning,
                    title=f"Evicted pod: {name}",
                    category="resource-usage",
                    resource=f"pod/{name}",
                    namespace=ns,
                    description=f"Pod '{name}' was evicted. {message}",
                    evidence=[
                        f"Phase: Failed, Reason: Evicted",
                        f"Message: {message}" if message else "No message provided",
                    ],
                    remediation=(
                        "Eviction usually occurs due to node resource pressure (disk, memory). "
                        "Check node conditions and resource usage. "
                        "Consider setting appropriate resource requests and priority classes."
                    ),
                    ai_confidence=0.90,
                ))

    def _check_node_pressure(self) -> None:
        pressure_types = ["DiskPressure", "MemoryPressure", "PIDPressure"]
        for node in self.data.get("nodes", []):
            node_name = node.get("metadata", {}).get("name", "unknown")
            conditions = node.get("status", {}).get("conditions", []) or []
            for cond in conditions:
                if cond.get("type") in pressure_types and cond.get("status") == "True":
                    self.issues.append(Issue(
                        severity=Severity.critical,
                        title=f"{cond['type']} on node {node_name}",
                        category="resource-usage",
                        resource=f"node/{node_name}",
                        description=(
                            f"Node '{node_name}' has {cond['type']} condition active. "
                            f"Message: {cond.get('message', 'N/A')}"
                        ),
                        evidence=[
                            f"Condition: {cond['type']}=True",
                            f"Reason: {cond.get('reason', 'N/A')}",
                            f"Message: {cond.get('message', 'N/A')}",
                        ],
                        remediation=(
                            f"Node '{node_name}' is under resource pressure. "
                            "Free up resources, add capacity, or evict low-priority workloads. "
                            f"kubectl describe node {node_name}"
                        ),
                        ai_confidence=0.95,
                    ))

    def _check_deprecated_apis(self) -> None:
        deprecated_patterns = [
            (re.compile(r"extensions/v1beta1", re.IGNORECASE), "extensions/v1beta1"),
            (re.compile(r"apps/v1beta[12]", re.IGNORECASE), "apps/v1beta1/v1beta2"),
            (re.compile(r"policy/v1beta1", re.IGNORECASE), "policy/v1beta1"),
        ]

        found: list[str] = []

        # Check events for deprecation warnings
        for event in self.data.get("events", []):
            msg = event.get("message", "")
            for pattern, label in deprecated_patterns:
                if pattern.search(msg):
                    found.append(f"Event: {msg[:200]} (uses {label})")
                    break

        # Check resource apiVersions
        for resource_type in ("pods", "deployments", "services"):
            for resource in self.data.get(resource_type, []):
                api_version = resource.get("apiVersion", "")
                for pattern, label in deprecated_patterns:
                    if pattern.search(api_version):
                        name = resource.get("metadata", {}).get("name", "unknown")
                        found.append(f"{resource_type}/{name} uses deprecated {label}")
                        break

        if found:
            self.issues.append(Issue(
                severity=Severity.info,
                title="Deprecated API versions in use",
                category="configuration",
                description=(
                    "Some resources use deprecated Kubernetes API versions. "
                    "These may stop working after cluster upgrades."
                ),
                evidence=found[:10],
                remediation=(
                    "Update manifests to use current API versions. "
                    "Use 'kubectl convert' or update apiVersion fields. "
                    "See https://kubernetes.io/docs/reference/using-api/deprecation-guide/"
                ),
                ai_confidence=0.90,
            ))
