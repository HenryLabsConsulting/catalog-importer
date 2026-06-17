"""Core conversion.

Reads a messy supplier sheet and produces a clean, platform-ready import along
with a report of what was fixed and what was dropped and why. The logic is a
pure function over rows, so it is easy to test and trust.
"""

import html
import re
from dataclasses import dataclass, field

from .mapping import HEADER_ALIASES, REQUIRED_INPUT, TARGET_COLUMNS
from .slug import slugify

_TAGS = re.compile(r"<[^>]+>")
_PRICE_JUNK = re.compile(r"[^0-9.\-]")
_TRUTHY = {"y", "yes", "true", "1", "on"}


@dataclass
class Report:
    input_rows: int = 0
    output_rows: int = 0
    excluded_not_on_sale: int = 0
    dropped: list = field(default_factory=list)   # (row_number, sku_or_name, reason)
    unmapped_headers: list = field(default_factory=list)
    missing_required: list = field(default_factory=list)


def detect_columns(header: list[str]) -> tuple[dict, list[str]]:
    """Map canonical field -> column index. Returns (mapping, unmapped_headers)."""
    mapping: dict[str, int] = {}
    unmapped: list[str] = []
    for i, raw in enumerate(header):
        key = raw.strip().lower()
        field_name = HEADER_ALIASES.get(key)
        if field_name and field_name not in mapping:
            mapping[field_name] = i
        elif not field_name:
            unmapped.append(raw)
    return mapping, unmapped


def clean_text(value: str) -> str:
    return html.unescape(_TAGS.sub("", value)).strip()


def parse_price(value: str):
    cleaned = _PRICE_JUNK.sub("", value or "")
    if not cleaned or cleaned in ("-", ".", "-."):
        return None
    try:
        price = float(cleaned)
    except ValueError:
        return None
    return price if price > 0 else None


def coerce_stock(value: str) -> int:
    digits = re.sub(r"[^0-9]", "", value or "")
    return int(digits) if digits else 0


def normalize_sku(value: str) -> str:
    return re.sub(r"\s+", "-", value.strip().upper())


def is_truthy(value: str) -> bool:
    return (value or "").strip().lower() in _TRUTHY


def convert(header: list[str], rows: list[list[str]], mode: str = "all") -> tuple[list[dict], Report]:
    report = Report(input_rows=len(rows))
    cols, unmapped = detect_columns(header)
    report.unmapped_headers = unmapped
    report.missing_required = [f for f in REQUIRED_INPUT if f not in cols]
    if report.missing_required:
        return [], report

    def cell(row, field_name):
        idx = cols.get(field_name)
        return row[idx] if idx is not None and idx < len(row) else ""

    out: list[dict] = []
    for n, row in enumerate(rows, start=2):  # row 1 is the header
        raw_sku = cell(row, "sku").strip()
        raw_name = clean_text(cell(row, "name"))

        if not raw_sku:
            report.dropped.append((n, raw_name or "(blank)", "missing SKU"))
            continue
        if not raw_name:
            report.dropped.append((n, raw_sku, "missing product name"))
            continue

        price = parse_price(cell(row, "price"))
        if price is None:
            report.dropped.append((n, raw_sku, f"unusable price: {cell(row, 'price')!r}"))
            continue

        on_sale = is_truthy(cell(row, "sale"))
        if mode == "sale" and not on_sale:
            report.excluded_not_on_sale += 1
            continue

        stock = coerce_stock(cell(row, "stock"))
        out.append({
            "sku": normalize_sku(raw_sku),
            "name": raw_name,
            "price": f"{price:.2f}",
            "category": re.sub(r"\s*>\s*", " > ", cell(row, "category").strip()),
            "url_slug": slugify(raw_name),
            "stock": str(stock),
            "weight": f"{parse_price(cell(row, 'weight')) or 0:.2f}",
            "available": "Yes" if stock > 0 else "No",
            "description": clean_text(cell(row, "description")),
        })

    report.output_rows = len(out)
    return out, report


def to_csv_rows(records: list[dict]) -> list[list[str]]:
    """Header plus one row per record, in the platform's column order."""
    yield_rows = [list(TARGET_COLUMNS)]
    for rec in records:
        yield_rows.append([rec[c] for c in TARGET_COLUMNS])
    return yield_rows
