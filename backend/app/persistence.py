"""Persistence service — abstracts DB operations so routers stay clean."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.database import SessionLocal, BundleRecord, AnalysisRecord, init_db

logger = logging.getLogger(__name__)

# Flag to track if DB is available
_db_available = False


def try_init_db() -> bool:
    """Try to initialize the database. Returns True if successful."""
    global _db_available
    try:
        init_db()
        _db_available = True
        logger.info("Database connected and initialized")
        return True
    except Exception as e:
        _db_available = False
        logger.warning("Database unavailable, using in-memory only: %s", e)
        return False


def is_db_available() -> bool:
    return _db_available


def save_bundle(bundle_id: str, filename: str, status: str, file_path: str = "") -> None:
    """Save bundle metadata to DB."""
    if not _db_available:
        return
    try:
        db = SessionLocal()
        existing = db.query(BundleRecord).filter_by(id=bundle_id).first()
        if existing:
            existing.status = status
            existing.file_path = file_path
        else:
            db.add(BundleRecord(
                id=bundle_id,
                filename=filename,
                status=status,
                file_path=file_path,
            ))
        db.commit()
        db.close()
    except Exception as e:
        logger.warning("Failed to save bundle to DB: %s", e)


def update_bundle_status(bundle_id: str, status: str) -> None:
    """Update bundle status in DB."""
    if not _db_available:
        return
    try:
        db = SessionLocal()
        record = db.query(BundleRecord).filter_by(id=bundle_id).first()
        if record:
            record.status = status
            db.commit()
        db.close()
    except Exception as e:
        logger.warning("Failed to update bundle status: %s", e)


def save_analysis(bundle_id: str, result_dict: dict[str, Any]) -> None:
    """Save analysis result to DB."""
    if not _db_available:
        return
    try:
        db = SessionLocal()
        health = result_dict.get("cluster_health", {})
        record = AnalysisRecord(
            bundle_id=bundle_id,
            status="completed",
            health_score=health.get("score", 100),
            critical_count=health.get("critical_count", 0),
            warning_count=health.get("warning_count", 0),
            info_count=health.get("info_count", 0),
            issue_count=len(result_dict.get("issues", [])),
            summary=result_dict.get("summary", ""),
            full_result=result_dict,
        )
        db.add(record)
        db.commit()
        db.close()
    except Exception as e:
        logger.warning("Failed to save analysis to DB: %s", e)


def load_all_bundles() -> list[dict]:
    """Load all bundles from DB."""
    if not _db_available:
        return []
    try:
        db = SessionLocal()
        records = db.query(BundleRecord).all()
        result = [
            {
                "id": r.id,
                "filename": r.filename,
                "upload_time": r.upload_time.isoformat() if r.upload_time else "",
                "status": r.status,
                "file_path": r.file_path or "",
            }
            for r in records
        ]
        db.close()
        return result
    except Exception as e:
        logger.warning("Failed to load bundles from DB: %s", e)
        return []


def load_latest_analysis(bundle_id: str) -> dict | None:
    """Load the latest analysis for a bundle from DB."""
    if not _db_available:
        return None
    try:
        db = SessionLocal()
        record = (
            db.query(AnalysisRecord)
            .filter_by(bundle_id=bundle_id)
            .order_by(AnalysisRecord.analyzed_at.desc())
            .first()
        )
        db.close()
        if record and record.full_result:
            return record.full_result
        return None
    except Exception as e:
        logger.warning("Failed to load analysis from DB: %s", e)
        return None


def load_analysis_history(bundle_id: str) -> list[dict]:
    """Load analysis history for a bundle from DB."""
    if not _db_available:
        return []
    try:
        db = SessionLocal()
        records = (
            db.query(AnalysisRecord)
            .filter_by(bundle_id=bundle_id)
            .order_by(AnalysisRecord.analyzed_at.desc())
            .all()
        )
        result = [
            {
                "analyzed_at": r.analyzed_at.isoformat() if r.analyzed_at else "",
                "health_score": r.health_score,
                "critical_count": r.critical_count,
                "warning_count": r.warning_count,
                "info_count": r.info_count,
                "issue_count": r.issue_count,
            }
            for r in records
        ]
        db.close()
        return result
    except Exception as e:
        logger.warning("Failed to load history from DB: %s", e)
        return []


def delete_bundle(bundle_id: str) -> None:
    """Delete a bundle and its analyses from DB."""
    if not _db_available:
        return
    try:
        db = SessionLocal()
        db.query(AnalysisRecord).filter_by(bundle_id=bundle_id).delete()
        db.query(BundleRecord).filter_by(id=bundle_id).delete()
        db.commit()
        db.close()
    except Exception as e:
        logger.warning("Failed to delete bundle from DB: %s", e)
