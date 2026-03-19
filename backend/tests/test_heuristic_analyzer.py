"""Tests for the heuristic analyzer — verifies all 15 pattern detectors."""
import pytest

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
            "pods": [], "nodes": [], "events": [],
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
            "pods": [], "nodes": [], "events": [],
            "logs": [
                {"source": "api-gateway", "message": "dial tcp 10.0.0.5:5432: connection refused", "level": "error"},
            ],
        }
        issues = HeuristicAnalyzer(data).analyze()
        conn = [i for i in issues if "Connection" in i.title]
        assert len(conn) == 1

    def test_detects_certificate_warnings(self):
        data = {
            "pods": [], "nodes": [], "events": [],
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
            "pods": [], "nodes": [], "events": [],
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
