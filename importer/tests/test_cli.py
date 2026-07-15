"""Tests for the CLI entry point, focused on the encoding fallback (B38).

Before this fix, cli.run() opened the input strictly as utf-8-sig with no
UnicodeDecodeError handling, so a Windows-1252/Latin-1 supplier export
(common from Excel: curly quotes, em dashes) crashed with a raw traceback.
"""

from importer.cli import run

HEADER_ROW = "Item #,Product Name,Retail Price,Category,Qty On Hand,Weight (lbs),Description,On Sale?\n"


def test_cli_handles_non_utf8_file_gracefully(tmp_path, capsys):
    # "Café Chair" and an em dash, encoded as Windows-1252 -- invalid UTF-8.
    data_row = "1001,Caf\xe9 Chair,19.99,Furniture,5,2.0,Nice — chair,no\n"
    raw = (HEADER_ROW + data_row).encode("cp1252")

    in_path = tmp_path / "supplier_cp1252.csv"
    in_path.write_bytes(raw)
    out_path = tmp_path / "out.csv"

    exit_code = run(str(in_path), str(out_path), "all")

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Warning" in captured.out
    assert "Windows-1252" in captured.out
    # And the product name must be decoded correctly, not mangled into
    # replacement characters.
    assert "Café Chair" in out_path.read_text(encoding="utf-8")


def test_cli_handles_clean_utf8_file_with_no_warning(tmp_path, capsys):
    data_row = "1001,Widget,9.99,Tools,5,1.0,plain ascii,no\n"
    raw = (HEADER_ROW + data_row).encode("utf-8-sig")

    in_path = tmp_path / "supplier_utf8.csv"
    in_path.write_bytes(raw)
    out_path = tmp_path / "out.csv"

    exit_code = run(str(in_path), str(out_path), "all")

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Warning" not in captured.out
