"""GSTR-2B working purchase reconciliation (stdlib only).

The portal's official file formats are not claimed or reproduced. This module
accepts a documented CSV shape, imports it idempotently, and matches it to
posted purchase bills by supplier GSTIN and normalised invoice number. Amount
differences are reported, never silently corrected.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import sqlite3
from datetime import date, datetime, timezone

from . import accounting as acct
from . import db
from .money import MoneyError, parse_amount, split_tax

GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$")
DATE_FORMATS = (
    "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%d %b %Y", "%d-%b-%Y", "%d/%b/%Y", "%d %B %Y",
    "%Y/%m/%d", "%Y.%m.%d", "%d/%m/%y", "%d-%m-%y",
)

ALIASES: dict[str, set[str]] = {
    "supplier_gstin": {"gstin", "suppliergstin", "gstinofsupplier", "suppliergstinuan",
                       "suppliergstinuin", "gstinuin"},
    "supplier_name": {"suppliername", "tradename", "legalname", "supplier"},
    "invoice_no": {"invoiceno", "invoicenumber", "documentnumber", "documentno",
                   "invoice", "billno"},
    "invoice_date": {"invoicedate", "documentdate", "date"},
    "taxable": {"taxablevalue", "taxableamount", "taxable", "taxablevalueinr"},
    "igst": {"igst", "integratedtax", "igstamount"},
    "cgst": {"cgst", "centraltax", "cgstamount"},
    "sgst": {"sgst", "statetax", "stateutgst", "sgstamount", "utgst"},
    "cess": {"cess", "cessamount"},
    "total": {"total", "invoicevalue", "totalamount", "invoicevalueinr"},
}


REVIEW_STATUSES = ("open", "follow_up", "itc_hold", "accepted")
REVIEW_LABELS = {
    "open": "Open",
    "follow_up": "Supplier follow-up",
    "itc_hold": "ITC on hold",
    "accepted": "Accepted",
}


class Gstr2bError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _norm_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _cell(row: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    return row[idx]


def _parse_date(value: str) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip())
    if not text:
        raise Gstr2bError("BAD_DATE", "A GSTR-2B row has no invoice date")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise Gstr2bError("BAD_DATE", f"Unrecognised invoice date: {value!r}")


def _parse_money(value: str, label: str) -> int:
    text = (value or "").strip().replace(",", "")
    if not text or text in {"-", "--", "—"}:
        return 0
    try:
        return parse_amount(text)
    except MoneyError as exc:
        raise Gstr2bError("BAD_AMOUNT", f"Bad {label} amount {value!r}: {exc}") from exc


def normalize_invoice(value: str) -> str:
    text = re.sub(r"[^A-Z0-9]", "", (value or "").upper())
    match = re.fullmatch(r"([A-Z]*)(\d+)", text)
    if match:
        return match.group(1) + str(int(match.group(2)))
    return text


def _column_map(header: list[str]) -> dict[str, int]:
    found: dict[str, int] = {}
    for idx, name in enumerate(header):
        norm = _norm_header(name)
        for field, aliases in ALIASES.items():
            if norm in aliases and field not in found:
                found[field] = idx
                break
    return found


def parse_csv(text: str) -> list[dict]:
    raw = (text or "").lstrip("\ufeff")
    if not raw.strip():
        raise Gstr2bError("EMPTY_CSV", "Paste or choose a GSTR-2B CSV first")
    lines = raw.splitlines()
    header_at = None
    for i, line in enumerate(lines[:30]):
        norm = _norm_header(line)
        if (("gstin" in norm or "supplier" in norm)
                and ("invoice" in norm or "document" in norm)):
            header_at = i
            break
    if header_at is None:
        raise Gstr2bError(
            "NO_HEADER",
            "Could not find a header row with supplier GSTIN and invoice columns.",
        )
    reader = csv.reader(io.StringIO("\n".join(lines[header_at:])))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise Gstr2bError("EMPTY_CSV", "The CSV has no header row") from exc
    cols = _column_map(header)
    if "invoice_no" not in cols:
        raise Gstr2bError("NO_INVOICE_COLUMN", "The CSV needs an invoice number column")
    if "invoice_date" not in cols:
        raise Gstr2bError("NO_DATE_COLUMN", "The CSV needs an invoice date column")
    if "taxable" not in cols:
        raise Gstr2bError("NO_TAXABLE_COLUMN", "The CSV needs a taxable value column")

    out: list[dict] = []
    for line_no, row in enumerate(reader, start=header_at + 2):
        if not row or not any((c or "").strip() for c in row):
            continue
        invoice_no = _cell(row, cols.get("invoice_no")).strip()
        if not invoice_no:
            continue  # summary/footer rows
        try:
            gstin = _cell(row, cols.get("supplier_gstin")).strip().upper()
            if gstin and not GSTIN_RE.fullmatch(gstin):
                raise Gstr2bError("BAD_GSTIN", f"Invalid supplier GSTIN {gstin!r}")
            invoice_date = _parse_date(_cell(row, cols.get("invoice_date")))
            taxable = _parse_money(_cell(row, cols.get("taxable")), "taxable")
            igst = _parse_money(_cell(row, cols.get("igst")), "IGST")
            cgst = _parse_money(_cell(row, cols.get("cgst")), "CGST")
            sgst = _parse_money(_cell(row, cols.get("sgst")), "SGST")
            cess = _parse_money(_cell(row, cols.get("cess")), "cess")
            tax = igst + cgst + sgst + cess
            total_text = _cell(row, cols.get("total")).strip()
            total = _parse_money(total_text, "total") if total_text else taxable + tax
        except Gstr2bError as exc:
            raise Gstr2bError(exc.code, f"Line {line_no}: {exc.message}") from exc
        out.append({
            "supplier_gstin": gstin,
            "supplier_name": _cell(row, cols.get("supplier_name")).strip()[:160],
            "invoice_no": invoice_no[:80],
            "invoice_date": invoice_date,
            "taxable_paise": taxable,
            "igst_paise": igst,
            "cgst_paise": cgst,
            "sgst_paise": sgst,
            "cess_paise": cess,
            "tax_paise": tax,
            "total_paise": total,
        })
    if not out:
        raise Gstr2bError("NO_ROWS", "No usable GSTR-2B rows were found")
    return out


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def import_2b(conn: sqlite3.Connection, tenant_id: str, period: str, text: str,
              filename: str = "", created_by: str | None = None) -> dict:
    date_from, date_to = acct.month_bounds(period)
    rows = parse_csv(text)
    sha = hashlib.sha256((text or "").encode("utf-8")).hexdigest()
    existing = conn.execute(
        "SELECT * FROM gstr2b_import WHERE tenant_id=? AND sha256=?", (tenant_id, sha)
    ).fetchone()
    if existing:
        return {"duplicate": True, "import_id": existing["id"], "imported": 0,
                "rows_total": existing["rows_total"], "period": existing["period"],
                "tax_paise": existing["tax_paise"], "date_from": date_from,
                "date_to": date_to}
    totals = {key: sum(r[key] for r in rows) for key in
              ("taxable_paise", "igst_paise", "cgst_paise", "sgst_paise",
               "cess_paise", "tax_paise")}
    import_id = db.new_id()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "UPDATE gstr2b_import SET status='superseded'"
            " WHERE tenant_id=? AND period=? AND status='active'", (tenant_id, period))
        conn.execute(
            "INSERT INTO gstr2b_import (id, tenant_id, period, filename, sha256, rows_total,"
            " taxable_paise, igst_paise, cgst_paise, sgst_paise, cess_paise, tax_paise,"
            " status, created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'active',?,?)",
            (import_id, tenant_id, period, (filename or "")[:200], sha, len(rows),
             totals["taxable_paise"], totals["igst_paise"], totals["cgst_paise"],
             totals["sgst_paise"], totals["cess_paise"], totals["tax_paise"],
             created_by, _now()),
        )
        for row in rows:
            conn.execute(
                "INSERT INTO gstr2b_line (id, tenant_id, import_id, supplier_gstin,"
                " supplier_name, invoice_no, invoice_date, taxable_paise, igst_paise,"
                " cgst_paise, sgst_paise, cess_paise, tax_paise, total_paise,"
                " match_status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'unmatched',?)",
                (db.new_id(), tenant_id, import_id, row["supplier_gstin"],
                 row["supplier_name"], row["invoice_no"], row["invoice_date"],
                 row["taxable_paise"], row["igst_paise"], row["cgst_paise"],
                 row["sgst_paise"], row["cess_paise"], row["tax_paise"],
                 row["total_paise"], _now()),
            )
        acct.audit(conn, tenant_id, created_by, "gstr2b.import", "gstr2b_import", import_id,
                   meta={"period": period, "rows": len(rows), "tax_paise": totals["tax_paise"],
                         "filename": (filename or "")[:200]})
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return {"duplicate": False, "import_id": import_id, "imported": len(rows),
            "rows_total": len(rows), "period": period, "tax_paise": totals["tax_paise"],
            "date_from": date_from, "date_to": date_to,
            "taxable_paise": totals["taxable_paise"]}


def latest_import(conn: sqlite3.Connection, tenant_id: str, period: str):
    row = conn.execute(
        "SELECT * FROM gstr2b_import WHERE tenant_id=? AND period=? AND status='active'"
        " ORDER BY created_at DESC LIMIT 1", (tenant_id, period),
    ).fetchone()
    return dict(row) if row else None


def import_history(conn: sqlite3.Connection, tenant_id: str, period: str | None = None):
    sql = "SELECT * FROM gstr2b_import WHERE tenant_id=?"
    params: list = [tenant_id]
    if period:
        sql += " AND period=?"
        params.append(period)
    sql += " ORDER BY created_at DESC LIMIT 25"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def review_line(conn: sqlite3.Connection, tenant_id: str, line_id: str, status: str,
                note: str = "", updated_by: str | None = None) -> dict:
    """Set the ITC review state for one active GSTR-2B line.

    This is deliberately a review annotation only: it never changes the imported
    line, a purchase bill, ITC or a tax return.
    """
    if status not in REVIEW_STATUSES:
        raise Gstr2bError("BAD_REVIEW_STATUS", "Choose a valid ITC review status")
    note = (note or "").strip()[:500]
    now = _now()
    conn.execute("BEGIN IMMEDIATE")
    try:
        line = conn.execute(
            "SELECT l.*, i.status AS import_status FROM gstr2b_line l"
            " JOIN gstr2b_import i ON i.id=l.import_id"
            " WHERE l.id=? AND l.tenant_id=?", (line_id, tenant_id),
        ).fetchone()
        if not line:
            raise Gstr2bError("LINE_NOT_FOUND", "GSTR-2B line not found")
        if line["import_status"] != "active":
            raise Gstr2bError("SUPERSEDED_IMPORT",
                              "This GSTR-2B import has been superseded; review the active import")
        previous = conn.execute(
            "SELECT status FROM gstr2b_review WHERE line_id=? AND tenant_id=?",
            (line_id, tenant_id),
        ).fetchone()
        conn.execute(
            "INSERT INTO gstr2b_review (id, tenant_id, line_id, status, note, updated_by,"
            " updated_at) VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(line_id) DO UPDATE SET status=excluded.status, note=excluded.note,"
            " updated_by=excluded.updated_by, updated_at=excluded.updated_at",
            (db.new_id(), tenant_id, line_id, status, note, updated_by, now),
        )
        acct.audit(conn, tenant_id, updated_by, "gstr2b.review", "gstr2b_line", line_id,
                   meta={"status": status, "previous": previous["status"] if previous else "open",
                         "note": note})
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return {"line_id": line_id, "status": status, "note": note,
            "label": REVIEW_LABELS[status], "updated_at": now}


def _bill_tax(bill, tenant_state: str) -> tuple[int, int, int]:
    tax = bill["tax_paise"] or 0
    if bill["place_of_supply_state"] == tenant_state:
        cgst, sgst = split_tax(tax)
        return 0, cgst, sgst
    return tax, 0, 0


def _money_diff(value: int) -> int:
    return value


def reconcile(conn: sqlite3.Connection, tenant_id: str, period: str) -> dict:
    date_from, date_to = acct.month_bounds(period)
    tenant = conn.execute("SELECT * FROM tenant WHERE id=?", (tenant_id,)).fetchone()
    if not tenant:
        raise Gstr2bError("TENANT_NOT_FOUND", "Business not found")
    imported = latest_import(conn, tenant_id, period)
    if not imported:
        return {"period": {"month": period, "from": date_from, "to": date_to},
                "import": None, "rows": [], "books": [], "summary": {
                    "two_b": {"count": 0, "taxable": 0, "tax": 0, "igst": 0},
                    "books": {"count": 0, "taxable": 0, "tax": 0},
                    "matched": {"count": 0, "taxable": 0, "tax": 0},
                    "mismatch": {"count": 0, "taxable": 0, "tax": 0, "difference": 0},
                    "missing_in_books": {"count": 0, "taxable": 0, "tax": 0},
                    "missing_in_2b": {"count": 0, "taxable": 0, "tax": 0},
                    "review": {s: {"count": 0, "tax": 0} for s in REVIEW_STATUSES},
                    "itc_available": 0, "itc_claimed": 0, "difference": 0},
                "warnings": ["No active GSTR-2B import for this month."]}

    lines = [dict(r) for r in conn.execute(
        "SELECT * FROM gstr2b_line WHERE import_id=? ORDER BY invoice_date, invoice_no",
        (imported["id"],)).fetchall()]
    reviews = {r["line_id"]: dict(r) for r in conn.execute(
        "SELECT r.*, u.full_name AS reviewer_name FROM gstr2b_review r"
        " LEFT JOIN user u ON u.id=r.updated_by WHERE r.tenant_id=?",
        (tenant_id,)).fetchall()}
    vendors = {((r["gstin"] or "").strip().upper()): dict(r) for r in conn.execute(
        "SELECT * FROM vendor WHERE tenant_id=?", (tenant_id,)).fetchall()}
    bills_by_vendor: dict[str, list] = {}
    for bill in conn.execute(
        "SELECT b.*, v.name AS vendor_name, v.gstin AS vendor_gstin FROM bill b"
        " JOIN vendor v ON v.id=b.vendor_id WHERE b.tenant_id=? AND b.status='posted'"
        " ORDER BY b.bill_date, b.bill_no", (tenant_id,)).fetchall():
        bills_by_vendor.setdefault(bill["vendor_id"], []).append(dict(bill))

    rows = []
    matched_bill_ids = set()
    warnings: list[str] = []
    seen_two_b: dict[tuple[str, str], str] = {}
    for line in lines:
        key = (line["supplier_gstin"], normalize_invoice(line["invoice_no"]))
        if key in seen_two_b:
            warnings.append(
                f"Duplicate invoice in GSTR-2B: {line['supplier_gstin']} / {line['invoice_no']}")
        seen_two_b[key] = line["invoice_no"]
        vendor = vendors.get(line["supplier_gstin"])
        bill = None
        note = ""
        if not line["supplier_gstin"]:
            status = "unmatched"
            note = "Supplier GSTIN is missing in GSTR-2B"
        elif not vendor:
            status = "unmatched"
            note = "Supplier GSTIN is not in the vendor master"
        else:
            target = normalize_invoice(line["invoice_no"])
            candidates = [b for b in bills_by_vendor.get(vendor["id"], [])
                          if normalize_invoice(b["vendor_bill_no"]) == target]
            if not candidates:
                status = "missing_in_books"
                note = "No posted purchase bill with this vendor invoice number"
            else:
                bill = candidates[0]
                if len(candidates) > 1:
                    warnings.append(
                        f"Multiple posted bills match {vendor['name']} / {line['invoice_no']}; matched {bill['bill_no']} first")
                matched_bill_ids.add(bill["id"])
                igst, cgst, sgst = _bill_tax(bill, tenant["state_code"])
                diffs = {
                    "taxable": bill["sub_total_paise"] - line["taxable_paise"],
                    "igst": igst - line["igst_paise"],
                    "cgst": cgst - line["cgst_paise"],
                    "sgst": sgst - line["sgst_paise"],
                    "cess": 0 - line["cess_paise"],
                }
                if all(v == 0 for v in diffs.values()):
                    status = "matched"
                else:
                    status = "mismatch"
                    parts = [f"{k} {v/100:+.2f}" for k, v in diffs.items() if v]
                    note = "Amount difference: " + ", ".join(parts)
                if bill["bill_date"] != line["invoice_date"]:
                    note = (note + "; " if note else "") + \
                        f"Bill date {bill['bill_date']} vs 2B {line['invoice_date']}"
        if line["cess_paise"]:
            note = (note + "; " if note else "") + "Cess is not tracked in purchase bills"
        if status == "unmatched" and "not in the vendor master" in note:
            warnings.append(f"Supplier not in vendor master: {line['supplier_gstin']}")
        if status == "missing_in_books":
            warnings.append(f"2B invoice missing in books: {line['supplier_gstin']} / {line['invoice_no']}")
        if status == "mismatch":
            warnings.append(f"Amount mismatch: {line['supplier_gstin']} / {line['invoice_no']}")
        line["match_status"] = status
        line["matched_bill_id"] = bill["id"] if bill else None
        line["note"] = note
        line["bill"] = bill
        line["bill_no"] = bill["bill_no"] if bill else ""
        line["bill_date"] = bill["bill_date"] if bill else ""
        line["igst_book"] = _bill_tax(bill, tenant["state_code"])[0] if bill else 0
        line["cgst_book"] = _bill_tax(bill, tenant["state_code"])[1] if bill else 0
        line["sgst_book"] = _bill_tax(bill, tenant["state_code"])[2] if bill else 0
        review = reviews.get(line["id"])
        line["review_status"] = review["status"] if review else "open"
        line["review_note"] = review["note"] if review else ""
        line["review_label"] = REVIEW_LABELS[line["review_status"]]
        line["reviewed_at"] = review["updated_at"] if review else ""
        line["reviewer_name"] = review["reviewer_name"] if review else ""
        conn.execute(
            "UPDATE gstr2b_line SET match_status=?, matched_bill_id=?, note=? WHERE id=?",
            (status, line["matched_bill_id"], note, line["id"]))
        rows.append(line)

    period_bills = []
    for bill in conn.execute(
        "SELECT b.*, v.name AS vendor_name, v.gstin AS vendor_gstin FROM bill b"
        " JOIN vendor v ON v.id=b.vendor_id WHERE b.tenant_id=? AND b.status='posted'"
        " AND b.bill_date BETWEEN ? AND ? ORDER BY b.bill_date, b.bill_no",
        (tenant_id, date_from, date_to)).fetchall():
        bill = dict(bill)
        if bill["id"] in matched_bill_ids:
            continue
        igst, cgst, sgst = _bill_tax(bill, tenant["state_code"])
        bill["igst_book"], bill["cgst_book"], bill["sgst_book"] = igst, cgst, sgst
        bill["match_status"] = "missing_in_2b"
        bill["note"] = ("Vendor GSTIN missing" if not bill["vendor_gstin"]
                        else "Posted bill not found in this GSTR-2B import")
        period_bills.append(bill)
        warnings.append(f"Book bill missing in 2B: {bill['bill_no']} / {bill['vendor_bill_no'] or ''}")

    def summary_for(items, key_tax="tax_paise", status=None):
        selected = [x for x in items if status is None or x["match_status"] == status]
        return {"count": len(selected),
                "taxable": sum(x["taxable_paise"] if "taxable_paise" in x else x["sub_total_paise"]
                               for x in selected),
                "tax": sum(x[key_tax] for x in selected)}

    two_b = {"count": imported["rows_total"], "taxable": imported["taxable_paise"],
             "tax": imported["tax_paise"], "igst": imported["igst_paise"]}
    # Books total must include matched bills too, so compute from the period query directly.
    book_rows = [dict(r) for r in conn.execute(
        "SELECT sub_total_paise, tax_paise FROM bill WHERE tenant_id=? AND status='posted'"
        " AND bill_date BETWEEN ? AND ?", (tenant_id, date_from, date_to)).fetchall()]
    books = {"count": len(book_rows),
             "taxable": sum(r["sub_total_paise"] for r in book_rows),
             "tax": sum(r["tax_paise"] for r in book_rows)}
    matched = summary_for(rows, status="matched")
    mismatch = summary_for(rows, status="mismatch")
    missing_books = summary_for(rows, status="missing_in_books")
    missing_2b = summary_for(period_bills, "tax_paise")
    mismatch["difference"] = sum(
        ((b["bill"]["tax_paise"] if b["bill"] else 0) - b["tax_paise"])
        for b in rows if b["match_status"] == "mismatch")
    review = {s: {"count": 0, "tax": 0} for s in REVIEW_STATUSES}
    for row in rows:
        bucket = review[row["review_status"]]
        bucket["count"] += 1
        bucket["tax"] += row["tax_paise"]
    if review["open"]["count"]:
        warnings.append(f"{review['open']['count']} GSTR-2B line(s) still need ITC review.")
    if review["itc_hold"]["count"]:
        warnings.append(f"{review['itc_hold']['count']} line(s) marked ITC on hold.")
    return {
        "period": {"month": period, "from": date_from, "to": date_to},
        "import": imported,
        "rows": rows,
        "books": period_bills,
        "summary": {
            "two_b": two_b, "books": books, "matched": matched, "mismatch": mismatch,
            "missing_in_books": missing_books, "missing_in_2b": missing_2b,
            "review": review,
            "itc_available": two_b["tax"], "itc_claimed": books["tax"],
            "difference": two_b["tax"] - books["tax"],
        },
        "warnings": list(dict.fromkeys(warnings)),
    }


def itc_comparison(conn: sqlite3.Connection, tenant_id: str, period: str,
                   result: dict | None = None) -> dict:
    """Compare the month's GSTR-3B eligible ITC with the imported GSTR-2B.

    The comparison is a working paper: it shows the gap, matched/mismatch and
    review hold amounts, and never posts ITC or changes a return.
    """
    result = result or reconcile(conn, tenant_id, period)
    three_b = acct.gstr3b_data(conn, tenant_id, period)
    s = result["summary"]
    two_b_itc = s["two_b"]["tax"]
    books_itc = three_b["itc"]["net_total"]
    difference = two_b_itc - books_itc
    hold = s["review"]["itc_hold"]
    open_review = s["review"]["open"]
    follow_up = s["review"]["follow_up"]
    accepted = s["review"]["accepted"]
    warnings = []
    if difference:
        warnings.append(
            f"GSTR-2B ITC differs from GSTR-3B eligible ITC by {difference / 100:+.2f}.")
    if hold["count"]:
        warnings.append(
            f"{hold['count']} line(s) with {hold['tax'] / 100:.2f} ITC are on hold; "
            "do not claim them until resolved.")
    if open_review["count"]:
        warnings.append(f"{open_review['count']} GSTR-2B line(s) are still open for review.")
    return {
        "period": result["period"],
        "two_b_itc": two_b_itc,
        "books_itc": books_itc,
        "books_itc_gross": three_b["itc"]["gross_total"],
        "books_itc_reversal": three_b["itc"]["reversal_total"],
        "difference": difference,
        "status": "ok" if difference == 0 else "check",
        "matched_tax": s["matched"]["tax"],
        "mismatch_tax": s["mismatch"]["tax"],
        "missing_in_books_tax": s["missing_in_books"]["tax"],
        "missing_in_2b_tax": s["missing_in_2b"]["tax"],
        "hold": hold,
        "follow_up": follow_up,
        "accepted": accepted,
        "open_review": open_review,
        "warnings": warnings,
    }
