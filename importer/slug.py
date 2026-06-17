"""URL slug generation.

The store platform rejects an import if a product URL has a leading slash or a
double separator, which is easy to produce by accident from a product name.
This builds a clean slug every time: lowercase, words joined by single hyphens,
no leading or trailing separator.
"""

import re

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    s = name.strip().lower()
    s = s.replace('"', "").replace("'", "")
    s = _NON_SLUG.sub("-", s)
    s = s.strip("-")
    return s or "item"
