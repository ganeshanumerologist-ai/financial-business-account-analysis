"""Draft documents and maker-checker approval.

Drafts never touch the ledger, stock, tax-invoice numbers or receivables.
Posting a draft uses the same accounting functions as a direct entry, so all
balanced-posting, tenant and period rules still apply. Nothing here mutates a
posted journal; approvals are additive workflow records around the existing
accounting core.
"""
from __future__ import annotations

import sqlite3
from datetime import date

from . import accounting as acct
from . import db

BILL_DRAFT_STATUSES = ("draft", "pending", "approved", "rejected", "posted", "void")
JOURNAL_DRAFT_STATUSES = ("draft", "pending", "approved", "rejected", "posted", "void")


def _today() -> str:
    return date.today().isoformat()


def _clean_date(value: str, field: str) -> str:
    try:
        return date.fromisoformat((value or "").strip()).isoformat()
    except ValueError as exc:
        raise acct.AccountingError("BAD_DATE", f"Choose a valid {field}.") from exc


def _bill_draft(conn: sqlite3.Connection, tenant_id: str, draft_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM bill_draft WHERE id=? AND tenant_id=?", (draft_id, tenant_id)
    ).fetchone()
    if not row:
        raise acct.AccountingError("DRAFT_NOT_FOUND", "Bill draft not found in this business")
    return row


def _journal_draft(conn: sqlite3.Connection, tenant_id: str, draft_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM journal_draft WHERE id=? AND tenant_id=?", (draft_id, tenant_id)
    ).fetchone()
    if not row:
        raise acct.AccountingError("DRAFT_NOT_FOUND", "Journal draft not found in this business")
    return row


def bill_draft_lines(conn: sqlite3.Connection, tenant_id: str, draft_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM bill_draft_line WHERE draft_id=? AND tenant_id=? ORDER BY rowid",
        (draft_id, tenant_id),
    ).fetchall()


def journal_draft_lines(conn: sqlite3.Connection, tenant_id: str,
                        draft_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT l.*, a.code, a.name FROM journal_draft_line l"
        " JOIN account a ON a.id=l.account_id"
        " WHERE l.draft_id=? AND l.tenant_id=? ORDER BY l.line_no",
        (draft_id, tenant_id),
    ).fetchall()


def _bill_items_from_lines(conn: sqlite3.Connection, tenant_id: str,
                           draft_id: str) -> list[dict]:
    return [
        {"item_id": r["item_id"], "qty": r["qty_milli"], "unit_price": r["unit_price_paise"],
         "discount": r["discount_paise"], "tax_rate_bp": r["tax_rate_bp"],
         "description": r["description"]}
        for r in bill_draft_lines(conn, tenant_id, draft_id)
    ]


def _journal_lines_from_draft(conn: sqlite3.Connection, tenant_id: str,
                              draft_id: str) -> list[dict]:
    return [
        {"account_id": r["account_id"], "debit": r["debit_paise"],
         "credit": r["credit_paise"], "memo": r["memo"],
         "dimension_id": r["dimension_id"]}
        for r in journal_draft_lines(conn, tenant_id, draft_id)
    ]


