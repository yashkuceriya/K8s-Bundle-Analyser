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
        self._check_probe_failures()
        self._check_job_failures()
        self._check_cronjob_issues()
        self._check_statefulset_stuck_rollout()
        self._check_hpa_unable_to_scale()
        self._check_ingress_misconfiguration()
        self._check_service_selector_mismatch()
        self._check_missing_resource_limits()
        self._check_init_container_failures()
        self._check_rbac_failures()
        self._check_bundled_analysis()
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
                    self.issues.append(
                        Issue(
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
                                "Container state: CrashLoopBackOff",
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
                        )
                    )

    def _check_image_pull_errors(self) -> None:
        for pod in self.data.get("pods", []):
            ns, name = self._get_pod_id(pod)
            for cs in self._get_container_statuses(pod):
                waiting = cs.get("state", {}).get("waiting", {})
                reason = waiting.get("reason", "")
                if reason in ("ImagePullBackOff", "ErrImagePull"):
                    image = cs.get("image", "unknown")
                    container_name = cs.get("name", "unknown")
                    self.issues.append(
                        Issue(
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
                        )
                    )

    def _check_oom_killed(self) -> None:
        for pod in self.data.get("pods", []):
            ns, name = self._get_pod_id(pod)
            for cs in self._get_container_statuses(pod):
                last_state = cs.get("lastState", {})
                terminated = last_state.get("terminated", {})
                reason = terminated.get("reason", "")
                if reason == "OOMKilled":
                    container_name = cs.get("name", "unknown")
                    self.issues.append(
                        Issue(
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
                                "Termination reason: OOMKilled",
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
                        )
                    )

    def _check_pending_pods(self) -> None:
        for pod in self.data.get("pods", []):
            ns, name = self._get_pod_id(pod)
            phase = pod.get("status", {}).get("phase", "")
            if phase == "Pending":
                conditions = pod.get("status", {}).get("conditions", []) or []
                condition_msgs = [
                    f"{c.get('type')}: {c.get('message', 'N/A')}" for c in conditions if c.get("status") != "True"
                ]
                self.issues.append(
                    Issue(
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
                    )
                )

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
                    self.issues.append(
                        Issue(
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
                        )
                    )

    def _check_failed_events(self) -> None:
        # Note: "Unhealthy" is handled by _check_probe_failures with better severity logic
        fail_patterns = [
            "Failed",
            "Error",
            "BackOff",
            "FailedScheduling",
            "FailedMount",
            "FailedAttachVolume",
            "FailedCreate",
        ]

        # Aggregate events by resource to avoid duplicate issues per pod
        resource_events: dict[str, dict] = {}
        for event in self.data.get("events", []):
            if event.get("type") != "Warning":
                continue
            reason = event.get("reason", "")
            if not any(pat.lower() in reason.lower() for pat in fail_patterns):
                continue

            involved = event.get("involvedObject", {})
            resource_kind = involved.get("kind", "")
            resource_name = involved.get("name", "")
            ns = involved.get("namespace", "")
            key = f"{ns}/{resource_kind}/{resource_name}"

            if key not in resource_events:
                resource_events[key] = {
                    "kind": resource_kind,
                    "name": resource_name,
                    "ns": ns,
                    "reasons": [],
                    "total_count": 0,
                    "messages": [],
                }
            info = resource_events[key]
            if reason not in info["reasons"]:
                info["reasons"].append(reason)
            info["total_count"] += event.get("count", 1)
            msg = event.get("message", "")
            if msg and len(info["messages"]) < 3:
                info["messages"].append(msg[:200])

        for info in resource_events.values():
            resource_kind = info["kind"]
            resource_name = info["name"]
            ns = info["ns"]
            reasons = ", ".join(info["reasons"])

            self.issues.append(
                Issue(
                    severity=Severity.warning,
                    title=f"Warning events on {resource_kind}/{resource_name}: {reasons}",
                    category="pod-health",
                    resource=f"{resource_kind}/{resource_name}" if resource_kind else None,
                    namespace=ns or None,
                    description=f"Kubernetes warning events ({reasons}) occurred {info['total_count']} time(s) on {resource_kind}/{resource_name}.",
                    evidence=[f"{r}" for r in info["messages"]],
                    remediation=(
                        f"Investigate {resource_kind}/{resource_name} in namespace '{ns}'. "
                        f"Check the resource status and logs for more details."
                    ),
                    ai_confidence=0.85,
                )
            )

    def _check_node_not_ready(self) -> None:
        for node in self.data.get("nodes", []):
            metadata = node.get("metadata", {})
            node_name = metadata.get("name", "unknown")
            conditions = node.get("status", {}).get("conditions", []) or []
            for cond in conditions:
                if cond.get("type") == "Ready" and cond.get("status") != "True":
                    self.issues.append(
                        Issue(
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
                        )
                    )

    def _check_pvc_issues(self) -> None:
        pvs = self.data.get("pvs") or []
        if isinstance(pvs, dict):
            pvs = pvs.get("items", []) if "items" in pvs else [pvs]
        for pv in pvs:
            phase = pv.get("status", {}).get("phase", "")
            pv_name = pv.get("metadata", {}).get("name", "unknown")
            if phase in ("Pending", "Lost"):
                self.issues.append(
                    Issue(
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
                    )
                )

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
            self.issues.append(
                Issue(
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
                )
            )

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
            self.issues.append(
                Issue(
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
                )
            )

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
            self.issues.append(
                Issue(
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
                )
            )

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
            self.issues.append(
                Issue(
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
                )
            )

    def _check_evicted_pods(self) -> None:
        for pod in self.data.get("pods", []):
            ns, name = self._get_pod_id(pod)
            phase = pod.get("status", {}).get("phase", "")
            reason = pod.get("status", {}).get("reason", "")
            if phase == "Failed" and reason == "Evicted":
                message = pod.get("status", {}).get("message", "")
                self.issues.append(
                    Issue(
                        severity=Severity.warning,
                        title=f"Evicted pod: {name}",
                        category="resource-usage",
                        resource=f"pod/{name}",
                        namespace=ns,
                        description=f"Pod '{name}' was evicted. {message}",
                        evidence=[
                            "Phase: Failed, Reason: Evicted",
                            f"Message: {message}" if message else "No message provided",
                        ],
                        remediation=(
                            "Eviction usually occurs due to node resource pressure (disk, memory). "
                            "Check node conditions and resource usage. "
                            "Consider setting appropriate resource requests and priority classes."
                        ),
                        ai_confidence=0.90,
                    )
                )

    def _check_node_pressure(self) -> None:
        pressure_types = ["DiskPressure", "MemoryPressure", "PIDPressure"]
        for node in self.data.get("nodes", []):
            node_name = node.get("metadata", {}).get("name", "unknown")
            conditions = node.get("status", {}).get("conditions", []) or []
            for cond in conditions:
                if cond.get("type") in pressure_types and cond.get("status") == "True":
                    self.issues.append(
                        Issue(
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
                        )
                    )

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
            self.issues.append(
                Issue(
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
                )
            )

    def _check_probe_failures(self) -> None:
        """Detect liveness/readiness probe failures from events and logs."""
        # Group Unhealthy events by pod to avoid one issue per event
        pod_probes: dict[str, dict] = {}  # key: "ns/pod" -> aggregated info
        for event in self.data.get("events", []):
            if event.get("type") != "Warning":
                continue
            if event.get("reason") != "Unhealthy":
                continue
            message = event.get("message", "")
            involved = event.get("involvedObject", {})
            pod_name = involved.get("name", "unknown")
            ns = involved.get("namespace", "")
            count = event.get("count", 1)
            key = f"{ns}/{pod_name}"

            if key not in pod_probes:
                pod_probes[key] = {
                    "pod_name": pod_name,
                    "ns": ns,
                    "total_count": 0,
                    "has_liveness": False,
                    "messages": [],
                }
            info = pod_probes[key]
            info["total_count"] += count
            if "liveness" in message.lower():
                info["has_liveness"] = True
            if len(info["messages"]) < 3:
                info["messages"].append(message[:200])

        for key, info in pod_probes.items():
            pod_name = info["pod_name"]
            ns = info["ns"]
            # Liveness failures are critical (cause restarts); readiness is warning
            severity = Severity.critical if info["has_liveness"] else Severity.warning

            self.issues.append(
                Issue(
                    severity=severity,
                    title=f"Probe failure: {pod_name}",
                    category="pod-health",
                    resource=f"pod/{pod_name}",
                    namespace=ns or None,
                    description=(
                        f"Pod '{pod_name}' has failing health probes. Total occurrences: {info['total_count']}."
                    ),
                    evidence=[f"Unhealthy: {m}" for m in info["messages"]],
                    remediation=(
                        "Review the probe configuration. Common causes: "
                        "incorrect port, path, or timeout settings. "
                        "Check if the application starts slowly and needs a higher initialDelaySeconds. "
                        f"kubectl describe pod {pod_name}" + (f" -n {ns}" if ns else "")
                    ),
                    ai_confidence=0.90,
                )
            )

    def _check_job_failures(self) -> None:
        """Detect failed Kubernetes Jobs."""
        for job in self.data.get("jobs", []):
            meta = job.get("metadata", {})
            name = meta.get("name", "unknown")
            ns = meta.get("namespace", "unknown")
            status = job.get("status", {})
            failed = status.get("failed", 0) or 0
            conditions = status.get("conditions", []) or []

            is_failed = failed > 0
            if not is_failed:
                for cond in conditions:
                    if cond.get("type") == "Failed" and cond.get("status") == "True":
                        is_failed = True
                        break

            if is_failed:
                reason = ""
                for cond in conditions:
                    if cond.get("type") == "Failed":
                        reason = cond.get("reason", "")
                        break

                self.issues.append(
                    Issue(
                        severity=Severity.warning,
                        title=f"Job failed: {name}",
                        category="pod-health",
                        resource=f"job/{name}",
                        namespace=ns,
                        description=(
                            f"Job '{name}' in namespace '{ns}' has {failed} failure(s). "
                            f"{'Reason: ' + reason if reason else 'Check job events for details.'}"
                        ),
                        evidence=[
                            f"Failed count: {failed}",
                            f"Reason: {reason}" if reason else "No failure reason available",
                        ],
                        remediation=(
                            f"Check job pod logs: kubectl logs job/{name} -n {ns}. "
                            f"Describe the job: kubectl describe job {name} -n {ns}. "
                            "Common causes: application errors, misconfigured commands, or resource limits."
                        ),
                        ai_confidence=0.90,
                    )
                )

    def _check_cronjob_issues(self) -> None:
        """Detect suspended or problematic CronJobs."""
        for cj in self.data.get("cronjobs", []):
            meta = cj.get("metadata", {})
            name = meta.get("name", "")
            ns = meta.get("namespace", "")
            spec = cj.get("spec", {})
            status = cj.get("status", {})

            # Skip empty/invalid CronJob entries (parsed from empty namespace files)
            if not name or not spec.get("schedule"):
                continue

            issues_found = []

            # Check if suspended
            if spec.get("suspend", False):
                issues_found.append("CronJob is suspended")

            # Check for missed schedules
            last_schedule = status.get("lastScheduleTime")
            if not last_schedule and not spec.get("suspend", False):
                issues_found.append("CronJob has never been scheduled")

            if issues_found:
                self.issues.append(
                    Issue(
                        severity=Severity.warning,
                        title=f"CronJob issue: {name}",
                        category="pod-health",
                        resource=f"cronjob/{name}",
                        namespace=ns,
                        description=(f"CronJob '{name}' in namespace '{ns}' has issues: " + "; ".join(issues_found)),
                        evidence=issues_found,
                        remediation=(
                            f"Review the CronJob: kubectl describe cronjob {name} -n {ns}. "
                            "If suspended, ensure it was intentional. "
                            "Check for resource quota issues preventing job creation."
                        ),
                        ai_confidence=0.85,
                    )
                )

    def _check_statefulset_stuck_rollout(self) -> None:
        """Detect StatefulSets with stuck rollouts."""
        for sts in self.data.get("statefulsets", []):
            meta = sts.get("metadata", {})
            name = meta.get("name", "unknown")
            ns = meta.get("namespace", "unknown")
            spec = sts.get("spec", {})
            status = sts.get("status", {})

            desired = spec.get("replicas", 0) or 0
            ready = status.get("readyReplicas", 0) or 0
            current = status.get("currentReplicas", 0) or 0
            updated = status.get("updatedReplicas", 0) or 0

            if desired == 0:
                continue

            if ready < desired:
                severity = Severity.critical if ready == 0 else Severity.warning
                self.issues.append(
                    Issue(
                        severity=severity,
                        title=f"StatefulSet degraded: {name} ({ready}/{desired} ready)",
                        category="pod-health",
                        resource=f"statefulset/{name}",
                        namespace=ns,
                        description=(
                            f"StatefulSet '{name}' in namespace '{ns}' has {ready}/{desired} "
                            f"ready replicas. Current: {current}, Updated: {updated}."
                        ),
                        evidence=[
                            f"Desired: {desired}",
                            f"Ready: {ready}",
                            f"Current: {current}",
                            f"Updated: {updated}",
                        ],
                        remediation=(
                            f"Check StatefulSet pods: kubectl get pods -l app={name} -n {ns}. "
                            f"Describe: kubectl describe statefulset {name} -n {ns}. "
                            "StatefulSet rollouts are sequential — a stuck pod blocks the rest."
                        ),
                        ai_confidence=0.90,
                    )
                )

    def _check_hpa_unable_to_scale(self) -> None:
        """Detect HPAs at max replicas or with scaling issues."""
        for hpa in self.data.get("hpas", []):
            meta = hpa.get("metadata", {})
            name = meta.get("name", "unknown")
            ns = meta.get("namespace", "unknown")
            spec = hpa.get("spec", {})
            status = hpa.get("status", {})

            max_replicas = spec.get("maxReplicas", 0) or 0
            current = status.get("currentReplicas", 0) or 0
            conditions = status.get("conditions", []) or []

            issues_found = []

            # Check if at max replicas
            if max_replicas > 0 and current >= max_replicas:
                issues_found.append(f"Running at max replicas ({current}/{max_replicas})")

            # Check for ScalingLimited or AbleToScale=False conditions
            for cond in conditions:
                cond_type = cond.get("type", "")
                cond_status = cond.get("status", "")
                if cond_type == "ScalingLimited" and cond_status == "True":
                    issues_found.append(f"ScalingLimited: {cond.get('message', '')[:200]}")
                elif cond_type == "AbleToScale" and cond_status == "False":
                    issues_found.append(f"Unable to scale: {cond.get('message', '')[:200]}")

            if issues_found:
                self.issues.append(
                    Issue(
                        severity=Severity.warning,
                        title=f"HPA scaling issue: {name}",
                        category="resource-usage",
                        resource=f"hpa/{name}",
                        namespace=ns,
                        description=(
                            f"HPA '{name}' in namespace '{ns}' has scaling concerns: " + "; ".join(issues_found)
                        ),
                        evidence=issues_found,
                        remediation=(
                            f"Review HPA status: kubectl describe hpa {name} -n {ns}. "
                            "Consider increasing maxReplicas or adding node capacity. "
                            "Check metrics-server is providing data."
                        ),
                        ai_confidence=0.85,
                    )
                )

    def _check_ingress_misconfiguration(self) -> None:
        """Detect ingresses pointing to non-existent backend services."""
        # Build set of existing services per namespace
        svc_by_ns: dict[str, set[str]] = {}
        for svc in self.data.get("services", []):
            svc_ns = svc.get("metadata", {}).get("namespace", "default")
            svc_name = svc.get("metadata", {}).get("name", "")
            if svc_name:
                svc_by_ns.setdefault(svc_ns, set()).add(svc_name)

        for ing in self.data.get("ingresses", []):
            meta = ing.get("metadata", {})
            name = meta.get("name", "unknown")
            ns = meta.get("namespace", "default")
            spec = ing.get("spec", {})

            ns_services = svc_by_ns.get(ns, set())
            missing_backends = []

            for rule in spec.get("rules", []) or []:
                for path_entry in (rule.get("http", {}) or {}).get("paths", []) or []:
                    backend = path_entry.get("backend", {})
                    # Handle both v1 and v1beta1 ingress formats
                    svc_name = backend.get("service", {}).get("name", backend.get("serviceName", ""))
                    if svc_name and svc_name not in ns_services:
                        host = rule.get("host", "*")
                        path = path_entry.get("path", "/")
                        missing_backends.append(f"{host}{path} -> {svc_name}")

            if missing_backends:
                self.issues.append(
                    Issue(
                        severity=Severity.warning,
                        title=f"Ingress bad backend: {name}",
                        category="networking",
                        resource=f"ingress/{name}",
                        namespace=ns,
                        description=(
                            f"Ingress '{name}' in namespace '{ns}' references services "
                            f"that don't exist: {', '.join(missing_backends)}"
                        ),
                        evidence=[f"Missing: {b}" for b in missing_backends],
                        remediation=(
                            f"Verify backend services exist in namespace '{ns}'. "
                            f"kubectl get services -n {ns}. "
                            "Create the missing service or update the ingress backend."
                        ),
                        ai_confidence=0.90,
                    )
                )

    def _check_service_selector_mismatch(self) -> None:
        """Detect services whose selectors match zero pods."""
        pods = self.data.get("pods", [])
        for svc in self.data.get("services", []):
            meta = svc.get("metadata", {})
            name = meta.get("name", "unknown")
            ns = meta.get("namespace", "default")
            svc_type = svc.get("spec", {}).get("type", "ClusterIP")

            # Skip headless and ExternalName services
            if svc_type == "ExternalName":
                continue
            selector = svc.get("spec", {}).get("selector") or {}
            if not selector:
                continue

            # Count matching pods in the same namespace
            matching = 0
            for pod in pods:
                pod_ns = pod.get("metadata", {}).get("namespace", "default")
                if pod_ns != ns:
                    continue
                pod_labels = pod.get("metadata", {}).get("labels", {}) or {}
                if all(pod_labels.get(k) == v for k, v in selector.items()):
                    matching += 1

            if matching == 0:
                selector_str = ", ".join(f"{k}={v}" for k, v in selector.items())
                self.issues.append(
                    Issue(
                        severity=Severity.warning,
                        title=f"Service has no endpoints: {name}",
                        category="networking",
                        resource=f"service/{name}",
                        namespace=ns,
                        description=(
                            f"Service '{name}' in namespace '{ns}' selector ({selector_str}) "
                            f"matches 0 pods. Traffic to this service will fail."
                        ),
                        evidence=[
                            f"Selector: {selector_str}",
                            "Matching pods: 0",
                            f"Service type: {svc_type}",
                        ],
                        remediation=(
                            f"Check that pods with labels matching {selector_str} exist in namespace '{ns}'. "
                            f"kubectl get pods -n {ns} -l {selector_str.replace(', ', ',')}. "
                            "Verify the selector matches the pod template labels in the deployment."
                        ),
                        ai_confidence=0.90,
                    )
                )

    def _check_missing_resource_limits(self) -> None:
        """Detect containers without resource requests or limits."""
        pods_missing = []
        for pod in self.data.get("pods", []):
            ns, name = self._get_pod_id(pod)
            phase = pod.get("status", {}).get("phase", "")
            # Only check running/pending pods
            if phase not in ("Running", "Pending"):
                continue
            spec_containers = pod.get("spec", {}).get("containers", []) or []
            for container in spec_containers:
                resources = container.get("resources", {})
                has_limits = bool(resources.get("limits"))
                has_requests = bool(resources.get("requests"))
                if not has_limits and not has_requests:
                    c_name = container.get("name", "unknown")
                    pods_missing.append(f"{ns}/{name}/{c_name}")
                    if len(pods_missing) >= 20:
                        break
            if len(pods_missing) >= 20:
                break

        if pods_missing:
            self.issues.append(
                Issue(
                    severity=Severity.info,
                    title=f"Missing resource limits ({len(pods_missing)} container(s))",
                    category="configuration",
                    description=(
                        f"{len(pods_missing)} container(s) have no resource requests or limits set. "
                        "This can lead to resource contention, OOM kills, and unpredictable scheduling."
                    ),
                    evidence=pods_missing[:10],
                    remediation=(
                        "Add resource requests and limits to all containers. "
                        "Example: resources: {requests: {cpu: 100m, memory: 128Mi}, limits: {cpu: 500m, memory: 512Mi}}. "
                        "Use kubectl top pods to estimate current usage."
                    ),
                    ai_confidence=0.85,
                )
            )

    def _check_init_container_failures(self) -> None:
        """Detect init containers stuck in failure states."""
        for pod in self.data.get("pods", []):
            ns, name = self._get_pod_id(pod)
            init_statuses = pod.get("status", {}).get("initContainerStatuses", []) or []
            for cs in init_statuses:
                c_name = cs.get("name", "unknown")
                waiting = cs.get("state", {}).get("waiting", {})
                terminated = cs.get("state", {}).get("terminated", {})

                reason = waiting.get("reason", "") or terminated.get("reason", "")
                if reason in ("CrashLoopBackOff", "Error", "ImagePullBackOff", "ErrImagePull"):
                    exit_code = terminated.get("exitCode", "N/A")
                    self.issues.append(
                        Issue(
                            severity=Severity.critical,
                            title=f"Init container failed: {name}/{c_name}",
                            category="pod-health",
                            resource=f"pod/{name}",
                            namespace=ns,
                            description=(
                                f"Init container '{c_name}' in pod '{name}' is in {reason} state. "
                                f"This blocks the pod from starting."
                            ),
                            evidence=[
                                f"Init container: {c_name}",
                                f"State: {reason}",
                                f"Exit code: {exit_code}",
                                f"Message: {waiting.get('message', terminated.get('message', 'N/A'))}",
                            ],
                            remediation=(
                                f"Check init container logs: kubectl logs {name} -c {c_name} -n {ns}. "
                                "Init containers must complete successfully before the main containers start. "
                                "Common causes: missing dependencies, incorrect commands, or network issues."
                            ),
                            ai_confidence=0.90,
                        )
                    )

    def _check_rbac_failures(self) -> None:
        """Detect RBAC/permission failures from events and logs."""
        rbac_pattern = re.compile(
            r"(forbidden|cannot .+ in the namespace|RBAC|unauthorized|"
            r"User .+ cannot|forbidden: User|no RBAC policy matched)",
            re.IGNORECASE,
        )
        found: list[str] = []

        # Check events for Forbidden
        for event in self.data.get("events", []):
            msg = event.get("message", "")
            reason = event.get("reason", "")
            if reason == "Forbidden" or rbac_pattern.search(msg):
                involved = event.get("involvedObject", {})
                resource = f"{involved.get('kind', '')}/{involved.get('name', '')}"
                found.append(f"Event on {resource}: {msg[:200]}")
                if len(found) >= 10:
                    break

        # Check logs
        if len(found) < 10:
            for log in self.data.get("logs", []):
                msg = log.get("message", "")
                if rbac_pattern.search(msg):
                    found.append(f"[{log.get('source', '')}] {msg[:200]}")
                    if len(found) >= 10:
                        break

        if found:
            self.issues.append(
                Issue(
                    severity=Severity.warning,
                    title=f"RBAC/permission failures ({len(found)} occurrence(s))",
                    category="security",
                    description=(
                        "RBAC authorization failures detected. Services may be unable to access "
                        "required Kubernetes resources."
                    ),
                    evidence=found[:10],
                    remediation=(
                        "Review RBAC configuration: kubectl get clusterrolebindings,rolebindings --all-namespaces. "
                        "Check service account permissions. "
                        "Ensure pods are using the correct service account with appropriate roles."
                    ),
                    ai_confidence=0.85,
                )
            )

    def _check_bundled_analysis(self) -> None:
        """Import findings from the bundle's own analysis.json (troubleshoot.sh results)."""
        analysis = self.data.get("analysis_json")
        if not analysis:
            return
        # analysis.json can be a list or a dict with items
        items = analysis if isinstance(analysis, list) else analysis.get("items", [analysis])
        existing = {i.title.lower() for i in self.issues}

        for item in items:
            if not isinstance(item, dict):
                continue
            title = item.get("title", item.get("name", ""))
            message = item.get("message", "")
            if not title or not message:
                continue
            if title.lower() in existing:
                continue

            is_fail = item.get("isFail", False)
            is_warn = item.get("isWarn", False)
            is_pass = item.get("isPass", False)
            if is_pass and not is_fail and not is_warn:
                continue

            severity = Severity.critical if is_fail else Severity.warning if is_warn else Severity.info
            uri = item.get("uri", "")

            self.issues.append(
                Issue(
                    severity=severity,
                    title=f"[Preflight] {title}",
                    category="configuration",
                    description=message,
                    evidence=["Source: troubleshoot.sh bundled analysis"],
                    remediation=f"See: {uri}" if uri else "Review the troubleshoot.sh analyzer for this check.",
                    ai_confidence=0.95,
                )
            )
