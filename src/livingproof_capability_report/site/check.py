# SPDX-License-Identifier: Apache-2.0
"""Link, checksum and wording checks for a built `reports/` tree.

Ported from verification-reports-action `tools/site_fixture.py` (va#75).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .assemble import MARKER, _parse_sha256sums, public_page_problems


def check_reports_tree(reports_dir: Path) -> list[str]:
    """Return a list of link, checksum, or content issues inside `reports_dir`."""
    issues: list[str] = []
    if not (reports_dir / "index.html").is_file():
        issues.append("index.html missing")
    if not (reports_dir / MARKER).is_file():
        issues.append(f"{MARKER} missing")
    else:
        index_text = (reports_dir / "index.html").read_text(encoding="utf-8")
        for needle in ("livingproof-verification/", "Earlier history"):
            if needle in index_text:
                issues.append(f"index.html still contains {needle!r}")

    parent_overview = (reports_dir.parent / "index.html").resolve()
    pages = sorted(reports_dir.rglob("*.html"))
    for page in pages:
        text = page.read_text(encoding="utf-8")
        for href in re.findall(r"""(?:href|src)=["']([^"'#]+)""", text):
            if re.match(r"^[a-z][a-z0-9+.-]*:", href, re.I) or href.startswith("//"):
                continue
            if href.startswith("/"):
                issues.append(
                    f"{page.relative_to(reports_dir)}: unexpected root-relative link {href}"
                )
                continue
            resolved = (page.parent / href).resolve()
            if href.endswith("/"):
                resolved = resolved / "index.html"
            if resolved == parent_overview and not parent_overview.exists():
                continue
            if not resolved.is_file():
                issues.append(f"{page.relative_to(reports_dir)}: broken link {href}")

    for run_folder in sorted(reports_dir.glob("*/*/runs/*")):
        if not run_folder.is_dir():
            continue
        sums_path = run_folder / "SHA256SUMS"
        if not sums_path.is_file():
            issues.append(f"{run_folder.relative_to(reports_dir)}: missing SHA256SUMS")
            continue
        listed = _parse_sha256sums(sums_path)
        actual_files = {
            p.relative_to(run_folder).as_posix()
            for p in run_folder.rglob("*")
            if p.is_file() and p.name != "SHA256SUMS"
        }
        if set(listed) != actual_files:
            issues.append(
                f"{run_folder.relative_to(reports_dir)}: SHA256SUMS file set mismatch "
                f"(listed={sorted(listed)}, files={sorted(actual_files)})"
            )
            continue
        for rel_name, digest in listed.items():
            actual = hashlib.sha256((run_folder / rel_name).read_bytes()).hexdigest()
            if actual != digest:
                issues.append(f"{run_folder.relative_to(reports_dir)}/{rel_name}: sha256 mismatch")

    issues.extend(public_page_problems(reports_dir))
    return issues
