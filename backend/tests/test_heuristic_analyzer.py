"""Tests for the heuristic analyzer — verifies all 25 pattern detectors."""

from app.analyzers.heuristic import HeuristicAnalyzer


class TestCrashLoopBackOff:
    def test_detects_crashloop(self, crashloop_pod):
        data = {"pods": [crashloop_pod], "nodes": [], "events": [], "logs": []}
        issues = HeuristicAnalyzer(data).analyze()
        crashloop = [i for i in issues if "CrashLoopBackOff" in i.title]
        assert len(crashloop) == 1
        assert crashloop[0].severity.value == "critical"
        assert crashloop[0].category == "pod-health"
        assert "payment-api" in crashloop[0].title
        assert crashloop[0].namespace == "payments"
        assert "42 restarts" in crashloop[0].description

    def test_no_false_positive_on_running_pod(self, healthy_cluster_data):
        issues = HeuristicAnalyzer(healthy_cluster_data).analyze()
        crashloop = [i for i in issues if "CrashLoopBackOff" in i.title]
        assert len(crashloop) == 0


class TestOOMKilled:
    def test_detects_oom(self, oom_killed_pod):
        data = {"pods": [oom_killed_pod], "nodes": [], "events": [], "logs": []}
        issues = HeuristicAnalyzer(data).analyze()
        oom = [i for i in issues if "OOMKilled" in i.title]
        assert len(oom) == 1
        assert oom[0].severity.value == "critical"
        assert oom[0].category == "resource-usage"
        assert "worker" in oom[0].title


class TestImagePullErrors:
    def test_detects_image_pull(self, image_pull_pod):
        data = {"pods": [image_pull_pod], "nodes": [], "events": [], "logs": []}
        issues = HeuristicAnalyzer(data).analyze()
        pull = [i for i in issues if "Image pull" in i.title]
        assert len(pull) == 1
        assert pull[0].severity.value == "critical"
        assert "v99.0.0" in pull[0].description


class TestPendingPods:
    def test_detects_pending(self, pending_pod):
        data = {"pods": [pending_pod], "nodes": [], "events": [], "logs": []}
        issues = HeuristicAnalyzer(data).analyze()
        pending = [i for i in issues if "pending" in i.title.lower()]
        assert len(pending) == 1
        assert pending[0].severity.value == "warning"
        assert "Insufficient memory" in pending[0].evidence[0]


class TestHighRestartCount:
    def test_detects_high_restarts(self):
        pod = {
            "metadata": {"name": "flaky-app-xyz", "namespace": "staging"},
            "status": {
                "phase": "Running",
                "containerStatuses": [
                    {
                        "name": "app",
                        "restartCount": 15,
                        "state": {"running": {}},
                    }
                ],
            },
        }
        data = {"pods": [pod], "nodes": [], "events": [], "logs": []}
        issues = HeuristicAnalyzer(data).analyze()
        restarts = [i for i in issues if "restart" in i.title.lower()]
        assert len(restarts) == 1
        assert "(15)" in restarts[0].title

    def test_skips_if_already_crashloop(self, crashloop_pod):
        """High restarts should not duplicate CrashLoopBackOff detection."""
        data = {"pods": [crashloop_pod], "nodes": [], "events": [], "logs": []}
        issues = HeuristicAnalyzer(data).analyze()
        restart_issues = [i for i in issues if "High restart" in i.title]
        assert len(restart_issues) == 0


class TestNodeNotReady:
    def test_detects_not_ready(self, unhealthy_node):
        data = {"pods": [], "nodes": [unhealthy_node], "events": [], "logs": []}
        issues = HeuristicAnalyzer(data).analyze()
        not_ready = [i for i in issues if "not ready" in i.title.lower()]
        assert len(not_ready) == 1
        assert not_ready[0].severity.value == "critical"
        assert "worker-3" in not_ready[0].title


class TestNodePressure:
    def test_detects_memory_pressure(self, pressure_node):
        data = {"pods": [], "nodes": [pressure_node], "events": [], "logs": []}
        issues = HeuristicAnalyzer(data).analyze()
        pressure = [i for i in issues if "Pressure" in i.title]
        assert len(pressure) == 1
        assert pressure[0].severity.value == "critical"
        assert "MemoryPressure" in pressure[0].title


