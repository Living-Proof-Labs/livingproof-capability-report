"""Compare new presentation to frozen evidence without rewriting historical files.

Only the three intentional #98 substitutions are reversed here. Dedicated tests
assert the new labels, exact links, escaping and unchanged JSON independently.
"""

import re


def legacy_provenance(text):
    link = r'<a href="https://github.com/Living-Proof-Labs/([^/]+)/commit/([0-9a-f]{40})" title="\2">([^<]+)</a>'
    text = re.sub(
        r"<dt>Spec</dt><dd>" + link + r" revision ([^<]+)</dd>",
        lambda m: f"<dt>Spec</dt><dd>{m[3]} revision {m[4]} {m[2]}</dd>",
        text,
    )
    text = re.sub(
        r"<dt>Assessed by</dt><dd>capability-verifier@" + link + r"</dd>",
        lambda m: f"<dt>Assessed by</dt><dd>capability-verifier@{m[3].removeprefix('v')} {m[2]}</dd>",
        text,
    )
    return re.sub(link, lambda m: f"{m[3]} @ {m[2][:7]}", text)
