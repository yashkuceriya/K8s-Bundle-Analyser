"""Integration tests for the FastAPI endpoints."""
import io
import tarfile
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_bundle_bytes():
    """Create a minimal valid tar.gz support bundle in memory."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        # cluster-info/cluster_version.json
        version_data = json.dumps({"gitVersion": "v1.28.4"}).encode()
        info = tarfile.TarInfo(name="test-bundle/cluster-info/cluster_version.json")
        info.size = len(version_data)
        tar.addfile(info, io.BytesIO(version_data))

        # cluster-resources/nodes.json
        nodes_data = json.dumps({"items": [
            {"metadata": {"name": "node-1"}, "status": {"conditions": [{"type": "Ready", "status": "True"}]}}
        ]}).encode()
        info = tarfile.TarInfo(name="test-bundle/cluster-resources/nodes.json")
        info.size = len(nodes_data)
        tar.addfile(info, io.BytesIO(nodes_data))

        # cluster-resources/pods/default.json
        pods_data = json.dumps({"items": [
            {
                "metadata": {"name": "test-pod", "namespace": "default"},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [{"name": "app", "restartCount": 0, "state": {"running": {}}, "image": "nginx:1.25"}],
                },
            }
        ]}).encode()
        info = tarfile.TarInfo(name="test-bundle/cluster-resources/pods/default.json")
        info.size = len(pods_data)
        tar.addfile(info, io.BytesIO(pods_data))

        # cluster-resources/namespaces.json
        ns_data = json.dumps({"items": [{"metadata": {"name": "default"}}]}).encode()
        info = tarfile.TarInfo(name="test-bundle/cluster-resources/namespaces.json")
        info.size = len(ns_data)
        tar.addfile(info, io.BytesIO(ns_data))

    buf.seek(0)
    return buf.read()


class TestHealthEndpoint:
    def test_health_check(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestBundleWorkflow:
    def test_upload_and_analyze(self, client, sample_bundle_bytes):
        # Upload
        resp = client.post(
            "/api/bundles/upload",
            files={"file": ("test-bundle.tar.gz", sample_bundle_bytes, "application/gzip")},
        )
        assert resp.status_code == 200
        bundle = resp.json()
        assert bundle["filename"] == "test-bundle.tar.gz"
        assert bundle["status"] == "uploaded"
        bundle_id = bundle["id"]

        # Analyze
        resp = client.post(f"/api/bundles/{bundle_id}/analyze")
        assert resp.status_code == 200
        analysis = resp.json()
        assert analysis["bundle_id"] == bundle_id
        assert analysis["status"] == "completed"
        assert "cluster_health" in analysis
        assert isinstance(analysis["issues"], list)

        # Get analysis
        resp = client.get(f"/api/bundles/{bundle_id}/analysis")
        assert resp.status_code == 200
        assert resp.json()["bundle_id"] == bundle_id

        # List bundles
        resp = client.get("/api/bundles/")
        assert resp.status_code == 200
        bundles = resp.json()
        assert any(b["id"] == bundle_id for b in bundles)

        # Delete
        resp = client.delete(f"/api/bundles/{bundle_id}")
        assert resp.status_code == 200

    def test_analyze_nonexistent_bundle(self, client):
        resp = client.post("/api/bundles/nonexistent-id/analyze")
        assert resp.status_code == 404

    def test_get_analysis_nonexistent(self, client):
        resp = client.get("/api/bundles/nonexistent-id/analysis")
        assert resp.status_code == 404
