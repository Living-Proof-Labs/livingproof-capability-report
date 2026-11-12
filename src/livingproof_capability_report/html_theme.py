"""Self-contained HTML theme for a stored capability report.

Visual presentation only: the report still shows stored decisions and never grades
or recalculates a result. A pass-rate ring, when shown, is the stored k of n.

DM Sans is embedded from the package so a saved report does not fetch a font.
The SIL Open Font License travels with those bytes.
"""

import base64
from importlib.resources import files

CSS = """
:root {
  color-scheme: light;
  --font-sans: "DM Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --navy: #01152d;
  --teal: #0e8785;
  --teal-bright: #64dfc7;
  --track: #0b4f4d;
  --text: #0f172a;
  --text-muted: #475569;
  --bg: #f4f7fb;
  --bg-muted: #e8eef5;
  --surface: #ffffff;
  --border: #d5dee9;
  --border-strong: #c3cedb;
  --shadow: 0 12px 32px rgba(1, 21, 45, 0.06);
  --chip-pass-fg: #0f5f5c;
  --chip-pass-bg: #d7f3ef;
  --chip-fail-fg: #9f1239;
  --chip-fail-bg: #ffe4e6;
  --chip-warn-fg: #92400e;
  --chip-warn-bg: #fef3c7;
  --chip-muted-fg: #334155;
  --chip-muted-bg: #e2e8f0;
  --header-text: #f8fafc;
  --header-muted: #b7c5d6;
  --focus: #0e8785;
  --pre-bg: #0b1120;
  --pre-text: #e2e8f0;
  --link: #0b6e6c;
  --link-hover: #08524f;
}

@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --text: #e2e8f0;
    --text-muted: #94a3b8;
    --bg: #0b1120;
    --bg-muted: #111827;
    --surface: #151f32;
    --border: #2a364a;
    --border-strong: #3d4b63;
    --shadow: 0 16px 40px rgba(0, 0, 0, 0.35);
    --chip-pass-fg: #5eead4;
    --chip-pass-bg: #0f2e2b;
    --chip-fail-fg: #fda4af;
    --chip-fail-bg: #4c0519;
    --chip-warn-fg: #fcd34d;
    --chip-warn-bg: #33260a;
    --chip-muted-fg: #cbd5e1;
    --chip-muted-bg: #1e293b;
    --link: #64dfc7;
    --link-hover: #8ef3e4;
  }
}

html:has(#theme-light:checked) {
  color-scheme: light;
  --text: #0f172a;
  --text-muted: #475569;
  --bg: #f4f7fb;
  --bg-muted: #e8eef5;
  --surface: #ffffff;
  --border: #d5dee9;
  --border-strong: #c3cedb;
  --shadow: 0 12px 32px rgba(1, 21, 45, 0.06);
  --chip-pass-fg: #0f5f5c;
  --chip-pass-bg: #d7f3ef;
  --chip-fail-fg: #9f1239;
  --chip-fail-bg: #ffe4e6;
  --chip-warn-fg: #92400e;
  --chip-warn-bg: #fef3c7;
  --chip-muted-fg: #334155;
  --chip-muted-bg: #e2e8f0;
  --link: #0b6e6c;
  --link-hover: #08524f;
}

html:has(#theme-dark:checked) {
  color-scheme: dark;
  --text: #e2e8f0;
  --text-muted: #94a3b8;
  --bg: #0b1120;
  --bg-muted: #111827;
  --surface: #151f32;
  --border: #2a364a;
  --border-strong: #3d4b63;
  --shadow: 0 16px 40px rgba(0, 0, 0, 0.35);
  --chip-pass-fg: #5eead4;
  --chip-pass-bg: #0f2e2b;
  --chip-fail-fg: #fda4af;
  --chip-fail-bg: #4c0519;
  --chip-warn-fg: #fcd34d;
  --chip-warn-bg: #33260a;
  --chip-muted-fg: #cbd5e1;
  --chip-muted-bg: #1e293b;
  --link: #64dfc7;
  --link-hover: #8ef3e4;
}

*, *::before, *::after { box-sizing: border-box; }

html { scroll-behavior: auto; }

body {
  margin: 0;
  font-family: var(--font-sans);
  font-size: 1.0625rem;
  line-height: 1.6;
  color: var(--text);
  background: var(--bg);
  -webkit-font-smoothing: antialiased;
}

main, .wrap, .hero, .hero > div, dl, dd, section { min-width: 0; }

body, table, .num {
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum" 1;
}

a {
  color: var(--link);
  text-decoration-thickness: 1px;
  text-underline-offset: 0.15em;
}

a:hover { color: var(--link-hover); }

a:focus-visible, button:focus-visible, summary:focus-visible, input:focus-visible,
.card[role="region"]:focus-visible {
  outline: 3px solid var(--focus);
  outline-offset: 3px;
}

.masthead {
  background:
    radial-gradient(ellipse 70% 80% at 88% 0%, rgba(14, 135, 133, 0.28), transparent 58%),
    var(--navy);
  color: var(--header-text);
  border-bottom: 3px solid var(--teal);
}

.masthead-inner, .wrap, main {
  width: min(76rem, 100% - 2.5rem);
  margin-inline: auto;
}

.masthead-inner {
  padding: 1.75rem 0 2.15rem;
}

.masthead-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.75rem;
}

.eyebrow {
  margin: 0;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--teal-bright);
}

.theme {
  position: relative;
  display: flex;
  gap: 0.15rem;
  margin: 0;
  min-inline-size: 0;
  padding: 0.15rem;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
}

.theme legend {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
  border: 0;
}

.theme label {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 1.7rem;
  padding: 0 0.7rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--header-muted);
  cursor: pointer;
}

.theme input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.theme label:has(input:checked) {
  background: rgba(14, 135, 133, 0.35);
  color: #fff;
}

.theme label:hover { color: #fff; }

.theme label:focus-within {
  outline: 3px solid var(--teal-bright);
  outline-offset: 2px;
}

.hero {
  display: grid;
  gap: 1.75rem;
  align-items: center;
}

@media (min-width: 720px) {
  .hero {
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 2.5rem;
  }
}

.masthead h1 {
  margin: 0 0 0.75rem;
  font-size: clamp(1.65rem, 3vw, 2.15rem);
  font-weight: 650;
  letter-spacing: -0.03em;
  line-height: 1.2;
  color: var(--header-text);
}

.masthead .lede {
  margin: 0;
  max-width: 40rem;
  color: var(--header-muted);
  font-size: 0.98rem;
  line-height: 1.55;
}

.grades {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem 2rem;
  align-items: center;
}

.masthead .grade {
  display: flex;
  align-items: center;
  gap: 1.1rem;
}

.masthead .grade svg {
  width: 6.5rem;
  height: 6.5rem;
  flex: none;
  display: block;
}

.masthead .grade .meta { min-width: 0; }

.masthead .grade .caption {
  margin: 0 0 0.65rem;
  color: var(--header-muted);
  font-size: 0.9rem;
}

main {
  padding: 2.25rem 0 4rem;
  display: grid;
  gap: 1.35rem;
}

.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 1rem;
  box-shadow: var(--shadow);
  padding: 1.6rem 1.7rem 1.7rem;
  min-width: 0;
  overflow-x: auto;
}

.card > h2, #summary > h2, #summary > h3, .evidence h2, .table-wrap > h2, details summary {
  margin: 0 0 1.1rem;
  font-size: 0.78rem;
  font-weight: 650;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-muted);
}

section.run + section.run,
#summary .run + h3,
.verdict + .verdict,
.run-detail > section + section {
  margin-top: 1.5rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--border);
}

section.run h3, .context > h3, .failures > h3, .trials > h3 {
  margin: 0 0 1rem;
  font-size: 1.15rem;
  font-weight: 650;
  letter-spacing: -0.02em;
  text-transform: none;
  color: var(--text);
}

.failures h4 {
  margin: 1.25rem 0 0.7rem;
  font-size: 0.95rem;
  font-weight: 650;
}

.verdict p { margin: 0 0 0.75rem; }
.verdict p:last-child { margin-bottom: 0; }
.verdict .robot {
  font-weight: 650;
  font-size: 1.2rem;
  letter-spacing: -0.02em;
}
.verdict .grade {
  margin: 0.15rem 0 0.75rem;
  font-size: 1.85rem;
  font-weight: 700;
  letter-spacing: 0.04em;
}
.verdict[data-grade="PASS"] .grade { color: var(--chip-pass-fg); }
.verdict[data-grade="FAIL"] .grade { color: var(--chip-fail-fg); }
.verdict[data-grade="INSUFFICIENT_EVIDENCE"] .grade { color: var(--chip-warn-fg); }
.verdict[data-grade="INCOMPATIBLE"] .grade { color: var(--chip-muted-fg); }
.verdict .facts {
  margin: 0 0 0.9rem;
  padding-left: 1.15rem;
  color: var(--text-muted);
}

dl {
  display: grid;
  grid-template-columns: minmax(8.5rem, 14rem) minmax(0, 1fr);
  gap: 0.55rem 1.5rem;
  margin: 0;
}

dt {
  margin: 0;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-muted);
  padding-top: 0.15rem;
}

dd, td, .lede, .caption {
  min-width: 0;
  overflow-wrap: anywhere;
}

dd { margin: 0; }

dd ul { margin: 0.2rem 0 0; padding-left: 1.1rem; }

.muted, .limit { color: var(--text-muted); }
.limit { font-size: 0.9rem; }

.note {
  border-left: 4px solid var(--chip-warn-fg);
  padding: 0.55rem 0.9rem;
  background: var(--chip-warn-bg);
  border-radius: 0.35rem;
}

code { font-size: 0.92em; }

.table-wrap { overflow-x: auto; }

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.95rem;
}

th, td {
  text-align: left;
  vertical-align: top;
  padding: 0.85rem 1rem;
  border: 0;
  border-bottom: 1px solid var(--border);
}

thead th {
  position: sticky;
  top: 0;
  font-size: 0.72rem;
  font-weight: 650;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
  background: var(--bg-muted);
  border-bottom: 1px solid var(--border-strong);
  white-space: nowrap;
}

tbody tr:last-child td { border-bottom: 0; }

tbody tr:hover td { background: color-mix(in srgb, var(--bg-muted) 70%, transparent); }

.chip {
  display: inline-flex;
  align-items: center;
  min-height: 1.55rem;
  padding: 0.1rem 0.6rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  line-height: 1.3;
}

.chip-pass, .chip.pass { color: var(--chip-pass-fg); background: var(--chip-pass-bg); }
.chip-fail { color: var(--chip-fail-fg); background: var(--chip-fail-bg); }
.chip-warn { color: var(--chip-warn-fg); background: var(--chip-warn-bg); }
.chip-muted { color: var(--chip-muted-fg); background: var(--chip-muted-bg); }

.chips {
  list-style: none;
  margin: 0.35rem 0 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.evidence ul {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 0.55rem;
}

.evidence li {
  padding: 0.65rem 0.85rem;
  border-radius: 0.55rem;
  background: var(--bg-muted);
}

details summary {
  list-style: none;
  cursor: pointer;
  margin: 0;
}

details summary::-webkit-details-marker { display: none; }

details summary::after {
  content: "Show";
  float: right;
  text-transform: none;
  letter-spacing: 0;
  font-weight: 600;
  color: var(--link);
}

details[open] summary::after { content: "Hide"; }

details[open] summary { margin-bottom: 1rem; }

pre {
  margin: 0;
  padding: 1.1rem 1.2rem;
  border-radius: 0.75rem;
  background: var(--pre-bg);
  color: var(--pre-text);
  font-size: 0.82rem;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

@media (max-width: 640px) {
  .masthead-inner, .wrap, main { width: min(76rem, 100% - 1.5rem); }
  .masthead-inner { padding-top: 1.25rem; }
  .masthead-top { align-items: flex-start; }
  .card { padding: 1.2rem 1.15rem 1.3rem; border-radius: 0.85rem; }
  dl { grid-template-columns: 1fr; gap: 0.15rem 0; }
  dt { padding-top: 0.55rem; }
  .grades { justify-content: flex-start; }
  th, td { padding: 0.7rem 0.7rem; }
}

/* Scenario-step success rings. The rate bar is the share of successes, not a k-of-n marker. */

.scenario-steps h2 { margin-bottom: 1rem; }

.split { display: grid; gap: 1.1rem; }
@media (min-width: 800px) {
  .split { grid-template-columns: 1.15fr 0.85fr; align-items: start; }
}
.locked {
  border: 1px solid var(--border);
  border-radius: 0.85rem;
  padding: 1.05rem 1.15rem 1.15rem;
  min-width: 0;
}
.locked h3 {
  margin: 0 0 0.85rem;
  font-size: 0.74rem;
  font-weight: 650;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-muted);
}
.run-hero { display: flex; flex-wrap: wrap; align-items: center; gap: 1.15rem 1.4rem; }
.run-hero .badge svg { display: block; width: 8rem; height: 8rem; }
.run-hero .pct {
  margin: 0;
  font-size: clamp(1.55rem, 3vw, 2rem);
  font-weight: 650;
  letter-spacing: -0.03em;
  line-height: 1.15;
}
.run-hero .count, .run-hero .stored-status, .confidence {
  margin: 0.35rem 0 0;
  color: var(--text-muted);
}
.run-hero .count { font-size: 0.85rem; }
.run-hero .stored-status, .confidence { font-size: 0.78rem; }
.plan-note {
  margin: 1.05rem 0 0;
  padding: 0.7rem 0 0.15rem 0.95rem;
  border-left: 2px solid var(--border-strong);
  color: var(--text-muted);
  font-size: 0.8rem;
  line-height: 1.5;
  max-width: 36rem;
}
.plan-note strong { font-weight: 650; color: var(--text); }
.success-bar {
  display: block;
  height: 0.5rem;
  margin: 0.85rem 0 0.1rem;
  max-width: 28rem;
  background: var(--bg-muted);
  border-radius: 999px;
  overflow: hidden;
}
.rank-body .success-bar { margin-top: 0.45rem; max-width: 22rem; }
.success-bar > i {
  display: block;
  height: 100%;
  width: calc(var(--p) * 1%);
  background: var(--teal);
  border-radius: 999px;
}
.step-intro, .close-note, .sources, .foot {
  margin: 0;
  color: var(--text-muted);
  font-size: 0.88rem;
}
.step-intro { margin: -0.4rem 0 0.9rem; }
.close-note { margin: 0.15rem 0 0.35rem; }
.sources { margin-top: 0.8rem; font-size: 0.75rem; line-height: 1.5; max-width: 52rem; }
.sources code { font-size: 0.92em; }
.foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.55rem 0.85rem;
  margin-top: 1rem;
  font-size: 0.85rem;
}
.step-list { display: grid; }
.step { border-bottom: 1px solid var(--border); }
.step:last-of-type { border-bottom: 0; }
.step-summary {
  display: grid;
  grid-template-columns: 2.1rem 5.5rem minmax(0, 1fr);
  gap: 0.85rem 1rem;
  align-items: center;
  padding: 0.95rem 0;
  cursor: pointer;
  list-style: none;
  margin: 0;
  color: inherit;
  font-size: 1rem;
  font-weight: 400;
  letter-spacing: normal;
  text-transform: none;
}
.step-summary::-webkit-details-marker, .step-summary::marker { content: ""; }
.step-summary::after { content: none; float: none; }
details[open] > .step-summary { margin-bottom: 0; }
details[open] > .step-summary::after { content: none; }
.step-summary .badge svg { width: 5.5rem; height: 5.5rem; display: block; }
.step-name {
  margin: 0;
  font-size: 1.08rem;
  font-weight: 650;
  letter-spacing: -0.02em;
  line-height: 1.3;
  text-transform: none;
  color: var(--text);
}
.step-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem 0.7rem;
  margin: 0.3rem 0 0;
  color: var(--text-muted);
  font-size: 0.82rem;
}
.step-meta .count { margin: 0; font-size: 0.82rem; color: var(--text-muted); }
.eval-line {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  color: var(--text-muted);
  font-size: 0.82rem;
}
.eval-icon { width: 1rem; height: 1rem; flex: none; color: var(--link); }
.disclose {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  margin-left: auto;
  color: var(--link);
  font-weight: 650;
  font-size: 0.78rem;
}
.disclose .chevron {
  display: inline-block;
  width: 0.42rem;
  height: 0.42rem;
  border-right: 2px solid currentColor;
  border-bottom: 2px solid currentColor;
  transform: rotate(45deg) translate(-1px, -1px);
}
details[open] > .step-summary .chevron { transform: rotate(-135deg) translate(-1px, -1px); }
.disclose-open { display: none; }
details[open] > .step-summary .disclose-closed { display: none; }
details[open] > .step-summary .disclose-open { display: inline; }
.complete {
  display: block;
  margin-top: 0.25rem;
  font-size: 0.78rem;
  color: var(--text-muted);
}
.trial-panel { padding: 0 0 1.15rem; min-width: 0; }
@media (min-width: 801px) {
  .trial-panel { padding-left: calc(2.1rem + 5.5rem + 2rem); }
}
.trial-note { margin: 0 0 0.65rem; color: var(--text-muted); font-size: 0.8rem; }
.trial-table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
.trial-table th, .trial-table td {
  text-align: left;
  vertical-align: top;
  padding: 0.55rem 0.7rem;
  border-bottom: 1px solid var(--border);
}
.trial-table thead th {
  position: static;
  font-size: 0.68rem;
  font-weight: 650;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
  background: var(--bg-muted);
  border-bottom: 1px solid var(--border-strong);
  white-space: nowrap;
}
.trial-table tbody tr:last-child td { border-bottom: 0; }
.trial-table tbody tr.is-success td {
  background: color-mix(in srgb, var(--teal) 5%, transparent);
}
.trial-table .time-kind, .trial-table .margin-note {
  display: block;
  color: var(--text-muted);
  font-size: 0.75rem;
  font-weight: 500;
}
.step-result {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-weight: 650;
  font-size: 0.86rem;
}
.step-result-success { color: var(--link); }
.step-result-success svg { width: 0.85rem; height: 0.85rem; flex: none; }
.step-result-quiet, .step-result-neutral { color: var(--text-muted); font-weight: 550; }
.place {
  font-weight: 700;
  font-size: 1.15rem;
  letter-spacing: -0.03em;
  color: var(--text-muted);
}
.place.tie { font-size: 0.95rem; letter-spacing: 0; }
.nowrap { white-space: nowrap; }

@media (max-width: 700px) {
  .run-hero .badge svg { width: 6.25rem; height: 6.25rem; }
  .step-summary {
    grid-template-columns: 1.6rem 4.4rem minmax(0, 1fr);
    gap: 0.55rem 0.7rem;
    align-items: start;
  }
  .step-summary .badge svg { width: 4.4rem; height: 4.4rem; }
  .step-summary .place { padding-top: 1.15rem; }
  .step-name { font-size: 0.98rem; }
  .step-name .colon { display: none; }
  .step-name .rate { display: block; margin-top: 0.1rem; }
  .trial-table thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
  }
  .trial-table, .trial-table tbody, .trial-table tr, .trial-table td { display: block; width: 100%; }
  .trial-table tr { padding: 0.7rem 0.15rem; border-bottom: 1px solid var(--border); }
  .trial-table tbody tr:last-child { border-bottom: 0; }
  .trial-table td {
    display: grid;
    grid-template-columns: 8.2rem minmax(0, 1fr);
    gap: 0.35rem 0.75rem;
    padding: 0.15rem 0;
    border: 0;
  }
  .trial-table td::before {
    content: attr(data-label);
    font-size: 0.68rem;
    font-weight: 650;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-muted);
    padding-top: 0.15rem;
  }
}

@media print {
  :root, html:has(#theme-dark:checked) {
    color-scheme: light;
    --text: #0f172a;
    --text-muted: #475569;
    --bg: #fff;
    --bg-muted: #f1f5f9;
    --surface: #fff;
    --border: #cbd5e1;
    --shadow: none;
    --chip-pass-fg: #0f5f5c;
    --chip-pass-bg: #d7f3ef;
    --chip-fail-fg: #9f1239;
    --chip-fail-bg: #ffe4e6;
    --chip-warn-fg: #92400e;
    --chip-warn-bg: #fef3c7;
    --chip-muted-fg: #334155;
    --chip-muted-bg: #e2e8f0;
    --link: #0b6e6c;
    --link-hover: #08524f;
  }
  .theme { display: none; }
  .masthead { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .card { box-shadow: none; break-inside: avoid; }
  details[open] summary::after, details summary::after { content: none; }
  pre { background: #f8fafc; color: #0f172a; border: 1px solid var(--border); }
}
""".strip()

