"""Tests for the conversion engine and slug generation."""

from importer.convert import (
    coerce_stock,
    convert,
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
