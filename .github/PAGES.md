# Reporter Pages activation plan

Prepared canonical URL: https://docs.livingprooflabs.com/livingproof-capability-report/.
No per-project custom domain or CNAME file is needed. Scoped owner approval covers main-only deployment and deployment-job permissions.
The parent browser worker handles Pages and environment settings; this change
does not mutate those settings. No live deployment is claimed.

The deployment workflow implements the approved job boundaries below. Settings
and live verification remain separate required steps:

1. Enable GitHub Pages with source **GitHub Actions** for this repository.
2. Create/configure `github-pages` with deployment branches restricted to `main`.
3. The main-only deployment workflow is gated on successful `task verify` and
   `task docs:verify` at the exact deployed revision. Keep the build job at
   `contents: read`. Upload only `artifacts/docs/html` through a reviewed, fully
   pinned `actions/upload-pages-artifact` action.
4. Only the separate deployment job is granted `pages: write` and `id-token: write`
   alongside `contents: read`; it uses pinned `actions/deploy-pages`, the `github-pages`
   environment and its returned page URL. Do not checkout or execute repository
   code in that privileged job. No organization-wide default-token change is needed.
5. Serialize deployments and check current main inside the deployment lock so an
   older build cannot replace a newer manual. Never deploy PR artifacts or use
   `pull_request_target`. Manual dispatch, if added, must also reject non-main refs.
6. Verify the actual URL, assets, navigation, deep links, search-result opening,
   mobile layout, system/light/dark themes and displayed revision. Record the
   source commit and run, then add the prominent README and directory links.

Until those steps are completed and independently verified, the 14-day preview
is review evidence only. The existing release workflow remains pinned to v3.0.0;
the working agreement deliberately adopts v5.0.0 without changing release behavior.
