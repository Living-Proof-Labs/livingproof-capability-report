# SPDX-License-Identifier: Apache-2.0
"""Shared constants and helpers for the reports site build and render modules.

Each definition here is the single copy; the other modules import it.
"""

from __future__ import annotations

import re
import urllib.parse
from datetime import datetime, timezone


class SiteError(Exception):
    """Raised when report validation, single-robot constraints, or history restore fails."""


ARTIFACT_WORD = re.compile(r"artifacts?", re.I)


SITE_PATH = re.compile(r"[A-Za-z0-9._~!$&'()*+,;=@%/-]{1,240}")


RELEASE_TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


COMMIT_SHA = re.compile(r"[0-9a-f]{40}")


EVALUATOR_ANCHOR = "#summary"


ANCHOR_REPORTER = (3, 14, 0)


_REPORTER_TAG = re.compile(r"v(\d+)\.(\d+)\.(\d+)")


MARKED_INTEGRITY_STATUSES = ("ERROR", "INCONCLUSIVE")


def _stored_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _stamp(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError) as error:
        raise SiteError(
            f"Unexpected timestamp {value!r}; expected UTC ISO-8601 YYYY-MM-DDTHH:MM:SSZ"
        ) from error


def _plain_label(value: object) -> str:
    text = value if isinstance(value, str) else ""
    cleaned = ARTIFACT_WORD.sub("", text).strip(" .:-")
    if not cleaned or re.search(r"[\[\]()|`<>\n]", cleaned) or len(cleaned) > 80:
        return "evidence"
    return cleaned


def _require_single_robot(robots: set[str]) -> str | None:
    if len(robots) > 1:
        names = ", ".join(sorted(robots))
        raise SiteError(
            f"Expected runs for one robot per site, found multiple robots: {names}. "
            "Each robot repository publishes only its own verification reports."
        )
    return next(iter(robots), None)


def site_path(value: object) -> str | None:
    if not isinstance(value, str) or not SITE_PATH.fullmatch(value):
        return None
    decoded = urllib.parse.unquote(value)
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in decoded):
        return None
    if (
        # Decoding cannot remove a leading "/", a "." or ".." segment, ":", a backslash or
        # "/actions/", so those are checked on the decoded value only. It can remove part
        # of the artifact word ("%aartifact" decodes to "\xaartifact"), so that is checked
        # on both.
        decoded.startswith("/")
        or "\\" in decoded
        or any(part in (".", "..") for part in decoded.split("/"))
        or ":" in decoded
        or "/actions/" in decoded.lower()
        or ARTIFACT_WORD.search(value)
        or ARTIFACT_WORD.search(decoded)
    ):
        return None
    return value


def listing_path(record: dict) -> str | None:
    name = (record.get("artifact") or {}).get("name") or _stored_text(record.get("name"))
    if not (record.get("preserved") and len(record.get("files") or []) > 1 and name):
        return None
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "-", str(name))
    return f"evidence/{safe_name}.html"
