# SPDX-License-Identifier: Apache-2.0
"""Static single-robot reports section (`reports/`): index, scenario histories, run pages.

`build` adds incoming run folders to a reports tree (which may already hold restored
history), prunes expired evidence, and renders the index, history listings and navigation.
`check_reports_tree` lists broken links, checksum mismatches and forbidden wording.
Fetching earlier history is the caller's job; this package never reads the network.
`checked_report_html` applies the published HTML policy to one page, and
`write_published_checksums` rewrites a run folder's SHA256SUMS, for callers that add to a
published run (verification-reports-action composes trusted viewers this way).
"""

from .assemble import MARKER, build, parse_exclude_runs, render, write_published_checksums
from .check import check_reports_tree
from .common import SiteError
from .pages import checked_report_html

__all__ = [
    "MARKER",
    "SiteError",
    "build",
    "check_reports_tree",
    "checked_report_html",
    "parse_exclude_runs",
    "render",
    "write_published_checksums",
]
