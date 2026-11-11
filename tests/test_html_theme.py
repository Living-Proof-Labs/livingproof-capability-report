"""WCAG AA contrast for body-sized teal text in every colour theme."""

import re

from livingproof_capability_report import html_theme

# Show/Hide and in-card links sit on the card. Evidence links sit on the muted
# list. Passing-trial chips can contain links, so that chip background counts.
_SURFACES = ("--surface", "--bg-muted", "--chip-pass-bg")


def _channel(value):
    value = value / 255
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def _luminance(color):
    hex_color = color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(part * 2 for part in hex_color)
    channels = [int(hex_color[index : index + 2], 16) for index in (0, 2, 4)]
    weights = (0.2126, 0.7152, 0.0722)
    return sum(weight * _channel(channel) for weight, channel in zip(weights, channels))


def contrast(foreground, background):
    """WCAG 2 relative-luminance contrast ratio."""
    lighter = max(_luminance(foreground), _luminance(background))
    darker = min(_luminance(foreground), _luminance(background))
    return (lighter + 0.05) / (darker + 0.05)


def _rules(css):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    rules = []
    index = 0
    selector_at = 0
    while index < len(css):
        if css[index] != "{":
            index += 1
            continue
        selector = " ".join(css[selector_at:index].split())
        depth = 1
        index += 1
        body_at = index
        while index < len(css) and depth:
            depth += (css[index] == "{") - (css[index] == "}")
            index += 1
        rules.append((selector, css[body_at : index - 1]))
        selector_at = index
    return rules


def _properties(body):
    return {
        name: value.strip()
        for name, value in re.findall(r"(--[A-Za-z0-9-]+)\s*:\s*([^;]+);", body)
    }


def _resolve(value, environment):
    seen = set()
    while value.startswith("var("):
        name = value[len("var(") :].split(")", 1)[0].strip()
        assert name not in seen, name
        seen.add(name)
        value = environment[name]
    return value.lower()


def _modes(css):
    top = dict(_rules(css))
    root = _properties(top[":root"])
    dark = _properties(dict(_rules(top["@media (prefers-color-scheme: dark)"]))[":root"])
    chosen_light = _properties(top["html:has(#theme-light:checked)"])
    chosen_dark = _properties(top["html:has(#theme-dark:checked)"])
    printed = _properties(
        dict(_rules(top["@media print"]))[":root, html:has(#theme-dark:checked)"]
    )

    def merge(*parts):
        environment = {}
        for part in parts:
            environment.update(part)
        return environment

    return {
        "system-light": merge(root),
        "system-dark": merge(root, dark),
        "light": merge(root, dark, chosen_light),
        "dark": merge(root, chosen_dark),
        "print": merge(root, dark, chosen_dark, printed),
    }


def _declared_color(body):
    return re.search(r"(?<![\w-])color\s*:\s*([^;]+);", body).group(1).strip()


def test_contrast_formula_matches_the_reviewed_teal():
    """The old #0e8785 pair was 4.35:1 on white and 3.79:1 on the dark card."""
    assert 4.30 < contrast("#0e8785", "#ffffff") < 4.40
    assert 3.74 < contrast("#0e8785", "#151f32") < 3.84


def test_body_teal_meets_wcag_aa_on_each_surface():
    top = dict(_rules(html_theme.CSS))
    used = {
        "link": _declared_color(top["a"]),
        "link-hover": _declared_color(top["a:hover"]),
        "summary": _declared_color(top["details summary::after"]),
    }
    assert _properties(top[":root"])["--teal"] == "#0e8785"
    assert "system-ui" in html_theme.CSS
    for mode, environment in _modes(html_theme.CSS).items():
        for role, declared in used.items():
            foreground = _resolve(declared, environment)
            for surface_name in _SURFACES:
                background = _resolve(environment[surface_name], environment)
                ratio = contrast(foreground, background)
                assert ratio >= 4.5, (
                    f"{mode} {role} {foreground} on {surface_name} {background} = {ratio:.2f}"
                )
