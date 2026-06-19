"""Command-line interface.

    python -m importer.cli samples/supplier_products_messy.csv --out import.csv
    python -m importer.cli supplier.csv --mode sale --out sale_import.csv
"""

import argparse
import csv
import sys

from .convert import convert, to_csv_rows


def run(in_path: str, out_path: str, mode: str) -> int:
    with open(in_path, newline="", encoding="utf-8-sig") as f:
        try:
            rows = list(csv.reader(f))
        except csv.Error as exc:
            print(f"Input is not valid CSV: {exc}", file=sys.stderr)
            return 1
    if not rows:
        print("Input file is empty.", file=sys.stderr)
        return 1

    header, data = rows[0], rows[1:]
    records, report = convert(header, data, mode=mode)

    if report.missing_required:
        print("Could not map required columns: " + ", ".join(report.missing_required),
              file=sys.stderr)
        print("Headers seen: " + ", ".join(header), file=sys.stderr)
        return 2

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(to_csv_rows(records))

    print(f"Read {report.input_rows} rows, wrote {report.output_rows} to {out_path}.")
    if mode == "sale":
        print(f"Excluded {report.excluded_not_on_sale} rows that were not on sale.")
    if report.unmapped_headers:
        print(f"Ignored unmapped columns: {', '.join(report.unmapped_headers)}")
    if report.dropped:
        print(f"Dropped {len(report.dropped)} rows that could not be imported:")
        for row_num, ident, reason in report.dropped:
            print(f"  row {row_num} ({ident}): {reason}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a supplier CSV to a platform-ready import file.")
    parser.add_argument("input", help="Path to the supplier CSV.")
    parser.add_argument("--out", default="import_ready.csv", help="Output path.")
    parser.add_argument("--mode", choices=["all", "sale"], default="all",
                        help="Import the full catalog or only on-sale items.")
    args = parser.parse_args()
    raise SystemExit(run(args.input, args.out, args.mode))


if __name__ == "__main__":
    main()