def save_bill_draft(conn: sqlite3.Connection, tenant_id: str, vendor_id: str, bill_date: str,
                    vendor_bill_no: str, place_of_supply_state: str, items: list[dict],
                    round_to_rupee: bool = False, created_by: str | None = None) -> dict:
    """Save a purchase bill as an unposted draft."""
    vendor = acct._doc_or_raise(conn, tenant_id, "vendor", vendor_id, "Vendor")
    bill_date = _clean_date(bill_date, "bill date")
    prep = acct._prepare_bill_lines(conn, tenant_id, items, round_to_rupee=round_to_rupee)
    if prep["total"] <= 0:
        raise acct.AccountingError("BAD_AMOUNT", "Bill total must be greater than zero")
    draft_id = db.new_id()
    draft_no = db.next_number(conn, tenant_id, "bill_draft", "DRAFT-BILL")
    now = db.now()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "INSERT INTO bill_draft (id, tenant_id, draft_no, bill_date, vendor_id,"
            " vendor_bill_no, place_of_supply_state, sub_total_paise, tax_paise,"
            " round_off_paise, total_paise, round_to_rupee, status, created_by,"
            " created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'draft', ?,?,?)",
            (draft_id, tenant_id, draft_no, bill_date, vendor["id"], (vendor_bill_no or "")[:60],
             place_of_supply_state, prep["sub_total"], prep["tax_total"], prep["round_off"],
             prep["total"], 1 if round_to_rupee else 0, created_by, now, now),
        )
        for c in prep["computed"]:
            conn.execute(
                "INSERT INTO bill_draft_line (id, tenant_id, draft_id, item_id, description,"
                " qty_milli, unit_price_paise, gross_paise, discount_paise, taxable_paise,"
                " tax_rate_bp, tax_paise, line_total_paise)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (db.new_id(), tenant_id, draft_id, c["item_id"], c["description"],
                 c["qty_milli"], c["unit_price_paise"], c["gross_paise"], c["discount_paise"],
                 c["taxable_paise"], c["tax_rate_bp"], c["tax_paise"], c["line_total_paise"]),
            )
        acct.audit(conn, tenant_id, created_by, "bill.draft_create", "bill_draft", draft_id,
                   meta={"total": prep["total"], "draft_no": draft_no,
                         "lines": len(prep["computed"])})
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return dict(_bill_draft(conn, tenant_id, draft_id))


def update_bill_draft(conn: sqlite3.Connection, tenant_id: str, draft_id: str, vendor_id: str,
                      bill_date: str, vendor_bill_no: str, place_of_supply_state: str,
                      items: list[dict], round_to_rupee: bool = False,
                      created_by: str | None = None) -> dict:
    draft = _bill_draft(conn, tenant_id, draft_id)
    if draft["status"] not in ("draft", "rejected"):
        raise acct.AccountingError(
            "DRAFT_NOT_EDITABLE",
            "Only a draft or rejected bill can be edited. Pending approval must be rejected first.",
        )
    vendor = acct._doc_or_raise(conn, tenant_id, "vendor", vendor_id, "Vendor")
    bill_date = _clean_date(bill_date, "bill date")
    prep = acct._prepare_bill_lines(conn, tenant_id, items, round_to_rupee=round_to_rupee)
    if prep["total"] <= 0:
        raise acct.AccountingError("BAD_AMOUNT", "Bill total must be greater than zero")
    now = db.now()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "UPDATE bill_draft SET bill_date=?, vendor_id=?, vendor_bill_no=?,"
            " place_of_supply_state=?, sub_total_paise=?, tax_paise=?, round_off_paise=?,"
            " total_paise=?, round_to_rupee=?, status='draft', rejection_reason='',"
            " updated_at=? WHERE id=? AND tenant_id=?",
            (bill_date, vendor["id"], (vendor_bill_no or "")[:60], place_of_supply_state,
             prep["sub_total"], prep["tax_total"], prep["round_off"], prep["total"],
             1 if round_to_rupee else 0, now, draft_id, tenant_id),
        )
        conn.execute("DELETE FROM bill_draft_line WHERE draft_id=? AND tenant_id=?",
                     (draft_id, tenant_id))
        for c in prep["computed"]:
            conn.execute(
                "INSERT INTO bill_draft_line (id, tenant_id, draft_id, item_id, description,"
                " qty_milli, unit_price_paise, gross_paise, discount_paise, taxable_paise,"
                " tax_rate_bp, tax_paise, line_total_paise)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (db.new_id(), tenant_id, draft_id, c["item_id"], c["description"],
                 c["qty_milli"], c["unit_price_paise"], c["gross_paise"], c["discount_paise"],
                 c["taxable_paise"], c["tax_rate_bp"], c["tax_paise"], c["line_total_paise"]),
            )
        acct.audit(conn, tenant_id, created_by, "bill.draft_update", "bill_draft", draft_id,
                   meta={"total": prep["total"], "draft_no": draft["draft_no"],
                         "lines": len(prep["computed"])})
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return dict(_bill_draft(conn, tenant_id, draft_id))


