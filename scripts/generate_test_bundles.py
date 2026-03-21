#!/usr/bin/env python3
"""
Generate realistic synthetic Kubernetes support bundles for testing.

Creates 8 bundles with varying severity levels, each as a .tar.gz file
containing realistic K8s API objects, pod logs, events, and analysis results.
"""

import json
import os
import shutil
import tarfile
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

OUTPUT_DIR = "/Users/yash/Downloads/Replicated/test-bundles"
TMP_BASE = tempfile.mkdtemp(prefix="test-bundles-")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime(2026, 3, 17, 10, 30, 0, tzinfo=timezone.utc)


def ts(delta_minutes: int = 0) -> str:
    """Return an RFC-3339 timestamp offset from NOW."""
    t = NOW - timedelta(minutes=abs(delta_minutes))
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def uid() -> str:
    return str(uuid.uuid4())


def make_namespace(name: str) -> dict:
    return {
        "metadata": {"name": name, "uid": uid(), "creationTimestamp": ts(10000)},
        "spec": {"finalizers": ["kubernetes"]},
        "status": {"phase": "Active"},
    }


def namespace_list(names: list[str]) -> dict:
    return {
        "kind": "NamespaceList",
        "apiVersion": "v1",
        "items": [make_namespace(n) for n in names],
    }


def cluster_version() -> dict:
    return {
        "major": "1",
        "minor": "28",
        "gitVersion": "v1.28.4",
        "gitCommit": "bae2c62678db6b5f265a3a5f48ae85f1c41c686c",
        "gitTreeState": "clean",
        "buildDate": "2024-11-12T12:15:00Z",
        "goVersion": "go1.21.4",
        "compiler": "gc",
        "platform": "linux/amd64",
    }


def make_node(
    name: str,
    ready: bool = True,
    conditions_extra: list[dict] | None = None,
    capacity_cpu: str = "4",
    capacity_mem: str = "16Gi",
    allocatable_cpu: str = "3800m",
    allocatable_mem: str = "15Gi",
) -> dict:
    conds = [
        {
            "type": "Ready",
            "status": "True" if ready else "False",
            "lastHeartbeatTime": ts(0 if ready else 30),
            "lastTransitionTime": ts(0 if ready else 30),
            "reason": "KubeletReady" if ready else "KubeletNotReady",
            "message": "kubelet is posting ready status" if ready else "Kubelet stopped posting node status.",
        },
        {
            "type": "MemoryPressure",
            "status": "False",
            "lastHeartbeatTime": ts(0),
            "lastTransitionTime": ts(10000),
            "reason": "KubeletHasSufficientMemory",
            "message": "kubelet has sufficient memory available",
        },
        {
            "type": "DiskPressure",
            "status": "False",
            "lastHeartbeatTime": ts(0),
            "lastTransitionTime": ts(10000),
            "reason": "KubeletHasNoDiskPressure",
            "message": "kubelet has no disk pressure",
        },
        {
            "type": "PIDPressure",
            "status": "False",
            "lastHeartbeatTime": ts(0),
            "lastTransitionTime": ts(10000),
            "reason": "KubeletHasSufficientPID",
            "message": "kubelet has sufficient PID available",
        },
    ]
    if conditions_extra:
        for ce in conditions_extra:
            for i, c in enumerate(conds):
                if c["type"] == ce["type"]:
                    conds[i] = ce
                    break
            else:
                conds.append(ce)
    return {
        "metadata": {
            "name": name,
            "uid": uid(),
            "creationTimestamp": ts(50000),
            "labels": {
                "kubernetes.io/hostname": name,
                "kubernetes.io/os": "linux",
                "kubernetes.io/arch": "amd64",
                "node-role.kubernetes.io/control-plane": "",
            },
        },
        "spec": {},
        "status": {
            "capacity": {"cpu": capacity_cpu, "memory": capacity_mem, "pods": "110"},
            "allocatable": {"cpu": allocatable_cpu, "memory": allocatable_mem, "pods": "110"},
            "conditions": conds,
            "nodeInfo": {
                "kubeletVersion": "v1.28.4",
                "containerRuntimeVersion": "containerd://1.7.11",
                "osImage": "Ubuntu 22.04.3 LTS",
                "kernelVersion": "5.15.0-91-generic",
                "architecture": "amd64",
                "operatingSystem": "linux",
            },
            "addresses": [
                {"type": "InternalIP", "address": f"10.0.1.{hash(name) % 200 + 10}"},
                {"type": "Hostname", "address": name},
            ],
        },
    }


def node_list(nodes: list[dict]) -> dict:
    return {"kind": "NodeList", "apiVersion": "v1", "items": nodes}


def make_container_status(
    name: str,
    image: str,
    ready: bool = True,
    restart_count: int = 0,
    state: str = "running",
    reason: str | None = None,
    message: str | None = None,
    last_state: dict | None = None,
) -> dict:
    state_obj: dict[str, Any] = {}
    if state == "running":
        state_obj = {"running": {"startedAt": ts(120)}}
    elif state == "waiting":
        w: dict[str, Any] = {}
        if reason:
            w["reason"] = reason
        if message:
            w["message"] = message
        state_obj = {"waiting": w}
    elif state == "terminated":
        t: dict[str, Any] = {"exitCode": 137, "finishedAt": ts(5)}
        if reason:
            t["reason"] = reason
        if message:
            t["message"] = message
        state_obj = {"terminated": t}
    cs: dict[str, Any] = {
        "name": name,
        "image": image,
        "imageID": f"docker-pullable://{image}@sha256:{uuid.uuid4().hex}",
        "containerID": f"containerd://{uuid.uuid4().hex}",
        "ready": ready,
        "restartCount": restart_count,
        "state": state_obj,
        "started": ready,
    }
    if last_state:
        cs["lastState"] = last_state
    return cs


def make_pod(
    name: str,
    namespace: str,
    containers: list[dict],
    container_statuses: list[dict],
    phase: str = "Running",
    node_name: str = "node-1",
    labels: dict | None = None,
    conditions: list[dict] | None = None,
    creation_offset: int = 5000,
    reason: str | None = None,
    message: str | None = None,
) -> dict:
    pod_labels = {"app": name.rsplit("-", 1)[0] if "-" in name else name}
    if labels:
        pod_labels.update(labels)

    status: dict[str, Any] = {
        "phase": phase,
        "hostIP": f"10.0.1.{hash(node_name) % 200 + 10}",
        "podIP": f"10.244.{hash(name) % 255}.{hash(name + 'x') % 255}",
        "startTime": ts(creation_offset),
        "containerStatuses": container_statuses,
    }
    if conditions:
        status["conditions"] = conditions
    if reason:
        status["reason"] = reason
    if message:
        status["message"] = message

    return {
        "metadata": {
            "name": name,
            "namespace": namespace,
            "uid": uid(),
            "creationTimestamp": ts(creation_offset),
            "labels": pod_labels,
        },
        "spec": {
            "nodeName": node_name,
            "containers": containers,
            "restartPolicy": "Always",
            "serviceAccountName": "default",
        },
        "status": status,
    }


def container_spec(name: str, image: str, cpu_req: str = "100m", mem_req: str = "128Mi",
                    cpu_lim: str = "500m", mem_lim: str = "512Mi", ports: list[int] | None = None,
                    env: list[dict] | None = None) -> dict:
    c: dict[str, Any] = {
        "name": name,
        "image": image,
        "resources": {
            "requests": {"cpu": cpu_req, "memory": mem_req},
            "limits": {"cpu": cpu_lim, "memory": mem_lim},
        },
    }
    if ports:
        c["ports"] = [{"containerPort": p, "protocol": "TCP"} for p in ports]
    if env:
        c["env"] = env
    return c


def pod_list(pods: list[dict]) -> dict:
    return {"kind": "PodList", "apiVersion": "v1", "items": pods}


def make_deployment(name: str, namespace: str, replicas: int, ready_replicas: int,
                    image: str, labels: dict | None = None) -> dict:
    sel_labels = {"app": name}
    if labels:
        sel_labels.update(labels)
    return {
        "metadata": {
            "name": name,
            "namespace": namespace,
            "uid": uid(),
            "creationTimestamp": ts(10000),
            "labels": sel_labels,
        },
        "spec": {
            "replicas": replicas,
            "selector": {"matchLabels": {"app": name}},
            "template": {
                "metadata": {"labels": {"app": name}},
                "spec": {
                    "containers": [{"name": name, "image": image}],
                },
            },
            "strategy": {"type": "RollingUpdate", "rollingUpdate": {"maxSurge": "25%", "maxUnavailable": "25%"}},
        },
        "status": {
            "replicas": replicas,
            "readyReplicas": ready_replicas,
            "availableReplicas": ready_replicas,
            "updatedReplicas": replicas,
            "conditions": [
                {
                    "type": "Available",
                    "status": "True" if ready_replicas > 0 else "False",
                    "lastTransitionTime": ts(9000),
                    "reason": "MinimumReplicasAvailable" if ready_replicas > 0 else "MinimumReplicasUnavailable",
                },
                {
                    "type": "Progressing",
                    "status": "True",
                    "lastTransitionTime": ts(9000),
                    "reason": "NewReplicaSetAvailable",
                },
            ],
        },
    }


def deployment_list(deps: list[dict]) -> dict:
    return {"kind": "DeploymentList", "apiVersion": "apps/v1", "items": deps}


def make_service(name: str, namespace: str, port: int, target_port: int,
                 svc_type: str = "ClusterIP") -> dict:
    return {
        "metadata": {
            "name": name,
            "namespace": namespace,
            "uid": uid(),
            "creationTimestamp": ts(10000),
            "labels": {"app": name},
        },
        "spec": {
            "type": svc_type,
            "selector": {"app": name},
            "ports": [{"port": port, "targetPort": target_port, "protocol": "TCP"}],
            "clusterIP": f"10.96.{hash(name) % 255}.{hash(name + 'svc') % 255}",
        },
    }


def service_list(svcs: list[dict]) -> dict:
    return {"kind": "ServiceList", "apiVersion": "v1", "items": svcs}


def make_event(
    name: str,
    namespace: str,
    involved_name: str,
    involved_kind: str,
    reason: str,
    message: str,
    event_type: str = "Normal",
    count: int = 1,
    first_offset: int = 60,
    last_offset: int = 5,
) -> dict:
    return {
        "metadata": {
            "name": f"{involved_name}.{uuid.uuid4().hex[:16]}",
            "namespace": namespace,
            "uid": uid(),
            "creationTimestamp": ts(first_offset),
        },
        "involvedObject": {
            "kind": involved_kind,
            "name": involved_name,
            "namespace": namespace,
        },
        "reason": reason,
        "message": message,
        "type": event_type,
        "count": count,
        "firstTimestamp": ts(first_offset),
        "lastTimestamp": ts(last_offset),
        "source": {"component": "kubelet" if involved_kind == "Pod" else "deployment-controller"},
    }


def event_list(events: list[dict]) -> dict:
    return {"kind": "EventList", "apiVersion": "v1", "items": events}


def log_lines(entries: list[tuple[int, str, str]]) -> str:
    """Build timestamped log output. entries = [(offset_minutes, level, message), ...]"""
    lines = []
    for offset, level, msg in entries:
        t = NOW - timedelta(minutes=offset)
        ts_str = t.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        lines.append(f"{ts_str} {level} {msg}")
    return "\n".join(lines) + "\n"


