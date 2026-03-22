"""Database configuration and session management."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Handle Railway's postgres:// vs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = None
SessionLocal = None
Base = declarative_base()

if DATABASE_URL:
    try:
        engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=10, pool_pre_ping=True)
        SessionLocal = sessionmaker(bind=engine)
    except Exception as e:
        logger.warning("Failed to create DB engine: %s", e)


class BundleRecord(Base):
    __tablename__ = "bundles"

    id = Column(String, primary_key=True)
    filename = Column(String, nullable=False)
    upload_time = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    status = Column(String, default="uploaded")
    file_path = Column(String, default="")


class AnalysisRecord(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bundle_id = Column(String, nullable=False, index=True)
    analyzed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    status = Column(String, default="completed")
    health_score = Column(Integer, default=100)
    critical_count = Column(Integer, default=0)
    warning_count = Column(Integer, default=0)
    info_count = Column(Integer, default=0)
    issue_count = Column(Integer, default=0)
    summary = Column(Text, default="")
    full_result = Column(JSON, nullable=True)  # stores the complete AnalysisResult as JSON


class BundleChunk(Base):
    __tablename__ = "bundle_chunks"

    id = Column(String, primary_key=True)
    bundle_id = Column(String, nullable=False, index=True)
    chunk_type = Column(String, nullable=False)  # pod_log, event, issue, resource_summary
    content = Column(Text, nullable=False)
    namespace = Column(String, nullable=True)
    pod = Column(String, nullable=True)
    node = Column(String, nullable=True)
    resource_kind = Column(String, nullable=True)
    resource_name = Column(String, nullable=True)
    severity = Column(String, nullable=True)
    source_path = Column(String, nullable=True)
    token_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    metadata_json = Column(JSON, nullable=True)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String, primary_key=True)
    bundle_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False)  # user, assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    retrieval_sources = Column(JSON, nullable=True)


def init_db():
    """Create all tables."""
    if not engine:
        logger.info("No DATABASE_URL configured, skipping DB init")
        return
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created/verified")
    except Exception as e:
        logger.warning("Database init failed (will use in-memory fallback): %s", e)


def get_db():
    """Get a database session."""
    if not SessionLocal:
        return None
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
