"""Tests for the conversion engine and slug generation."""

from importer.convert import (
    coerce_stock,
    convert,
    decode_upload,
    detect_columns,
    normalize_sku,
    parse_price,
)
from importer.slug import slugify

HEADER = ["Item #", "Product Name", "Retail Price", "Category", "Qty On Hand",
          "Weight (lbs)", "Description", "On Sale?"]


def test_parse_price_handles_messy_values():
    assert parse_price("$12.99") == 12.99
    assert parse_price("USD 8.50") == 8.50
    assert parse_price("19") == 19.0
    assert parse_price("1,299.00") == 1299.0
    assert parse_price("n/a") is None
    assert parse_price("") is None
    assert parse_price("-3.00") is None  # negative is rejected


def test_parse_price_rejects_scientific_notation():
    # "3.0e2" must not be silently read as 3.02 or 300.
    assert parse_price("3.0e2") is None
    assert parse_price("1e3") is None
    assert parse_price("2.5E1") is None


def test_parse_price_rejects_ambiguous_multi_separator():
    # European "1.299,00" is ambiguous; drop it rather than read it as 1.299.
    assert parse_price("1.299,00") is None
    assert parse_price("1.2.3") is None
    # Unambiguous European decimal comma is still parsed.
    assert parse_price("8,50") == 8.50


def test_coerce_stock_handles_decimals_and_scientific():
    # "3.5" is 3 units (floored), not 35.
    assert coerce_stock("3.5") == 3
    assert coerce_stock("3.99") == 3
    # "1e3" is 1000, not 13.
    assert coerce_stock("1e3") == 1000
    assert coerce_stock("10") == 10


def test_coerce_stock_clamps_negative_to_zero():
    # "-5" must stay out of stock, not flip to 5 available.
    assert coerce_stock("-5") == 0
    assert coerce_stock("-0.5") == 0


def test_coerce_stock_handles_comma_grouped_values():
    # B36: "1,000" must not fail to parse and silently default to 0 --
    # that reads a fully-stocked item as out of stock.
    assert coerce_stock("1,000") == 1000
    assert coerce_stock("42,500") == 42500
    # Comma thousands + dot decimal (US grouping), same disambiguation
    # parse_price uses.
    assert coerce_stock("2,500.75") == 2500


def test_coerce_stock_ambiguous_separators_returns_none():
    # Reversed European form ("1.299,00") is genuinely ambiguous -- don't
    # guess. The caller (convert()) drops and flags the row instead of
    # silently writing a stock level that might be wrong.
    assert coerce_stock("1.299,00") is None


def test_coerce_stock_handles_infinite_without_crashing():
    # B37: int(float('inf')) raises OverflowError uncaught upstream of this
    # function. coerce_stock must never raise; it returns None so the row
    # is dropped and flagged rather than crashing the whole batch.
    assert coerce_stock("inf") is None
    assert coerce_stock("Infinity") is None
    assert coerce_stock("-inf") is None
    # NaN keeps its pre-existing behavior: treated as 0, not dropped.
    assert coerce_stock("nan") == 0


def test_dropped_ambiguous_price_is_flagged_in_report():
    rows = [
        ["1001", "Euro Priced", "1.299,00", "Tools", "5", "0.2", "x", "no"],
    ]
    records, report = convert(HEADER, rows, mode="all")
    assert report.output_rows == 0
    assert len(report.dropped) == 1
    assert "unusable price" in report.dropped[0][2]


def test_slugify_is_url_safe():
    assert slugify('Copper Fitting 1/2"') == "copper-fitting-1-2"
    assert slugify("  Spaces  Everywhere  ") == "spaces-everywhere"
    assert slugify("///leading and trailing///") == "leading-and-trailing"
    assert slugify("&&&") == "item"  # never empty


