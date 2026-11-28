# SPDX-License-Identifier: Apache-2.0
"""Static single-robot reports section (`reports/`): index, scenario histories, run pages.

`build` adds incoming run folders to a reports tree (which may already hold restored
history), prunes expired evidence, and renders the index, history listings and navigation.
`check_reports_tree` lists broken links, checksum mismatches and forbidden wording.
Fetching earlier history is the caller's job; this package never reads the network.
"""

from .assemble import MARKER, build, parse_exclude_runs, render
from .check import check_reports_tree
from .common import SiteError

__all__ = [
    "MARKER",
    "SiteError",
    "build",
    "check_reports_tree",
    "parse_exclude_runs",
    "render",
]
