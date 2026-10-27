# Reporter Pages operation

<a id="reporter-pages-activation-plan"></a>

Canonical URL: https://docs.livingprooflabs.com/livingproof-capability-report/.
No per-project custom domain or CNAME file is needed. Pages uses **GitHub Actions**
and the `github-pages` environment restricts deployment to `main`.
Live browser verification of revision `fa1a4e708f3d1330667967fe420adcdf18cbb8ef`
is recorded in the [verification guide](../docs/verification.md).

Keep these deployment boundaries when maintaining the manual:

1. The main-only deployment workflow is gated on successful `task verify` and
   `task docs:verify` at the exact deployed revision. Keep the build job at
   `contents: read`. Upload only `artifacts/docs/html` through a reviewed, fully
   pinned `actions/upload-pages-artifact` action.
2. Only the separate deployment job is granted `pages: write` and `id-token: write`
   alongside `contents: read`; it uses pinned `actions/deploy-pages`, the `github-pages`
   environment and its returned page URL. Do not checkout or execute repository
   code in that privileged job. No organization-wide default-token change is needed.
3. Serialize deployments and check current main inside the deployment lock so an
   older build cannot replace a newer manual. Never deploy PR artifacts or use
   `pull_request_target`. Manual dispatch, if added, must also reject non-main refs.
4. Verify the actual URL, assets, navigation, deep links, search-result opening,
   mobile layout, system/light/dark themes and displayed revision. Record the
   source commit and run after each delivery.

The 14-day preview is review evidence, separate from the durable public manual.
The existing release workflow remains pinned to v3.0.0;
the working agreement deliberately adopts v6.0.0 without changing release behavior.