def submit_bill_draft(conn: sqlite3.Connection, tenant_id: str, draft_id: str,
                      submitted_by: str | None = None) -> dict:
    draft = _bill_draft(conn, tenant_id, draft_id)
    if draft["status"] not in ("draft", "rejected"):
        raise acct.AccountingError("DRAFT_NOT_SUBMITTABLE",
                                   "Only a draft or rejected bill can be submitted")
    now = db.now()
    conn.execute(
        "UPDATE bill_draft SET status='pending', submitted_at=?, rejection_reason='',"
        " updated_at=? WHERE id=? AND tenant_id=?",
        (now, now, draft_id, tenant_id),
    )
    acct.audit(conn, tenant_id, submitted_by, "bill.draft_submit", "bill_draft", draft_id,
               meta={"draft_no": draft["draft_no"]})
    return dict(_bill_draft(conn, tenant_id, draft_id))


def _post_bill_draft(conn: sqlite3.Connection, tenant_id: str, draft_id: str,
                     actor: str | None, require_pending: bool) -> dict:
    draft = _bill_draft(conn, tenant_id, draft_id)
    if draft["status"] == "posted":
        return dict(draft)
    if draft["status"] not in (("pending",) if require_pending else ("draft", "pending", "rejected")):
        raise acct.AccountingError("DRAFT_NOT_POSTABLE",
                                   "This bill draft cannot be posted in its current state")
    bill = acct.create_bill(
        conn, tenant_id, draft["vendor_id"], draft["bill_date"], draft["vendor_bill_no"],
        draft["place_of_supply_state"], _bill_items_from_lines(conn, tenant_id, draft_id),
        idempotency_key=f"bill-draft-{draft_id}",
        round_to_rupee=bool(draft["round_to_rupee"]), created_by=actor,
    )
    conn.execute(
        "UPDATE bill_draft SET status='posted', posted_bill_id=?, approved_by=?,"
        " approved_at=?, updated_at=? WHERE id=? AND tenant_id=?",
        (bill["id"], actor, db.now(), db.now(), draft_id, tenant_id),
    )
    acct.audit(conn, tenant_id, actor, "bill.draft_post", "bill_draft", draft_id,
               meta={"draft_no": draft["draft_no"], "bill_id": bill["id"],
                     "bill_no": bill["bill_no"], "total": bill["total_paise"]})
    return dict(_bill_draft(conn, tenant_id, draft_id))


def approve_bill_draft(conn: sqlite3.Connection, tenant_id: str, draft_id: str,
                       approved_by: str | None = None) -> dict:
    """Approve a pending bill and post it to the ledger/stock."""
    return _post_bill_draft(conn, tenant_id, draft_id, approved_by, require_pending=True)


def post_bill_draft(conn: sqlite3.Connection, tenant_id: str, draft_id: str,
                    posted_by: str | None = None) -> dict:
    """Post a bill draft directly (used when the actor may approve/post)."""
    return _post_bill_draft(conn, tenant_id, draft_id, posted_by, require_pending=False)


def reject_bill_draft(conn: sqlite3.Connection, tenant_id: str, draft_id: str, reason: str,
                      rejected_by: str | None = None) -> dict:
    if not reason or not reason.strip():
        raise acct.AccountingError("REASON_REQUIRED", "A rejection reason is required")
    draft = _bill_draft(conn, tenant_id, draft_id)
    if draft["status"] != "pending":
        raise acct.AccountingError("DRAFT_NOT_PENDING", "Only a pending bill can be rejected")
    now = db.now()
    conn.execute(
        "UPDATE bill_draft SET status='rejected', rejection_reason=?, approved_by=?,"
        " approved_at=?, updated_at=? WHERE id=? AND tenant_id=?",
        (reason.strip()[:300], rejected_by, now, now, draft_id, tenant_id),
    )
    acct.audit(conn, tenant_id, rejected_by, "bill.draft_reject", "bill_draft", draft_id,
               meta={"draft_no": draft["draft_no"], "reason": reason.strip()[:200]})
    return dict(_bill_draft(conn, tenant_id, draft_id))


