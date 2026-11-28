# SPDX-License-Identifier: Apache-2.0
"""Cited advisory details files. The action does not name an evaluator or a file."""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath


class DetailsPathError(ValueError):
    """A cited details path or checksum the action will not publish."""


def advisory_documents(stored) -> list[dict]:
    """Results in ``advisory_results``. One result or a list, or a map of either."""
    if stored is None:
        return []
    if isinstance(stored, list):
        return [item for item in stored if isinstance(item, dict)]
    if not isinstance(stored, dict):
        return []
    if isinstance(stored.get("advisory"), dict) or isinstance(stored.get("evaluator"), dict):
        return [stored]
    documents = []
    for item in stored.values():
        if isinstance(item, list):
            documents.extend(entry for entry in item if isinstance(entry, dict))
        elif isinstance(item, dict):
            documents.append(item)
    return documents


def advisory_results_store(document: dict):
    """``assessment.advisory_results`` on a bundle, or on a report's source bundle."""
    if not isinstance(document, dict):
        return None
    assessment = document.get("assessment")
    if not isinstance(assessment, dict):
        bundle = document.get("source_bundle")
        assessment = bundle.get("assessment") if isinstance(bundle, dict) else None
    if not isinstance(assessment, dict):
        return None
    return assessment.get("advisory_results")


def cited_details_uris(document: dict) -> list[str]:
    """Relative paths cited by ``advisory.details_file.uri``. Not a glob."""
    uris = []
    for result in advisory_documents(advisory_results_store(document)):
        payload = result.get("advisory")
        if not isinstance(payload, dict):
            continue
        details = payload.get("details_file")
        if not isinstance(details, dict):
            continue
        uri = details.get("uri")
        if isinstance(uri, str) and uri:
            uris.append(uri)
    return uris


def safe_relative(uri: str) -> PurePosixPath:
    """A relative details path. Absolute paths and ``..`` are refused."""
    if not isinstance(uri, str) or uri == "":
        raise DetailsPathError(f"cited details path {uri!r} is not a relative path")
    if "\\" in uri or "\x00" in uri:
        raise DetailsPathError(f"cited details path {uri!r} is not a relative path")
    if uri.startswith("/") or PurePosixPath(uri).is_absolute():
        raise DetailsPathError(f"cited details path {uri!r} is absolute")
    parts = PurePosixPath(uri).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise DetailsPathError(f"cited details path {uri!r} is not a relative path")
    return PurePosixPath(*parts)


def read_cited_details(root: Path, uri: str, sums: dict[str, str]) -> bytes:
    """The cited file's bytes, when the path is safe and the checksum matches.

    ``sums`` is the ``SHA256SUMS`` map. A missing entry, a symlink, or a
    different sha is refused.
    """
    relative = safe_relative(uri)
    key = relative.as_posix()
    if key not in sums:
        raise DetailsPathError(f"cited details file {key} is not listed in SHA256SUMS")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise DetailsPathError(f"cited details file {key} is a symlink")
    if not current.is_file():
        raise DetailsPathError(f"cited details file {key} is missing")
    data = current.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != sums[key]:
        raise DetailsPathError(f"cited details file {key} does not match SHA256SUMS")
    return data