class TestEvictedPods:
    def test_detects_eviction(self, evicted_pod):
        data = {"pods": [evicted_pod], "nodes": [], "events": [], "logs": []}
        issues = HeuristicAnalyzer(data).analyze()
        evicted = [i for i in issues if "Evicted" in i.title]
        assert len(evicted) == 1
        assert evicted[0].severity.value == "warning"


class TestWarningEvents:
    def test_detects_failed_scheduling(self, warning_event):
        data = {"pods": [], "nodes": [], "events": [warning_event], "logs": []}
        issues = HeuristicAnalyzer(data).analyze()
        events = [i for i in issues if "FailedScheduling" in i.title]
        assert len(events) == 1
        assert events[0].severity.value == "warning"

    def test_ignores_normal_events(self):
        event = {"type": "Normal", "reason": "Pulled", "message": "Successfully pulled image"}
        data = {"pods": [], "nodes": [], "events": [event], "logs": []}
        issues = HeuristicAnalyzer(data).analyze()
        assert len(issues) == 0


class TestLogBasedDetectors:
    def test_detects_dns_failures(self):
        data = {
            "pods": [],
            "nodes": [],
            "events": [],
            "logs": [
                {"source": "coredns", "message": "dns resolution failed for api.internal", "level": "error"},
            ],
        }
        issues = HeuristicAnalyzer(data).analyze()
        dns = [i for i in issues if "DNS" in i.title]
        assert len(dns) == 1
        assert dns[0].category == "networking"

    def test_detects_connection_errors(self):
        data = {
            "pods": [],
            "nodes": [],
            "events": [],
            "logs": [
                {"source": "api-gateway", "message": "dial tcp 10.0.0.5:5432: connection refused", "level": "error"},
            ],
        }
        issues = HeuristicAnalyzer(data).analyze()
        conn = [i for i in issues if "Connection" in i.title]
        assert len(conn) == 1

    def test_detects_certificate_warnings(self):
        data = {
            "pods": [],
            "nodes": [],
            "events": [],
            "logs": [
                {"source": "cert-manager", "message": "certificate cert-prod will expire in 2 days", "level": "warn"},
            ],
        }
        issues = HeuristicAnalyzer(data).analyze()
        cert = [i for i in issues if "ertificat" in i.title]
        assert len(cert) == 1
        assert cert[0].category == "security"

    def test_no_false_positives_on_clean_logs(self):
        data = {
            "pods": [],
            "nodes": [],
            "events": [],
            "logs": [
                {"source": "app", "message": "Server started on port 8080", "level": "info"},
                {"source": "app", "message": "Request handled successfully", "level": "info"},
            ],
        }
        issues = HeuristicAnalyzer(data).analyze()
        assert len(issues) == 0


class TestMultipleIssues:
    """Verify the analyzer finds all issues in a complex cluster state."""

    def test_finds_multiple_issues(self, crashloop_pod, oom_killed_pod, unhealthy_node, warning_event):
        data = {
            "pods": [crashloop_pod, oom_killed_pod],
            "nodes": [unhealthy_node],
            "events": [warning_event],
            "logs": [],
        }
        issues = HeuristicAnalyzer(data).analyze()
        severities = {i.severity.value for i in issues}
        assert "critical" in severities
        assert len(issues) >= 3  # CrashLoop, OOM, Node NotReady, FailedScheduling

    def test_healthy_cluster_has_no_issues(self, healthy_cluster_data):
        issues = HeuristicAnalyzer(healthy_cluster_data).analyze()
        assert len(issues) == 0


