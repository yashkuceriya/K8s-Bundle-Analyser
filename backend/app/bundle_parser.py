from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

MAX_LOG_LINES_PER_FILE = 5000
MAX_HOST_FILE_BYTES = 10_000


class BundleParser:
    """Parses an extracted Troubleshoot support bundle directory."""

    def __init__(self, bundle_path: str):
        self.bundle_path = Path(bundle_path)
        # Handle nested top-level directory: the extracted tar.gz often has
        # a single top-level directory like support-bundle-2024-01-01T00:00:00/
        self._root = self._find_root()

    def _find_root(self) -> Path:
        """Find the actual root of the bundle, handling nested directories."""
        if not self.bundle_path.exists():
            return self.bundle_path

        # Check if the extracted path itself has the expected structure
        expected_dirs = {
            "cluster-info",
            "cluster-resources",
            "pod-logs",
            "host-collectors",
            "analysis.json",
            "version.yaml",
        }
        children = {p.name for p in self.bundle_path.iterdir()} if self.bundle_path.is_dir() else set()

        if children & expected_dirs:
            return self.bundle_path

        # Check one level deeper for a single subdirectory that contains bundle content
        subdirs = [p for p in self.bundle_path.iterdir() if p.is_dir()]
        if len(subdirs) >= 1:
            for subdir in subdirs:
                sub_children = {p.name for p in subdir.iterdir()} if subdir.is_dir() else set()
                if sub_children & expected_dirs:
                    return subdir

        # Fall back to the original path
        return self.bundle_path

    def parse(self) -> dict[str, Any]:
        """Parse the full support bundle and return structured data."""
        logger.info("Parsing bundle at %s", self._root)
        data: dict[str, Any] = {
            "pods": [],
            "deployments": [],
            "services": [],
            "nodes": [],
            "events": [],
            "namespaces": [],
            "logs": [],
            "cluster_version": None,
            "host_info": {},
            "analysis_json": None,
            "pvs": [],
            "storage_classes": [],
            "configmaps": [],
            "statefulsets": [],
            "daemonsets": [],
            "replicasets": [],
            "jobs": [],
            "cronjobs": [],
            "ingresses": [],
            "hpas": [],
            "network_policies": [],
            "service_accounts": [],
            "pvcs": [],
            "roles": [],
            "role_bindings": [],
            "custom_resource_definitions": [],
            "limit_ranges": [],
            "resource_quotas": [],
            "cluster_roles": [],
            "cluster_role_bindings": [],
        }

        data["cluster_version"] = self._parse_cluster_version()
        data["nodes"] = self._parse_nodes()
        data["namespaces"] = self._parse_namespaces()
        data["pods"] = self._parse_resource_by_namespace("pods")
        data["deployments"] = self._parse_resource_by_namespace("deployments")
        data["services"] = self._parse_resource_by_namespace("services")
        data["events"] = self._parse_events()
        data["logs"] = self._parse_pod_logs()
        data["host_info"] = self._parse_host_info()
        data["analysis_json"] = self._parse_analysis_json()
        pvs_raw = self._parse_json_file(self._root / "cluster-resources" / "pvs.json")
        data["pvs"] = self._extract_items(pvs_raw) if pvs_raw else []
        sc_raw = self._parse_json_file(self._root / "cluster-resources" / "storage-classes.json")
        data["storage_classes"] = self._extract_items(sc_raw) if sc_raw else []

        # Additional resource types for comprehensive analysis
        data["configmaps"] = self._parse_resource_by_namespace("configmaps")
        data["statefulsets"] = self._parse_resource_by_namespace("statefulsets")
        data["daemonsets"] = self._parse_resource_by_namespace("daemonsets")
        data["replicasets"] = self._parse_resource_by_namespace("replicasets")
        data["jobs"] = self._parse_resource_by_namespace("jobs")
        data["cronjobs"] = self._parse_resource_by_namespace("cronjobs")
        data["ingresses"] = self._parse_resource_by_namespace("ingresses")
        data["hpas"] = self._parse_resource_by_namespace("horizontalpodautoscalers")
        data["network_policies"] = self._parse_resource_by_namespace("network-policies")
        data["service_accounts"] = self._parse_resource_by_namespace("serviceaccounts")
        data["pvcs"] = self._parse_resource_by_namespace("pvcs")
        data["roles"] = self._parse_resource_by_namespace("roles")
        data["role_bindings"] = self._parse_resource_by_namespace("rolebindings")

        cr_raw = self._parse_json_file(self._root / "cluster-resources" / "custom-resource-definitions.json")
        data["custom_resource_definitions"] = self._extract_items(cr_raw) if cr_raw else []
        lr_raw = self._parse_json_file(self._root / "cluster-resources" / "limitranges.json")
        data["limit_ranges"] = self._extract_items(lr_raw) if lr_raw else []
        rq_raw = self._parse_json_file(self._root / "cluster-resources" / "resource-quotas.json")
        data["resource_quotas"] = self._extract_items(rq_raw) if rq_raw else []
        clusterroles_raw = self._parse_json_file(self._root / "cluster-resources" / "clusterroles.json")
        data["cluster_roles"] = self._extract_items(clusterroles_raw) if clusterroles_raw else []
        crb_raw = self._parse_json_file(self._root / "cluster-resources" / "clusterrolebindings.json")
        data["cluster_role_bindings"] = self._extract_items(crb_raw) if crb_raw else []

        # Scan for YAML resources (handles non-standard bundle formats)
        self._scan_yaml_resources(data)

        # Scan JSON resources in cluster-resources/ that we might have missed
        self._scan_json_resources(data)

        # Synthesize resource info from events/logs when direct data is missing
        self._synthesize_from_events(data)

        # Summary counts
        logger.info(
            "Parsed: %d pods, %d deploys, %d svcs, %d nodes, %d events, %d logs, %d sts, %d ds, %d jobs, %d ingresses",
            len(data["pods"]),
            len(data["deployments"]),
            len(data["services"]),
            len(data["nodes"]),
            len(data["events"]),
            len(data["logs"]),
            len(data["statefulsets"]),
            len(data["daemonsets"]),
            len(data["jobs"]),
            len(data["ingresses"]),
        )

        return data

    def _parse_json_file(self, path: Path) -> Any:
        """Safely parse a single JSON file."""
        try:
            if path.exists() and path.is_file():
                with open(path, encoding="utf-8", errors="replace") as f:
                    return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not parse %s: %s", path, e)
        return None

    def _parse_yaml_file(self, path: Path) -> Any:
        """Safely parse a single YAML file."""
        try:
            if path.exists() and path.is_file():
                with open(path, encoding="utf-8", errors="replace") as f:
                    return yaml.safe_load(f)
        except (yaml.YAMLError, OSError) as e:
            logger.warning("Could not parse YAML %s: %s", path, e)
        return None

    def _parse_data_file(self, path: Path) -> Any:
        """Parse a JSON or YAML file based on extension."""
        if path.suffix in (".yaml", ".yml"):
            return self._parse_yaml_file(path)
        return self._parse_json_file(path)

    def _scan_yaml_resources(self, data: dict[str, Any]) -> None:
        """Scan extracted directory for YAML resource files and merge into parsed data."""
        # Look for pod-status/, events/, cluster-resources/ with .yaml files
        for yaml_file in self._root.rglob("*.yaml"):
            try:
                content = self._parse_yaml_file(yaml_file)
                if not content or not isinstance(content, dict):
                    continue
                kind = content.get("kind", "").lower()
                relative = str(yaml_file.relative_to(self._root))

                if kind == "pod" or (kind == "" and "pod" in relative.lower()):
                    items = self._extract_items(content)
                    data["pods"].extend(items)
                elif kind == "podlist":
                    data["pods"].extend(self._extract_items(content))
                elif kind == "deployment" or kind == "deploymentlist":
                    data["deployments"].extend(self._extract_items(content))
                elif kind == "service" or kind == "servicelist":
                    data["services"].extend(self._extract_items(content))
                elif kind == "node" or kind == "nodelist":
                    data["nodes"].extend(self._extract_items(content))
                elif kind == "event" or kind == "eventlist":
                    data["events"].extend(self._extract_items(content))
                elif kind == "persistentvolume" or kind == "persistentvolumelist":
                    data["pvs"].extend(self._extract_items(content))
                elif kind in ("statefulset", "statefulsetlist"):
                    data["statefulsets"].extend(self._extract_items(content))
                elif kind in ("daemonset", "daemonsetlist"):
                    data["daemonsets"].extend(self._extract_items(content))
                elif kind in ("replicaset", "replicasetlist"):
                    data["replicasets"].extend(self._extract_items(content))
                elif kind in ("job", "joblist"):
                    data["jobs"].extend(self._extract_items(content))
                elif kind in ("cronjob", "cronjoblist"):
                    data["cronjobs"].extend(self._extract_items(content))
                elif kind in ("ingress", "ingresslist"):
                    data["ingresses"].extend(self._extract_items(content))
                elif kind in ("horizontalpodautoscaler", "horizontalpodautoscalerlist"):
                    data["hpas"].extend(self._extract_items(content))
                elif kind in ("configmap", "configmaplist"):
                    data["configmaps"].extend(self._extract_items(content))
                elif kind in ("persistentvolumeclaim", "persistentvolumeclaimlist"):
                    data["pvcs"].extend(self._extract_items(content))
            except Exception as e:
                logger.warning("Error scanning YAML %s: %s", yaml_file, e)

    def _scan_json_resources(self, data: dict[str, Any]) -> None:
        """Scan cluster-resources/ for JSON files that match known resource types."""
        cr_dir = self._root / "cluster-resources"
        if not cr_dir.exists():
            return

        # Map filenames to data keys
        json_map: dict[str, str] = {
            "pods": "pods",
            "deployments": "deployments",
            "services": "services",
            "nodes": "nodes",
            "namespaces": "namespaces",
            "statefulsets": "statefulsets",
            "daemonsets": "daemonsets",
            "replicasets": "replicasets",
            "jobs": "jobs",
            "cronjobs": "cronjobs",
            "ingresses": "ingresses",
            "events": "events",
        }

        for json_file in cr_dir.rglob("*.json"):
            try:
                stem = json_file.stem.lower()
                # Match by filename
                for pattern, key in json_map.items():
                    if pattern in stem and not data.get(key):
                        file_data = self._parse_json_file(json_file)
                        if file_data:
                            items = self._extract_items(file_data)
                            if items:
                                data[key].extend(items)
                                logger.info("Found %d %s from %s", len(items), key, json_file.name)
                                break
            except Exception as e:
                logger.warning("Error scanning JSON %s: %s", json_file, e)

    def _synthesize_from_events(self, data: dict[str, Any]) -> None:
        """Extract pod/node info from events and logs when resource files are missing."""
        # Only synthesize if we have no pods/nodes but do have events or logs
        events = data.get("events", [])
        logs = data.get("logs", [])

        if not data.get("pods") and (events or logs):
            seen_pods: dict[str, dict] = {}
            # Extract from events
            for event in events:
                involved = event.get("involvedObject", {})
                kind = involved.get("kind", "")
                name = involved.get("name", "")
                ns = involved.get("namespace", "default")
                if kind == "Pod" and name and name not in seen_pods:
                    seen_pods[name] = {
                        "metadata": {"name": name, "namespace": ns},
                        "status": {"phase": "Unknown"},
                    }
                elif kind == "Node" and name:
                    if not any(n.get("metadata", {}).get("name") == name for n in data["nodes"]):
                        data["nodes"].append({"metadata": {"name": name}, "status": {"conditions": []}})
            # Extract from logs
            for log in logs:
                pod = log.get("pod", "")
                ns = log.get("namespace", "default")
                if pod and pod not in seen_pods:
                    seen_pods[pod] = {
                        "metadata": {"name": pod, "namespace": ns},
                        "status": {"phase": "Unknown"},
                    }

            data["pods"].extend(seen_pods.values())
            if seen_pods:
                logger.info("Synthesized %d pods from events/logs", len(seen_pods))

        # Synthesize namespaces from any resource that has namespace info
        if not data.get("namespaces"):
            ns_set: set[str] = set()
            for key in ("pods", "deployments", "services", "events"):
                for item in data.get(key, []):
                    ns = item.get("metadata", {}).get("namespace", "")
                    if not ns and key == "events":
                        ns = item.get("involvedObject", {}).get("namespace", "")
                    if ns:
                        ns_set.add(ns)
            data["namespaces"] = [{"metadata": {"name": ns}} for ns in ns_set]
            if ns_set:
                logger.info("Synthesized %d namespaces", len(ns_set))

    def _parse_cluster_version(self) -> dict | None:
        """Parse cluster-info/cluster_version.json."""
        path = self._root / "cluster-info" / "cluster_version.json"
        return self._parse_json_file(path)

    def _parse_nodes(self) -> list[dict]:
        """Parse cluster-resources/nodes.json."""
        path = self._root / "cluster-resources" / "nodes.json"
        data = self._parse_json_file(path)
        if data is None:
            return []
        # Could be a list or a k8s List object
        return self._extract_items(data)

    def _parse_namespaces(self) -> list[dict]:
        """Parse cluster-resources/namespaces.json."""
        path = self._root / "cluster-resources" / "namespaces.json"
        data = self._parse_json_file(path)
        if data is None:
            return []
        return self._extract_items(data)

    def _parse_resource_by_namespace(self, resource_type: str) -> list[dict]:
        """Parse cluster-resources/<resource_type>/ directory or single file.

        Handles multiple bundle layouts:
        - cluster-resources/<type>/<namespace>.json  (namespace-level lists)
        - cluster-resources/<type>/<namespace>/<name>.json  (individual resource files)
        - cluster-resources/<type>.json  (single file with all items)
        """
        cr_dir = self._root / "cluster-resources"
        all_items: list[dict] = []

        resource_dir = cr_dir / resource_type
        if resource_dir.exists() and resource_dir.is_dir():
            # Recursively find all JSON/YAML files under the resource dir
            for data_file in resource_dir.rglob("*"):
                if data_file.suffix not in (".json", ".yaml", ".yml"):
                    continue
                # Skip log files that live under pods/logs/
                if "logs" in data_file.parts or data_file.suffix == ".log":
                    continue
                try:
                    data = self._parse_data_file(data_file)
                    if data is not None:
                        all_items.extend(self._extract_items(data))
                except Exception as e:
                    logger.warning("Error parsing %s: %s", data_file, e)

        # Fallback: cluster-resources/<type>.json (single file)
        if not all_items:
            for ext in (".json", ".yaml", ".yml"):
                single_file = cr_dir / f"{resource_type}{ext}"
                if single_file.exists():
                    data = self._parse_data_file(single_file)
                    if data is not None:
                        all_items.extend(self._extract_items(data))
                    break

        return all_items

    def _parse_events(self) -> list[dict]:
        """Parse cluster-resources/events/<namespace>.json files."""
        events_dir = self._root / "cluster-resources" / "events"
        all_events: list[dict] = []

        if not events_dir.exists() or not events_dir.is_dir():
            return all_events

        for json_file in events_dir.iterdir():
            if not json_file.name.endswith(".json"):
                continue
            try:
                data = self._parse_json_file(json_file)
                if data is not None:
                    items = self._extract_items(data)
                    all_events.extend(items)
            except Exception as e:
                logger.warning("Error parsing %s: %s", json_file, e)

        # Sort by lastTimestamp or metadata.creationTimestamp
        def event_sort_key(ev: dict) -> str:
            return ev.get("lastTimestamp") or ev.get("eventTime") or ev.get("metadata", {}).get("creationTimestamp", "")

        all_events.sort(key=event_sort_key)
        return all_events

    def _parse_pod_logs(self) -> list[dict]:
        """Parse pod logs from multiple possible locations."""
        log_entries: list[dict] = []

        # Strategy 1: pod-logs/<namespace>/<pod>/<container>.log (synthetic bundles)
        logs_dir = self._root / "pod-logs"
        if logs_dir.exists() and logs_dir.is_dir():
            for ns_dir in logs_dir.iterdir():
                if not ns_dir.is_dir():
                    continue
                namespace = ns_dir.name
                for pod_dir in ns_dir.iterdir():
                    if not pod_dir.is_dir():
                        continue
                    pod_name = pod_dir.name
                    for log_file in pod_dir.iterdir():
                        if not log_file.is_file():
                            continue
                        container = log_file.stem
                        try:
                            log_entries.extend(self._parse_log_file(log_file, namespace, pod_name, container))
                        except Exception as e:
                            logger.warning("Error parsing log %s: %s", log_file, e)

        # Strategy 2: cluster-resources/pods/logs/<namespace>/<pod>/<container>.log
        cr_logs_dir = self._root / "cluster-resources" / "pods" / "logs"
        if cr_logs_dir.exists() and cr_logs_dir.is_dir():
            for ns_dir in cr_logs_dir.iterdir():
                if not ns_dir.is_dir():
                    continue
                namespace = ns_dir.name
                for pod_dir in ns_dir.iterdir():
                    if not pod_dir.is_dir():
                        continue
                    pod_name = pod_dir.name
                    for log_file in pod_dir.iterdir():
                        if not log_file.is_file() or log_file.suffix != ".log":
                            continue
                        container = log_file.stem.replace("-previous", "")
                        try:
                            log_entries.extend(self._parse_log_file(log_file, namespace, pod_name, container))
                        except Exception as e:
                            logger.warning("Error parsing log %s: %s", log_file, e)

        # Strategy 3: <pod-name>/<container>.log at bundle root (real Troubleshoot bundles)
        skip_dirs = {
            "cluster-info",
            "cluster-resources",
            "host-collectors",
            "execution-data",
            "pod-logs",
            "host-os-info",
        }
        if self._root.is_dir():
            for entry in self._root.iterdir():
                if not entry.is_dir() or entry.name in skip_dirs or entry.name.startswith("."):
                    continue
                # Check if this dir contains .log files (it's a pod log dir)
                log_files = [f for f in entry.iterdir() if f.is_file() and f.suffix == ".log"]
                if not log_files:
                    continue
                pod_name = entry.name
                for log_file in log_files:
                    container = log_file.stem.replace("-previous", "")
                    try:
                        log_entries.extend(self._parse_log_file(log_file, "default", pod_name, container))
                    except Exception as e:
                        logger.warning("Error parsing log %s: %s", log_file, e)

        return log_entries

    def _parse_log_file(self, path: Path, namespace: str, pod_name: str, container: str) -> list[dict]:
        """Parse a single log file into structured entries."""
        entries: list[dict] = []
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                # Read up to 5000 lines per file to avoid memory issues
                for i, line in enumerate(f):
                    if i >= MAX_LOG_LINES_PER_FILE:
                        break
                    line = line.strip()
                    if not line:
                        continue

                    entry = {
                        "namespace": namespace,
                        "pod": pod_name,
                        "container": container,
                        "message": line,
                        "source": f"{namespace}/{pod_name}/{container}",
                        "timestamp": None,
                        "level": "info",
                    }

                    # Try to extract timestamp from beginning of line
                    # Common formats: ISO 8601, or k8s log format
                    ts_match = re.match(
                        r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[\w:.+-]*)\s*",
                        line,
                    )
                    if ts_match:
                        entry["timestamp"] = ts_match.group(1)

                    # Determine log level
                    line_lower = line.lower()
                    if any(kw in line_lower for kw in ["error", "fatal", "panic", "exception", "traceback"]):
                        entry["level"] = "error"
                    elif any(kw in line_lower for kw in ["warn", "warning"]):
                        entry["level"] = "warn"

                    entries.append(entry)
        except OSError as e:
            logger.warning("Could not read log file %s: %s", path, e)

        return entries

    def _parse_host_info(self) -> dict[str, str]:
        """Parse host-collectors/system/ text files."""
        host_dir = self._root / "host-collectors" / "system"
        info: dict[str, str] = {}

        if not host_dir.exists() or not host_dir.is_dir():
            # Try alternative path
            host_dir = self._root / "host-collectors"
            if not host_dir.exists():
                return info

        for txt_file in host_dir.rglob("*.txt"):
            try:
                with open(txt_file, encoding="utf-8", errors="replace") as f:
                    content = f.read(MAX_HOST_FILE_BYTES)
                info[txt_file.stem] = content
            except OSError:
                pass

        return info

    def _parse_analysis_json(self) -> dict | None:
        """Parse existing analysis.json if present."""
        path = self._root / "analysis.json"
        return self._parse_json_file(path)

    @staticmethod
    def _extract_items(data: Any) -> list[dict]:
        """Extract items from a Kubernetes List object or return as-is if already a list."""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if "items" in data and isinstance(data["items"], list):
                return data["items"]
            return [data]
        return []
