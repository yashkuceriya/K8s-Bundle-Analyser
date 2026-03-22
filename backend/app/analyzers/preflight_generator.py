"""Generate Troubleshoot preflight check YAML from detected issues."""

from __future__ import annotations

from typing import Any

import yaml


class PreflightGenerator:
    """Generate Troubleshoot preflight check YAML specs from detected issues.

    Maps detected issue categories to Troubleshoot preflight analyzers so the
    same problems get caught before they happen again.
    """

    def __init__(self, issues: list, parsed_data: dict[str, Any]) -> None:
        self.issues = issues
        self.parsed_data = parsed_data

    def generate(self) -> str:
        """Return a complete YAML string for a Troubleshoot Preflight spec."""
        collectors = self._build_collectors()
        analyzers = self._build_analyzers()

        spec: dict[str, Any] = {
            "apiVersion": "troubleshoot.sh/v1beta2",
            "kind": "Preflight",
            "metadata": {
                "name": "auto-generated-preflights",
            },
            "spec": {
                "collectors": collectors,
                "analyzers": analyzers,
            },
        }

        return yaml.dump(spec, default_flow_style=False, sort_keys=False, allow_unicode=True)

    # ------------------------------------------------------------------
    # Collectors
    # ------------------------------------------------------------------

    def _build_collectors(self) -> list[dict[str, Any]]:
        collectors: list[dict[str, Any]] = [
            {"clusterInfo": {}},
            {"clusterResources": {}},
        ]
        return collectors

    # ------------------------------------------------------------------
    # Analyzers
    # ------------------------------------------------------------------

    def _build_analyzers(self) -> list[dict[str, Any]]:
        analyzers: list[dict[str, Any]] = []

        # Always include general cluster health checks
        analyzers.extend(self._general_cluster_health())

        # Deduplicate deployment status checks
        seen_deployments: set[tuple[str, str]] = set()
        seen_oom_pods: set[str] = set()
        has_node_pressure = False
        has_connection_error = False

        for issue in self.issues:
            category = getattr(issue, "category", "") or ""
            title = getattr(issue, "title", "") or ""
            namespace = getattr(issue, "namespace", None) or "default"
            resource = getattr(issue, "resource", None) or ""

            # Pod health issues: CrashLoopBackOff, ImagePullBackOff
            if category == "pod-health" and any(
                keyword in title
                for keyword in ("CrashLoopBackOff", "Image pull failure", "High restart count", "Pod pending")
            ):
                deployment_name = self._extract_deployment_name(resource)
                key = (namespace, deployment_name)
                if key not in seen_deployments:
                    seen_deployments.add(key)
                    analyzers.append(self._deployment_status_analyzer(deployment_name, namespace))

            # OOMKilled issues -> resource checks
            if "OOMKilled" in title:
                pod_name = self._extract_pod_name(resource)
                if pod_name not in seen_oom_pods:
                    seen_oom_pods.add(pod_name)
                    analyzers.append(self._oom_resource_analyzer(pod_name))

            # Node pressure conditions
            if category == "resource-usage" and any(keyword in title for keyword in ("Pressure", "Evicted")):
                if not has_node_pressure:
                    has_node_pressure = True
                    analyzers.append(self._node_pressure_analyzer())

            # Connection/networking errors
            if category == "networking":
                if not has_connection_error:
                    has_connection_error = True
                    analyzers.append(self._networking_version_analyzer())

        return analyzers

    # ------------------------------------------------------------------
    # General cluster health (always included)
    # ------------------------------------------------------------------

    def _general_cluster_health(self) -> list[dict[str, Any]]:
        return [
            {
                "clusterVersion": {
                    "outcomes": [
                        {
                            "fail": {
                                "when": "< 1.24.0",
                                "message": "Kubernetes version must be >= 1.24.0",
                            },
                        },
                        {
                            "pass": {
                                "message": "Cluster version is OK",
                            },
                        },
                    ],
                },
            },
            {
                "nodeResources": {
                    "checkName": "Minimum node count",
                    "outcomes": [
                        {
                            "fail": {
                                "when": "count() < 1",
                                "message": "At least 1 node is required",
                            },
                        },
                        {
                            "warn": {
                                "when": "count() < 3",
                                "message": "Recommended: at least 3 nodes for HA",
                            },
                        },
                        {
                            "pass": {
                                "message": "Sufficient nodes available",
                            },
                        },
                    ],
                },
            },
        ]

    # ------------------------------------------------------------------
    # Deployment status (pod health issues)
    # ------------------------------------------------------------------

    def _deployment_status_analyzer(self, deployment_name: str, namespace: str) -> dict[str, Any]:
        return {
            "deploymentStatus": {
                "name": deployment_name,
                "namespace": namespace,
                "outcomes": [
                    {
                        "fail": {
                            "when": "< 1",
                            "message": f"{deployment_name} has no available replicas",
                        },
                    },
                    {
                        "pass": {
                            "message": f"{deployment_name} is running",
                        },
                    },
                ],
            },
        }

    # ------------------------------------------------------------------
    # OOM resource analyzer
    # ------------------------------------------------------------------

    def _oom_resource_analyzer(self, pod_name: str) -> dict[str, Any]:
        return {
            "nodeResources": {
                "checkName": f"Sufficient memory for {pod_name}",
                "outcomes": [
                    {
                        "fail": {
                            "when": "min(memoryAllocatable) < 1Gi",
                            "message": "Nodes need at least 1Gi allocatable memory",
                        },
                    },
                    {
                        "pass": {
                            "message": "Memory resources are sufficient",
                        },
                    },
                ],
            },
        }

    # ------------------------------------------------------------------
    # Node pressure analyzer
    # ------------------------------------------------------------------

    def _node_pressure_analyzer(self) -> dict[str, Any]:
        return {
            "nodeResources": {
                "checkName": "No node memory pressure",
                "outcomes": [
                    {
                        "fail": {
                            "when": "count() == 0",
                            "message": "No nodes found in cluster",
                        },
                    },
                    {
                        "warn": {
                            "when": "min(memoryAllocatable) < 2Gi",
                            "message": "Node memory may be insufficient",
                        },
                    },
                    {
                        "pass": {
                            "message": "Node resources look healthy",
                        },
                    },
                ],
            },
        }

    # ------------------------------------------------------------------
    # Networking / cluster version analyzer
    # ------------------------------------------------------------------

    def _networking_version_analyzer(self) -> dict[str, Any]:
        return {
            "clusterVersion": {
                "outcomes": [
                    {
                        "fail": {
                            "when": "< 1.24.0",
                            "message": "Kubernetes version too old, may have networking issues",
                        },
                    },
                    {
                        "pass": {
                            "message": "Kubernetes version is supported",
                        },
                    },
                ],
            },
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_deployment_name(resource: str) -> str:
        """Extract a deployment-style name from a resource string like 'pod/my-app-abc123'."""
        name = resource
        if "/" in name:
            name = name.split("/", 1)[1]
        # Strip trailing pod hash (e.g. my-app-7f8b9c6d4-xk2jl -> my-app)
        parts = name.rsplit("-", 2)
        if len(parts) >= 3 and len(parts[-1]) >= 4 and len(parts[-2]) >= 4:
            return "-".join(parts[:-2])
        if len(parts) >= 2 and len(parts[-1]) >= 5:
            return "-".join(parts[:-1])
        return name

    @staticmethod
    def _extract_pod_name(resource: str) -> str:
        """Extract the pod name from a resource string like 'pod/my-app-abc123'."""
        if "/" in resource:
            return resource.split("/", 1)[1]
        return resource
