"""ChromaDB vector store for bundle chunk embeddings."""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_client = None
_collection = None


def _get_collection():
    """Lazy-init ChromaDB collection with OpenAI embeddings."""
    global _client, _collection
    if _collection is not None:
        return _collection
    try:
        import chromadb
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

        persist_dir = os.environ.get("CHROMA_PERSIST_DIR", "./data/chroma")
        _client = chromadb.PersistentClient(path=persist_dir)

        # Use OpenAI embeddings if key available, otherwise default
        openai_key = os.environ.get("OPENAI_API_KEY", "")
        if openai_key:
            embedding_fn = OpenAIEmbeddingFunction(
                api_key=openai_key,
                model_name="text-embedding-3-small",
            )
            _collection = _client.get_or_create_collection(
                name="bundle_chunks_openai",
                embedding_function=embedding_fn,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("ChromaDB using OpenAI text-embedding-3-small (persist=%s, count=%d)", persist_dir, _collection.count())
        else:
            _collection = _client.get_or_create_collection(
                name="bundle_chunks",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("ChromaDB using default embeddings (persist=%s, count=%d)", persist_dir, _collection.count())

        return _collection
    except Exception as e:
        logger.warning("ChromaDB unavailable: %s", e)
        return None


def index_chunks(chunks: list[dict]) -> int:
    """Index chunks into ChromaDB. Returns count indexed."""
    collection = _get_collection()
    if collection is None:
        return 0

    try:
        ids = [c["id"] for c in chunks]
        documents = [c["content"] for c in chunks]
        metadatas = [c["metadata"] for c in chunks]

        # Clean metadata — ChromaDB needs flat string/int/float values
        clean_metadatas = []
        for m in metadatas:
            clean = {}
            for k, v in m.items():
                if v is not None:
                    clean[k] = str(v) if not isinstance(v, (int, float, bool)) else v
            clean_metadatas.append(clean)

        # Upsert in batches of 100
        batch_size = 100
        total = 0
        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i:i+batch_size]
            batch_docs = documents[i:i+batch_size]
            batch_meta = clean_metadatas[i:i+batch_size]
            collection.upsert(ids=batch_ids, documents=batch_docs, metadatas=batch_meta)
            total += len(batch_ids)

        logger.info("Indexed %d chunks into ChromaDB (total: %d)", total, collection.count())
        return total
    except Exception as e:
        logger.error("Failed to index chunks: %s", e)
        return 0


def retrieve(query: str, bundle_id: str, n_results: int = 10, filters: dict | None = None) -> list[dict]:
    """Retrieve relevant chunks for a query.

    Returns list of dicts with: id, content, metadata, distance
    """
    collection = _get_collection()
    if collection is None:
        return []

    try:
        # Build where filter
        where = {"bundle_id": bundle_id}
        if filters:
            for k, v in filters.items():
                if v is not None:
                    where[k] = str(v)

        # Use $and for multiple conditions
        if len(where) > 1:
            where_filter = {"$and": [{k: v} for k, v in where.items()]}
        else:
            where_filter = where

        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, collection.count()),
            where=where_filter,
        )

        if not results or not results["documents"]:
            return []

        chunks = []
        for i, doc in enumerate(results["documents"][0]):
            chunks.append({
                "id": results["ids"][0][i] if results["ids"] else "",
                "content": doc,
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i] if results["distances"] else 0,
            })

        return chunks
    except Exception as e:
        logger.error("Retrieval failed: %s", e)
        return []


def get_chunk_count(bundle_id: str | None = None) -> int:
    """Get total chunk count, optionally filtered by bundle."""
    collection = _get_collection()
    if collection is None:
        return 0
    if bundle_id:
        try:
            results = collection.get(where={"bundle_id": bundle_id})
            return len(results["ids"]) if results else 0
        except:
            return 0
    return collection.count()


def delete_bundle_chunks(bundle_id: str) -> None:
    """Delete all chunks for a bundle."""
    collection = _get_collection()
    if collection is None:
        return
    try:
        results = collection.get(where={"bundle_id": bundle_id})
        if results and results["ids"]:
            collection.delete(ids=results["ids"])
            logger.info("Deleted %d chunks for bundle %s", len(results["ids"]), bundle_id)
    except Exception as e:
        logger.warning("Failed to delete chunks: %s", e)