def void_bill_draft(conn: sqlite3.Connection, tenant_id: str, draft_id: str, reason: str,
                    voided_by: str | None = None) -> dict:
    if not reason or not reason.strip():
        raise acct.AccountingError("REASON_REQUIRED", "A void reason is required")
    draft = _bill_draft(conn, tenant_id, draft_id)
    if draft["status"] == "void":
        return dict(draft)
    if draft["status"] == "posted":
        raise acct.AccountingError("DRAFT_POSTED", "A posted bill draft cannot be voided here")
    now = db.now()
    conn.execute(
        "UPDATE bill_draft SET status='void', rejection_reason=?, updated_at=?"
        " WHERE id=? AND tenant_id=?",
        (reason.strip()[:300], now, draft_id, tenant_id),
    )
    acct.audit(conn, tenant_id, voided_by, "bill.draft_void", "bill_draft", draft_id,
               meta={"draft_no": draft["draft_no"], "reason": reason.strip()[:200]})
    return dict(_bill_draft(conn, tenant_id, draft_id))


# --------------------------------------------------------------------------
# journal drafts
# --------------------------------------------------------------------------

def save_journal_draft(conn: sqlite3.Connection, tenant_id: str, entry_date: str,
                       narration: str, lines: list[dict], is_intercompany: bool = False,
                       created_by: str | None = None) -> dict:
    entry_date = _clean_date(entry_date, "journal date")
    narration = (narration or "").strip()
    if len(narration) < 3:
        raise acct.AccountingError("NARRATION_REQUIRED", "Enter a narration")
    clean = acct.validate_journal_lines(conn, tenant_id, entry_date, lines)
    draft_id = db.new_id()
    draft_no = db.next_number(conn, tenant_id, "journal_draft", "DRAFT-JV")
    now = db.now()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "INSERT INTO journal_draft (id, tenant_id, draft_no, entry_date, narration,"
            " is_intercompany, status, created_by, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?, 'draft', ?,?,?)",
            (draft_id, tenant_id, draft_no, entry_date, narration,
             1 if is_intercompany else 0, created_by, now, now),
        )
        for i, (account_id, debit, credit, memo, party_id, dimension_id) in enumerate(clean, 1):
            conn.execute(
                "INSERT INTO journal_draft_line (id, tenant_id, draft_id, line_no, account_id,"
                " dimension_id, debit_paise, credit_paise, memo) VALUES (?,?,?,?,?,?,?,?,?)",
                (db.new_id(), tenant_id, draft_id, i, account_id, dimension_id, debit, credit,
                 memo),
            )
        acct.audit(conn, tenant_id, created_by, "journal.draft_create", "journal_draft", draft_id,
                   meta={"draft_no": draft_no, "lines": len(clean),
                         "amount": sum(c[1] for c in clean)})
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return dict(_journal_draft(conn, tenant_id, draft_id))


def update_journal_draft(conn: sqlite3.Connection, tenant_id: str, draft_id: str,
                         entry_date: str, narration: str, lines: list[dict],
                         is_intercompany: bool = False, created_by: str | None = None) -> dict:
    draft = _journal_draft(conn, tenant_id, draft_id)
    if draft["status"] not in ("draft", "rejected"):
        raise acct.AccountingError(
            "DRAFT_NOT_EDITABLE",
            "Only a draft or rejected journal can be edited. Pending approval must be rejected first.",
        )
    entry_date = _clean_date(entry_date, "journal date")
    narration = (narration or "").strip()
    if len(narration) < 3:
        raise acct.AccountingError("NARRATION_REQUIRED", "Enter a narration")
    clean = acct.validate_journal_lines(conn, tenant_id, entry_date, lines)
    now = db.now()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "UPDATE journal_draft SET entry_date=?, narration=?, is_intercompany=?,"
            " status='draft', rejection_reason='', updated_at=? WHERE id=? AND tenant_id=?",
            (entry_date, narration, 1 if is_intercompany else 0, now, draft_id, tenant_id),
        )
        conn.execute("DELETE FROM journal_draft_line WHERE draft_id=? AND tenant_id=?",
                     (draft_id, tenant_id))
        for i, (account_id, debit, credit, memo, party_id, dimension_id) in enumerate(clean, 1):
            conn.execute(
                "INSERT INTO journal_draft_line (id, tenant_id, draft_id, line_no, account_id,"
                " dimension_id, debit_paise, credit_paise, memo) VALUES (?,?,?,?,?,?,?,?,?)",
                (db.new_id(), tenant_id, draft_id, i, account_id, dimension_id, debit, credit,
                 memo),
            )
        acct.audit(conn, tenant_id, created_by, "journal.draft_update", "journal_draft", draft_id,
                   meta={"draft_no": draft["draft_no"], "lines": len(clean),
                         "amount": sum(c[1] for c in clean)})
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return dict(_journal_draft(conn, tenant_id, draft_id))


