"""Bulk opening-balance import from a pasted/uploaded CSV.

The importer is deliberately a thin validation layer over
:func:`app.accounting.set_opening_balance`. Every row still becomes its own
balanced opening journal against Opening Balance Equity, so the normal
audit trail, period lock, party tag and reversal rules apply unchanged.

Nothing is written until the whole file has been validated. If one row later
fails while posting, the outer transaction is rolled back and no partial
opening balance remains.
"""
from __future__ import annotations

import csv
import io
import sqlite3
from datetime import date

from . import accounting as acct
from . import money


class OpeningImportError(Exception):
    def __init__(self, message: str, preview: dict | None = None):
        super().__init__(message)
        self.message = message
        self.preview = preview


HEADER_ALIASES = {
    "code": "code", "account_code": "code", "ledger_code": "code",
    "account": "code", "ledger": "code",
    "side": "side", "dr_cr": "side", "debit_credit": "side",
    "dr/cr": "side", "debit/credit": "side",
    "balance_side": "side", "balance": "side",
    "amount": "amount", "opening_amount": "amount", "value": "amount",
    "as_of": "as_of", "date": "as_of", "opening_date": "as_of",
    "note": "note", "narration": "note", "description": "note",
}
REQUIRED_COLUMNS = ("code", "side", "amount")


def template_csv() -> str:
    return (
        "code,side,amount,as_of,note\r\n"
        "1000,debit,25000.00,2026-04-01,Cash opening balance\r\n"
        "2000,credit,18000.00,2026-04-01,Supplier opening balance\r\n"
    )


def _normalise_header(value: str) -> str:
    text = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return HEADER_ALIASES.get(text, text)


def _normalise_side(value: str) -> str:
    side = (value or "").strip().lower()
    if side in ("debit", "dr", "d"):
        return "debit"
    if side in ("credit", "cr", "c"):
        return "credit"
    return ""


def parse_csv(text: str, default_as_of: str) -> list[dict]:
    """Parse CSV text into raw rows. Raises for a missing/invalid header."""
    text = (text or "").lstrip("\ufeff")
    if not text.strip():
        raise OpeningImportError("Paste or upload a CSV with at least one opening-balance row.")

    try:
        raw = list(csv.reader(io.StringIO(text)))
    except csv.Error as exc:
        raise OpeningImportError(f"CSV could not be read: {exc}") from exc

    header_at = next((i for i, row in enumerate(raw) if any(cell.strip() for cell in row)), None)
    if header_at is None:
        raise OpeningImportError("The CSV is empty.")

    header = [_normalise_header(cell) for cell in raw[header_at]]
    if any(not name for name in header):
        raise OpeningImportError("Every CSV column needs a name.")
    if len(set(header)) != len(header):
        raise OpeningImportError("The CSV has duplicate column names.")
    missing = [name for name in REQUIRED_COLUMNS if name not in header]
    if missing:
        raise OpeningImportError(
            "CSV must have columns: code, side, amount. Optional: as_of, note."
        )

    rows = []
    for line_no, cells in enumerate(raw[header_at + 1:], start=header_at + 2):
        if not any(cell.strip() for cell in cells):
            continue
        record = {
            header[index]: (cells[index].strip() if index < len(cells) else "")
            for index in range(len(header))
        }
        if not any(record.get(name, "") for name in REQUIRED_COLUMNS):
            continue
        rows.append({
            "line": line_no,
            "code": record.get("code", "").strip().upper(),
            "side": _normalise_side(record.get("side", "")),
            "side_text": record.get("side", "").strip(),
            "amount_text": record.get("amount", "").strip(),
            "as_of": record.get("as_of", "").strip() or (default_as_of or "").strip(),
            "note": record.get("note", "").strip()[:160],
        })
    if not rows:
        raise OpeningImportError("The CSV has a header but no opening-balance rows.")
    return rows


def _date_error(value: str) -> str:
    try:
        parsed = date.fromisoformat((value or "").strip())
    except ValueError:
        return "Use a date in YYYY-MM-DD format."
    if parsed.isoformat() > date.today().isoformat():
        return "The opening date cannot be in the future."
    return ""


