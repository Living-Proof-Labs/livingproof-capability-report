# Narrow existing-page viewer composition (candidate)

This isolated follow-up is based on Reporter #139 at
191e18c2310574ce9728580d171d552741ab30b5; it does not amend that branch.
It does not move the site renderer, navigation or history command from Action #75.

`viewer_page.compose_viewer_page(page, report, trusted_viewers=..., asset_root=...,
validate_shell=...)` composes a player only into the exact advisory-panel fragment
produced by Reporter's existing `_panel` renderer. There is no HTML scraper,
arbitrary insertion selector, evaluator-supplied code or new wire schema. The
existing page must have exactly one unchanged native panel. All surrounding bytes,
including site navigation, anchors, Pinned inputs and provenance, are preserved.

`viewer_page.validate_viewer_page` is read-only and returns None. It revalidates
report integrity, caller pins, asset/data hashes and exact trial binding, verifies
the exact generated native panel, and passes an undecorated in-memory projection
to the caller's existing shell validator. It never writes that projection or
regenerates history. A missing or altered viewer, extra iframe or rejected shell
fails. The caller verifies the complete incoming file set and manifest BEFORE this
check and keeps all published bytes unchanged after success.

The mandatory `validate_shell` callback is trusted caller code, never evaluator
input. Its existing policy must reject executable content not previously approved
for that site. It must return the input unchanged; sanitization changes are a
refusal. This API does not certify arbitrary HTML as safe on its own. Action can
pass `lambda page: checked_report_html(page, location)` without adding HTML logic.

Consumer integration after independent review/release:
- Fresh run: ordinary site processing first, stage Health-owned immutable assets,
  call compose on the resulting page, write only its returned page and asset files.
- Restore: complete manifest validation; call validate on decorated pages before
  the normal recheck. The normal recheck uses Reporter's validated projection for
  its existing shell policy (within the callback); it must not separately reject
  the already-validated generated wrapper, nor skip other evidence checks.
- Never run fresh composition on old pages. Keep Reporter compatibility pinned for
  immutable fragments; unknown old renderer output fails rather than being rewritten.
- Existing ordinary page expiration rewrites remain a separate integration edge:
  do not strip the player or regenerate old pages implicitly. An independently
  reviewed retention policy is required before the consumer advertises that case.

Proof: 40 focused tests passed including #139 checks. Local genuine 574-sample G1
recording and the existing site-generated shell compose successfully and validate
twice without writes; the unchanged Action sanitizer rejects an extra iframe.
This uses the already prepared explicit valid local report fixture, not a claim
that a historical published report's stale digest has been repaired. No data or
executable viewer is committed here. No release, publish or Action push occurred.