CHIP = {
    "PASS": "chip chip-pass",
    "FAIL": "chip chip-fail",
    "INSUFFICIENT_EVIDENCE": "chip chip-warn",
    "INCOMPATIBLE": "chip chip-muted",
}

# Official Living Proof grade-mark geometry, 1024 viewBox, traced from the circular logo.
_CX, _CY, _R = 510.5, 505.75, 381.1


def pass_rate(k, n):
    """Integer percent of stored k/n, only for drawing the existing fraction."""
    if k is None or n in (None, 0):
        return None
    try:
        return max(0, min(100, int(round(100 * int(k) / int(n)))))
    except (TypeError, ValueError):
        return None


def grade_badge(k, n, grade, escape):
    """Inline grade mark for a stored k of n. No animation; 100% shows the check."""
    pct = pass_rate(k, n)
    if pct is None:
        return ""
    done = pct == 100
    digits = "100" if done else f"{pct:02d}"
    label = f"{k} of {n} trials passed"
    if grade:
        label = f"{label}; overall {grade}"
    fill_op = "0" if pct == 0 else "1"
    fill_off = 100 - pct
    check_vis = "visible" if done else "hidden"
    check_off = "0" if done else "100"
    d0, d1 = ("", "") if done else (digits[0], digits[1])
    pct_vis = "none" if done else "block"
    chip = (
        f"<span class='{CHIP.get(grade, 'chip chip-muted')}'>{escape(grade)}</span>"
        if grade
        else ""
    )
    return f"""<div class='grade'>
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1024 1024' role='img' aria-label='{escape(label)}' width='104' height='104'>
<title>{escape(label)}</title>
<circle cx='{_CX}' cy='{_CY}' r='{_R}' fill='none' stroke='#0B4F4D' stroke-width='42'/>
<circle cx='{_CX}' cy='{_CY}' r='{_R}' fill='none' stroke='#0E8785' stroke-width='42' stroke-linecap='round' pathLength='100' stroke-dasharray='100 100' stroke-dashoffset='{fill_off}' opacity='{fill_op}' transform='rotate(-90 {_CX} {_CY})'/>
<path d='M 401 306 L 487.25 392.25 L 635 244.5' fill='none' stroke='#0E8785' stroke-width='47' stroke-linecap='round' stroke-linejoin='round' pathLength='100' stroke-dasharray='100 100' stroke-dashoffset='{check_off}' visibility='{check_vis}'/>
<g fill='#FFFFFF' font-family='DM Sans, system-ui, sans-serif' font-weight='700' text-anchor='middle' style='display:{pct_vis}' aria-hidden='true'>
<text x='386.66' y='366' font-size='172'>{d0}</text>
<text x='510.50' y='366' font-size='172'>{d1}</text>
<text x='634.34' y='366' font-size='134.16'>%</text>
</g>
<g fill='#FFFFFF' stroke='none'>
<rect x='252' y='509' width='31' height='109' rx='15.5'/>
<rect x='738' y='509' width='31' height='109' rx='15.5'/>
</g>
<rect x='305.625' y='428.25' width='408.75' height='273.25' rx='88.5' fill='none' stroke='#FFFFFF' stroke-width='33'/>
<g fill='#FFFFFF' stroke='none'>
<circle cx='427.2' cy='547.9' r='33.2'/>
<circle cx='591.8' cy='547.9' r='33.2'/>
<rect x='448' y='620' width='114' height='22' rx='11'/>
</g>
</svg>
<div class='meta'><p class='caption'>{escape(f"{k} of {n} trials passed")}</p>{chip}</div>
</div>"""


