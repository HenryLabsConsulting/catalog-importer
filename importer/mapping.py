"""Target format and header auto-detection.

The store platform expects an exact set of columns in an exact order. Supplier
exports never match it. The aliases below let the tool recognize common header
names automatically, so a new supplier file usually works with no setup.
"""

# The columns the platform import expects, in order.
TARGET_COLUMNS = [
    "sku", "name", "price", "category", "url_slug",
    "stock", "weight", "available", "description",
]

# Incoming header (lowercased, trimmed) -> canonical input field.
HEADER_ALIASES = {
    "sku": "sku",
    "item #": "sku",
    "item number": "sku",
    "item": "sku",
    "product name": "name",
    "name": "name",
    "title": "name",
    "retail price": "price",
    "price": "price",
    "unit price": "price",
    "category": "category",
    "cat": "category",
    "qty on hand": "stock",
    "quantity": "stock",
    "qty": "stock",
    "stock": "stock",
    "weight (lbs)": "weight",
    "weight": "weight",
    "description": "description",
    "desc": "description",
    "on sale?": "sale",
    "on sale": "sale",
    "sale": "sale",
}

REQUIRED_INPUT = ("sku", "name", "price")
