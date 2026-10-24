"""Bank statement import and reconciliation (stdlib only).

Design rules:
  * A bank statement line never creates a journal entry by itself. It is matched
    to an existing posted journal line on the bank account, so the ledger stays
    the single source of truth.
  * Matching is amount-exact. Dates may differ by a configurable window because
    banks post a day or two after the entry date.
  * Imports are idempotent per (tenant, bank account, row hash).
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import sqlite3
from datetime import date, datetime

from . import db
from .accounting import audit
from .money import MoneyError, parse_amount

BANK_ACCOUNT_CODE = "1010"
DEFAULT_WINDOW_DAYS = 7


class BankError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# --------------------------------------------------------------------------
# CSV parsing
# --------------------------------------------------------------------------

def _norm_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


ALIASES: dict[str, set[str]] = {
    "date": {"date", "txndate", "transactiondate", "valuedate", "postingdate", "bookdate"},
    "description": {"description", "narration", "particulars", "details",
                    "transactiondetails", "remarks", "narrative"},
    "reference": {"reference", "ref", "referenceno", "chequeno", "chqno", "chq",
                  "transactionid", "utr", "utrno", "instrumentno"},
    "debit": {"debit", "debitamount", "withdrawal", "withdrawals", "withdrawalamt",
              "withdrawalamount", "dr", "paidout", "moneyout", "outflow"},
    "credit": {"credit", "creditamount", "deposit", "deposits", "depositamt",
               "depositamount", "cr", "paidin", "moneyin", "inflow"},
    "amount": {"amount", "transactionamount", "amt", "value"},
    "type": {"type", "direction", "drcr", "debitcredit", "txntype", "transactiontype"},
    "balance": {"balance", "closingbalance", "runningbalance", "balanceamount",
                "availablebalance"},
}

DATE_FORMATS = (
    "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%d %b %Y", "%d-%b-%Y", "%d/%b/%Y", "%d %B %Y",
    "%Y/%m/%d", "%Y.%m.%d", "%b %d, %Y",
)

DR_WORDS = {"dr", "debit", "d", "withdrawal", "withdrawals", "out", "paidout",
            "payment", "w"}
CR_WORDS = {"cr", "credit", "c", "deposit", "deposits", "in", "paidin",
            "receipt", "dep"}


def parse_date(value: str) -> str:
    text = (value or "").strip()
    if not text:
        raise BankError("BAD_DATE", "Statement row has no date")
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        try:
            return date.fromisoformat(text[:10]).isoformat()
        except ValueError:
            pass
    cleaned = re.sub(r"\s+", " ", text)
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    raise BankError("BAD_DATE", f"Unrecognised date: {value!r} (use YYYY-MM-DD or DD/MM/YYYY)")


def _parse_money(value: str, *, allow_blank: bool = True, allow_negative: bool = False) -> int | None:
    text = (value or "").strip()
    if not text or text in {"-", "--", "—"}:
        if allow_blank:
            return 0
        return None
    text = re.sub(r"(?i)\s*(cr|dr)$", "", text).strip()
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()
    if text.startswith("-"):
        negative = True
        text = text[1:].strip()
    try:
        amount = parse_amount(text)
    except MoneyError as exc:
        raise BankError("BAD_AMOUNT", f"Unrecognised amount {value!r}: {exc}") from exc
    if negative:
        if not allow_negative:
            raise BankError("BAD_AMOUNT", f"Negative amount not allowed here: {value!r}")
        amount = -amount
    return amount


def _column_map(header: list[str]) -> dict[str, int]:
    found: dict[str, int] = {}
    for idx, name in enumerate(header):
        norm = _norm_header(name)
        for field, aliases in ALIASES.items():
            if norm in aliases and field not in found:
                found[field] = idx
                break
    return found


def _cell(row: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    return row[idx]


def parse_csv(text: str) -> list[dict]:
    """Parse a bank CSV into normalised rows.

    Accepted layouts:
      * Date, Description, Reference, Debit, Credit, Balance
      * Date, Narration, Amount, Dr/Cr
      * Date, Particulars, Withdrawal Amt, Deposit Amt

    Returns rows with integer paise and ISO dates. Raises BankError on bad input.
    """
    raw = (text or "").lstrip("\ufeff")
    if not raw.strip():
        raise BankError("EMPTY_CSV", "Paste or choose a CSV file first")

    lines = raw.splitlines()
    header_at = None
    for i, line in enumerate(lines[:20]):
        norm = _norm_header(line)
        if "date" in norm and any(k in norm for k in
                                  ("debit", "credit", "withdrawal", "deposit", "amount")):
            header_at = i
            break
    if header_at is None:
        raise BankError(
            "NO_HEADER",
            "Could not find a header row. Include Date and Debit/Credit (or Amount) columns.",
        )

    reader = csv.reader(io.StringIO("\n".join(lines[header_at:])))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise BankError("EMPTY_CSV", "The CSV has no header row") from exc

    cols = _column_map(header)
    if "date" not in cols:
        raise BankError("NO_DATE_COLUMN", "The CSV needs a Date column")
    if "debit" not in cols and "credit" not in cols and "amount" not in cols:
        raise BankError("NO_AMOUNT_COLUMN",
                        "The CSV needs Debit and Credit columns, or an Amount column")

    out: list[dict] = []
    for line_no, row in enumerate(reader, start=header_at + 2):
        if not row or not any((c or "").strip() for c in row):
            continue
        date_text = _cell(row, cols.get("date")).strip()
        if not date_text:
            continue  # summary/footer rows commonly have no date
        try:
            txn_date = parse_date(date_text)
            description = (_cell(row, cols.get("description")).strip()
                           or _cell(row, cols.get("reference")).strip()
                           or "Bank transaction")
            reference = _cell(row, cols.get("reference")).strip()

            if "debit" in cols or "credit" in cols:
                debit = _parse_money(_cell(row, cols.get("debit"))) or 0
                credit = _parse_money(_cell(row, cols.get("credit"))) or 0
                if debit and credit:
                    raise BankError("BAD_ROW", "Both debit and credit are set")
            else:
                amount = _parse_money(_cell(row, cols.get("amount")),
                                      allow_blank=False, allow_negative=True) or 0
                type_text = _norm_header(_cell(row, cols.get("type")))
                if type_text:
                    if type_text in DR_WORDS:
                        debit, credit = abs(amount), 0
                    elif type_text in CR_WORDS:
                        debit, credit = 0, abs(amount)
                    else:
                        raise BankError("BAD_TYPE", f"Unknown Dr/Cr value {type_text!r}")
                elif amount < 0:
                    debit, credit = -amount, 0
                else:
                    debit, credit = 0, amount

            if debit < 0 or credit < 0:
                raise BankError("BAD_AMOUNT", "Debit/credit cannot be negative")
            if debit == 0 and credit == 0:
                continue
            balance = None
            if "balance" in cols:
                balance_text = _cell(row, cols.get("balance")).strip()
                if balance_text and balance_text not in {"-", "--", "—"}:
                    balance = _parse_money(balance_text, allow_blank=True,
                                           allow_negative=True)
        except BankError as exc:
            raise BankError(exc.code, f"Line {line_no}: {exc.message}") from exc

        out.append({
            "txn_date": txn_date,
            "description": description[:240],
            "reference": reference[:120],
            "debit_paise": debit,
            "credit_paise": credit,
            "balance_paise": balance,
        })

    if not out:
        raise BankError("NO_ROWS", "No usable transaction rows were found in the CSV")
    return out


def _row_hash(account_id: str, row: dict) -> str:
    desc = re.sub(r"\s+", " ", row["description"]).strip().lower()
    ref = re.sub(r"\s+", " ", row["reference"]).strip().lower()
    key = "|".join((account_id, row["txn_date"], desc, ref,
                    str(row["debit_paise"]), str(row["credit_paise"])))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# accounts / import
# --------------------------------------------------------------------------

def bank_accounts(conn: sqlite3.Connection, tenant_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM account WHERE tenant_id=? AND code=? AND type='asset' ORDER BY code",
        (tenant_id, BANK_ACCOUNT_CODE),
    ).fetchall()
    return [dict(r) for r in rows]


def _bank_account(conn: sqlite3.Connection, tenant_id: str, account_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM account WHERE id=? AND tenant_id=?", (account_id, tenant_id)
    ).fetchone()
    if not row:
        raise BankError("ACCOUNT_NOT_FOUND", "Bank account not found in this business")
    if row["type"] != "asset":
        raise BankError("NOT_A_BANK_ACCOUNT", "Reconciliation needs an asset account")
    return row


def import_statement(conn: sqlite3.Connection, tenant_id: str, account_id: str,
                     rows: list[dict], filename: str = "",
                     created_by: str | None = None) -> dict:
    if not rows:
        raise BankError("NO_ROWS", "There are no statement rows to import")
    _bank_account(conn, tenant_id, account_id)
    period_start = min(r["txn_date"] for r in rows)
    period_end = max(r["txn_date"] for r in rows)
    import_id = db.new_id()

    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "INSERT INTO bank_import (id, tenant_id, account_id, filename, period_start,"
            " period_end, rows_total, rows_imported, rows_duplicate, created_by, created_at)"
            " VALUES (?,?,?,?,?,?,?,0,0,?,?)",
            (import_id, tenant_id, account_id, (filename or "")[:200], period_start, period_end,
             len(rows), created_by, db.now()),
        )
        imported = duplicates = 0
        for row in rows:
            cur = conn.execute(
                "INSERT INTO bank_statement_line (id, tenant_id, account_id, import_id, txn_date,"
                " description, reference, debit_paise, credit_paise, balance_paise, source_hash,"
                " status, imported_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?, 'unmatched', ?)"
                " ON CONFLICT (tenant_id, account_id, source_hash) DO NOTHING",
                (db.new_id(), tenant_id, account_id, import_id, row["txn_date"],
                 row["description"], row["reference"], row["debit_paise"],
                 row["credit_paise"], row["balance_paise"], _row_hash(account_id, row),
                 db.now()),
            )
            if cur.rowcount:
                imported += 1
            else:
                duplicates += 1
        conn.execute(
            "UPDATE bank_import SET rows_imported=?, rows_duplicate=? WHERE id=?",
            (imported, duplicates, import_id),
        )
        audit(conn, tenant_id, created_by, "bank.import", "bank_import", import_id,
              meta={"rows": len(rows), "imported": imported, "duplicates": duplicates,
                    "period_start": period_start, "period_end": period_end})
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return {"import_id": import_id, "rows_total": len(rows), "imported": imported,
            "duplicates": duplicates, "period_start": period_start, "period_end": period_end}


def latest_import(conn: sqlite3.Connection, tenant_id: str, account_id: str):
    row = conn.execute(
        "SELECT * FROM bank_import WHERE tenant_id=? AND account_id=?"
        " ORDER BY created_at DESC LIMIT 1", (tenant_id, account_id),
    ).fetchone()
    return dict(row) if row else None


# --------------------------------------------------------------------------
# reconciliation
# --------------------------------------------------------------------------

def _ledger_candidates(conn: sqlite3.Connection, tenant_id: str, account_id: str,
                       date_from: str | None = None, date_to: str | None = None) -> list[dict]:
    sql = (
        "SELECT l.id AS line_id, l.debit_paise, l.credit_paise, e.id AS entry_id,"
        " e.entry_no, e.entry_date, e.narration, e.source_type, e.source_id,"
        " p.voucher_no, p.reference, p.mode, p.party_id,"
        " COALESCE(c.name, v.name) AS party_name"
        " FROM journal_line l"
        " JOIN journal_entry e ON e.id=l.entry_id"
        " LEFT JOIN payment p ON p.journal_entry_id=e.id"
        " LEFT JOIN customer c ON c.id=p.party_id AND p.party_type='customer'"
        " LEFT JOIN vendor v ON v.id=p.party_id AND p.party_type='vendor'"
        " WHERE l.tenant_id=? AND l.account_id=? AND e.status='posted'"
        " AND l.id NOT IN (SELECT matched_journal_line_id FROM bank_statement_line"
        "                  WHERE tenant_id=? AND matched_journal_line_id IS NOT NULL)"
    )
    params: list = [tenant_id, account_id, tenant_id]
    if date_from:
        sql += " AND e.entry_date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND e.entry_date <= ?"
        params.append(date_to)
    sql += " ORDER BY e.entry_date, e.entry_no"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def ledger_candidates(conn: sqlite3.Connection, tenant_id: str, account_id: str,
                      date_from: str | None = None,
                      date_to: str | None = None) -> list[dict]:
    """Posted bank journal lines that are not yet matched to a statement line."""
    return _ledger_candidates(conn, tenant_id, account_id, date_from, date_to)


def statement_lines(conn: sqlite3.Connection, tenant_id: str, account_id: str,
                    date_from: str, date_to: str) -> list[dict]:
    rows = conn.execute(
        "SELECT s.*, e.entry_no, e.entry_date AS ledger_date, e.narration,"
        " e.source_type, e.source_id, p.voucher_no, p.reference AS payment_reference,"
        " p.mode, COALESCE(c.name, v.name) AS party_name"
        " FROM bank_statement_line s"
        " LEFT JOIN journal_line l ON l.id=s.matched_journal_line_id"
        " LEFT JOIN journal_entry e ON e.id=l.entry_id"
        " LEFT JOIN payment p ON p.journal_entry_id=e.id"
        " LEFT JOIN customer c ON c.id=p.party_id AND p.party_type='customer'"
        " LEFT JOIN vendor v ON v.id=p.party_id AND p.party_type='vendor'"
        " WHERE s.tenant_id=? AND s.account_id=? AND s.txn_date BETWEEN ? AND ?"
        " ORDER BY s.txn_date, s.imported_at, s.id",
        (tenant_id, account_id, date_from, date_to),
    ).fetchall()
    return [dict(r) for r in rows]


def _signed_statement(row: dict) -> int:
    return row["credit_paise"] - row["debit_paise"]


def _signed_ledger(row: dict) -> int:
    return row["debit_paise"] - row["credit_paise"]


def _ref_match(stmt_ref: str, ledger_ref: str) -> bool:
    a = (stmt_ref or "").strip().lower()
    b = (ledger_ref or "").strip().lower()
    if not a or not b:
        return False
    return a in b or b in a


def suggest_matches(conn: sqlite3.Connection, tenant_id: str, account_id: str,
                    date_from: str, date_to: str,
                    window_days: int = DEFAULT_WINDOW_DAYS) -> list[dict]:
    """For every unmatched statement line, list plausible ledger entries.

    The best candidate is first. A candidate must have the exact same signed
    amount; the date may differ by window_days.
    """
    _bank_account(conn, tenant_id, account_id)
    statements = [r for r in statement_lines(conn, tenant_id, account_id, date_from, date_to)
                  if r["status"] == "unmatched"]
    ledger = _ledger_candidates(conn, tenant_id, account_id)
    by_amount: dict[int, list[dict]] = {}
    for row in ledger:
        by_amount.setdefault(_signed_ledger(row), []).append(row)

    out = []
    for stmt in statements:
        stmt_date = date.fromisoformat(stmt["txn_date"])
        candidates = []
        for row in by_amount.get(_signed_statement(stmt), []):
            diff = abs((date.fromisoformat(row["entry_date"]) - stmt_date).days)
            if diff > window_days:
                continue
            ref_penalty = 0 if _ref_match(stmt["reference"], row.get("reference") or "") else 1
            candidates.append({
                **row,
                "days_apart": diff,
                "ref_match": ref_penalty == 0,
                "_score": (diff, ref_penalty),
            })
        candidates.sort(key=lambda r: (r["_score"], r["entry_no"]))
        out.append({"statement": stmt, "candidates": candidates,
                    "best": candidates[0] if candidates else None})
    return out


def _apply_match(conn: sqlite3.Connection, tenant_id: str, statement_id: str,
                 journal_line_id: str, actor: str | None) -> None:
    stmt = conn.execute(
        "SELECT * FROM bank_statement_line WHERE id=? AND tenant_id=?",
        (statement_id, tenant_id),
    ).fetchone()
    if not stmt:
        raise BankError("LINE_NOT_FOUND", "Statement line not found")
    if stmt["status"] == "matched":
        raise BankError("ALREADY_MATCHED", "Statement line is already matched; unmatch it first")
    line = conn.execute(
        "SELECT l.*, e.status AS entry_status, e.entry_date, e.entry_no"
        " FROM journal_line l JOIN journal_entry e ON e.id=l.entry_id"
        " WHERE l.id=? AND l.tenant_id=?", (journal_line_id, tenant_id),
    ).fetchone()
    if not line:
        raise BankError("ENTRY_NOT_FOUND", "Ledger line not found")
    if line["account_id"] != stmt["account_id"]:
        raise BankError("WRONG_ACCOUNT", "That ledger line is not on this bank account")
    if line["entry_status"] != "posted":
        raise BankError("ENTRY_NOT_POSTED", "Only posted ledger entries can be matched")
    other = conn.execute(
        "SELECT 1 FROM bank_statement_line WHERE tenant_id=? AND matched_journal_line_id=?",
        (tenant_id, journal_line_id),
    ).fetchone()
    if other:
        raise BankError("ALREADY_MATCHED", "That ledger entry is already matched to another line")
    stmt_signed = stmt["credit_paise"] - stmt["debit_paise"]
    line_signed = line["debit_paise"] - line["credit_paise"]
    if stmt_signed != line_signed:
        raise BankError(
            "AMOUNT_MISMATCH",
            "Amounts do not match. Bank reconciliation matches equal amounts only.",
        )
    conn.execute(
        "UPDATE bank_statement_line SET status='matched', matched_journal_line_id=?,"
        " matched_at=?, matched_by=? WHERE id=?",
        (journal_line_id, db.now(), actor, statement_id),
    )
    audit(conn, tenant_id, actor, "bank.match", "bank_statement_line", statement_id,
          meta={"journal_line_id": journal_line_id, "amount": stmt_signed})


def match_line(conn: sqlite3.Connection, tenant_id: str, statement_id: str,
               journal_line_id: str, created_by: str | None = None) -> None:
    conn.execute("BEGIN IMMEDIATE")
    try:
        _apply_match(conn, tenant_id, statement_id, journal_line_id, created_by)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def unmatch_line(conn: sqlite3.Connection, tenant_id: str, statement_id: str,
                 created_by: str | None = None) -> None:
    stmt = conn.execute(
        "SELECT * FROM bank_statement_line WHERE id=? AND tenant_id=?",
        (statement_id, tenant_id),
    ).fetchone()
    if not stmt:
        raise BankError("LINE_NOT_FOUND", "Statement line not found")
    if stmt["status"] != "matched":
        raise BankError("NOT_MATCHED", "Statement line is not matched")
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "UPDATE bank_statement_line SET status='unmatched', matched_journal_line_id=NULL,"
            " matched_at=NULL, matched_by=NULL WHERE id=?",
            (statement_id,),
        )
        audit(conn, tenant_id, created_by, "bank.unmatch", "bank_statement_line", statement_id)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def auto_match(conn: sqlite3.Connection, tenant_id: str, account_id: str,
               date_from: str, date_to: str, window_days: int = DEFAULT_WINDOW_DAYS,
               created_by: str | None = None) -> dict:
    """Match only unambiguous candidates: one candidate, or a clear best score."""
    suggestions = suggest_matches(conn, tenant_id, account_id, date_from, date_to, window_days)
    used: set[str] = set()
    plan: list[tuple[str, str]] = []
    ambiguous = 0
    for item in suggestions:
        candidates = item["candidates"]
        if not candidates:
            continue
        best = candidates[0]
        if best["line_id"] in used:
            continue
        if len(candidates) > 1 and candidates[1]["_score"] == best["_score"]:
            ambiguous += 1
            continue
        plan.append((item["statement"]["id"], best["line_id"]))
        used.add(best["line_id"])

    conn.execute("BEGIN IMMEDIATE")
    try:
        for statement_id, line_id in plan:
            _apply_match(conn, tenant_id, statement_id, line_id, created_by)
        audit(conn, tenant_id, created_by, "bank.auto_match", "bank_account", account_id,
              meta={"matched": len(plan), "ambiguous": ambiguous})
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return {"matched": len(plan), "ambiguous": ambiguous,
            "remaining": len(suggestions) - len(plan)}


def reconciliation(conn: sqlite3.Connection, tenant_id: str, account_id: str,
                   date_from: str, date_to: str) -> dict:
    account = _bank_account(conn, tenant_id, account_id)
    stmt = statement_lines(conn, tenant_id, account_id, date_from, date_to)
    matched = [r for r in stmt if r["status"] == "matched"]
    unmatched = [r for r in stmt if r["status"] == "unmatched"]
    stmt_debit = sum(r["debit_paise"] for r in stmt)
    stmt_credit = sum(r["credit_paise"] for r in stmt)
    stmt_net = stmt_credit - stmt_debit
    matched_net = sum(_signed_statement(r) for r in matched)
    unmatched_net = sum(_signed_statement(r) for r in unmatched)

    ledger = conn.execute(
        "SELECT COALESCE(SUM(l.debit_paise),0) d, COALESCE(SUM(l.credit_paise),0) c"
        " FROM journal_line l JOIN journal_entry e ON e.id=l.entry_id"
        " WHERE l.tenant_id=? AND l.account_id=? AND e.status='posted'"
        " AND e.entry_date BETWEEN ? AND ?",
        (tenant_id, account_id, date_from, date_to),
    ).fetchone()
    ledger_net = ledger["d"] - ledger["c"]
    unmatched_ledger = _ledger_candidates(conn, tenant_id, account_id, date_from, date_to)
    unmatched_ledger_net = sum(_signed_ledger(r) for r in unmatched_ledger)

    opening_row = conn.execute(
        "SELECT COALESCE(SUM(l.debit_paise - l.credit_paise),0) b"
        " FROM journal_line l JOIN journal_entry e ON e.id=l.entry_id"
        " WHERE l.tenant_id=? AND l.account_id=? AND e.status='posted' AND e.entry_date < ?",
        (tenant_id, account_id, date_from),
    ).fetchone()
    closing_row = conn.execute(
        "SELECT COALESCE(SUM(l.debit_paise - l.credit_paise),0) b"
        " FROM journal_line l JOIN journal_entry e ON e.id=l.entry_id"
        " WHERE l.tenant_id=? AND l.account_id=? AND e.status='posted' AND e.entry_date <= ?",
        (tenant_id, account_id, date_to),
    ).fetchone()

    latest_balance = None
    for row in reversed(stmt):
        if row["balance_paise"] is not None:
            latest_balance = row["balance_paise"]
            break

    return {
        "account": dict(account),
        "from": date_from,
        "to": date_to,
        "statement": stmt,
        "matched": matched,
        "unmatched": unmatched,
        "statement_count": len(stmt),
        "matched_count": len(matched),
        "unmatched_count": len(unmatched),
        "statement_debit": stmt_debit,
        "statement_credit": stmt_credit,
        "statement_net": stmt_net,
        "matched_net": matched_net,
        "unmatched_net": unmatched_net,
        "ledger_net": ledger_net,
        "unmatched_ledger": unmatched_ledger,
        "unmatched_ledger_net": unmatched_ledger_net,
        "opening_ledger": opening_row["b"],
        "closing_ledger": closing_row["b"],
        "latest_statement_balance": latest_balance,
        "difference": ledger_net - stmt_net,
        "reconciled_difference": unmatched_ledger_net - unmatched_net,
    }