def submit_journal_draft(conn: sqlite3.Connection, tenant_id: str, draft_id: str,
                         submitted_by: str | None = None) -> dict:
    draft = _journal_draft(conn, tenant_id, draft_id)
    if draft["status"] not in ("draft", "rejected"):
        raise acct.AccountingError("DRAFT_NOT_SUBMITTABLE",
                                   "Only a draft or rejected journal can be submitted")
    now = db.now()
    conn.execute(
        "UPDATE journal_draft SET status='pending', submitted_at=?, rejection_reason='',"
        " updated_at=? WHERE id=? AND tenant_id=?",
        (now, now, draft_id, tenant_id),
    )
    acct.audit(conn, tenant_id, submitted_by, "journal.draft_submit", "journal_draft", draft_id,
               meta={"draft_no": draft["draft_no"]})
    return dict(_journal_draft(conn, tenant_id, draft_id))


def _post_journal_draft(conn: sqlite3.Connection, tenant_id: str, draft_id: str,
                        actor: str | None, require_pending: bool) -> dict:
    draft = _journal_draft(conn, tenant_id, draft_id)
    if draft["status"] == "posted":
        return dict(draft)
    if draft["status"] not in (("pending",) if require_pending else ("draft", "pending", "rejected")):
        raise acct.AccountingError("DRAFT_NOT_POSTABLE",
                                   "This journal draft cannot be posted in its current state")
    entry_id = acct.post_journal(
        conn, tenant_id, draft["entry_date"], draft["narration"],
        _journal_lines_from_draft(conn, tenant_id, draft_id), source_type="manual",
        source_id=draft_id, idempotency_key=f"journal-draft-{draft_id}", created_by=actor,
        is_intercompany=bool(draft["is_intercompany"]),
    )
    conn.execute(
        "UPDATE journal_draft SET status='posted', posted_entry_id=?, approved_by=?,"
        " approved_at=?, updated_at=? WHERE id=? AND tenant_id=?",
        (entry_id, actor, db.now(), db.now(), draft_id, tenant_id),
    )
    acct.audit(conn, tenant_id, actor, "journal.draft_post", "journal_draft", draft_id,
               meta={"draft_no": draft["draft_no"], "entry_id": entry_id})
    return dict(_journal_draft(conn, tenant_id, draft_id))


def approve_journal_draft(conn: sqlite3.Connection, tenant_id: str, draft_id: str,
                          approved_by: str | None = None) -> dict:
    return _post_journal_draft(conn, tenant_id, draft_id, approved_by, require_pending=True)


def post_journal_draft(conn: sqlite3.Connection, tenant_id: str, draft_id: str,
                       posted_by: str | None = None) -> dict:
    return _post_journal_draft(conn, tenant_id, draft_id, posted_by, require_pending=False)


def reject_journal_draft(conn: sqlite3.Connection, tenant_id: str, draft_id: str, reason: str,
                         rejected_by: str | None = None) -> dict:
    if not reason or not reason.strip():
        raise acct.AccountingError("REASON_REQUIRED", "A rejection reason is required")
    draft = _journal_draft(conn, tenant_id, draft_id)
    if draft["status"] != "pending":
        raise acct.AccountingError("DRAFT_NOT_PENDING", "Only a pending journal can be rejected")
    now = db.now()
    conn.execute(
        "UPDATE journal_draft SET status='rejected', rejection_reason=?, approved_by=?,"
        " approved_at=?, updated_at=? WHERE id=? AND tenant_id=?",
        (reason.strip()[:300], rejected_by, now, now, draft_id, tenant_id),
    )
    acct.audit(conn, tenant_id, rejected_by, "journal.draft_reject", "journal_draft", draft_id,
               meta={"draft_no": draft["draft_no"], "reason": reason.strip()[:200]})
    return dict(_journal_draft(conn, tenant_id, draft_id))


