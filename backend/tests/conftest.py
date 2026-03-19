"""Shared test fixtures for the K8s Bundle Analyzer backend."""
import pytest


@pytest.fixture
def crashloop_pod():
    """A pod in CrashLoopBackOff state."""
    return {
        "metadata": {"name": "payment-api-7f8d9c4b5-x2k9l", "namespace": "payments"},
        "status": {
            "phase": "Running",
            "containerStatuses": [
                {
                    "name": "payment-api",
                    "restartCount": 42,
                    "state": {
                        "waiting": {
                            "reason": "CrashLoopBackOff",
                            "message": "back-off 5m0s restarting failed container",
                        }
                    },
                    "image": "registry.example.com/payment-api:v2.3.1",
                }
            ],
        },
    }


@pytest.fixture
def oom_killed_pod():
    """A pod with OOMKilled container."""
    return {
        "metadata": {"name": "worker-processor-5c8f7d-abc12", "namespace": "batch"},
        "status": {
            "phase": "Running",
            "containerStatuses": [
                {
                    "name": "worker",
                    "restartCount": 3,
                    "state": {"running": {}},
                    "lastState": {
                        "terminated": {
                            "reason": "OOMKilled",
                            "exitCode": 137,
                            "finishedAt": "2024-01-15T10:30:00Z",
                        }
                    },
                    "image": "registry.example.com/worker:v1.0",
                }
            ],
        },
    }


@pytest.fixture
def image_pull_pod():
    """A pod with ImagePullBackOff."""
    return {
        "metadata": {"name": "frontend-deploy-9b8c7d-xyz99", "namespace": "web"},
        "status": {
            "phase": "Pending",
            "containerStatuses": [
                {
                    "name": "frontend",
                    "restartCount": 0,
                    "state": {
                        "waiting": {
                            "reason": "ImagePullBackOff",
                            "message": "Back-off pulling image \"registry.example.com/frontend:v99.0.0\"",
                        }
                    },
                    "image": "registry.example.com/frontend:v99.0.0",
                }
            ],
        },
    }


@pytest.fixture
def pending_pod():
    """A pod stuck in Pending state."""
    return {
        "metadata": {"name": "redis-cluster-0", "namespace": "cache"},
        "status": {
            "phase": "Pending",
            "conditions": [
                {
                    "type": "PodScheduled",
                    "status": "False",
                    "reason": "Unschedulable",
                    "message": "0/3 nodes are available: 3 Insufficient memory.",
                }
            ],
        },
    }


@pytest.fixture
def evicted_pod():
    """An evicted pod."""
    return {
        "metadata": {"name": "log-collector-x7h2p", "namespace": "monitoring"},
        "status": {
            "phase": "Failed",
            "reason": "Evicted",
            "message": "The node was low on resource: ephemeral-storage.",
        },
    }


@pytest.fixture
def unhealthy_node():
    """A node that is NotReady."""
    return {
        "metadata": {"name": "worker-3"},
        "status": {
            "conditions": [
                {
                    "type": "Ready",
                    "status": "False",
                    "reason": "KubeletNotReady",
                    "message": "container runtime network not ready",
                    "lastTransitionTime": "2024-01-15T08:00:00Z",
                },
            ]
        },
    }


@pytest.fixture
def pressure_node():
    """A node under memory pressure."""
    return {
        "metadata": {"name": "worker-2"},
        "status": {
            "conditions": [
                {"type": "Ready", "status": "True"},
                {
                    "type": "MemoryPressure",
                    "status": "True",
                    "reason": "KubeletHasInsufficientMemory",
                    "message": "kubelet has insufficient memory available",
                },
            ]
        },
    }


@pytest.fixture
def healthy_cluster_data():
    """Minimal parsed data for a healthy cluster."""
    return {
        "pods": [
            {
                "metadata": {"name": "nginx-abc12", "namespace": "default"},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [
                        {"name": "nginx", "restartCount": 0, "state": {"running": {}}, "image": "nginx:1.25"}
                    ],
                },
            }
        ],
        "nodes": [
            {
                "metadata": {"name": "node-1"},
                "status": {
                    "conditions": [{"type": "Ready", "status": "True"}]
                },
            }
        ],
        "events": [],
        "logs": [],
        "namespaces": [{"metadata": {"name": "default"}}],
        "deployments": [],
        "services": [],
        "pvs": [],
        "cluster_version": {"gitVersion": "v1.28.4"},
        "host_info": {},
    }


@pytest.fixture
def warning_event():
    """A Kubernetes warning event."""
    return {
        "type": "Warning",
        "reason": "FailedScheduling",
        "message": "0/3 nodes are available: 3 Insufficient cpu.",
        "involvedObject": {
            "kind": "Pod",
            "name": "api-server-deploy-abc",
            "namespace": "production",
        },
        "count": 5,
        "lastTimestamp": "2024-01-15T10:00:00Z",
    }