def _ring_number(value):
    text = f"{float(value):.4f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def success_badge(face, label, escape, *, complete=False, fill=0, size=88):
    """Success ring. The check is only for a complete success, never a rounded 100.

    ``face`` is the ring text, such as ``60%``, ``0%``, ``5%``, ``>99%`` or ``<1%``.
    It is not zero-padded.
    """
    portion = 100.0 if complete else max(0.0, min(100.0, float(fill or 0)))
    fill_op = "0" if portion <= 0 else "1"
    fill_off = _ring_number(100 - portion)
    check_vis = "visible" if complete else "hidden"
    check_off = "0" if complete else "100"
    pct_vis = "none" if complete else "block"
    # Shorter faces stay large; ">99%" still fits above the mark.
    face_size = 168 if len(face) <= 2 else 128 if len(face) == 3 else 104
    return f"""<svg class='success-ring' xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1024 1024' role='img' aria-label='{escape(label)}' width='{int(size)}' height='{int(size)}'>
<title>{escape(label)}</title>
<circle cx='512' cy='512' r='512' fill='#01152D'/>
<circle cx='{_CX}' cy='{_CY}' r='{_R}' fill='none' stroke='#0B4F4D' stroke-width='42'/>
<circle cx='{_CX}' cy='{_CY}' r='{_R}' fill='none' stroke='#0E8785' stroke-width='42' stroke-linecap='round' pathLength='100' stroke-dasharray='100 100' stroke-dashoffset='{fill_off}' opacity='{fill_op}' transform='rotate(-90 {_CX} {_CY})'/>
<path d='M 401 306 L 487.25 392.25 L 635 244.5' fill='none' stroke='#0E8785' stroke-width='47' stroke-linecap='round' stroke-linejoin='round' pathLength='100' stroke-dasharray='100 100' stroke-dashoffset='{check_off}' visibility='{check_vis}'/>
<g fill='#FFFFFF' font-family='DM Sans, system-ui, sans-serif' font-weight='700' text-anchor='middle' style='display:{pct_vis}' aria-hidden='true'>
<text x='512' y='372' font-size='{face_size}'>{escape(face)}</text>
</g>
<g fill='#FFFFFF' stroke='none'>
<rect x='252' y='509' width='31' height='109' rx='15.5'/>
<rect x='738' y='509' width='31' height='109' rx='15.5'/>
</g>
<rect x='305.625' y='428.25' width='408.75' height='273.25' rx='88.5' fill='none' stroke='#FFFFFF' stroke-width='33'/>
<g fill='#FFFFFF' stroke='none'>
<circle cx='427.2' cy='547.9' r='33.2'/>
<circle cx='591.8' cy='547.9' r='33.2'/>
<rect x='448' y='620' width='114' height='22' rx='11'/>
</g>
</svg>"""