def void_journal_draft(conn: sqlite3.Connection, tenant_id: str, draft_id: str, reason: str,
                       voided_by: str | None = None) -> dict:
    if not reason or not reason.strip():
        raise acct.AccountingError("REASON_REQUIRED", "A void reason is required")
    draft = _journal_draft(conn, tenant_id, draft_id)
    if draft["status"] == "void":
        return dict(draft)
    if draft["status"] == "posted":
        raise acct.AccountingError("DRAFT_POSTED", "A posted journal draft cannot be voided here")
    now = db.now()
    conn.execute(
        "UPDATE journal_draft SET status='void', rejection_reason=?, updated_at=?"
        " WHERE id=? AND tenant_id=?",
        (reason.strip()[:300], now, draft_id, tenant_id),
    )
    acct.audit(conn, tenant_id, voided_by, "journal.draft_void", "journal_draft", draft_id,
               meta={"draft_no": draft["draft_no"], "reason": reason.strip()[:200]})
    return dict(_journal_draft(conn, tenant_id, draft_id))


# --------------------------------------------------------------------------
# invoice approval
# --------------------------------------------------------------------------

def submit_invoice_draft(conn: sqlite3.Connection, tenant_id: str, invoice_id: str,
                         submitted_by: str | None = None) -> dict:
    inv = acct._doc_or_raise(conn, tenant_id, "invoice", invoice_id, "Invoice")
    if inv["status"] != "draft":
        raise acct.AccountingError("INVOICE_NOT_DRAFT", "Only a draft invoice can be submitted")
    approval = inv["approval_status"] if "approval_status" in inv.keys() else "draft"
    if approval == "pending":
        return dict(inv)
    if approval not in ("draft", "rejected"):
        raise acct.AccountingError("INVOICE_NOT_SUBMITTABLE",
                                   "This invoice cannot be submitted in its current state")
    now = db.now()
    conn.execute(
        "UPDATE invoice SET approval_status='pending', submitted_at=?, rejection_reason=''"
        " WHERE id=? AND tenant_id=? AND status='draft'",
        (now, invoice_id, tenant_id),
    )
    acct.audit(conn, tenant_id, submitted_by, "invoice.draft_submit", "invoice", invoice_id,
               meta={"invoice_no": inv["invoice_no"]})
    return dict(conn.execute("SELECT * FROM invoice WHERE id=?", (invoice_id,)).fetchone())


def approve_invoice_draft(conn: sqlite3.Connection, tenant_id: str, invoice_id: str,
                          approved_by: str | None = None) -> dict:
    inv = acct._doc_or_raise(conn, tenant_id, "invoice", invoice_id, "Invoice")
    if inv["status"] == "posted":
        return dict(inv)
    approval = inv["approval_status"] if "approval_status" in inv.keys() else "draft"
    if approval != "pending":
        raise acct.AccountingError("INVOICE_NOT_PENDING",
                                   "Only an invoice submitted for approval can be approved")
    return acct.post_draft_invoice(conn, tenant_id, invoice_id, created_by=approved_by)


def reject_invoice_draft(conn: sqlite3.Connection, tenant_id: str, invoice_id: str, reason: str,
                         rejected_by: str | None = None) -> dict:
    if not reason or not reason.strip():
        raise acct.AccountingError("REASON_REQUIRED", "A rejection reason is required")
    inv = acct._doc_or_raise(conn, tenant_id, "invoice", invoice_id, "Invoice")
    if inv["status"] != "draft":
        raise acct.AccountingError("INVOICE_NOT_DRAFT", "Only a draft invoice can be rejected")
    approval = inv["approval_status"] if "approval_status" in inv.keys() else "draft"
    if approval != "pending":
        raise acct.AccountingError("INVOICE_NOT_PENDING", "Only a pending invoice can be rejected")
    now = db.now()
    conn.execute(
        "UPDATE invoice SET approval_status='rejected', rejection_reason=?, approved_by=?,"
        " approved_at=? WHERE id=? AND tenant_id=?",
        (reason.strip()[:300], rejected_by, now, invoice_id, tenant_id),
    )
    acct.audit(conn, tenant_id, rejected_by, "invoice.draft_reject", "invoice", invoice_id,
               meta={"invoice_no": inv["invoice_no"], "reason": reason.strip()[:200]})
    return dict(conn.execute("SELECT * FROM invoice WHERE id=?", (invoice_id,)).fetchone())