def preview(conn: sqlite3.Connection, tenant_id: str, text: str, default_as_of: str) -> dict:
    """Validate every row without writing anything."""
    if _date_error(default_as_of):
        raise OpeningImportError("Choose a valid default opening date (YYYY-MM-DD, not in the future).")
    parsed = parse_csv(text, default_as_of)

    accounts = {
        row["code"]: row for row in conn.execute(
            "SELECT id, code, name, type, group_code, is_postable, status FROM account"
            " WHERE tenant_id=? ORDER BY code", (tenant_id,)
        ).fetchall()
    }
    locks = conn.execute(
        "SELECT period_start, period_end FROM period_lock WHERE tenant_id=?",
        (tenant_id,),
    ).fetchall()
    equity = conn.execute(
        "SELECT id FROM account WHERE tenant_id=? AND type='equity' AND name=?",
        (tenant_id, acct.OPENING_EQUITY_NAME),
    ).fetchone()
    equity_id = equity["id"] if equity else ""

    seen: dict[str, int] = {}
    rows: list[dict] = []
    errors: list[dict] = []
    total_debit = 0
    total_credit = 0
    valid_count = 0

    for par in parsed:
        messages: list[str] = []
        code = par["code"]
        account = accounts.get(code)

        if not code:
            messages.append("Account code is required.")
        elif code in seen:
            messages.append(f"Duplicate account code; already used on line {seen[code]}.")
        else:
            seen[code] = par["line"]

        if not par["side"]:
            messages.append("Side must be debit/Dr or credit/Cr.")
        if not par["amount_text"]:
            messages.append("Amount is required.")

        amount = 0
        if par["amount_text"]:
            try:
                amount = money.parse_amount(par["amount_text"])
            except money.MoneyError as exc:
                messages.append(str(exc))
            else:
                if amount <= 0:
                    messages.append("Amount must be greater than zero.")

        as_of = par["as_of"]
        date_message = _date_error(as_of)
        if date_message:
            messages.append(date_message)

        if code and not account:
            messages.append("Account code not found in this business.")
        if account and not account["is_postable"]:
            messages.append("This account cannot receive postings.")
        if account and account["status"] != "active":
            messages.append("This account is archived; restore it before posting.")
        if account and equity_id and account["id"] == equity_id:
            messages.append("Choose a normal account; Opening Balance Equity is the balancing account.")

        if account:
            existing = conn.execute(
                "SELECT entry_no FROM journal_entry WHERE tenant_id=? AND source_type='opening'"
                " AND source_id=? AND status='posted' ORDER BY entry_no DESC LIMIT 1",
                (tenant_id, account["id"]),
            ).fetchone()
            if existing:
                messages.append(
                    f"Opening balance already set by {existing['entry_no']}; reverse it first."
                )
            earliest = conn.execute(
                """SELECT MIN(e.entry_date) AS d
                   FROM journal_entry e JOIN journal_line l ON l.entry_id=e.id
                   WHERE e.tenant_id=? AND l.account_id=? AND e.status='posted'
                     AND e.source_type!='opening'""",
                (tenant_id, account["id"]),
            ).fetchone()["d"]
            if earliest and as_of and as_of > earliest:
                messages.append(
                    f"Date must be on or before the account's first posted entry ({earliest})."
                )
            if as_of:
                for lock in locks:
                    if lock["period_start"] <= as_of <= lock["period_end"]:
                        messages.append(
                            f"The period is locked ({lock['period_start']} to {lock['period_end']})."
                        )
                        break

        row = {
            "line": par["line"],
            "code": code,
            "account_id": account["id"] if account else "",
            "account_name": account["name"] if account else "",
            "account_type": account["type"] if account else "",
            "group_code": account["group_code"] if account else "",
            "side": par["side"],
            "side_text": par["side_text"],
            "amount_paise": amount,
            "amount_text": par["amount_text"],
            "as_of": as_of,
            "note": par["note"],
            "error": " ".join(messages),
        }
        rows.append(row)
        if messages:
            errors.append({"line": par["line"], "code": code, "message": " ".join(messages)})
        else:
            valid_count += 1
            if row["side"] == "debit":
                total_debit += amount
            else:
                total_credit += amount

    return {
        "rows": rows,
        "errors": errors,
        "count": len(rows),
        "valid_count": valid_count,
        "total_debit": total_debit,
        "total_credit": total_credit,
    }


def post_import(conn: sqlite3.Connection, tenant_id: str, text: str, default_as_of: str,
                filename: str, created_by: str | None) -> dict:
    """Validate and post every row atomically. Returns the created entry IDs."""
    own_tx = not conn.in_transaction
    if own_tx:
        conn.execute("BEGIN IMMEDIATE")
    try:
        result = preview(conn, tenant_id, text, default_as_of)
        if result["errors"]:
            raise OpeningImportError(
                "Nothing was posted. Fix the highlighted rows and preview again.",
                preview=result,
            )
        entries = []
        for row in result["rows"]:
            entry_id = acct.set_opening_balance(
                conn, tenant_id, row["account_id"], row["as_of"], row["amount_paise"],
                row["side"], created_by=created_by, note=row["note"],
            )
            entries.append({
                "line": row["line"], "account_id": row["account_id"],
                "code": row["code"], "entry_id": entry_id,
            })
        acct.audit(
            conn, tenant_id, created_by, "opening_balance.bulk_import", "opening_import",
            tenant_id,
            meta={
                "filename": (filename or "pasted CSV")[:120],
                "rows": len(entries),
                "total_debit": result["total_debit"],
                "total_credit": result["total_credit"],
                "entry_ids": [entry["entry_id"] for entry in entries],
            },
        )
        if own_tx:
            conn.execute("COMMIT")
    except Exception:
        if own_tx and conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return {
        "count": len(entries),
        "total_debit": result["total_debit"],
        "total_credit": result["total_credit"],
        "entries": entries,
        "preview": result,
    }
