"""Presentation-only commit links; stored provenance is never changed or resolved."""

import html
import re
from urllib.parse import quote

_GITHUB_REPOSITORY = re.compile(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?$")
_COMMIT_TEXT = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{7,40}(?![0-9a-fA-F])")
_RELEASE = re.compile(r"v?\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
_VERIFIER_REPOSITORY = "https://github.com/Living-Proof-Labs/capability-verifier"


def commit_link(reference, *, assessor=False):
    """Use supplied tags (or assessor release versions), never infer a tag from a SHA.

    The legacy verifier producer has no repository field; only its known identity
    gets that repository fallback. Unknown producers do not get invented links.
    """
    label = reference.get("tag")
    if not label and assessor:
        version = str(reference.get("version") or "")
        if _RELEASE.fullmatch(version) and version not in {"0.0.0", "v0.0.0"}:
            label = version if version.startswith("v") else f"v{version}"
    label = str(label or "commit")
    if _COMMIT_TEXT.search(label):
        label = "commit"
    repository = reference.get("repository") or (
        _VERIFIER_REPOSITORY if assessor and reference.get("id") == "capability-verifier" else ""
    )
    commit = reference.get("commit")
    text = html.escape(label, quote=True)
    if commit and isinstance(repository, str) and _GITHUB_REPOSITORY.fullmatch(repository):
        url = repository.rstrip("/").removesuffix(".git") + "/commit/" + quote(str(commit), safe="")
        text = f'<a href="{html.escape(url, quote=True)}" title="{html.escape(str(commit), quote=True)}">{text}</a>'
    if assessor and reference.get("id"):
        text = html.escape(str(reference["id"]), quote=True) + "@" + text
    return text
