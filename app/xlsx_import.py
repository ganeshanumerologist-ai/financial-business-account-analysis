"""Safe conversion of an uploaded .xlsx workbook into CSV text.

The existing opening-balance, bank-statement and GSTR-2B importers already have
careful validation and posting rules. This module does only one job: turn the
first worksheet into neutral CSV text so those same validators can run. It does
not post anything and it does not trust formulas.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal

try:
    from openpyxl import load_workbook
    OPENPYXL_AVAILABLE = True
except ImportError:  # pragma: no cover - only on a minimal install
    load_workbook = None
    OPENPYXL_AVAILABLE = False

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_ROWS = 50000
MAX_COLUMNS = 100


class XlsxImportError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return format(value, "f").rstrip("0").rstrip(".")
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value).strip()


def xlsx_to_csv(data: bytes, sheet_name: str | None = None) -> str:
    """Return the first non-empty worksheet as CSV text.

    The header must be the first non-empty row. Dates become ISO dates, numbers
    keep their decimal text, and blank rows are skipped. Formula cells are read
    as their cached values (data_only=True); a formula with no cached value
    becomes blank rather than being evaluated.
    """
    if not OPENPYXL_AVAILABLE:
        raise XlsxImportError(
            "Excel import needs the approved openpyxl package. "
            "Install it with: python -m pip install -r requirements.txt"
        )
    if not data:
        raise XlsxImportError("Choose an .xlsx file first.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise XlsxImportError("The .xlsx file is too large (maximum 8 MB).")
    if not data.startswith(b"PK"):
        raise XlsxImportError("That file is not a valid .xlsx workbook.")

    try:
        wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    except Exception as exc:  # noqa: BLE001 - openpyxl raises several types
        raise XlsxImportError(f"Could not read the .xlsx workbook: {exc}") from exc

    try:
        if sheet_name:
            if sheet_name not in wb.sheetnames:
                raise XlsxImportError(f"Worksheet {sheet_name!r} was not found.")
            ws = wb[sheet_name]
        else:
            ws = wb.worksheets[0] if wb.worksheets else None
        if ws is None:
            raise XlsxImportError("The workbook has no worksheet.")

        rows: list[list[str]] = []
        non_empty = 0
        for raw in ws.iter_rows(min_row=1, max_col=MAX_COLUMNS, values_only=True):
            cells = [_cell_text(value) for value in raw]
            while cells and not cells[-1]:
                cells.pop()
            if not cells:
                continue
            rows.append(cells)
            non_empty += 1
            if non_empty > MAX_ROWS:
                raise XlsxImportError(
                    f"The worksheet has more than {MAX_ROWS:,} non-empty rows. "
                    "Split the import into smaller files."
                )
        if not rows:
            raise XlsxImportError("The first worksheet has no data.")
        if not any(cells for cells in rows[0]):
            raise XlsxImportError("The first non-empty row must be the header row.")
    finally:
        wb.close()

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerows(rows)
    return buf.getvalue()
