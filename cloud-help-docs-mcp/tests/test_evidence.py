"""Tests for excerpt slicing and confidence mapping (no network)."""

from __future__ import annotations

from mcp_servers.cloud_help_docs.core.evidence import (
    EvidenceBuilder,
    confidence_from_score,
    slice_excerpt,
)


def test_confidence_buckets() -> None:
    assert confidence_from_score(0.9) == "high"
    assert confidence_from_score(0.8) == "medium"
    assert confidence_from_score(0.5) == "medium"
    assert confidence_from_score(0.4) == "low"
    assert confidence_from_score(None) == "medium"
    assert confidence_from_score("not-a-number") == "medium"  # type: ignore[arg-type]


def test_slice_excerpt_short_text_returned_as_is() -> None:
    assert slice_excerpt("short text", "query") == "short text"


def test_slice_excerpt_centers_on_query_tokens() -> None:
    content = ("padding " * 100) + "the SPECIAL keyword sits here " + ("tail " * 100)
    excerpt = slice_excerpt(content, "special keyword")
    assert "special" in excerpt.lower()
    # max_chars (500) + up to 32 whitespace-boundary extension each side + 2 ellipses
    assert len(excerpt) <= 566


def test_evidence_builder_produces_valid_object() -> None:
    builder = EvidenceBuilder(provider="aws")
    ev = builder.build(
        query="ec2 launch",
        url="https://docs.aws.amazon.com/ec2/launch",
        title="Launch an instance",
        content="A" * 1000,
        score=0.95,
        product="EC2",
        doc_language="en-US",
    )
    assert ev.id.startswith("ev_")
    assert ev.provider == "aws"
    assert ev.confidence == "high"
    assert ev.metadata["product"] == "EC2"
    assert ev.metadata["search_score"] == 0.95
