"""Command-line interface.

    python -m importer.cli samples/supplier_products_messy.csv --out import.csv
    python -m importer.cli supplier.csv --mode sale --out sale_import.csv
"""

import argparse
import csv
import io
import sys

from .convert import convert, decode_upload, to_csv_rows


def run(in_path: str, out_path: str, mode: str) -> int:
    with open(in_path, "rb") as f:
        raw = f.read()
    # Same graceful decoding the web app uses: try UTF-8 first, then fall
    # back to Windows-1252/Latin-1 so a non-UTF-8 supplier export (common
    # from Excel) never crashes the CLI with a raw traceback.
    text, decode_warning = decode_upload(raw)

    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error as exc:
        print(f"Input is not valid CSV: {exc}", file=sys.stderr)
        return 1
    if not rows:
        print("Input file is empty.", file=sys.stderr)
        return 1

    header, data = rows[0], rows[1:]
    records, report = convert(header, data, mode=mode)
    if decode_warning:
        report.warnings.append(decode_warning)

    if report.missing_required:
        print("Could not map required columns: " + ", ".join(report.missing_required),
              file=sys.stderr)
        print("Headers seen: " + ", ".join(header), file=sys.stderr)
        return 2

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(to_csv_rows(records))

    print(f"Read {report.input_rows} rows, wrote {report.output_rows} to {out_path}.")
    if report.warnings:
        for w in report.warnings:
            print(f"Warning: {w}")
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