def analysis_json(insights: list[dict]) -> dict:
    return {
        "kind": "SupportBundle",
        "apiVersion": "troubleshoot.sh/v1beta2",
        "spec": {},
        "status": {
            "analyzers": insights,
        },
    }


def analyzer_result(title: str, message: str, severity: str, icon_uri: str = "") -> dict:
    return {
        "name": title,
        "isPass": severity == "pass",
        "isWarn": severity == "warn",
        "isFail": severity == "fail",
        "title": title,
        "message": message,
        "severity": severity,
        "iconUri": icon_uri,
    }


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def write_json(base: str, path: str, data: dict):
    full = os.path.join(base, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        json.dump(data, f, indent=2)


def write_text(base: str, path: str, text: str):
    full = os.path.join(base, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(text)


def tar_bundle(base_dir: str, name: str):
    out = os.path.join(OUTPUT_DIR, name)
    with tarfile.open(out, "w:gz") as tar:
        tar.add(base_dir, arcname=os.path.basename(base_dir))
    return out


# ===================================================================
# BUNDLE 1: Healthy Cluster (~90% health)
# ===================================================================

def generate_healthy_cluster():
    bd = os.path.join(TMP_BASE, "healthy-cluster")
    ns = "default"

    nodes = [make_node("node-1"), make_node("node-2"), make_node("node-3")]
    write_json(bd, "cluster-resources/nodes.json", node_list(nodes))
    write_json(bd, "cluster-resources/namespaces.json", namespace_list(["default", "kube-system"]))
    write_json(bd, "cluster-info/cluster_version.json", cluster_version())

    # Pods
    pods = []
    for i in range(3):
        pods.append(make_pod(
            f"nginx-{uid()[:8]}", ns,
            [container_spec("nginx", "nginx:1.25.3", ports=[80])],
            [make_container_status("nginx", "nginx:1.25.3")],
            node_name=f"node-{i+1}",
        ))
    for i in range(2):
        pods.append(make_pod(
            f"api-server-{uid()[:8]}", ns,
            [container_spec("api-server", "myapp/api-server:v2.1.0", ports=[8080])],
            [make_container_status("api-server", "myapp/api-server:v2.1.0")],
            node_name=f"node-{i+1}",
        ))
    pods.append(make_pod(
        f"redis-{uid()[:8]}", ns,
        [container_spec("redis", "redis:7.2.3", ports=[6379])],
        [make_container_status("redis", "redis:7.2.3")],
        node_name="node-2",
    ))
    pods.append(make_pod(
        f"postgres-{uid()[:8]}", ns,
        [container_spec("postgres", "postgres:16.1", mem_req="256Mi", mem_lim="1Gi", ports=[5432])],
        [make_container_status("postgres", "postgres:16.1")],
        node_name="node-3",
    ))
    # A pod with 2 restarts but running
    pods.append(make_pod(
        f"worker-{uid()[:8]}", ns,
        [container_spec("worker", "myapp/worker:v2.1.0")],
        [make_container_status("worker", "myapp/worker:v2.1.0", restart_count=2,
                               last_state={"terminated": {"exitCode": 1, "reason": "Error", "finishedAt": ts(300)}})],
        node_name="node-1",
    ))
    # 2 more kube-system pods
    pods.append(make_pod(
        "coredns-5dd5756b68-abc12", "kube-system",
        [container_spec("coredns", "registry.k8s.io/coredns/coredns:v1.11.1", ports=[53])],
        [make_container_status("coredns", "registry.k8s.io/coredns/coredns:v1.11.1")],
        node_name="node-1",
    ))
    pods.append(make_pod(
        "kube-proxy-xz9k2", "kube-system",
        [container_spec("kube-proxy", "registry.k8s.io/kube-proxy:v1.28.4")],
        [make_container_status("kube-proxy", "registry.k8s.io/kube-proxy:v1.28.4")],
        node_name="node-1",
    ))

    default_pods = [p for p in pods if p["metadata"]["namespace"] == ns]
    ks_pods = [p for p in pods if p["metadata"]["namespace"] == "kube-system"]
    write_json(bd, f"cluster-resources/pods/{ns}.json", pod_list(default_pods))
    write_json(bd, "cluster-resources/pods/kube-system.json", pod_list(ks_pods))

    # Deployments
    deps = [
        make_deployment("nginx", ns, 3, 3, "nginx:1.25.3"),
        make_deployment("api-server", ns, 2, 2, "myapp/api-server:v2.1.0"),
        make_deployment("redis", ns, 1, 1, "redis:7.2.3"),
        make_deployment("postgres", ns, 1, 1, "postgres:16.1"),
    ]
    write_json(bd, f"cluster-resources/deployments/{ns}.json", deployment_list(deps))

    # Services
    svcs = [
        make_service("nginx", ns, 80, 80),
        make_service("api-server", ns, 8080, 8080),
        make_service("redis", ns, 6379, 6379),
        make_service("postgres", ns, 5432, 5432),
    ]
    write_json(bd, f"cluster-resources/services/{ns}.json", service_list(svcs))

    # Events — all normal
    events = []
    for p in default_pods:
        pn = p["metadata"]["name"]
        events.append(make_event(pn, ns, pn, "Pod", "Scheduled", f"Successfully assigned {ns}/{pn} to {p['spec']['nodeName']}"))
        events.append(make_event(pn, ns, pn, "Pod", "Pulled", f"Container image \"{p['spec']['containers'][0]['image']}\" already present on machine"))
        events.append(make_event(pn, ns, pn, "Pod", "Started", f"Started container {p['spec']['containers'][0]['name']}"))
    write_json(bd, f"cluster-resources/events/{ns}.json", event_list(events))

    # Logs
    for p in default_pods:
        pn = p["metadata"]["name"]
        cn = p["spec"]["containers"][0]["name"]
        entries = []
        for m in range(120, 0, -5):
            entries.append((m, "INFO", f"[{cn}] Request processed successfully, duration=12ms"))
        entries.insert(5, (90, "WARN", f"[{cn}] Retrying connection to upstream, attempt 1/3"))
        entries.insert(6, (89, "INFO", f"[{cn}] Connection to upstream re-established"))
        write_text(bd, f"{pn}/{cn}.log", log_lines(entries))

    # Analysis
    write_json(bd, "analysis.json", analysis_json([
        analyzer_result("Node Status", "All 3 nodes are ready", "pass"),
        analyzer_result("Pod Health", "9/10 pods running, 1 pod has 2 restarts but is currently healthy", "pass"),
        analyzer_result("Deployments Available", "All deployments have desired replicas available", "pass"),
        analyzer_result("Cluster Version", "Kubernetes v1.28.4 is a supported version", "pass"),
    ]))

    return tar_bundle(bd, "healthy-cluster.tar.gz")


# ===================================================================
# BUNDLE 2: Network Issues (~55% health)
# ===================================================================

def generate_network_issues():
    bd = os.path.join(TMP_BASE, "network-issues")
    ns = "default"

    nodes = [make_node("node-1"), make_node("node-2")]
    write_json(bd, "cluster-resources/nodes.json", node_list(nodes))
    write_json(bd, "cluster-resources/namespaces.json", namespace_list(["default", "kube-system"]))
    write_json(bd, "cluster-info/cluster_version.json", cluster_version())

    pods = []
    # 5 running pods
    pods.append(make_pod(
        "frontend-6b8f9c7d4-k2m3n", ns,
        [container_spec("frontend", "myapp/frontend:v1.8.0", ports=[3000])],
        [make_container_status("frontend", "myapp/frontend:v1.8.0")],
        node_name="node-1",
    ))
    pods.append(make_pod(
        "redis-master-0", ns,
        [container_spec("redis", "redis:7.2.3", ports=[6379])],
        [make_container_status("redis", "redis:7.2.3")],
        node_name="node-1",
    ))
    pods.append(make_pod(
        "monitoring-agent-dq8w2", ns,
        [container_spec("monitoring-agent", "prom/node-exporter:v1.7.0", ports=[9100])],
        [make_container_status("monitoring-agent", "prom/node-exporter:v1.7.0")],
        node_name="node-2",
    ))
    pods.append(make_pod(
        "coredns-5dd5756b68-zx8w1", "kube-system",
        [container_spec("coredns", "registry.k8s.io/coredns/coredns:v1.11.1")],
        [make_container_status("coredns", "registry.k8s.io/coredns/coredns:v1.11.1")],
        node_name="node-1",
    ))
    pods.append(make_pod(
        "ingress-controller-7f9b6c5d-m2x8", ns,
        [container_spec("ingress", "k8s.gcr.io/ingress-nginx/controller:v1.9.4", ports=[80, 443])],
        [make_container_status("ingress", "k8s.gcr.io/ingress-nginx/controller:v1.9.4")],
        node_name="node-1",
    ))

    # 3 pods with networking issues (still Running phase but broken)
    pods.append(make_pod(
        "api-gateway-5c8d7e6f-p9q2r", ns,
        [container_spec("api-gateway", "myapp/api-gateway:v2.3.1", ports=[8080])],
        [make_container_status("api-gateway", "myapp/api-gateway:v2.3.1", restart_count=5,
                               last_state={"terminated": {"exitCode": 1, "reason": "Error", "finishedAt": ts(10)}})],
        node_name="node-2",
    ))
    pods.append(make_pod(
        "backend-service-4b7c9d3e-s5t6u", ns,
        [container_spec("backend-service", "myapp/backend-service:v2.3.1", ports=[8081])],
        [make_container_status("backend-service", "myapp/backend-service:v2.3.1", restart_count=3,
                               last_state={"terminated": {"exitCode": 1, "reason": "Error", "finishedAt": ts(8)}})],
        node_name="node-2",
    ))
    pods.append(make_pod(
        "worker-7e6f5d4c-v8w9x", ns,
        [container_spec("worker", "myapp/worker:v2.3.1")],
        [make_container_status("worker", "myapp/worker:v2.3.1", restart_count=4,
                               last_state={"terminated": {"exitCode": 1, "reason": "Error", "finishedAt": ts(12)}})],
        node_name="node-1",
    ))

    default_pods = [p for p in pods if p["metadata"]["namespace"] == ns]
    ks_pods = [p for p in pods if p["metadata"]["namespace"] == "kube-system"]
    write_json(bd, f"cluster-resources/pods/{ns}.json", pod_list(default_pods))
    write_json(bd, "cluster-resources/pods/kube-system.json", pod_list(ks_pods))

    deps = [
        make_deployment("api-gateway", ns, 1, 1, "myapp/api-gateway:v2.3.1"),
        make_deployment("backend-service", ns, 1, 1, "myapp/backend-service:v2.3.1"),
        make_deployment("worker", ns, 1, 1, "myapp/worker:v2.3.1"),
        make_deployment("frontend", ns, 1, 1, "myapp/frontend:v1.8.0"),
        make_deployment("redis-master", ns, 1, 1, "redis:7.2.3"),
    ]
    write_json(bd, f"cluster-resources/deployments/{ns}.json", deployment_list(deps))

    svcs = [
        make_service("api-gateway", ns, 8080, 8080),
        make_service("backend-service", ns, 8081, 8081),
        make_service("frontend", ns, 3000, 3000),
        make_service("redis-master", ns, 6379, 6379),
        make_service("message-queue", ns, 5672, 5672),
    ]
    write_json(bd, f"cluster-resources/services/{ns}.json", service_list(svcs))

    # Events
    events = [
        make_event("ev1", ns, "api-gateway-5c8d7e6f-p9q2r", "Pod", "ConnectionRefused",
                    "Connection refused to backend-service:8080 - no route to host",
                    event_type="Warning", count=47, first_offset=120, last_offset=2),
        make_event("ev2", ns, "backend-service-4b7c9d3e-s5t6u", "Pod", "FailedResolve",
                    "Failed to resolve DNS name database.svc.cluster.local: NXDOMAIN",
                    event_type="Warning", count=34, first_offset=115, last_offset=3),
        make_event("ev3", ns, "worker-7e6f5d4c-v8w9x", "Pod", "ConnectionTimeout",
                    "Timeout connecting to message-queue:5672 after 30s",
                    event_type="Warning", count=28, first_offset=110, last_offset=4),
        make_event("ev4", ns, "backend-service-4b7c9d3e-s5t6u", "Pod", "NetworkPolicyDenied",
                    "NetworkPolicy default/restrict-egress is blocking egress traffic to 10.96.0.10:53",
                    event_type="Warning", count=12, first_offset=100, last_offset=5),
        make_event("ev5", ns, "api-gateway-5c8d7e6f-p9q2r", "Pod", "Unhealthy",
                    "Readiness probe failed: HTTP probe failed with statuscode: 503",
                    event_type="Warning", count=15, first_offset=90, last_offset=3),
    ]
    # Normal events too
    for p in default_pods[:3]:
        pn = p["metadata"]["name"]
        events.append(make_event(pn, ns, pn, "Pod", "Scheduled",
                                 f"Successfully assigned {ns}/{pn} to {p['spec']['nodeName']}"))
        events.append(make_event(pn, ns, pn, "Pod", "Started",
                                 f"Started container {p['spec']['containers'][0]['name']}"))
    write_json(bd, f"cluster-resources/events/{ns}.json", event_list(events))

    # Logs
    # api-gateway logs
    gw_logs = []
    for m in range(120, 0, -2):
        gw_logs.append((m, "ERROR", '[api-gateway] net/http: request canceled while waiting for connection (Client.Timeout exceeded) - POST http://backend-service:8080/api/v1/process'))
        gw_logs.append((m, "WARN", '[api-gateway] circuit breaker OPEN for backend-service, 47 consecutive failures'))
    gw_logs.insert(0, (121, "INFO", "[api-gateway] Starting API gateway v2.3.1 on :8080"))
    gw_logs.insert(1, (120, "INFO", "[api-gateway] Attempting to connect to backend-service:8080"))
    write_text(bd, "api-gateway-5c8d7e6f-p9q2r/api-gateway.log", log_lines(gw_logs))

    # backend-service logs
    bs_logs = []
    for m in range(120, 0, -3):
        bs_logs.append((m, "ERROR", "[backend-service] dial tcp: lookup database.svc.cluster.local on 10.96.0.10:53: no such host"))
        bs_logs.append((m - 1, "ERROR", "[backend-service] failed to connect to database: DNS resolution failed for database.svc.cluster.local"))
        bs_logs.append((m - 1, "WARN", "[backend-service] health check failing, marking service unhealthy"))
    write_text(bd, "backend-service-4b7c9d3e-s5t6u/backend-service.log", log_lines(bs_logs))

    # worker logs
    wk_logs = []
    for m in range(120, 0, -4):
        wk_logs.append((m, "ERROR", "[worker] failed to connect to AMQP broker at message-queue:5672: dial tcp 10.96.43.128:5672: i/o timeout"))
        wk_logs.append((m - 1, "WARN", "[worker] message queue connection lost, queued 0 messages locally, retrying in 10s"))
    write_text(bd, "worker-7e6f5d4c-v8w9x/worker.log", log_lines(wk_logs))

    # healthy pod logs
    for p in default_pods[:3]:
        pn = p["metadata"]["name"]
        cn = p["spec"]["containers"][0]["name"]
        entries = [(m, "INFO", f"[{cn}] Serving requests normally") for m in range(60, 0, -10)]
        write_text(bd, f"{pn}/{cn}.log", log_lines(entries))

    write_json(bd, "analysis.json", analysis_json([
        analyzer_result("Node Status", "All 2 nodes are ready", "pass"),
        analyzer_result("DNS Resolution", "backend-service cannot resolve database.svc.cluster.local - DNS queries returning NXDOMAIN", "fail"),
        analyzer_result("Service Connectivity", "api-gateway cannot connect to backend-service:8080 - connection refused", "fail"),
        analyzer_result("Message Queue", "worker cannot connect to message-queue:5672 - connection timeout", "fail"),
        analyzer_result("NetworkPolicy", "NetworkPolicy restrict-egress may be blocking DNS egress to kube-dns", "warn"),
        analyzer_result("Pod Restarts", "3 pods have elevated restart counts (3-5 restarts)", "warn"),
    ]))

    return tar_bundle(bd, "network-issues.tar.gz")


# ===================================================================
# BUNDLE 3: Resource Exhaustion (~25% health)
# ===================================================================

def generate_resource_exhaustion():
    bd = os.path.join(TMP_BASE, "resource-exhaustion")
    ns = "default"

    node2_conds = [
        {"type": "MemoryPressure", "status": "True", "lastHeartbeatTime": ts(2),
         "lastTransitionTime": ts(60), "reason": "KubeletHasInsufficientMemory",
         "message": "kubelet has insufficient memory available"},
        {"type": "DiskPressure", "status": "True", "lastHeartbeatTime": ts(2),
         "lastTransitionTime": ts(45), "reason": "KubeletHasDiskPressure",
         "message": "kubelet has disk pressure"},
    ]
    nodes = [
        make_node("node-1"),
        make_node("node-2", ready=True, conditions_extra=node2_conds,
                  capacity_mem="8Gi", allocatable_mem="7Gi"),
    ]
    write_json(bd, "cluster-resources/nodes.json", node_list(nodes))
    write_json(bd, "cluster-resources/namespaces.json", namespace_list(["default", "kube-system", "ml-workloads"]))
    write_json(bd, "cluster-info/cluster_version.json", cluster_version())

    pods = []
    # 6 running
    for i, (n, img) in enumerate([
        ("web-frontend-6b8c9d-ab12", "myapp/frontend:v1.5.0"),
        ("api-server-7c9d0e-cd34", "myapp/api-server:v3.0.1"),
        ("redis-cache-0", "redis:7.2.3"),
        ("monitoring-prometheus-0", "prom/prometheus:v2.48.1"),
        ("logging-fluentd-8x9w2", "fluent/fluentd:v1.16.3"),
        ("ingress-nginx-controller-5f6g7-ef56", "k8s.gcr.io/ingress-nginx/controller:v1.9.4"),
    ]):
        pods.append(make_pod(n, ns,
            [container_spec(n.rsplit("-", 1)[0], img)],
            [make_container_status(n.rsplit("-", 1)[0], img)],
            node_name="node-1"))

    # 2 OOMKilled
    pods.append(make_pod(
        "ml-training-job-9a8b7c", "ml-workloads",
        [container_spec("ml-training", "myapp/ml-training:v1.2.0", mem_req="2Gi", mem_lim="4Gi", cpu_req="2", cpu_lim="4")],
        [make_container_status("ml-training", "myapp/ml-training:v1.2.0", ready=False, restart_count=3,
                               state="terminated", reason="OOMKilled",
                               last_state={"terminated": {"exitCode": 137, "reason": "OOMKilled",
                                                          "finishedAt": ts(15)}})],
        phase="Failed", node_name="node-2", reason="OOMKilled",
        message="The container was killed because it exceeded its memory limit of 4Gi",
    ))
    pods.append(make_pod(
        "data-processor-6d5e4f", ns,
        [container_spec("data-processor", "myapp/data-processor:v2.0.3", mem_req="1Gi", mem_lim="2Gi", cpu_req="1", cpu_lim="2")],
        [make_container_status("data-processor", "myapp/data-processor:v2.0.3", ready=False, restart_count=5,
                               state="terminated", reason="OOMKilled",
                               last_state={"terminated": {"exitCode": 137, "reason": "OOMKilled",
                                                          "finishedAt": ts(8)}})],
        phase="Failed", node_name="node-2", reason="OOMKilled",
        message="The container was killed because it exceeded its memory limit of 2Gi",
    ))

    # 2 Evicted
    pods.append(make_pod(
        "batch-worker-1a2b3c", ns,
        [container_spec("batch-worker", "myapp/batch-worker:v1.1.0", mem_req="512Mi", mem_lim="1Gi")],
        [make_container_status("batch-worker", "myapp/batch-worker:v1.1.0", ready=False,
                               state="terminated", reason="Evicted")],
        phase="Failed", node_name="node-2", reason="Evicted",
        message="The node was low on resource: memory. Threshold quantity: 100Mi, available: 48Mi.",
    ))
    pods.append(make_pod(
        "log-aggregator-4d5e6f", ns,
        [container_spec("log-aggregator", "myapp/log-aggregator:v1.0.2", mem_req="256Mi", mem_lim="512Mi")],
        [make_container_status("log-aggregator", "myapp/log-aggregator:v1.0.2", ready=False,
                               state="terminated", reason="Evicted")],
        phase="Failed", node_name="node-2", reason="Evicted",
        message="The node was low on resource: ephemeral-storage. Threshold quantity: 1Gi, available: 214Mi.",
    ))

    # 2 Pending
    pods.append(make_pod(
        "batch-job-7g8h9i", ns,
        [container_spec("batch-job", "myapp/batch-job:v1.3.0", mem_req="4Gi", mem_lim="8Gi", cpu_req="2", cpu_lim="4")],
        [make_container_status("batch-job", "myapp/batch-job:v1.3.0", ready=False,
                               state="waiting", reason="Unschedulable",
                               message="0/2 nodes are available: 1 Insufficient memory, 1 node(s) had taint {node-role.kubernetes.io/control-plane: }, that the pod didn't tolerate.")],
        phase="Pending", node_name="",
        conditions=[{"type": "PodScheduled", "status": "False", "reason": "Unschedulable",
                     "message": "0/2 nodes are available: 1 Insufficient memory, 1 Insufficient cpu."}],
    ))
    pods.append(make_pod(
        "analytics-worker-0j1k2l", ns,
        [container_spec("analytics-worker", "myapp/analytics:v2.1.0", mem_req="2Gi", mem_lim="4Gi")],
        [make_container_status("analytics-worker", "myapp/analytics:v2.1.0", ready=False,
                               state="waiting", reason="Unschedulable",
                               message="0/2 nodes are available: 1 Insufficient memory.")],
        phase="Pending", node_name="",
        conditions=[{"type": "PodScheduled", "status": "False", "reason": "Unschedulable",
                     "message": "0/2 nodes are available: 1 Insufficient memory, 1 node(s) had taint."}],
    ))

    default_pods = [p for p in pods if p["metadata"]["namespace"] == ns]
    ml_pods = [p for p in pods if p["metadata"]["namespace"] == "ml-workloads"]
    write_json(bd, f"cluster-resources/pods/{ns}.json", pod_list(default_pods))
    write_json(bd, "cluster-resources/pods/ml-workloads.json", pod_list(ml_pods))

    deps = [
        make_deployment("web-frontend", ns, 1, 1, "myapp/frontend:v1.5.0"),
        make_deployment("api-server", ns, 1, 1, "myapp/api-server:v3.0.1"),
        make_deployment("data-processor", ns, 1, 0, "myapp/data-processor:v2.0.3"),
        make_deployment("batch-worker", ns, 1, 0, "myapp/batch-worker:v1.1.0"),
    ]
    write_json(bd, f"cluster-resources/deployments/{ns}.json", deployment_list(deps))

    svcs = [
        make_service("web-frontend", ns, 3000, 3000),
        make_service("api-server", ns, 8080, 8080),
        make_service("redis-cache", ns, 6379, 6379),
    ]
    write_json(bd, f"cluster-resources/services/{ns}.json", service_list(svcs))

    events = [
        make_event("ev1", ns, "ml-training-job-9a8b7c", "Pod", "OOMKilling",
                    "Memory cgroup out of memory: Killed process 4521 (python3) total-vm:8912340kB, anon-rss:4194304kB, file-rss:0kB",
                    event_type="Warning", count=3, first_offset=120, last_offset=15),
        make_event("ev2", ns, "data-processor-6d5e4f", "Pod", "OOMKilling",
                    "Memory cgroup out of memory: Killed process 3891 (java) total-vm:4567890kB, anon-rss:2097152kB",
                    event_type="Warning", count=5, first_offset=100, last_offset=8),
        make_event("ev3", ns, "batch-worker-1a2b3c", "Pod", "Evicted",
                    "The node was low on resource: memory. Threshold quantity: 100Mi, available: 48Mi.",
                    event_type="Warning", count=1, first_offset=50, last_offset=50),
        make_event("ev4", ns, "log-aggregator-4d5e6f", "Pod", "Evicted",
                    "The node was low on resource: ephemeral-storage.",
                    event_type="Warning", count=1, first_offset=45, last_offset=45),
        make_event("ev5", ns, "batch-job-7g8h9i", "Pod", "FailedScheduling",
                    "0/2 nodes are available: 1 Insufficient memory, 1 Insufficient cpu. preemption: 0/2 nodes are available: 2 No preemption victims found for incoming pod.",
                    event_type="Warning", count=22, first_offset=90, last_offset=1),
        make_event("ev6", ns, "node-2", "Node", "SystemOOM",
                    "System OOM encountered, victim process: java, pid: 3891",
                    event_type="Warning", count=4, first_offset=100, last_offset=10),
        make_event("ev7", ns, "node-2", "Node", "EvictionThresholdMet",
                    "Attempting to reclaim memory",
                    event_type="Warning", count=6, first_offset=55, last_offset=5),
    ]
    write_json(bd, f"cluster-resources/events/{ns}.json", event_list(events))

    # Logs for OOMKilled pods
    ml_logs = []
    for m in range(60, 15, -1):
        mem_usage = int(2048 + (4096 - 2048) * (60 - m) / 45)
        ml_logs.append((m, "INFO", f"[ml-training] Epoch {61 - m}/100 - memory usage: {mem_usage}Mi / 4096Mi"))
        if mem_usage > 3500:
            ml_logs.append((m, "WARN", f"[ml-training] Memory usage critical: {mem_usage}Mi exceeds 85% of limit (4096Mi)"))
    ml_logs.append((15, "WARN", "[ml-training] Memory usage: 4091Mi / 4096Mi - approaching limit"))
    ml_logs.append((15, "ERROR", "[ml-training] runtime: out of memory allocating 134217728-byte block"))
    write_text(bd, "ml-training-job-9a8b7c/ml-training.log", log_lines(ml_logs))

    dp_logs = []
    for m in range(40, 8, -1):
        used = int(1024 + (2048 - 1024) * (40 - m) / 32)
        dp_logs.append((m, "INFO", f"[data-processor] Processing batch {41 - m}, heap usage: {used}Mi"))
        if used > 1800:
            dp_logs.append((m, "WARN", f"[data-processor] GC pressure high, heap: {used}Mi, GC pause: {(used - 1800) * 2}ms"))
    dp_logs.append((8, "ERROR", "[data-processor] java.lang.OutOfMemoryError: Java heap space"))
    dp_logs.append((8, "ERROR", "[data-processor] \tat java.util.Arrays.copyOf(Arrays.java:3236)"))
    dp_logs.append((8, "ERROR", "[data-processor] \tat java.util.ArrayList.grow(ArrayList.java:265)"))
    write_text(bd, "data-processor-6d5e4f/data-processor.log", log_lines(dp_logs))

    # Healthy pod logs
    for p in default_pods[:4]:
        pn = p["metadata"]["name"]
        cn = p["spec"]["containers"][0]["name"]
        entries = [(m, "INFO", f"[{cn}] Operating normally") for m in range(60, 0, -15)]
        write_text(bd, f"{pn}/{cn}.log", log_lines(entries))

    # Host info
    write_text(bd, "host-collectors/system/df.txt",
               "Filesystem      Size  Used Avail Use% Mounted on\n"
               "/dev/sda1       100G   95G  5.0G  95% /\n"
               "tmpfs           3.9G  1.2G  2.7G  31% /run\n"
               "/dev/sdb1       500G  412G   88G  83% /var/lib/containers\n")
    write_text(bd, "host-collectors/system/loadavg.txt",
               "12.47 11.83 10.21 14/387 29415\n")

    write_json(bd, "analysis.json", analysis_json([
        analyzer_result("Node Status", "node-2 has MemoryPressure and DiskPressure conditions", "fail"),
        analyzer_result("OOMKilled Pods", "2 pods terminated with OOMKilled: ml-training-job, data-processor", "fail"),
        analyzer_result("Evicted Pods", "2 pods evicted due to resource pressure on node-2", "fail"),
        analyzer_result("Pending Pods", "2 pods cannot be scheduled: Insufficient memory", "fail"),
        analyzer_result("Disk Usage", "Root filesystem is 95% full on node-2", "fail"),
        analyzer_result("Load Average", "System load average (12.47) exceeds CPU count (4)", "warn"),
        analyzer_result("Healthy Pods", "6 out of 12 pods are running normally", "warn"),
    ]))

    return tar_bundle(bd, "resource-exhaustion.tar.gz")


# ===================================================================
# BUNDLE 4: Configuration Errors (~35% health)
# ===================================================================

def generate_config_errors():
    bd = os.path.join(TMP_BASE, "config-errors")
    ns = "default"

    nodes = [make_node("node-1")]
    write_json(bd, "cluster-resources/nodes.json", node_list(nodes))
    write_json(bd, "cluster-resources/namespaces.json", namespace_list(["default", "kube-system"]))
    write_json(bd, "cluster-info/cluster_version.json", cluster_version())

    pods = []
    # 4 healthy
    pods.append(make_pod("nginx-proxy-5a6b7c8d-mn12", ns,
        [container_spec("nginx", "nginx:1.25.3", ports=[80])],
        [make_container_status("nginx", "nginx:1.25.3")], node_name="node-1"))
    pods.append(make_pod("redis-session-0", ns,
        [container_spec("redis", "redis:7.2.3", ports=[6379])],
        [make_container_status("redis", "redis:7.2.3")], node_name="node-1"))
    pods.append(make_pod("postgres-primary-0", ns,
        [container_spec("postgres", "postgres:16.1", ports=[5432],
                        env=[{"name": "POSTGRES_DB", "value": "appdb"},
                             {"name": "POSTGRES_USER", "value": "appuser"}])],
        [make_container_status("postgres", "postgres:16.1")], node_name="node-1"))
    pods.append(make_pod("metrics-collector-9x8w7v", ns,
        [container_spec("metrics", "prom/pushgateway:v1.7.0", ports=[9091])],
        [make_container_status("metrics", "prom/pushgateway:v1.7.0")], node_name="node-1"))

    # 4 broken
    # CreateContainerConfigError - missing configmap
    pods.append(make_pod("app-v2-3e4f5g6h-op34", ns,
        [container_spec("app-v2", "myapp/app:v2.0.0", ports=[8080],
                        env=[{"name": "CONFIG_PATH", "valueFrom": {"configMapKeyRef": {"name": "app-config", "key": "config.yaml"}}}])],
        [make_container_status("app-v2", "myapp/app:v2.0.0", ready=False, restart_count=0,
                               state="waiting", reason="CreateContainerConfigError",
                               message='configmap "app-config" not found')],
        node_name="node-1"))

    # CrashLoopBackOff - missing env var
    pods.append(make_pod("payment-api-7h8i9j0k-qr56", ns,
        [container_spec("payment-api", "myapp/payment-api:v1.4.2", ports=[8443])],
        [make_container_status("payment-api", "myapp/payment-api:v1.4.2", ready=False, restart_count=12,
                               state="waiting", reason="CrashLoopBackOff",
                               message="back-off 5m0s restarting failed container=payment-api pod=payment-api-7h8i9j0k-qr56_default",
                               last_state={"terminated": {"exitCode": 1, "reason": "Error",
                                                          "finishedAt": ts(2),
                                                          "startedAt": ts(3)}})],
        node_name="node-1"))

    # ImagePullBackOff
    pods.append(make_pod("auth-proxy-1l2m3n4o-st78", ns,
        [container_spec("auth-proxy", "registry.internal.io/auth:v3.2", ports=[8444])],
        [make_container_status("auth-proxy", "registry.internal.io/auth:v3.2", ready=False, restart_count=0,
                               state="waiting", reason="ImagePullBackOff",
                               message='Back-off pulling image "registry.internal.io/auth:v3.2"')],
        node_name="node-1"))

    # CrashLoopBackOff - invalid config
    pods.append(make_pod("scheduler-job-5p6q7r8s-uv90", ns,
        [container_spec("scheduler", "myapp/scheduler:v1.1.0")],
        [make_container_status("scheduler", "myapp/scheduler:v1.1.0", ready=False, restart_count=8,
                               state="waiting", reason="CrashLoopBackOff",
                               message="back-off 5m0s restarting failed container=scheduler pod=scheduler-job-5p6q7r8s-uv90_default",
                               last_state={"terminated": {"exitCode": 1, "reason": "Error",
                                                          "finishedAt": ts(3),
                                                          "startedAt": ts(4)}})],
        node_name="node-1"))

    write_json(bd, f"cluster-resources/pods/{ns}.json", pod_list(pods))

    deps = [
        make_deployment("nginx-proxy", ns, 1, 1, "nginx:1.25.3"),
        make_deployment("app-v2", ns, 1, 0, "myapp/app:v2.0.0"),
        make_deployment("payment-api", ns, 1, 0, "myapp/payment-api:v1.4.2"),
        make_deployment("auth-proxy", ns, 1, 0, "registry.internal.io/auth:v3.2"),
        make_deployment("scheduler-job", ns, 1, 0, "myapp/scheduler:v1.1.0"),
    ]
    write_json(bd, f"cluster-resources/deployments/{ns}.json", deployment_list(deps))

    svcs = [
        make_service("nginx-proxy", ns, 80, 80),
        make_service("app-v2", ns, 8080, 8080),
        make_service("payment-api", ns, 8443, 8443),
        make_service("auth-proxy", ns, 8444, 8444),
        make_service("redis-session", ns, 6379, 6379),
        make_service("postgres-primary", ns, 5432, 5432),
    ]
    write_json(bd, f"cluster-resources/services/{ns}.json", service_list(svcs))

    events = [
        make_event("ev1", ns, "app-v2-3e4f5g6h-op34", "Pod", "FailedMount",
                    'MountVolume.SetUp failed for volume "config-volume" : configmap "app-config" not found',
                    event_type="Warning", count=30, first_offset=180, last_offset=1),
        make_event("ev2", ns, "payment-api-7h8i9j0k-qr56", "Pod", "BackOff",
                    "Back-off restarting failed container payment-api in pod payment-api-7h8i9j0k-qr56_default(uid)",
                    event_type="Warning", count=12, first_offset=150, last_offset=2),
        make_event("ev3", ns, "auth-proxy-1l2m3n4o-st78", "Pod", "Failed",
                    'Failed to pull image "registry.internal.io/auth:v3.2": rpc error: code = Unknown desc = failed to resolve reference "registry.internal.io/auth:v3.2": failed to do request: Head "https://registry.internal.io/v2/auth/manifests/v3.2": dial tcp: lookup registry.internal.io on 10.96.0.10:53: no such host',
                    event_type="Warning", count=18, first_offset=170, last_offset=3),
        make_event("ev4", ns, "auth-proxy-1l2m3n4o-st78", "Pod", "ErrImagePull",
                    'rpc error: code = Unknown desc = failed to pull and unpack image "registry.internal.io/auth:v3.2": failed to resolve reference',
                    event_type="Warning", count=18, first_offset=170, last_offset=3),
        make_event("ev5", ns, "scheduler-job-5p6q7r8s-uv90", "Pod", "BackOff",
                    "Back-off restarting failed container scheduler in pod scheduler-job-5p6q7r8s-uv90_default(uid)",
                    event_type="Warning", count=8, first_offset=140, last_offset=3),
    ]
    write_json(bd, f"cluster-resources/events/{ns}.json", event_list(events))

    # Logs
    # payment-api
    pa_logs = []
    for cycle in range(12, 0, -1):
        offset = cycle * 10
        pa_logs.append((offset, "INFO", "[payment-api] Starting payment-api v1.4.2..."))
        pa_logs.append((offset - 1, "INFO", "[payment-api] Loading configuration from environment..."))
        pa_logs.append((offset - 2, "FATAL", "[payment-api] Environment variable DATABASE_URL is not set. Cannot start without database connection string."))
        pa_logs.append((offset - 2, "FATAL", "[payment-api] Required environment variables: DATABASE_URL, STRIPE_SECRET_KEY, JWT_SIGNING_KEY"))
        pa_logs.append((offset - 3, "ERROR", "[payment-api] Exiting with code 1"))
    write_text(bd, "payment-api-7h8i9j0k-qr56/payment-api.log", log_lines(pa_logs))

    # scheduler-job
    sj_logs = []
    for cycle in range(8, 0, -1):
        offset = cycle * 12
        sj_logs.append((offset, "INFO", "[scheduler] Initializing scheduler v1.1.0"))
        sj_logs.append((offset - 1, "INFO", "[scheduler] Parsing cron configuration from /etc/scheduler/crontab"))
        sj_logs.append((offset - 2, "ERROR", '[scheduler] Invalid cron expression "*/5 * * * * MON-FRI" in config: too many fields (6), expected 5'))
        sj_logs.append((offset - 2, "ERROR", "[scheduler] Failed to parse schedule for job 'cleanup-old-records': invalid cron expression"))
        sj_logs.append((offset - 3, "FATAL", "[scheduler] Cannot start: 1 invalid cron expression(s) found in configuration"))
    write_text(bd, "scheduler-job-5p6q7r8s-uv90/scheduler.log", log_lines(sj_logs))

    # app-v2 has no logs (container never started)
    write_text(bd, "app-v2-3e4f5g6h-op34/app-v2.log", "")

    # auth-proxy has no logs (image never pulled)
    write_text(bd, "auth-proxy-1l2m3n4o-st78/auth-proxy.log", "")

    # Healthy pods
    for p in pods[:4]:
        pn = p["metadata"]["name"]
        cn = p["spec"]["containers"][0]["name"]
        entries = [(m, "INFO", f"[{cn}] Running normally, connections active") for m in range(60, 0, -10)]
        write_text(bd, f"{pn}/{cn}.log", log_lines(entries))

    write_json(bd, "analysis.json", analysis_json([
        analyzer_result("Node Status", "node-1 is ready", "pass"),
        analyzer_result("ConfigMap Missing", 'Pod app-v2 cannot start: configmap "app-config" not found', "fail"),
        analyzer_result("Environment Variables", "Pod payment-api is crash-looping: DATABASE_URL environment variable not set", "fail"),
        analyzer_result("Image Pull", "Pod auth-proxy cannot pull image from registry.internal.io - host not resolvable", "fail"),
        analyzer_result("Configuration Parse", "Pod scheduler-job is crash-looping: invalid cron expression in configuration", "fail"),
        analyzer_result("Healthy Services", "4 out of 8 pods are running correctly", "warn"),
    ]))

    return tar_bundle(bd, "config-errors.tar.gz")


# ===================================================================
# BUNDLE 5: Cascading Failure (~15% health)
# ===================================================================

def generate_cascading_failure():
    bd = os.path.join(TMP_BASE, "cascading-failure")
    ns = "default"

    nodes = [
        make_node("node-1"),
        make_node("node-2"),
        make_node("node-3", ready=False),
    ]
    write_json(bd, "cluster-resources/nodes.json", node_list(nodes))
    write_json(bd, "cluster-resources/namespaces.json", namespace_list(["default", "kube-system", "monitoring"]))
    write_json(bd, "cluster-info/cluster_version.json", cluster_version())

    pods = []

    # ROOT CAUSE: postgres primary OOMKilled
    pods.append(make_pod("postgres-primary-0", ns,
        [container_spec("postgres", "postgres:16.1", mem_req="1Gi", mem_lim="2Gi", ports=[5432])],
        [make_container_status("postgres", "postgres:16.1", ready=False, restart_count=1,
                               state="terminated", reason="OOMKilled",
                               last_state={"terminated": {"exitCode": 137, "reason": "OOMKilled",
                                                          "finishedAt": ts(45)}})],
        phase="Failed", node_name="node-1", reason="OOMKilled",
        message="The container was killed because it exceeded its memory limit of 2Gi"))

    # postgres replica - running but read-only, no primary
    pods.append(make_pod("postgres-replica-0", ns,
        [container_spec("postgres", "postgres:16.1", mem_req="512Mi", mem_lim="1Gi", ports=[5432])],
        [make_container_status("postgres", "postgres:16.1", restart_count=3,
                               last_state={"terminated": {"exitCode": 1, "reason": "Error", "finishedAt": ts(30)}})],
        node_name="node-2"))

    # api-server: can't connect to DB
    for i in range(3):
        pods.append(make_pod(f"api-server-8c7d6e5f-{'abc'[i]}x{i}1", ns,
            [container_spec("api-server", "myapp/api-server:v3.2.0", ports=[8080])],
            [make_container_status("api-server", "myapp/api-server:v3.2.0", restart_count=6 + i,
                                   ready=False,
                                   last_state={"terminated": {"exitCode": 1, "reason": "Error", "finishedAt": ts(5 + i)}})],
            node_name=f"node-{(i % 2) + 1}"))

    # frontend getting 502
    for i in range(2):
        pods.append(make_pod(f"frontend-9d8e7f6g-{'de'[i]}y{i}2", ns,
            [container_spec("frontend", "myapp/frontend:v2.1.0", ports=[3000])],
            [make_container_status("frontend", "myapp/frontend:v2.1.0", restart_count=2 + i,
                                   last_state={"terminated": {"exitCode": 1, "reason": "Error", "finishedAt": ts(10 + i)}})],
            node_name=f"node-{(i % 2) + 1}"))

    # redis cache - still healthy
    pods.append(make_pod("redis-cache-0", ns,
        [container_spec("redis", "redis:7.2.3", ports=[6379])],
        [make_container_status("redis", "redis:7.2.3")],
        node_name="node-1"))

    # queue-worker: CrashLoopBackOff (depends on postgres)
    pods.append(make_pod("queue-worker-2f3g4h5i-gz31", ns,
        [container_spec("queue-worker", "myapp/queue-worker:v1.5.0")],
        [make_container_status("queue-worker", "myapp/queue-worker:v1.5.0", ready=False, restart_count=15,
                               state="waiting", reason="CrashLoopBackOff",
                               message="back-off 5m0s restarting failed container=queue-worker",
                               last_state={"terminated": {"exitCode": 1, "reason": "Error", "finishedAt": ts(2)}})],
        node_name="node-2"))

    # celery-beat: CrashLoopBackOff (depends on postgres)
    pods.append(make_pod("celery-beat-4j5k6l7m-hv42", ns,
        [container_spec("celery-beat", "myapp/celery:v1.5.0")],
        [make_container_status("celery-beat", "myapp/celery:v1.5.0", ready=False, restart_count=10,
                               state="waiting", reason="CrashLoopBackOff",
                               message="back-off 5m0s restarting failed container=celery-beat",
                               last_state={"terminated": {"exitCode": 1, "reason": "Error", "finishedAt": ts(3)}})],
        node_name="node-1"))

    # ingress-controller - running but reporting backend errors
    pods.append(make_pod("ingress-nginx-controller-6n7o8p-iw53", ns,
        [container_spec("controller", "k8s.gcr.io/ingress-nginx/controller:v1.9.4", ports=[80, 443])],
        [make_container_status("controller", "k8s.gcr.io/ingress-nginx/controller:v1.9.4")],
        node_name="node-1"))

    # Monitoring pod - healthy
    pods.append(make_pod("prometheus-server-0", "monitoring",
        [container_spec("prometheus", "prom/prometheus:v2.48.1", ports=[9090])],
        [make_container_status("prometheus", "prom/prometheus:v2.48.1")],
        node_name="node-2"))

    # Pods on node-3 (NotReady) - unknown state
    pods.append(make_pod("grafana-7q8r9s0t-jx64", "monitoring",
        [container_spec("grafana", "grafana/grafana:10.2.3", ports=[3000])],
        [make_container_status("grafana", "grafana/grafana:10.2.3", ready=False,
                               state="waiting", reason="ContainerStatusUnknown",
                               message="The node was not ready")],
        phase="Unknown", node_name="node-3"))

    pods.append(make_pod("alertmanager-0", "monitoring",
        [container_spec("alertmanager", "prom/alertmanager:v0.26.0", ports=[9093])],
        [make_container_status("alertmanager", "prom/alertmanager:v0.26.0", ready=False,
                               state="waiting", reason="ContainerStatusUnknown",
                               message="The node was not ready")],
        phase="Unknown", node_name="node-3"))

    default_pods = [p for p in pods if p["metadata"]["namespace"] == ns]
    monitoring_pods = [p for p in pods if p["metadata"]["namespace"] == "monitoring"]
    write_json(bd, f"cluster-resources/pods/{ns}.json", pod_list(default_pods))
    write_json(bd, "cluster-resources/pods/monitoring.json", pod_list(monitoring_pods))

    deps = [
        make_deployment("api-server", ns, 3, 0, "myapp/api-server:v3.2.0"),
        make_deployment("frontend", ns, 2, 2, "myapp/frontend:v2.1.0"),
        make_deployment("queue-worker", ns, 1, 0, "myapp/queue-worker:v1.5.0"),
        make_deployment("celery-beat", ns, 1, 0, "myapp/celery:v1.5.0"),
        make_deployment("ingress-nginx-controller", ns, 1, 1, "k8s.gcr.io/ingress-nginx/controller:v1.9.4"),
    ]
    write_json(bd, f"cluster-resources/deployments/{ns}.json", deployment_list(deps))

    svcs = [
        make_service("postgres-primary", ns, 5432, 5432),
        make_service("postgres-replica", ns, 5432, 5432),
        make_service("api-server", ns, 8080, 8080),
        make_service("frontend", ns, 3000, 3000),
        make_service("redis-cache", ns, 6379, 6379),
        make_service("ingress-nginx-controller", ns, 80, 80, svc_type="LoadBalancer"),
    ]
    write_json(bd, f"cluster-resources/services/{ns}.json", service_list(svcs))

    events = [
        # Postgres OOM
        make_event("ev1", ns, "postgres-primary-0", "Pod", "OOMKilling",
                    "Memory cgroup out of memory: Killed process 2891 (postgres) total-vm:3145728kB, anon-rss:2097152kB",
                    event_type="Warning", count=1, first_offset=45, last_offset=45),
        # API server failures
        make_event("ev2", ns, "api-server-8c7d6e5f-ax01", "Pod", "Unhealthy",
                    "Readiness probe failed: HTTP probe failed with statuscode: 503",
                    event_type="Warning", count=40, first_offset=44, last_offset=1),
        make_event("ev3", ns, "api-server-8c7d6e5f-bx11", "Pod", "BackOff",
                    "Back-off restarting failed container api-server",
                    event_type="Warning", count=6, first_offset=40, last_offset=2),
        # Frontend 502s
        make_event("ev4", ns, "frontend-9d8e7f6g-dy02", "Pod", "Unhealthy",
                    "Readiness probe failed: Get \"http://10.244.1.15:3000/healthz\": context deadline exceeded",
                    event_type="Warning", count=15, first_offset=38, last_offset=3),
        # Queue worker
        make_event("ev5", ns, "queue-worker-2f3g4h5i-gz31", "Pod", "BackOff",
                    "Back-off restarting failed container queue-worker",
                    event_type="Warning", count=15, first_offset=43, last_offset=1),
        # Celery beat
        make_event("ev6", ns, "celery-beat-4j5k6l7m-hv42", "Pod", "BackOff",
                    "Back-off restarting failed container celery-beat",
                    event_type="Warning", count=10, first_offset=42, last_offset=2),
        # Node-3 not ready
        make_event("ev7", ns, "node-3", "Node", "NodeNotReady",
                    "Node node-3 status is now: NodeNotReady",
                    event_type="Warning", count=1, first_offset=30, last_offset=30),
        make_event("ev8", ns, "node-3", "Node", "NodeHasInsufficientMemory",
                    "Node node-3 status is now: NodeHasInsufficientMemory",
                    event_type="Warning", count=1, first_offset=32, last_offset=32),
        # Ingress backend errors
        make_event("ev9", ns, "ingress-nginx-controller-6n7o8p-iw53", "Pod", "Warning",
                    "upstream server returned 502: api-server.default.svc.cluster.local:8080",
                    event_type="Warning", count=200, first_offset=43, last_offset=1),
    ]
    write_json(bd, f"cluster-resources/events/{ns}.json", event_list(events))

    # LOGS - showing cascade clearly

    # postgres primary
    pg_logs = []
    for m in range(120, 46, -3):
        pg_logs.append((m, "LOG", "[postgres] checkpoint starting: time"))
        pg_logs.append((m - 1, "LOG", "[postgres] checkpoint complete: wrote 847 buffers (5.2%)"))
    pg_logs.append((46, "LOG", "[postgres] server process (PID 291) was terminated by signal 9: Killed"))
    pg_logs.append((46, "LOG", "[postgres] terminating any other active server processes"))
    pg_logs.append((45, "LOG", "[postgres] all server processes terminated; reinitializing"))
    pg_logs.append((45, "FATAL", "[postgres] the database system is in recovery mode"))
    pg_logs.append((45, "FATAL", "[postgres] could not open file \"pg_wal/000000010000000000000047\": No such file or directory"))
    pg_logs.append((45, "PANIC", "[postgres] could not redo log record at 0/47000060"))
    write_text(bd, "postgres-primary-0/postgres.log", log_lines(pg_logs))

    # api-server logs — showing DB connection failures
    for idx, suffix in enumerate(["ax01", "bx11", "cx21"]):
        api_logs = []
        for m in range(44, 0, -1):
            api_logs.append((m, "ERROR", f"[api-server] Failed to connect to postgres-primary:5432 - connection refused"))
            api_logs.append((m, "ERROR", f"[api-server] sqlx::Error: pool timed out waiting for an open connection"))
            if m % 3 == 0:
                api_logs.append((m, "WARN", f"[api-server] Health check failing - database unreachable"))
                api_logs.append((m, "ERROR", f"[api-server] Returning HTTP 503 for all requests - database dependency unavailable"))
        api_logs.insert(0, (45, "INFO", "[api-server] Starting api-server v3.2.0 on :8080"))
        api_logs.insert(1, (45, "INFO", "[api-server] Attempting database connection to postgres-primary:5432..."))
        write_text(bd, f"api-server-8c7d6e5f-{suffix}/api-server.log", log_lines(api_logs))

    # frontend logs — 502 from api-server
    for idx, suffix in enumerate(["dy02", "ey12"]):
        fe_logs = []
        for m in range(42, 0, -1):
            fe_logs.append((m, "ERROR", f"[frontend] GET /api/v1/users - upstream returned 502 Bad Gateway"))
            fe_logs.append((m, "ERROR", f"[frontend] POST /api/v1/orders - upstream returned 502 Bad Gateway"))
            if m % 5 == 0:
                fe_logs.append((m, "WARN", f"[frontend] API server at api-server:8080 returning errors, 0 of last 100 requests succeeded"))
        write_text(bd, f"frontend-9d8e7f6g-{suffix}/frontend.log", log_lines(fe_logs))

    # redis cache — healthy
    redis_logs = [(m, "INFO", "[redis] Accepted connection from 10.244.0.0/16") for m in range(60, 0, -5)]
    write_text(bd, "redis-cache-0/redis.log", log_lines(redis_logs))

    # queue-worker logs
    qw_logs = []
    for cycle in range(15, 0, -1):
        o = cycle * 3
        qw_logs.append((o, "INFO", "[queue-worker] Connecting to postgres-primary:5432..."))
        qw_logs.append((o - 1, "ERROR", "[queue-worker] psycopg2.OperationalError: could not connect to server: Connection refused"))
        qw_logs.append((o - 1, "ERROR", "[queue-worker] \tIs the server running on host \"postgres-primary\" (10.96.42.17) and accepting TCP/IP connections on port 5432?"))
        qw_logs.append((o - 2, "FATAL", "[queue-worker] Cannot initialize worker without database connection. Exiting."))
    write_text(bd, "queue-worker-2f3g4h5i-gz31/queue-worker.log", log_lines(qw_logs))

    # celery-beat logs
    cb_logs = []
    for cycle in range(10, 0, -1):
        o = cycle * 4
        cb_logs.append((o, "INFO", "[celery-beat] Starting celery beat scheduler v1.5.0"))
        cb_logs.append((o - 1, "INFO", "[celery-beat] Connecting to database for schedule storage..."))
        cb_logs.append((o - 2, "ERROR", "[celery-beat] django.db.utils.OperationalError: could not connect to server: Connection refused"))
        cb_logs.append((o - 2, "ERROR", "[celery-beat] \tIs the server running on host \"postgres-primary\" and accepting connections on port 5432?"))
        cb_logs.append((o - 3, "FATAL", "[celery-beat] Scheduler cannot start without database backend"))
    write_text(bd, "celery-beat-4j5k6l7m-hv42/celery-beat.log", log_lines(cb_logs))

    # ingress logs
    ing_logs = []
    for m in range(43, 0, -1):
        ing_logs.append((m, "WARN", '[controller] upstream "default-api-server-8080" returned 502 while reading response header from upstream, client: 203.0.113.42, server: app.example.com, request: "GET /api/v1/users HTTP/2.0"'))
        ing_logs.append((m, "ERROR", "[controller] no healthy upstream servers for backend default-api-server-8080"))
    write_text(bd, "ingress-nginx-controller-6n7o8p-iw53/controller.log", log_lines(ing_logs))

    # prometheus - healthy
    write_text(bd, "prometheus-server-0/prometheus.log",
               log_lines([(m, "INFO", "[prometheus] Scrape completed, 42 targets scraped") for m in range(60, 0, -5)]))

    write_json(bd, "analysis.json", analysis_json([
        analyzer_result("Node Status", "node-3 is NotReady - kubelet has stopped responding", "fail"),
        analyzer_result("Root Cause: Database", "postgres-primary-0 was OOMKilled - this is the likely root cause of the cascading failure", "fail"),
        analyzer_result("API Server", "All 3 api-server replicas are failing - cannot connect to postgres-primary:5432", "fail"),
        analyzer_result("Frontend", "frontend pods returning 502 errors - upstream api-server is unavailable", "fail"),
        analyzer_result("Queue Workers", "queue-worker and celery-beat in CrashLoopBackOff - cannot connect to database", "fail"),
        analyzer_result("Redis Cache", "Redis cache is healthy and serving requests", "pass"),
        analyzer_result("Ingress", "ingress-nginx-controller reporting no healthy upstream backends", "warn"),
        analyzer_result("Monitoring", "grafana and alertmanager on node-3 are unreachable (node NotReady)", "warn"),
        analyzer_result("Cascade Summary", "Postgres OOM → API server 503 → Frontend 502 → Full service outage", "fail"),
    ]))

    return tar_bundle(bd, "cascading-failure.tar.gz")


# ===================================================================
# BUNDLE 6: Security & Certificate Issues (~45% health)
# ===================================================================

def generate_security_certs():
    """Bundle 6: Security & certificate issues (~45% health)."""
    bd = os.path.join(TMP_BASE, "security-certs")
    ns = "production"

    nodes = [make_node("sec-node-1"), make_node("sec-node-2")]
    write_json(bd, "cluster-resources/nodes.json", node_list(nodes))
    write_json(bd, "cluster-resources/namespaces.json",
               namespace_list(["default", "kube-system", "production", "cert-manager"]))
    write_json(bd, "cluster-info/cluster_version.json", cluster_version())

    pods = []
    # cert-manager pod in CrashLoopBackOff
    pods.append(make_pod(
        "cert-manager-controller-7b4d8f-xk2m", "cert-manager",
        [container_spec("cert-manager", "quay.io/jetstack/cert-manager-controller:v1.13.3")],
        [make_container_status("cert-manager", "quay.io/jetstack/cert-manager-controller:v1.13.3",
                               ready=False, restart_count=15, state="waiting",
                               reason="CrashLoopBackOff", message="back-off 5m0s restarting failed container")],
        phase="Running", node_name="sec-node-1",
    ))
    # App pods with expired TLS certs causing failures
    for i in range(3):
        pods.append(make_pod(
            f"web-app-{uid()[:8]}", ns,
            [container_spec("web-app", "registry.internal.io/myorg/web-app:v3.2.1", ports=[443])],
            [make_container_status("web-app", "registry.internal.io/myorg/web-app:v3.2.1")],
            node_name=f"sec-node-{(i % 2) + 1}",
        ))
    # Pod with image pull error from private registry
    pods.append(make_pod(
        f"private-svc-{uid()[:8]}", ns,
        [container_spec("private-svc", "registry.internal.io/myorg/private-svc:v1.0.0")],
        [make_container_status("private-svc", "registry.internal.io/myorg/private-svc:v1.0.0",
                               ready=False, state="waiting",
                               reason="ImagePullBackOff", message="Back-off pulling image registry.internal.io/myorg/private-svc:v1.0.0")],
        phase="Pending", node_name="sec-node-2",
    ))
    # Pod that can't schedule due to quota
    pods.append(make_pod(
        f"batch-job-{uid()[:8]}", ns,
        [container_spec("batch-job", "myorg/batch:v2.0", cpu_req="2", mem_req="4Gi")],
        [make_container_status("batch-job", "myorg/batch:v2.0",
                               ready=False, state="waiting",
                               reason="CreateContainerError", message="forbidden: exceeded quota")],
        phase="Pending", node_name="sec-node-1",
    ))

    # kube-system pods (healthy)
    pods.append(make_pod(
        "coredns-5dd5756b68-r9x2m", "kube-system",
        [container_spec("coredns", "registry.k8s.io/coredns/coredns:v1.11.1", ports=[53])],
        [make_container_status("coredns", "registry.k8s.io/coredns/coredns:v1.11.1")],
        node_name="sec-node-1",
    ))
    write_json(bd, "cluster-resources/pods.json", pod_list(pods))

    # Deployments - some using deprecated API versions
    deps = [
        make_deployment("web-app", ns, 3, 3, "registry.internal.io/myorg/web-app:v3.2.1"),
        make_deployment("private-svc", ns, 1, 0, "registry.internal.io/myorg/private-svc:v1.0.0"),
    ]
    # Add a deployment with deprecated apiVersion
    legacy_dep = make_deployment("legacy-api", ns, 2, 2, "myorg/legacy-api:v1.5")
    legacy_dep["apiVersion"] = "extensions/v1beta1"
    deps.append(legacy_dep)
    write_json(bd, "cluster-resources/deployments.json", deployment_list(deps))

    svcs = [
        make_service("web-app", ns, 443, 443, "ClusterIP"),
        make_service("private-svc", ns, 8080, 8080, "ClusterIP"),
    ]
    write_json(bd, "cluster-resources/services.json", service_list(svcs))

    # Events - quota exceeded, image pull failures
    events = [
        make_event("quota-exceeded", ns, "batch-job", "Pod", "FailedCreate",
                   "Error creating: pods \"batch-job\" is forbidden: exceeded quota: compute-quota, "
                   "requested: cpu=2, used: cpu=7, limited: cpu=8",
                   event_type="Warning", count=5, first_offset=30, last_offset=2),
        make_event("image-pull-fail", ns, "private-svc", "Pod", "Failed",
                   "Failed to pull image \"registry.internal.io/myorg/private-svc:v1.0.0\": "
                   "unauthorized: authentication required",
                   event_type="Warning", count=8, first_offset=60, last_offset=3),
        make_event("cert-expired", "cert-manager", "cert-manager-controller", "Pod", "BackOff",
                   "Back-off restarting failed container",
                   event_type="Warning", count=15, first_offset=120, last_offset=1),
        make_event("deprecated-api", ns, "legacy-api", "Deployment", "Warning",
                   "extensions/v1beta1 Deployment is deprecated in v1.16+, unavailable in v1.22+; use apps/v1 Deployment",
                   event_type="Warning", count=1, first_offset=200, last_offset=200),
    ]
    write_json(bd, "cluster-resources/events.json", event_list(events))

    # Logs - certificate expiration warnings
    cert_logs = []
    for m in range(60, 0, -3):
        cert_logs.append((m, "ERROR", "[cert-manager] certificate \"web-app-tls\" has expired: NotAfter: 2026-03-10T00:00:00Z"))
        cert_logs.append((m, "WARN", "[cert-manager] certificate expiration detected for secret production/web-app-tls"))
    cert_logs.append((5, "ERROR", "[cert-manager] failed to renew certificate: ACME challenge failed"))
    write_text(bd, "cert-manager-controller-7b4d8f-xk2m/cert-manager.log", log_lines(cert_logs))

    # Web app logs with TLS errors
    web_logs = []
    for m in range(45, 0, -2):
        web_logs.append((m, "ERROR", "[web-app] TLS handshake error: certificate has expired"))
        web_logs.append((m, "WARN", "[web-app] x509: certificate has expired or is not yet valid"))
    write_text(bd, f"web-app-logs/web-app.log", log_lines(web_logs))

    # Quota warning logs
    quota_logs = [
        (10, "ERROR", "[kube-scheduler] forbidden: exceeded quota: compute-quota in namespace production"),
        (8, "WARN", "[kube-scheduler] pod batch-job cannot be scheduled: exceeded quota"),
    ]
    write_text(bd, "kube-scheduler/scheduler.log", log_lines(quota_logs))

    write_json(bd, "analysis.json", analysis_json([
        analyzer_result("Certificate Expiry", "TLS certificate for web-app-tls has expired", "fail"),
        analyzer_result("Image Pull", "Cannot pull from private registry - authentication failure", "fail"),
        analyzer_result("Resource Quota", "Namespace production has exceeded CPU quota", "warn"),
        analyzer_result("Deprecated APIs", "legacy-api deployment uses extensions/v1beta1", "warn"),
        analyzer_result("CoreDNS", "DNS resolution is functioning normally", "pass"),
    ]))

    return tar_bundle(bd, "security-certs.tar.gz")


# ===================================================================
# BUNDLE 7: Storage & PVC Issues (~40% health)
# ===================================================================

def generate_storage_pvcs():
    """Bundle 7: Storage & PVC issues (~40% health)."""
    bd = os.path.join(TMP_BASE, "storage-pvcs")
    ns = "data-platform"

    nodes = [
        make_node("storage-node-1", conditions_extra=[{
            "type": "DiskPressure",
            "status": "True",
            "lastHeartbeatTime": ts(0),
            "lastTransitionTime": ts(30),
            "reason": "KubeletHasDiskPressure",
            "message": "kubelet has disk pressure - available: 1.2Gi, threshold: 2Gi",
        }]),
        make_node("storage-node-2"),
        make_node("storage-node-3"),
    ]
    write_json(bd, "cluster-resources/nodes.json", node_list(nodes))
    write_json(bd, "cluster-resources/namespaces.json",
               namespace_list(["default", "kube-system", "data-platform"]))
    write_json(bd, "cluster-info/cluster_version.json", cluster_version())

    # PVs - some in Pending/Lost state
    pvs = [
        {
            "metadata": {"name": "pv-data-vol-01", "uid": uid(), "creationTimestamp": ts(5000)},
            "spec": {"capacity": {"storage": "100Gi"}, "accessModes": ["ReadWriteOnce"],
                     "storageClassName": "gp3", "persistentVolumeReclaimPolicy": "Retain"},
            "status": {"phase": "Bound"},
        },
        {
            "metadata": {"name": "pv-data-vol-02", "uid": uid(), "creationTimestamp": ts(3000)},
            "spec": {"capacity": {"storage": "50Gi"}, "accessModes": ["ReadWriteOnce"],
                     "storageClassName": "gp3", "persistentVolumeReclaimPolicy": "Retain"},
            "status": {"phase": "Pending"},
        },
        {
            "metadata": {"name": "pv-backup-vol", "uid": uid(), "creationTimestamp": ts(8000)},
            "spec": {"capacity": {"storage": "200Gi"}, "accessModes": ["ReadWriteOnce"],
                     "storageClassName": "gp3", "persistentVolumeReclaimPolicy": "Retain"},
            "status": {"phase": "Lost"},
        },
    ]
    write_json(bd, "cluster-resources/pvs.json", {"kind": "PersistentVolumeList", "apiVersion": "v1", "items": pvs})

    pods = []
    # Database pod bound to working PV
    pods.append(make_pod(
        "postgres-primary-0", ns,
        [container_spec("postgres", "postgres:16.1", mem_req="512Mi", mem_lim="2Gi", ports=[5432])],
        [make_container_status("postgres", "postgres:16.1")],
        node_name="storage-node-2",
    ))
    # Pod waiting on unbound PVC
    pods.append(make_pod(
        "elasticsearch-data-0", ns,
        [container_spec("elasticsearch", "elasticsearch:8.11.3", mem_req="1Gi", mem_lim="4Gi", ports=[9200])],
        [make_container_status("elasticsearch", "elasticsearch:8.11.3",
                               ready=False, state="waiting",
                               reason="ContainerCreating", message="waiting for PVC pvc-es-data-0 to be bound")],
        phase="Pending", node_name="storage-node-3",
    ))
    # Evicted pods from disk pressure
    for i in range(3):
        pods.append(make_pod(
            f"log-collector-{uid()[:8]}", ns,
            [container_spec("fluent-bit", "fluent/fluent-bit:2.2.0")],
            [make_container_status("fluent-bit", "fluent/fluent-bit:2.2.0", ready=False,
                                   state="terminated", reason="Evicted")],
            phase="Failed", node_name="storage-node-1",
            reason="Evicted", message="The node was low on resource: ephemeral-storage.",
        ))
    # Healthy app pods
    for i in range(2):
        pods.append(make_pod(
            f"api-gateway-{uid()[:8]}", ns,
            [container_spec("api-gateway", "myorg/api-gateway:v4.1.0", ports=[8080])],
            [make_container_status("api-gateway", "myorg/api-gateway:v4.1.0")],
            node_name=f"storage-node-{(i % 2) + 2}",
        ))
    # kube-system pods
    pods.append(make_pod(
        "coredns-5dd5756b68-st4m2", "kube-system",
        [container_spec("coredns", "registry.k8s.io/coredns/coredns:v1.11.1", ports=[53])],
        [make_container_status("coredns", "registry.k8s.io/coredns/coredns:v1.11.1")],
        node_name="storage-node-2",
    ))
    write_json(bd, "cluster-resources/pods.json", pod_list(pods))

    deps = [
        make_deployment("api-gateway", ns, 2, 2, "myorg/api-gateway:v4.1.0"),
        make_deployment("log-collector", ns, 3, 0, "fluent/fluent-bit:2.2.0"),
    ]
    write_json(bd, "cluster-resources/deployments.json", deployment_list(deps))

    svcs = [
        make_service("postgres-primary", ns, 5432, 5432),
        make_service("elasticsearch", ns, 9200, 9200),
        make_service("api-gateway", ns, 8080, 8080),
    ]
    write_json(bd, "cluster-resources/services.json", service_list(svcs))

    events = [
        make_event("pvc-pending", ns, "elasticsearch-data-0", "Pod", "FailedMount",
                   "Unable to attach or mount volumes: timed out waiting for the condition; "
                   "PVC pvc-es-data-0 is not bound",
                   event_type="Warning", count=12, first_offset=90, last_offset=2),
        make_event("pv-lost", ns, "pv-backup-vol", "PersistentVolume", "VolumeFailure",
                   "PV pv-backup-vol underlying volume has been deleted or is unreachable",
                   event_type="Warning", count=3, first_offset=120, last_offset=10),
        make_event("eviction", ns, "log-collector", "Pod", "Evicted",
                   "The node was low on resource: ephemeral-storage. Threshold quantity: 2Gi, available: 1.2Gi",
                   event_type="Warning", count=3, first_offset=45, last_offset=5),
        make_event("disk-pressure", "kube-system", "storage-node-1", "Node", "NodeHasDiskPressure",
                   "Node storage-node-1 status is now: NodeHasDiskPressure",
                   event_type="Warning", count=5, first_offset=60, last_offset=1),
        make_event("failed-attach", ns, "elasticsearch-data-0", "Pod", "FailedAttachVolume",
                   "AttachVolume.Attach failed for volume \"pv-data-vol-02\": volume is not available",
                   event_type="Warning", count=6, first_offset=80, last_offset=3),
    ]
    write_json(bd, "cluster-resources/events.json", event_list(events))

    # Logs
    kubelet_logs = []
    for m in range(60, 0, -2):
        kubelet_logs.append((m, "WARN", "[kubelet] evicting pod due to disk pressure: data-platform/log-collector"))
        kubelet_logs.append((m, "ERROR", "[kubelet] node storage-node-1: disk usage 94%, threshold 90%"))
    write_text(bd, "kubelet-storage-node-1/kubelet.log", log_lines(kubelet_logs))

    es_logs = []
    for m in range(50, 0, -3):
        es_logs.append((m, "ERROR", "[elasticsearch] failed to mount volume: PVC pvc-es-data-0 not bound"))
        es_logs.append((m, "WARN", "[elasticsearch] waiting for storage volume to become available"))
    write_text(bd, "elasticsearch-data-0/elasticsearch.log", log_lines(es_logs))

    write_json(bd, "analysis.json", analysis_json([
        analyzer_result("Node Disk Pressure", "storage-node-1 has DiskPressure condition", "fail"),
        analyzer_result("PV Status", "pv-backup-vol is in Lost state; pv-data-vol-02 is Pending", "fail"),
        analyzer_result("Pod Evictions", "3 pods evicted from storage-node-1 due to disk pressure", "fail"),
        analyzer_result("PVC Binding", "elasticsearch-data-0 waiting on unbound PVC", "warn"),
        analyzer_result("API Gateway", "api-gateway pods are healthy", "pass"),
        analyzer_result("Database", "postgres-primary is running normally", "pass"),
    ]))

    return tar_bundle(bd, "storage-pvcs.tar.gz")


# ===================================================================
# BUNDLE 8: DNS & Connectivity Issues (~50% health)
# ===================================================================

def generate_dns_connectivity():
    """Bundle 8: DNS & connectivity issues (~50% health)."""
    bd = os.path.join(TMP_BASE, "dns-connectivity")
    ns = "microservices"

    nodes = [
        make_node("net-node-1"),
        make_node("net-node-2", conditions_extra=[{
            "type": "PIDPressure",
            "status": "True",
            "lastHeartbeatTime": ts(0),
            "lastTransitionTime": ts(15),
            "reason": "KubeletHasInsufficientPID",
            "message": "kubelet has insufficient PID available: 127 out of 4096",
        }]),
        make_node("net-node-3"),
    ]
    write_json(bd, "cluster-resources/nodes.json", node_list(nodes))
    write_json(bd, "cluster-resources/namespaces.json",
               namespace_list(["default", "kube-system", "microservices", "monitoring"]))
    write_json(bd, "cluster-info/cluster_version.json", cluster_version())

    pods = []
    # CoreDNS pod with issues
    pods.append(make_pod(
        "coredns-5dd5756b68-dns01", "kube-system",
        [container_spec("coredns", "registry.k8s.io/coredns/coredns:v1.11.1", ports=[53])],
        [make_container_status("coredns", "registry.k8s.io/coredns/coredns:v1.11.1",
                               restart_count=8,
                               last_state={"terminated": {"exitCode": 2, "reason": "Error", "finishedAt": ts(10)}})],
        node_name="net-node-1",
    ))
    # Second CoreDNS pod OK
    pods.append(make_pod(
        "coredns-5dd5756b68-dns02", "kube-system",
        [container_spec("coredns", "registry.k8s.io/coredns/coredns:v1.11.1", ports=[53])],
        [make_container_status("coredns", "registry.k8s.io/coredns/coredns:v1.11.1")],
        node_name="net-node-3",
    ))
    # App pods experiencing DNS failures and connection timeouts
    for i in range(3):
        pods.append(make_pod(
            f"order-svc-{uid()[:8]}", ns,
            [container_spec("order-svc", "myorg/order-svc:v2.3.0", ports=[8080])],
            [make_container_status("order-svc", "myorg/order-svc:v2.3.0",
                                   restart_count=3,
                                   last_state={"terminated": {"exitCode": 1, "reason": "Error", "finishedAt": ts(15)}})],
            node_name=f"net-node-{(i % 3) + 1}",
        ))
    for i in range(2):
        pods.append(make_pod(
            f"payment-svc-{uid()[:8]}", ns,
            [container_spec("payment-svc", "myorg/payment-svc:v1.8.0", ports=[8443])],
            [make_container_status("payment-svc", "myorg/payment-svc:v1.8.0")],
            node_name=f"net-node-{(i % 2) + 1}",
        ))
    # Pod stuck with FailedMount
    pods.append(make_pod(
        f"config-svc-{uid()[:8]}", ns,
        [container_spec("config-svc", "myorg/config-svc:v3.0.0", ports=[8080])],
        [make_container_status("config-svc", "myorg/config-svc:v3.0.0",
                               ready=False, state="waiting",
                               reason="ContainerCreating", message="waiting for volume mount")],
        phase="Pending", node_name="net-node-2",
    ))
    # Healthy monitoring pods
    pods.append(make_pod(
        "prometheus-server-0", "monitoring",
        [container_spec("prometheus", "prom/prometheus:v2.48.1", ports=[9090])],
        [make_container_status("prometheus", "prom/prometheus:v2.48.1")],
        node_name="net-node-3",
    ))
    write_json(bd, "cluster-resources/pods.json", pod_list(pods))

    deps = [
        make_deployment("order-svc", ns, 3, 3, "myorg/order-svc:v2.3.0"),
        make_deployment("payment-svc", ns, 2, 2, "myorg/payment-svc:v1.8.0"),
        make_deployment("config-svc", ns, 1, 0, "myorg/config-svc:v3.0.0"),
    ]
    write_json(bd, "cluster-resources/deployments.json", deployment_list(deps))

    svcs = [
        make_service("order-svc", ns, 8080, 8080),
        make_service("payment-svc", ns, 8443, 8443),
        make_service("config-svc", ns, 8080, 8080),
    ]
    write_json(bd, "cluster-resources/services.json", service_list(svcs))

    events = [
        make_event("dns-fail", "kube-system", "coredns-5dd5756b68-dns01", "Pod", "Unhealthy",
                   "Readiness probe failed: DNS query timeout for kubernetes.default.svc.cluster.local",
                   event_type="Warning", count=10, first_offset=60, last_offset=2),
        make_event("conn-refused", ns, "order-svc", "Pod", "BackOff",
                   "Back-off restarting failed container: connection refused to payment-svc:8443",
                   event_type="Warning", count=5, first_offset=40, last_offset=5),
        make_event("failed-mount", ns, "config-svc", "Pod", "FailedMount",
                   "Unable to attach or mount volumes: timed out waiting for the condition",
                   event_type="Warning", count=8, first_offset=90, last_offset=3),
        make_event("failed-attach", ns, "config-svc", "Pod", "FailedAttachVolume",
                   "AttachVolume.Attach failed for volume \"config-vol\": rpc error: code = Internal",
                   event_type="Warning", count=4, first_offset=85, last_offset=5),
        make_event("pid-pressure", "kube-system", "net-node-2", "Node", "NodeHasInsufficientPID",
                   "Node net-node-2 status is now: NodeHasInsufficientPID",
                   event_type="Warning", count=3, first_offset=30, last_offset=1),
    ]
    write_json(bd, "cluster-resources/events.json", event_list(events))

    # CoreDNS logs with DNS failures
    dns_logs = []
    for m in range(60, 0, -2):
        dns_logs.append((m, "ERROR", "[coredns] plugin/errors: 2 order-svc.microservices.svc.cluster.local. A: dns resolution failed: read udp 10.244.0.2:53: i/o timeout"))
        dns_logs.append((m, "WARN", "[coredns] plugin/cache: name resolution timeout for payment-svc.microservices.svc.cluster.local"))
    dns_logs.append((1, "ERROR", "[coredns] dns resolve error: SERVFAIL for config-svc.microservices.svc.cluster.local"))
    write_text(bd, "coredns-5dd5756b68-dns01/coredns.log", log_lines(dns_logs))

    # Order service logs with connection errors
    order_logs = []
    for m in range(45, 0, -2):
        order_logs.append((m, "ERROR", "[order-svc] dial tcp 10.96.142.88:8443: connection refused"))
        order_logs.append((m, "ERROR", "[order-svc] failed to connect to payment-svc: connection timed out"))
        order_logs.append((m, "WARN", "[order-svc] dns resolution failed for payment-svc.microservices.svc.cluster.local"))
    write_text(bd, "order-svc-logs/order-svc.log", log_lines(order_logs))

    # Payment service logs
    pay_logs = []
    for m in range(30, 0, -3):
        pay_logs.append((m, "WARN", "[payment-svc] dns resolve error for order-svc.microservices.svc.cluster.local: no such host"))
        pay_logs.append((m, "ERROR", "[payment-svc] connection refused: dial tcp 10.96.55.120:8080: connect: connection refused"))
    write_text(bd, "payment-svc-logs/payment-svc.log", log_lines(pay_logs))

    write_json(bd, "analysis.json", analysis_json([
        analyzer_result("DNS Resolution", "CoreDNS pod dns01 has high restart count and DNS query timeouts", "fail"),
        analyzer_result("Service Connectivity", "order-svc cannot reach payment-svc - connection refused/timeout", "fail"),
        analyzer_result("Node PID Pressure", "net-node-2 has PIDPressure condition", "fail"),
        analyzer_result("Volume Mount", "config-svc pending on failed volume mount", "warn"),
        analyzer_result("Payment Service", "payment-svc pods are running but experiencing DNS issues", "warn"),
        analyzer_result("Monitoring", "Prometheus is healthy and scraping targets", "pass"),
    ]))

    return tar_bundle(bd, "dns-connectivity.tar.gz")


# ===================================================================
# Main
# ===================================================================

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("Generating test support bundles...\n")

    bundles = [
        ("Bundle 1: healthy-cluster", generate_healthy_cluster),
        ("Bundle 2: network-issues", generate_network_issues),
        ("Bundle 3: resource-exhaustion", generate_resource_exhaustion),
        ("Bundle 4: config-errors", generate_config_errors),
        ("Bundle 5: cascading-failure", generate_cascading_failure),
        ("Bundle 6: security-certs", generate_security_certs),
        ("Bundle 7: storage-pvcs", generate_storage_pvcs),
        ("Bundle 8: dns-connectivity", generate_dns_connectivity),
    ]

    for label, gen_fn in bundles:
        path = gen_fn()
        size_kb = os.path.getsize(path) / 1024
        print(f"  {label:40s} → {path}  ({size_kb:.1f} KB)")

    print(f"\nAll bundles saved to: {OUTPUT_DIR}/")
    print(f"Temporary files in: {TMP_BASE}")

    # Clean up temp dir
    shutil.rmtree(TMP_BASE)
    print("Temporary files cleaned up.")


if __name__ == "__main__":
    main()
