"""Core conversion.

Reads a messy supplier sheet and produces a clean, platform-ready import along
with a report of what was fixed and what was dropped and why. The logic is a
pure function over rows, so it is easy to test and trust.
"""

import html
import math
import re
from dataclasses import dataclass, field

from .mapping import HEADER_ALIASES, REQUIRED_INPUT, TARGET_COLUMNS
from .slug import slugify

_TAGS = re.compile(r"<[^>]+>")
_CURRENCY_JUNK = re.compile(r"[^0-9.,\-]")
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


def _clean_numeric(raw: str) -> str | None:
    """Strip currency junk and disambiguate thousands/decimal separators.

    Shared by parse_price and coerce_stock so both fields treat "1,299.00"
    style values the same way. Returns:
      - the cleaned numeric string, ready for float(), on success
      - "" if nothing numeric survives stripping (plain garbage text, e.g.
        "impressive" or "n/a") -- there's no data to lose here
      - None if the separators are genuinely ambiguous (e.g. the reversed
        European "1.299,00" form, or more than one decimal point) -- the
        caller should treat this as unparseable rather than guess and
        silently corrupt the value
    """
    cleaned = _CURRENCY_JUNK.sub("", raw)
    if not cleaned or cleaned in ("-", ".", "-.", ","):
        return ""

    has_dot = "." in cleaned
    has_comma = "," in cleaned

    if has_dot and has_comma:
        # Both separators present. Only US grouping ("1,299.00": comma before a
        # dot decimal) is unambiguous, so we accept it. The reverse European
        # form ("1.299,00") is ambiguous, so we flag it rather than silently
        # corrupt the value.
        if cleaned.rfind(".") > cleaned.rfind(","):
            cleaned = cleaned.replace(",", "")
        else:
            return None
    elif has_comma:
        # Only commas: a trailing ",dd" group is a decimal comma (European);
        # anything else is thousands grouping and is removed.
        if re.search(r",\d{1,2}$", cleaned):
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")

    # A clean amount has at most one decimal point.
    if cleaned.count(".") > 1:
        return None

    return cleaned


def parse_price(value: str):
    raw = value or ""
    # Reject scientific notation outright. "3.0e2" would otherwise be stripped
    # to "3.02" (silent money corruption) or, if parsed by float(), read as 300.
    # Plain currency codes like "USD 8.50" have no "e" next to a digit and are
    # still handled by stripping junk below.
    if re.search(r"\de", raw, re.IGNORECASE) or re.search(r"e\d", raw, re.IGNORECASE):
        return None

    cleaned = _clean_numeric(raw)
    if not cleaned:  # "" (nothing usable) or None (ambiguous) both drop
        return None

    try:
        price = float(cleaned)
    except ValueError:
        return None
    return price if price > 0 else None


def coerce_stock(value: str) -> int | None:
    """Parse a stock quantity.

    Tries a direct float() parse first -- that's what correctly reads
    decimals ("3.5" -> 3), scientific notation ("1e3" -> 1000), and the
    literal "inf"/"nan" tokens Python's float() itself recognizes. If that
    fails (e.g. a comma-grouped value like "1,000"), falls back to the same
    comma/dot disambiguation parse_price uses, so a fully-stocked item never
    gets silently zeroed out just because of thousands separators.

    Returns None -- instead of silently defaulting to 0 -- when the value is
    genuinely ambiguous (unresolvable separators, e.g. "1.299,00") or
    non-finite (inf/-inf), so the caller can drop and flag the row rather
    than write a wrong stock level or crash on OverflowError. Plain garbage
    text ("impressive") and blank cells still read as 0 stock.
    """
    raw = (value or "").strip()
    if not raw:
        return 0

    try:
        amount = float(raw)
    except ValueError:
        cleaned = _clean_numeric(raw)
        if cleaned is None:
            return None  # ambiguous separators - don't guess
        if not cleaned:
            return 0  # no numeric content at all
        try:
            amount = float(cleaned)
        except ValueError:
            return 0

    if amount != amount:  # NaN guard
        return 0
    if not math.isfinite(amount):  # inf / -inf guard
        return None
    return max(0, int(amount))


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

        raw_stock = cell(row, "stock")
        stock = coerce_stock(raw_stock)
        if stock is None:
            report.dropped.append((n, raw_sku, f"unusable stock value: {raw_stock!r}"))
            continue

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
    rows = [list(TARGET_COLUMNS)]
    for rec in records:
        rows.append([rec[c] for c in TARGET_COLUMNS])
    return rows
