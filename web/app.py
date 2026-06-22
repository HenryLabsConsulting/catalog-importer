"""Web interface.

A non-technical user uploads a supplier spreadsheet, picks full catalog or
sale only, and downloads a clean import file. Same conversion engine as the
CLI, so the result is identical either way.

    python web/app.py    ->    http://localhost:8090
"""

import base64
import csv
import io
import sys
from pathlib import Path

from flask import Flask, render_template, request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from importer.convert import convert, to_csv_rows  # noqa: E402

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB cap


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/convert")
def do_convert():
    upload = request.files.get("file")
    mode = request.form.get("mode", "all")
    if mode not in ("all", "sale"):
        mode = "all"
    if not upload or not upload.filename:
        return render_template("index.html", error="Please choose a CSV file."), 400

    text = upload.read().decode("utf-8-sig", errors="replace")
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error as exc:
        return render_template("index.html", error=f"That file is not valid CSV: {exc}"), 400
    if not rows:
        return render_template("index.html", error="That file looks empty."), 400

    records, report = convert(rows[0], rows[1:], mode=mode)
    if report.missing_required:
        msg = ("Could not find these required columns: "
               + ", ".join(report.missing_required)
               + ". Headers seen: " + ", ".join(rows[0]))
        return render_template("index.html", error=msg), 400

    buf = io.StringIO()
    csv.writer(buf).writerows(to_csv_rows(records))
    data_uri = "data:text/csv;base64," + base64.b64encode(buf.getvalue().encode()).decode()

    return render_template(
        "result.html",
        report=report,
        preview=records[:10],
        columns=to_csv_rows([])[0],
        data_uri=data_uri,
        mode=mode,
        filename="import_ready.csv",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090)
