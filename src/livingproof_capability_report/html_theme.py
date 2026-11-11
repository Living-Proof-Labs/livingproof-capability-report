"""Self-contained HTML theme for a stored capability report.

Visual presentation only: the report still shows stored decisions and never grades
or recalculates a result. A pass-rate ring, when shown, is the stored k of n.
"""

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
  color: var(--teal);
  text-decoration-thickness: 1px;
  text-underline-offset: 0.15em;
}

a:hover { color: #0b6e6c; }

@media (prefers-color-scheme: dark) {
  a:hover { color: var(--teal-bright); }
}
html:has(#theme-dark:checked) a:hover { color: var(--teal-bright); }
html:has(#theme-light:checked) a:hover { color: #0b6e6c; }

a:focus-visible, button:focus-visible, summary:focus-visible, input:focus-visible {
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
  color: var(--teal);
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


def _card(inner, extra=""):
    if not inner:
        return ""
    cls = "card" if not extra else f"card {extra}"
    return f"<div class='{cls}'>{inner}</div>"


def page(*, title, lede, summary, table, evidence, full, header_badge, headers="", detail=""):
    """Assemble a self-contained report. Callers keep tested markup snippets intact."""
    table_card = f"<div class='card'><div class='table-wrap'>{table}</div></div>" if table else ""
    return (
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{title}</title>"
        "<link rel='preconnect' href='https://fonts.googleapis.com'>"
        "<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>"
        "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=DM+Sans:"
        "ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700&amp;display=swap'>"
        f"<style>{CSS}</style>"
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
        + _card(headers)
        + _card(summary)
        + _card(detail)
        + table_card
        + _card(evidence, "evidence")
        + _card(full)
        + "</main></body></html>\n"
    )