def withdraw_invoice_draft(conn: sqlite3.Connection, tenant_id: str, invoice_id: str,
                           withdrawn_by: str | None = None) -> dict:
    inv = acct._doc_or_raise(conn, tenant_id, "invoice", invoice_id, "Invoice")
    if inv["status"] != "draft":
        raise acct.AccountingError("INVOICE_NOT_DRAFT", "Only a draft invoice can be withdrawn")
    approval = inv["approval_status"] if "approval_status" in inv.keys() else "draft"
    if approval != "pending":
        raise acct.AccountingError("INVOICE_NOT_PENDING", "Only a pending invoice can be withdrawn")
    conn.execute(
        "UPDATE invoice SET approval_status='draft', submitted_at=NULL"
        " WHERE id=? AND tenant_id=?",
        (invoice_id, tenant_id),
    )
    acct.audit(conn, tenant_id, withdrawn_by, "invoice.draft_withdraw", "invoice", invoice_id,
               meta={"invoice_no": inv["invoice_no"]})
    return dict(conn.execute("SELECT * FROM invoice WHERE id=?", (invoice_id,)).fetchone())


# --------------------------------------------------------------------------
# queues
# --------------------------------------------------------------------------

def list_bill_drafts(conn: sqlite3.Connection, tenant_id: str,
                     statuses: tuple[str, ...] | None = None) -> list[sqlite3.Row]:
    sql = ("SELECT d.*, v.name AS vendor_name FROM bill_draft d"
           " JOIN vendor v ON v.id=d.vendor_id WHERE d.tenant_id=?")
    params: list = [tenant_id]
    if statuses:
        sql += " AND d.status IN (" + ",".join("?" for _ in statuses) + ")"
        params.extend(statuses)
    sql += " ORDER BY d.updated_at DESC, d.draft_no DESC"
    return conn.execute(sql, params).fetchall()


def list_journal_drafts(conn: sqlite3.Connection, tenant_id: str,
                        statuses: tuple[str, ...] | None = None) -> list[sqlite3.Row]:
    sql = "SELECT * FROM journal_draft WHERE tenant_id=?"
    params: list = [tenant_id]
    if statuses:
        sql += " AND status IN (" + ",".join("?" for _ in statuses) + ")"
        params.extend(statuses)
    sql += " ORDER BY updated_at DESC, draft_no DESC"
    return conn.execute(sql, params).fetchall()


def pending_approvals(conn: sqlite3.Connection, tenant_id: str) -> list[dict]:
    rows: list[dict] = []
    for r in list_bill_drafts(conn, tenant_id, ("pending",)):
        rows.append({"kind": "bill", "id": r["id"], "no": r["draft_no"],
                     "date": r["bill_date"], "party": r["vendor_name"],
                     "total": r["total_paise"], "created_by": r["created_by"]})
    for r in list_journal_drafts(conn, tenant_id, ("pending",)):
        amount = conn.execute(
            "SELECT COALESCE(SUM(debit_paise),0) a FROM journal_draft_line"
            " WHERE draft_id=? AND tenant_id=?", (r["id"], tenant_id)).fetchone()["a"]
        rows.append({"kind": "journal", "id": r["id"], "no": r["draft_no"],
                     "date": r["entry_date"], "party": r["narration"],
                     "total": amount, "created_by": r["created_by"]})
    for r in conn.execute(
            "SELECT * FROM invoice WHERE tenant_id=? AND status='draft'"
            " AND approval_status='pending' ORDER BY submitted_at, invoice_date",
            (tenant_id,)).fetchall():
        customer = conn.execute("SELECT name FROM customer WHERE id=?",
                                (r["customer_id"],)).fetchone()
        rows.append({"kind": "invoice", "id": r["id"], "no": r["invoice_no"],
                     "date": r["invoice_date"], "party": customer["name"] if customer else "",
                     "total": r["total_paise"], "created_by": r["created_by"]
                     if "created_by" in r.keys() else None})
    rows.sort(key=lambda x: (x["date"] or "", x["no"] or ""))
    return rows


def count_pending_approvals(conn: sqlite3.Connection, tenant_id: str) -> int:
    return len(pending_approvals(conn, tenant_id))
