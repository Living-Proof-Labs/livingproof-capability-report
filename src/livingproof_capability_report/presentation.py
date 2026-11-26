"""Typed display-only API for already-validated optional observations.

This is not an evaluator result, an attestation, or a grading input. Callers own
payload validation; the bundle digest binds their contribution to this report.
"""

from dataclasses import dataclass
import re
from typing import Literal


@dataclass(frozen=True)
class EvaluatorPresentation:
    """Version 1 contains bounded plain text and an optional local evidence link."""

    id: str
    title: str
    version: str
    purpose: str
    details: str
    source_bundle_sha256: str
    details_href: str | None = None
    format: Literal["livingproof-evaluator-presentation/1"] = "livingproof-evaluator-presentation/1"
    state: Literal["advisory"] = "advisory"

    def __post_init__(self):
        if self.format != "livingproof-evaluator-presentation/1" or self.state != "advisory":
            raise ValueError("Unsupported evaluator presentation format or state")
        if not isinstance(self.id, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", self.id):
            raise ValueError("Evaluator presentation id must be a stable lowercase slug")
        for name, limit in (("title", 80), ("version", 64), ("purpose", 400), ("details", 2000)):
            text = getattr(self, name)
            if (
                not isinstance(text, str)
                or not text.strip()
                or len(text) > limit
                or re.search(r"[<>\x00-\x1f\x7f-\x9f\u2028\u2029]", text)
            ):
                raise ValueError(f"Evaluator presentation {name} must be bounded plain text")
        if not isinstance(self.source_bundle_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", self.source_bundle_sha256
        ):
            raise ValueError("Evaluator presentation requires the report source bundle SHA-256")
        # No URL schemes, traversal, query strings, fragments, escapes, or executable links.
        if self.details_href is not None and (
            not isinstance(self.details_href, str)
            or len(self.details_href) > 256
            or not re.fullmatch(
                r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*\.(?:json|txt)", self.details_href
            )
        ):
            raise ValueError(
                "Evaluator presentation details_href must be a local JSON or text path"
            )

    @classmethod
    def from_dict(cls, document):
        """Decode the documented wire object; unknown fields and absent versions fail."""
        if not isinstance(document, dict) or not {"format", "state"} <= document.keys():
            raise ValueError("Evaluator presentation requires explicit format and state")
        try:
            return cls(**document)
        except TypeError as exc:
            raise ValueError("Unknown or missing evaluator presentation fields") from exc


def validate_presentations(items, report):
    if items is None:
        return ()
    if not isinstance(items, (list, tuple)) or len(items) > 16:
        raise ValueError(
            "evaluator_presentations must be a list or tuple of at most 16 contributions"
        )
    ids = set()
    for item in items:
        if not isinstance(item, EvaluatorPresentation):
            raise ValueError("Use EvaluatorPresentation for each optional contribution")
        # Recheck at the boundary, including instances constructed without the normal initializer.
        item.__post_init__()
        if item.id in ids:
            raise ValueError("Duplicate evaluator presentation id")
        ids.add(item.id)
        if item.source_bundle_sha256 != report.get("source_bundle_sha256"):
            raise ValueError("Evaluator presentation source bundle digest does not match report")
    return tuple(items)
