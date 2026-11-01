"""Post or update the one capability-report comment on a pull request.

The body is the reporter's own markdown (``render --format markdown``), unchanged, under a
hidden marker. An existing comment carrying the marker is updated in place; otherwise one is
created. Uses the GitHub REST API with ``GITHUB_TOKEN`` (or ``GH_TOKEN``) through urllib, so
the image needs no ``gh``. ``--dry-run`` reads comments but writes nothing.
"""

import json
import os
import urllib.request

MARKER = "<!-- livingproof-capability-report -->"
API = "https://api.github.com"


def body(texts):
    return "\n\n".join([MARKER, *(t.strip() for t in texts)]) + "\n"


def http(method, path, payload=None, token=None, api=API):
    """One REST call; returns (decoded JSON, Link header)."""
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        path if path.startswith("https://") else f"{api}/{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "livingproof-capability-report",
            **({"Content-Type": "application/json"} if data else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 (https only)
        return json.loads(response.read() or b"null"), response.headers.get("Link", "")


def _next(link):
    for part in link.split(","):
        if 'rel="next"' in part:
            return part[part.index("<") + 1 : part.index(">")]
    return None


def existing(repo, pr, call):
    url = f"repos/{repo}/issues/{pr}/comments?per_page=100"
    while url:
        page, link = call("GET", url)
        for c in page:
            if MARKER in (c.get("body") or ""):
                return int(c["id"])
        url = _next(link)
    return None


def publish(repo, pr, text, call, dry_run=False):
    cid = existing(repo, pr, call)
    if cid is None:
        method, path = "POST", f"repos/{repo}/issues/{pr}/comments"
    else:
        method, path = "PATCH", f"repos/{repo}/issues/comments/{cid}"
    if not dry_run:
        call(method, path, {"body": text})
    return method, path


def token():
    value = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not value:
        raise ValueError("Set GITHUB_TOKEN (or GH_TOKEN) to post the comment")
    return value