class TestProbeFailures:
    def test_detects_liveness_probe_failure(self, probe_failure_event):
        data = {
            "pods": [],
            "nodes": [],
            "events": [probe_failure_event],
            "logs": [],
            "jobs": [],
            "cronjobs": [],
            "statefulsets": [],
            "hpas": [],
            "ingresses": [],
            "services": [],
        }
        issues = HeuristicAnalyzer(data).analyze()
        probes = [i for i in issues if "Probe failure" in i.title]
        assert len(probes) == 1
        assert probes[0].severity.value == "critical"  # liveness probe
        assert probes[0].category == "pod-health"
        assert "web-app" in probes[0].title
        # Verify no duplicate from _check_failed_events
        unhealthy_events = [i for i in issues if "Unhealthy" in i.title and "Probe" not in i.title]
        assert len(unhealthy_events) == 0

    def test_readiness_probe_is_warning(self):
        event = {
            "type": "Warning",
            "reason": "Unhealthy",
            "message": "Readiness probe failed: connection refused",
            "involvedObject": {"kind": "Pod", "name": "api-pod", "namespace": "ns"},
            "count": 5,
        }
        data = {
            "pods": [],
            "nodes": [],
            "events": [event],
            "logs": [],
            "jobs": [],
            "cronjobs": [],
            "statefulsets": [],
            "hpas": [],
            "ingresses": [],
            "services": [],
        }
        issues = HeuristicAnalyzer(data).analyze()
        probes = [i for i in issues if "Probe failure" in i.title]
        assert len(probes) == 1
        assert probes[0].severity.value == "warning"

    def test_deduplicates_multiple_events_per_pod(self):
        """Multiple Unhealthy events for the same pod should produce one issue."""
        events = [
            {
                "type": "Warning",
                "reason": "Unhealthy",
                "message": "Liveness probe failed: timeout",
                "count": 3,
                "involvedObject": {"kind": "Pod", "name": "api-pod", "namespace": "ns"},
            },
            {
                "type": "Warning",
                "reason": "Unhealthy",
                "message": "Readiness probe failed: 503",
                "count": 7,
                "involvedObject": {"kind": "Pod", "name": "api-pod", "namespace": "ns"},
            },
        ]
        data = {
            "pods": [],
            "nodes": [],
            "events": events,
            "logs": [],
            "jobs": [],
            "cronjobs": [],
            "statefulsets": [],
            "hpas": [],
            "ingresses": [],
            "services": [],
        }
        issues = HeuristicAnalyzer(data).analyze()
        probes = [i for i in issues if "Probe failure" in i.title]
        assert len(probes) == 1
        # Should be critical because one of the events is liveness
        assert probes[0].severity.value == "critical"


class TestJobFailures:
    def test_detects_failed_job(self, failed_job):
        data = {
            "pods": [],
            "nodes": [],
            "events": [],
            "logs": [],
            "jobs": [failed_job],
            "cronjobs": [],
            "statefulsets": [],
            "hpas": [],
            "ingresses": [],
            "services": [],
        }
        issues = HeuristicAnalyzer(data).analyze()
        jobs = [i for i in issues if "Job failed" in i.title]
        assert len(jobs) == 1
        assert jobs[0].severity.value == "warning"
        assert "data-migration" in jobs[0].title

    def test_successful_job_no_issue(self):
        job = {
            "metadata": {"name": "ok-job", "namespace": "batch"},
            "status": {"succeeded": 1, "failed": 0},
        }
        data = {
            "pods": [],
            "nodes": [],
            "events": [],
            "logs": [],
            "jobs": [job],
            "cronjobs": [],
            "statefulsets": [],
            "hpas": [],
            "ingresses": [],
            "services": [],
        }
        issues = HeuristicAnalyzer(data).analyze()
        jobs = [i for i in issues if "Job failed" in i.title]
        assert len(jobs) == 0


class TestCronJobIssues:
    def test_detects_suspended_cronjob(self, suspended_cronjob):
        data = {
            "pods": [],
            "nodes": [],
            "events": [],
            "logs": [],
            "jobs": [],
            "cronjobs": [suspended_cronjob],
            "statefulsets": [],
            "hpas": [],
            "ingresses": [],
            "services": [],
        }
        issues = HeuristicAnalyzer(data).analyze()
        cj = [i for i in issues if "CronJob issue" in i.title]
        assert len(cj) == 1
        assert "suspended" in cj[0].description.lower()