_LATIN_EXT = (
    "U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, "
    "U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, "
    "U+20AD-20C4, U+2113, U+2C60-2C7F, U+A720-A7FF"
)
_LATIN = (
    "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, "
    "U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, "
    "U+2212, U+2215, U+FEFF, U+FFFD"
)


def _font_face(filename, unicode_range):
    encoded = base64.b64encode(
        files("livingproof_capability_report").joinpath("fonts", filename).read_bytes()
    ).decode("ascii")
    return (
        "@font-face{font-family:'DM Sans';font-style:normal;font-weight:100 1000;"
        "font-display:swap;"
        f"src:url(data:font/woff2;base64,{encoded}) format('woff2');"
        f"unicode-range:{unicode_range};}}"
    )


def _build_stylesheet():
    """Theme CSS with the embedded DM Sans files and their SIL license."""
    ofl = (
        files("livingproof_capability_report")
        .joinpath("fonts", "OFL.txt")
        .read_text(encoding="utf-8")
        .strip()
    )
    if "*/" in ofl:
        raise RuntimeError("The font license cannot be placed in a CSS comment")
    return (
        "/*\n"
        + ofl
        + "\n*/\n"
        + _font_face("DMSans-latin-ext.woff2", _LATIN_EXT)
        + _font_face("DMSans-latin.woff2", _LATIN)
        + CSS
    )


