"""Persistence service — abstracts DB operations so routers stay clean."""

from __future__ import annotations

import logging
from typing import Any

from app.database import AnalysisRecord, BundleRecord, SessionLocal, init_db

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
            db.add(
                BundleRecord(
                    id=bundle_id,
                    filename=filename,
                    status=status,
                    file_path=file_path,
                )
            )
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
            db.query(AnalysisRecord).filter_by(bundle_id=bundle_id).order_by(AnalysisRecord.analyzed_at.desc()).first()
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
            db.query(AnalysisRecord).filter_by(bundle_id=bundle_id).order_by(AnalysisRecord.analyzed_at.desc()).all()
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


def save_chunks(chunks: list[dict]) -> None:
    """Save chunk metadata to Postgres for audit/debug."""
    if not _db_available:
        return
    try:
        from app.database import BundleChunk
        from app.database import SessionLocal as _SessionLocal

        db = _SessionLocal()
        for chunk in chunks:
            meta = chunk.get("metadata", {})
            existing = db.query(BundleChunk).filter_by(id=chunk["id"]).first()
            if existing:
                continue  # skip duplicates
            db.add(
                BundleChunk(
                    id=chunk["id"],
                    bundle_id=chunk["bundle_id"],
                    chunk_type=chunk["chunk_type"],
                    content=chunk["content"][:5000],  # truncate for DB
                    namespace=meta.get("namespace"),
                    pod=meta.get("pod"),
                    node=meta.get("node"),
                    resource_kind=meta.get("resource_kind"),
                    resource_name=meta.get("resource_name"),
                    severity=meta.get("severity"),
                    source_path=meta.get("source_path"),
                    token_count=len(chunk["content"].split()),
                    metadata_json=meta,
                )
            )
        db.commit()
        db.close()
        logger.info("Saved %d chunk records to Postgres", len(chunks))
    except Exception as e:
        logger.warning("Failed to save chunks to DB: %s", e)


def get_chunk_stats(bundle_id: str) -> dict:
    """Get chunk statistics for a bundle from Postgres."""
    if not _db_available:
        return {}
    try:
        from sqlalchemy import func

        from app.database import BundleChunk
        from app.database import SessionLocal as _SessionLocal

        db = _SessionLocal()
        total = db.query(func.count(BundleChunk.id)).filter_by(bundle_id=bundle_id).scalar() or 0
        type_rows = (
            db.query(BundleChunk.chunk_type, func.count(BundleChunk.id))
            .filter_by(bundle_id=bundle_id)
            .group_by(BundleChunk.chunk_type)
            .all()
        )
        types = {row[0]: row[1] for row in type_rows}
        db.close()
        return {"total_chunks": total, "by_type": types}
    except Exception as e:
        logger.warning("Failed to get chunk stats: %s", e)
        return {}
