"""High-level retriever that combines vector search with metadata for RAG."""

from __future__ import annotations

import logging

from app.rag.vector_store import retrieve

logger = logging.getLogger(__name__)


def retrieve_for_question(question: str, bundle_id: str, n_results: int = 10) -> list[dict]:
    """Retrieve relevant chunks for a chat question.

    Uses the question to do semantic search, then ranks by relevance.
    Returns list of chunk dicts sorted by relevance.
    """
    # Direct semantic search
    chunks = retrieve(query=question, bundle_id=bundle_id, n_results=n_results)

    # Boost chunks that match question keywords
    q_lower = question.lower()
    for chunk in chunks:
        boost = 0.0
        chunk["content"].lower()
        meta = chunk.get("metadata", {})

        # Boost error/critical chunks for problem questions
        if any(kw in q_lower for kw in ("why", "crash", "error", "fail", "wrong", "issue", "problem")):
            if meta.get("severity") in ("critical", "error", "warning"):
                boost -= 0.1  # Lower distance = more relevant

        # Boost if question mentions a specific resource
        if meta.get("pod") and meta["pod"].lower() in q_lower:
            boost -= 0.2
        if meta.get("namespace") and meta["namespace"].lower() in q_lower:
            boost -= 0.1
        if meta.get("node") and meta["node"].lower() in q_lower:
            boost -= 0.15

        chunk["distance"] = chunk.get("distance", 0) + boost

    # Re-sort by adjusted distance
    chunks.sort(key=lambda c: c.get("distance", 0))

    return chunks


def retrieve_for_analysis(bundle_id: str, heuristic_issues: list, n_per_issue: int = 5) -> dict[str, list[dict]]:
    """Retrieve evidence for each heuristic issue.

    Returns dict mapping issue.id to list of relevant chunks.
    """
    evidence: dict[str, list[dict]] = {}

    for issue in heuristic_issues:
        # Build query from issue title + description
        query = f"{issue.title} {issue.description}"

        # Add resource-specific filter if available
        filters = {}
        if issue.namespace:
            filters["namespace"] = issue.namespace

        chunks = retrieve(
            query=query,
            bundle_id=bundle_id,
            n_results=n_per_issue,
            filters=filters if filters else None,
        )
        evidence[issue.id] = chunks

    return evidence


def build_rag_context(question: str, bundle_id: str, max_tokens: int = 6000) -> str:
    """Build a retrieval-augmented context string for the LLM.

    Retrieves relevant chunks and formats them into a bounded context.
    """
    chunks = retrieve_for_question(question, bundle_id, n_results=12)

    if not chunks:
        return ""

    sections: list[str] = []
    total_chars = 0
    char_budget = max_tokens * 4  # rough chars-to-tokens

    for chunk in chunks:
        content = chunk["content"]
        meta = chunk.get("metadata", {})
        source_info = []
        if meta.get("chunk_type"):
            source_info.append(meta["chunk_type"])
        if meta.get("namespace"):
            source_info.append(f"ns:{meta['namespace']}")
        if meta.get("pod"):
            source_info.append(f"pod:{meta['pod']}")

        header = f"[{', '.join(source_info)}]" if source_info else "[source]"
        section = f"{header}\n{content}"

        if total_chars + len(section) > char_budget:
            break

        sections.append(section)
        total_chars += len(section)

    return "\n\n---\n\n".join(sections)