_STYLESHEET = _build_stylesheet()


def stylesheet():
    return _STYLESHEET


def _card(inner, extra="", label=""):
    """One surface card. ``label`` marks a scrollable region for keyboard access."""
    if not inner:
        return ""
    cls = "card" if not extra else f"card {extra}"
    # The test-context card scrolls horizontally at a narrow viewport. It has no
    # single heading of its own (the inner "Test context" heading names one section),
    # so the region carries an explicit name and stays in the tab order. No script.
    attrs = f" tabindex='0' role='region' aria-label='{label}'" if label else ""
    return f"<div class='{cls}'{attrs}>{inner}</div>"


def page(
    *,
    title,
    lede,
    summary,
    table,
    evidence,
    full,
    header_badge,
    headers="",
    detail="",
    steps="",
):
    """Assemble a self-contained report. Callers keep tested markup snippets intact."""
    table_card = f"<div class='card'><div class='table-wrap'>{table}</div></div>" if table else ""
    return (
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{title}</title>"
        f"<style>{stylesheet()}</style>"
        "<body>"
        "<header class='masthead'><div class='masthead-inner'>"
        "<div class='masthead-top'><p class='eyebrow'>Living Proof Labs</p>"
        "<fieldset class='theme'><legend>Colour theme</legend>"
        "<label><input type='radio' name='theme' id='theme-system' value='system' checked> "
        "System</label>"
        "<label><input type='radio' name='theme' id='theme-light' value='light'> Light</label>"
        "<label><input type='radio' name='theme' id='theme-dark' value='dark'> Dark</label>"
        "</fieldset></div>"
        "<div class='hero'><div>"
        f"<h1>{title}</h1>"
        f"<p class='lede'>{lede}</p>"
        f"</div>{header_badge}</div>"
        "</div></header>"
        "<main class='wrap'>"
        + steps
        + _card(headers)
        + _card(summary)
        + _card(detail, label="Test context")
        + table_card
        + _card(evidence, "evidence")
        + _card(full)
        + "</main></body></html>\n"
    )