def test_normalize_sku_and_stock():
    assert normalize_sku("sku 1001") == "SKU-1001"
    assert normalize_sku("  abc 12 ") == "ABC-12"
    assert coerce_stock("") == 0
    assert coerce_stock("impressive") == 0
    assert coerce_stock("42") == 42


def test_detect_columns_maps_aliases():
    cols, unmapped = detect_columns(HEADER)
    for field in ("sku", "name", "price", "category", "stock", "weight", "description", "sale"):
        assert field in cols
    assert unmapped == []


def test_convert_full_catalog_drops_bad_rows():
    rows = [
        ["sku 1001", "Copper Fitting", "$12.99", "Plumbing > Fittings", "42", "0.2", "<p>Lead free</p>", "no"],
        ["1006", "", "9.99", "Tools", "5", "0.3", "no name", "no"],          # dropped: no name
        ["1007", "Flux", "-3.00", "Tools", "20", "0.25", "neg price", "no"],  # dropped: bad price
    ]
    records, report = convert(HEADER, rows, mode="all")
    assert report.input_rows == 3
    assert report.output_rows == 1
    assert len(report.dropped) == 2
    rec = records[0]
    assert rec["sku"] == "SKU-1001"
    assert rec["price"] == "12.99"
    assert rec["url_slug"] == "copper-fitting"
    assert rec["description"] == "Lead free"  # HTML stripped
    assert rec["available"] == "Yes"          # stock > 0


def test_sale_mode_filters_non_sale():
    rows = [
        ["1", "On Sale Item", "10", "Tools", "5", "1", "x", "yes"],
        ["2", "Regular Item", "10", "Tools", "5", "1", "x", "no"],
    ]
    records, report = convert(HEADER, rows, mode="sale")
    assert report.output_rows == 1
    assert report.excluded_not_on_sale == 1
    assert records[0]["name"] == "On Sale Item"


def test_missing_required_column_is_reported():
    bad_header = ["Product Name", "Retail Price"]  # no SKU column
    records, report = convert(bad_header, [["x", "1.0"]], mode="all")
    assert records == []
    assert "sku" in report.missing_required


def test_convert_preserves_comma_grouped_stock():
    rows = [
        ["1001", "Bulk Screws", "9.99", "Hardware", "1,000", "5", "box of screws", "no"],
    ]
    records, report = convert(HEADER, rows, mode="all")
    assert report.output_rows == 1
    assert report.dropped == []
    assert records[0]["stock"] == "1000"
    assert records[0]["available"] == "Yes"


def test_convert_drops_and_flags_infinite_stock_without_crashing():
    rows = [
        ["1001", "Bad Stock Row", "9.99", "Hardware", "inf", "5", "x", "no"],
        ["1002", "Good Row", "5.00", "Hardware", "10", "1", "x", "no"],
    ]
    records, report = convert(HEADER, rows, mode="all")
    assert report.output_rows == 1
    assert records[0]["sku"] == "1002"
    assert len(report.dropped) == 1
    assert "unusable stock" in report.dropped[0][2]


def test_decode_upload_passes_through_clean_utf8():
    text, warning = decode_upload("café, naïve".encode("utf-8-sig"))
    assert text == "café, naïve"
    assert warning is None


def test_decode_upload_falls_back_to_cp1252_and_warns():
    # Smart quotes and an em dash: valid Windows-1252 bytes, invalid UTF-8.
    original = "“Hello—World”"
    raw = original.encode("cp1252")
    text, warning = decode_upload(raw)
    assert text == original
    assert warning is not None
    assert "Windows-1252" in warning


def test_decode_upload_never_raises_on_arbitrary_bytes():
    # Bytes invalid in both UTF-8 and cp1252 must still decode via the
    # Latin-1 backstop rather than raising UnicodeDecodeError.
    raw = bytes([0x81, 0x8D, 0x90])  # undefined in cp1252
    text, warning = decode_upload(raw)
    assert isinstance(text, str)
    assert warning is not None