class TestStatefulSetStuckRollout:
    def test_detects_stuck_statefulset(self, stuck_statefulset):
        data = {
            "pods": [],
            "nodes": [],
            "events": [],
            "logs": [],
            "jobs": [],
            "cronjobs": [],
            "statefulsets": [stuck_statefulset],
            "hpas": [],
            "ingresses": [],
            "services": [],
        }
        issues = HeuristicAnalyzer(data).analyze()
        sts = [i for i in issues if "StatefulSet degraded" in i.title]
        assert len(sts) == 1
        assert "1/3" in sts[0].title
        assert sts[0].severity.value == "warning"

    def test_healthy_statefulset_no_issue(self):
        sts = {
            "metadata": {"name": "healthy-sts", "namespace": "default"},
            "spec": {"replicas": 3},
            "status": {"readyReplicas": 3, "currentReplicas": 3, "updatedReplicas": 3},
        }
        data = {
            "pods": [],
            "nodes": [],
            "events": [],
            "logs": [],
            "jobs": [],
            "cronjobs": [],
            "statefulsets": [sts],
            "hpas": [],
            "ingresses": [],
            "services": [],
        }
        issues = HeuristicAnalyzer(data).analyze()
        sts_issues = [i for i in issues if "StatefulSet" in i.title]
        assert len(sts_issues) == 0

    def test_zero_ready_is_critical(self):
        sts = {
            "metadata": {"name": "down-sts", "namespace": "db"},
            "spec": {"replicas": 3},
            "status": {"readyReplicas": 0, "currentReplicas": 0, "updatedReplicas": 0},
        }
        data = {
            "pods": [],
            "nodes": [],
            "events": [],
            "logs": [],
            "jobs": [],
            "cronjobs": [],
            "statefulsets": [sts],
            "hpas": [],
            "ingresses": [],
            "services": [],
        }
        issues = HeuristicAnalyzer(data).analyze()
        sts_issues = [i for i in issues if "StatefulSet degraded" in i.title]
        assert len(sts_issues) == 1
        assert sts_issues[0].severity.value == "critical"


class TestHPAScalingIssues:
    def test_detects_maxed_hpa(self, maxed_hpa):
        data = {
            "pods": [],
            "nodes": [],
            "events": [],
            "logs": [],
            "jobs": [],
            "cronjobs": [],
            "statefulsets": [],
            "hpas": [maxed_hpa],
            "ingresses": [],
            "services": [],
        }
        issues = HeuristicAnalyzer(data).analyze()
        hpa = [i for i in issues if "HPA scaling" in i.title]
        assert len(hpa) == 1
        assert hpa[0].severity.value == "warning"
        assert "10/10" in hpa[0].evidence[0]


class TestIngressMisconfiguration:
    def test_detects_bad_backend(self, ingress_bad_backend):
        data = {
            "pods": [],
            "nodes": [],
            "events": [],
            "logs": [],
            "jobs": [],
            "cronjobs": [],
            "statefulsets": [],
            "hpas": [],
            "ingresses": [ingress_bad_backend],
            "services": [],
        }
        issues = HeuristicAnalyzer(data).analyze()
        ing = [i for i in issues if "Ingress bad backend" in i.title]
        assert len(ing) == 1
        assert "api-service-v2" in ing[0].description

    def test_valid_ingress_no_issue(self):
        ingress = {
            "metadata": {"name": "ok-ingress", "namespace": "web"},
            "spec": {
                "rules": [
                    {
                        "host": "app.example.com",
                        "http": {
                            "paths": [
                                {
                                    "path": "/",
                                    "backend": {"service": {"name": "web-svc", "port": {"number": 80}}},
                                }
                            ]
                        },
                    }
                ]
            },
        }
        svc = {
            "metadata": {"name": "web-svc", "namespace": "web"},
            "spec": {"type": "ClusterIP"},
        }
        data = {
            "pods": [],
            "nodes": [],
            "events": [],
            "logs": [],
            "jobs": [],
            "cronjobs": [],
            "statefulsets": [],
            "hpas": [],
            "ingresses": [ingress],
            "services": [svc],
        }
        issues = HeuristicAnalyzer(data).analyze()
        ing = [i for i in issues if "Ingress bad backend" in i.title]
        assert len(ing) == 0


class TestServiceSelectorMismatch:
    def test_detects_service_with_no_matching_pods(self, service_no_endpoints):
        data = {
            "pods": [],
            "nodes": [],
            "events": [],
            "logs": [],
            "jobs": [],
            "cronjobs": [],
            "statefulsets": [],
            "hpas": [],
            "ingresses": [],
            "services": [service_no_endpoints],
        }
        issues = HeuristicAnalyzer(data).analyze()
        svc = [i for i in issues if "no endpoints" in i.title.lower()]
        assert len(svc) == 1
        assert svc[0].severity.value == "warning"
        assert "nonexistent-app" in svc[0].description

    def test_service_with_matching_pods_no_issue(self):
        svc = {
            "metadata": {"name": "good-svc", "namespace": "default"},
            "spec": {"type": "ClusterIP", "selector": {"app": "myapp"}},
        }
        pod = {
            "metadata": {"name": "myapp-abc", "namespace": "default", "labels": {"app": "myapp"}},
            "status": {"phase": "Running"},
        }
        data = {
            "pods": [pod],
            "nodes": [],
            "events": [],
            "logs": [],
            "jobs": [],
            "cronjobs": [],
            "statefulsets": [],
            "hpas": [],
            "ingresses": [],
            "services": [svc],
        }
        issues = HeuristicAnalyzer(data).analyze()
        svc_issues = [i for i in issues if "no endpoints" in i.title.lower()]
        assert len(svc_issues) == 0


class TestMissingResourceLimits:
    def test_detects_missing_limits(self, pod_no_limits):
        data = {
            "pods": [pod_no_limits],
            "nodes": [],
            "events": [],
            "logs": [],
            "jobs": [],
            "cronjobs": [],
            "statefulsets": [],
            "hpas": [],
            "ingresses": [],
            "services": [],
        }
        issues = HeuristicAnalyzer(data).analyze()
        limits = [i for i in issues if "Missing resource limits" in i.title]
        assert len(limits) == 1
        assert limits[0].severity.value == "info"
        assert limits[0].category == "configuration"

    def test_pod_with_limits_no_issue(self):
        pod = {
            "metadata": {"name": "good-pod", "namespace": "default"},
            "spec": {
                "containers": [
                    {
                        "name": "app",
                        "resources": {
                            "requests": {"cpu": "100m", "memory": "128Mi"},
                            "limits": {"cpu": "500m", "memory": "512Mi"},
                        },
                    }
                ]
            },
            "status": {"phase": "Running"},
        }
        data = {
            "pods": [pod],
            "nodes": [],
            "events": [],
            "logs": [],
            "jobs": [],
            "cronjobs": [],
            "statefulsets": [],
            "hpas": [],
            "ingresses": [],
            "services": [],
        }
        issues = HeuristicAnalyzer(data).analyze()
        limits = [i for i in issues if "Missing resource limits" in i.title]
        assert len(limits) == 0


class TestInitContainerFailures:
    def test_detects_init_container_crash(self, init_container_crash_pod):
        data = {
            "pods": [init_container_crash_pod],
            "nodes": [],
            "events": [],
            "logs": [],
            "jobs": [],
            "cronjobs": [],
            "statefulsets": [],
            "hpas": [],
            "ingresses": [],
            "services": [],
        }
        issues = HeuristicAnalyzer(data).analyze()
        init = [i for i in issues if "Init container failed" in i.title]
        assert len(init) == 1
        assert init[0].severity.value == "critical"
        assert "db-init" in init[0].title


class TestRBACFailures:
    def test_detects_rbac_forbidden(self, rbac_forbidden_event):
        data = {
            "pods": [],
            "nodes": [],
            "events": [rbac_forbidden_event],
            "logs": [],
            "jobs": [],
            "cronjobs": [],
            "statefulsets": [],
            "hpas": [],
            "ingresses": [],
            "services": [],
        }
        issues = HeuristicAnalyzer(data).analyze()
        rbac = [i for i in issues if "RBAC" in i.title]
        assert len(rbac) == 1
        assert rbac[0].severity.value == "warning"
        assert rbac[0].category == "security"

    def test_no_rbac_issues_on_clean_events(self):
        event = {"type": "Normal", "reason": "Created", "message": "Created pod"}
        data = {
            "pods": [],
            "nodes": [],
            "events": [event],
            "logs": [],
            "jobs": [],
            "cronjobs": [],
            "statefulsets": [],
            "hpas": [],
            "ingresses": [],
            "services": [],
        }
        issues = HeuristicAnalyzer(data).analyze()
        rbac = [i for i in issues if "RBAC" in i.title]
        assert len(rbac) == 0
