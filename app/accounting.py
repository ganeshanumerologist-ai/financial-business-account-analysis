"""Double-entry accounting core: posting, invoicing, reports.

All amounts are integer paise. Every posting is validated, balanced and atomic.
"""
from __future__ import annotations

import json
import re
import sqlite3
from calendar import monthrange
from datetime import date

from . import db, money
from .money import mul_qty_price, split_tax, tax_on


class AccountingError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _today_iso() -> str:
    return date.today().isoformat()


def _assert_period_open(conn: sqlite3.Connection, tenant_id: str, on_date: str) -> None:
    row = conn.execute(
        "SELECT 1 FROM period_lock WHERE tenant_id=? AND ? BETWEEN period_start AND period_end",
        (tenant_id, on_date),
    ).fetchone()
    if row:
        raise AccountingError("PERIOD_LOCKED", f"Period containing {on_date} is locked")


def _assert_accounts(conn: sqlite3.Connection, tenant_id: str, account_ids: set[str]) -> None:
    for aid in account_ids:
        row = conn.execute(
            "SELECT is_postable, status FROM account WHERE id=? AND tenant_id=?",
            (aid, tenant_id),
        ).fetchone()
        if not row:
            raise AccountingError("ACCOUNT_NOT_FOUND", f"Account {aid} not in this tenant")
        if not row["is_postable"]:
            raise AccountingError("ACCOUNT_NOT_POSTABLE", f"Account {aid} is not postable")
        if row["status"] != "active":
            raise AccountingError(
                "ACCOUNT_ARCHIVED",
                f"Account {aid} is archived. Restore it before posting.",
            )


def audit(conn: sqlite3.Connection, tenant_id: str | None, actor: str | None, action: str,
          target_type: str | None = None, target_id: str | None = None,
          result: str = "success", meta: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO audit_log (id, tenant_id, actor_user_id, action, target_type, target_id, result, meta, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (db.new_id(), tenant_id, actor, action, target_type, target_id, result,
         json.dumps(meta or {}), db.now()),
    )


ACCOUNT_TYPES = ("asset", "liability", "equity", "income", "expense")

# The five accounting types are not enough on their own: an SME thinks in
# groups such as Sundry Debtors, Sundry Creditors, Purchase, Sales and Bank.
# A group always belongs to exactly one type, so reports and the trial balance
# keep their accounting meaning.
ACCOUNT_GROUP_DEFS = (
    ("cash", "asset", "Cash-in-Hand",
     "Cash box, counter cash and petty cash.", "debit"),
    ("bank", "asset", "Bank Account",
     "Current, savings or overdraft account. Full bank details are stored too.", "debit"),
    ("receivable", "asset", "Sundry Debtors / Accounts Receivable",
     "Money customers owe. Creates a linked customer sub-ledger for invoices.", "debit"),
    ("inventory", "asset", "Inventory / Stock-in-Hand",
     "Stock valued at cost. Usually controlled by item postings.", "debit"),
    ("fixed_asset", "asset", "Fixed Assets",
     "Plant, machinery, furniture, vehicles and other long-term assets.", "debit"),
    ("investments", "asset", "Investments",
     "Shares, deposits and other investments held by the business.", "debit"),
    ("loans_advances", "asset", "Loans & Advances (Asset)",
     "Advances to suppliers, staff loans and deposits paid.", "debit"),
    ("gst_input", "asset", "GST Input Credit",
     "Input CGST, SGST and IGST control ledgers.", "debit"),
    ("other_asset", "asset", "Other Current Assets",
     "Any other asset that does not fit a more specific group.", "debit"),
    ("payable", "liability", "Sundry Creditors / Accounts Payable",
     "Money owed to suppliers. Creates a linked vendor sub-ledger for bills.", "credit"),
    ("loans", "liability", "Loans (Liability)",
     "Bank loans, NBFC loans, director loans and other borrowings.", "credit"),
    ("duties_taxes", "liability", "Duties & Taxes (GST/TDS)",
     "GST output, TDS payable and other statutory dues.", "credit"),
    ("provisions", "liability", "Provisions",
     "Provident fund, gratuity, audit fee and other provisions.", "credit"),
    ("suspense", "liability", "Suspense A/c",
     "Temporary holding account for unidentified or unreconciled amounts; clear it before closing.", "credit"),
    ("other_liability", "liability", "Other Current Liabilities",
     "Any other liability that does not fit a more specific group.", "credit"),
    ("capital", "equity", "Capital Account",
     "Owner or shareholder capital introduced into the business.", "credit"),
    ("drawings", "equity", "Drawings",
     "Owner withdrawals and personal drawings.", "debit"),
    ("retained_earnings", "equity", "Retained Earnings",
     "Accumulated profits retained in the business.", "credit"),
    ("profit_loss", "equity", "Profit & Loss A/c",
     "Accumulated profit or loss carried to equity; use only if your process keeps a separate P&L account.", "credit"),
    ("opening_equity", "equity", "Opening Balance Equity",
     "Balancing account used only by opening-balance journals.", "credit"),
    ("other_equity", "equity", "Other Equity",
     "Any other equity reserve or adjustment account.", "credit"),
    ("sales", "income", "Sales",
     "Sale of goods. Product-wise price, margin and GST live in Items.", "credit"),
    ("service_income", "income", "Service Income",
     "Consulting, professional and other service revenue.", "credit"),
    ("other_income", "income", "Other Income",
     "Commission, rent received and miscellaneous income.", "credit"),
    ("interest_income", "income", "Interest Income",
     "Interest earned on deposits or advances.", "credit"),
    ("purchase", "expense", "Purchase",
     "Purchase of goods or direct trading material.", "debit"),
    ("direct_expense", "expense", "Direct Expenses",
     "Freight, labour and other costs directly tied to sales.", "debit"),
    ("cost_of_goods_sold", "expense", "Cost of Goods Sold",
     "Cost of stock sold when using perpetual inventory.", "debit"),
    ("employee_expense", "expense", "Employee Benefit Expense",
     "Salaries, wages, bonus, PF and staff welfare.", "debit"),
    ("finance_cost", "expense", "Finance Costs",
     "Interest, bank charges and loan-processing fees.", "debit"),
    ("depreciation", "expense", "Depreciation",
     "Depreciation and amortisation of fixed assets.", "debit"),
    ("other_expense", "expense", "Other Expenses",
     "Rent, utilities, professional fees and other operating costs.", "debit"),
)

ACCOUNT_GROUPS = {
    code: {"code": code, "type": account_type, "label": label,
           "hint": hint, "default_side": side}
    for code, account_type, label, hint, side in ACCOUNT_GROUP_DEFS
}
ACCOUNT_GROUP_ORDER = [code for code, *_rest in ACCOUNT_GROUP_DEFS]
PARTY_GROUPS = {"receivable": "customer", "payable": "vendor"}

PROFILE_TEXT_FIELDS = (
    "legal_name", "contact_person", "phone", "email", "website", "address", "city",
    "state_code", "pincode", "country", "gstin", "pan", "cin", "organisation_type",
    "industry", "loan_lender", "loan_account_no", "loan_sanction_date",
    "loan_maturity_date", "security_details", "notes",
)
PROFILE_INT_FIELDS = (
    "credit_days", "credit_limit_paise", "interest_rate_bp", "tenure_months", "emi_paise",
)


def account_group_label(group_code: str, account_type: str = "") -> str:
    group = ACCOUNT_GROUPS.get((group_code or "").strip())
    if group:
        return group["label"]
    fallback = {
        "asset": "Other Current Assets", "liability": "Other Current Liabilities",
        "equity": "Other Equity", "income": "Other Income", "expense": "Other Expenses",
    }
    return fallback.get((account_type or "").lower(), "Ungrouped")


def default_group_for_type(account_type: str) -> str:
    return {
        "asset": "other_asset", "liability": "other_liability", "equity": "other_equity",
        "income": "other_income", "expense": "other_expense",
    }.get((account_type or "").lower(), "")


def account_groups_for_type(account_type: str) -> list[dict]:
    return [ACCOUNT_GROUPS[c] for c in ACCOUNT_GROUP_ORDER
            if ACCOUNT_GROUPS[c]["type"] == account_type]


def _clean_profile(profile: dict | None, group_code: str) -> dict:
    """Validate and normalise the optional account profile fields."""
    data = {name: "" for name in PROFILE_TEXT_FIELDS}
    data.update({name: 0 for name in PROFILE_INT_FIELDS})
    source = profile or {}
    for name in PROFILE_TEXT_FIELDS:
        data[name] = str(source.get(name, "") or "").strip()
    for name in PROFILE_INT_FIELDS:
        value = source.get(name, 0)
        try:
            data[name] = int(value or 0)
        except (TypeError, ValueError) as exc:
            raise AccountingError("BAD_PROFILE_NUMBER", f"{name.replace('_', ' ').title()} must be a number.") from exc

    limits = {
        "legal_name": 120, "contact_person": 80, "phone": 24, "email": 120,
        "website": 120, "address": 240, "city": 60, "state_code": 2, "pincode": 6,
        "country": 60, "gstin": 15, "pan": 10, "cin": 21, "organisation_type": 80,
        "industry": 80, "loan_lender": 120, "loan_account_no": 60,
        "loan_sanction_date": 10, "loan_maturity_date": 10, "security_details": 240,
        "notes": 500,
    }
    for name, max_len in limits.items():
        if len(data[name]) > max_len:
            raise AccountingError("BAD_PROFILE_TEXT",
                                  f"{name.replace('_', ' ').title()} is too long.")
    data["gstin"] = data["gstin"].upper()
    data["pan"] = data["pan"].upper()
    data["cin"] = data["cin"].upper()
    data["state_code"] = data["state_code"].upper()

    if data["email"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", data["email"]):
        raise AccountingError("BAD_PROFILE_EMAIL", "Enter a valid email address.")
    if data["gstin"] and not re.fullmatch(r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]",
                                          data["gstin"]):
        raise AccountingError("BAD_PROFILE_GSTIN", "GSTIN must be 15 characters, e.g. 27ABCDE1234F1Z5.")
    if data["pan"] and not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", data["pan"]):
        raise AccountingError("BAD_PROFILE_PAN", "PAN must be 10 characters, e.g. ABCDE1234F.")
    if data["cin"] and not re.fullmatch(r"[A-Z0-9]{21}", data["cin"]):
        raise AccountingError("BAD_PROFILE_CIN", "CIN must be 21 letters/digits.")
    if data["state_code"] and not re.fullmatch(r"[0-9]{2}", data["state_code"]):
        raise AccountingError("BAD_PROFILE_STATE", "State code must be two digits.")
    if data["pincode"] and not re.fullmatch(r"[1-9][0-9]{5}", data["pincode"]):
        raise AccountingError("BAD_PROFILE_PINCODE", "PIN code must be six digits.")
    if not 0 <= data["credit_days"] <= 365:
        raise AccountingError("BAD_PROFILE_CREDIT_DAYS", "Credit days must be between 0 and 365.")
    if data["credit_limit_paise"] < 0:
        raise AccountingError("BAD_PROFILE_CREDIT_LIMIT", "Credit limit cannot be negative.")
    if not 0 <= data["interest_rate_bp"] <= 10000:
        raise AccountingError("BAD_PROFILE_INTEREST", "Interest rate must be between 0% and 100%.")
    if not 0 <= data["tenure_months"] <= 600:
        raise AccountingError("BAD_PROFILE_TENURE", "Loan tenure must be between 0 and 600 months.")
    if data["emi_paise"] < 0:
        raise AccountingError("BAD_PROFILE_EMI", "EMI cannot be negative.")

    for name in ("loan_sanction_date", "loan_maturity_date"):
        if data[name]:
            try:
                data[name] = date.fromisoformat(data[name]).isoformat()
            except ValueError as exc:
                raise AccountingError("BAD_PROFILE_LOAN_DATE",
                                      "Loan dates must use YYYY-MM-DD.") from exc
    if (data["loan_sanction_date"] and data["loan_maturity_date"]
            and data["loan_maturity_date"] < data["loan_sanction_date"]):
        raise AccountingError("BAD_PROFILE_LOAN_DATE",
                              "Loan maturity date cannot be before the sanction date.")
    if group_code == "loans" and not data["loan_lender"]:
        raise AccountingError("LOAN_LENDER_REQUIRED", "Enter the lender name for a loan account.")
    return data


def _save_profile(conn: sqlite3.Connection, tenant_id: str, account_id: str,
                  group_code: str, profile: dict, actor: str | None,
                  party_type: str = "", party_id: str | None = None) -> None:
    now = db.now()
    existing = conn.execute(
        "SELECT id, party_type, party_id FROM account_profile WHERE account_id=? AND tenant_id=?",
        (account_id, tenant_id),
    ).fetchone()
    values = dict(profile)
    values["party_type"] = party_type or (existing["party_type"] if existing else "")
    values["party_id"] = party_id or (existing["party_id"] if existing else None)
    columns = (*PROFILE_TEXT_FIELDS, *PROFILE_INT_FIELDS)
    if existing:
        assignments = ", ".join(f"{name}=?" for name in
                                 (*columns, "party_type", "party_id", "updated_at", "updated_by"))
        conn.execute(
            f"UPDATE account_profile SET {assignments} WHERE id=?",
            (*[values.get(name, "") for name in PROFILE_TEXT_FIELDS],
             *[values.get(name, 0) for name in PROFILE_INT_FIELDS],
             values["party_type"], values["party_id"], now, actor, existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO account_profile (id, tenant_id, account_id, "
            + ", ".join((*columns, "party_type", "party_id", "created_at", "updated_at",
                         "created_by", "updated_by"))
            + ") VALUES (?,?,?,"
            + ",".join("?" for _ in range(len(columns) + 2))
            + ",?,?,?,?)",
            (db.new_id(), tenant_id, account_id,
             *[values.get(name, "") for name in PROFILE_TEXT_FIELDS],
             *[values.get(name, 0) for name in PROFILE_INT_FIELDS],
             values["party_type"], values["party_id"], now, now, actor, actor),
        )


def _ensure_party(conn: sqlite3.Connection, tenant_id: str, account_id: str,
                  account_name: str, group_code: str, profile: dict,
                  actor: str | None) -> tuple[str, str] | None:
    """Create or link the customer/vendor sub-ledger for a party account."""
    party_type = PARTY_GROUPS.get(group_code)
    if not party_type:
        return None
    table = party_type
    state_code = (profile.get("state_code") or "").strip()[:2]
    values = {
        "name": (profile.get("legal_name") or account_name)[:120],
        "phone": profile.get("phone", "")[:20],
        "gstin": profile.get("gstin", "")[:15],
        "email": profile.get("email", "")[:120],
        "address": profile.get("address", "")[:240],
        "state_code": state_code,
        "credit_days": profile.get("credit_days", 0),
        "credit_limit_paise": profile.get("credit_limit_paise", 0),
    }
    existing = conn.execute(
        f"SELECT * FROM {table} WHERE tenant_id=? AND lower(name)=lower(?) ORDER BY created_at LIMIT 1",
        (tenant_id, values["name"]),
    ).fetchone()
    if existing and existing["account_id"] not in (None, "", account_id):
        existing = None
    if existing:
        # Linking an existing party must not erase details the user did not
        # re-enter. A later profile edit is the explicit way to clear a field.
        merged = {
            field: values[field] if values[field] not in (None, "", 0) else existing[field]
            for field in ("name", "phone", "gstin", "email", "address",
                          "credit_days", "credit_limit_paise")
        }
        merged["state_code"] = state_code or existing["state_code"] or "27"
        party_id = existing["id"]
        conn.execute(
            f"UPDATE {table} SET account_id=?, name=?, phone=?, gstin=?, email=?, address=?,"
            " state_code=?, credit_days=?, credit_limit_paise=? WHERE id=?",
            (account_id, merged["name"], merged["phone"], merged["gstin"], merged["email"],
             merged["address"], merged["state_code"], merged["credit_days"],
             merged["credit_limit_paise"], party_id),
        )
    else:
        values["state_code"] = state_code or "27"
        party_id = db.new_id()
        conn.execute(
            f"INSERT INTO {table} (id, tenant_id, name, phone, gstin, email, address,"
            " state_code, account_id, credit_days, credit_limit_paise, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (party_id, tenant_id, values["name"], values["phone"], values["gstin"],
             values["email"], values["address"], values["state_code"], account_id,
             values["credit_days"], values["credit_limit_paise"], db.now()),
        )
    return party_type, party_id


def _clean_bank_details(details: dict) -> dict:
    bank_name = str(details.get("bank_name", "") or "").strip()
    account_number = str(details.get("account_number", "") or "").strip()
    ifsc = str(details.get("ifsc", "") or "").strip().upper()
    branch = str(details.get("branch", "") or "").strip()
    holder_name = str(details.get("holder_name", "") or "").strip()
    if len(bank_name) < 2 or len(bank_name) > 80:
        raise AccountingError("BAD_BANK_NAME", "Bank name must be between 2 and 80 characters.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 /.-]{3,33}", account_number):
        raise AccountingError("BAD_BANK_ACCOUNT",
                              "Bank account number must be 4 to 34 letters, digits, spaces, /, . or -.")
    if ifsc and not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", ifsc):
        raise AccountingError("BAD_BANK_IFSC", "IFSC must be 11 characters, e.g. HDFC0001234.")
    if len(branch) > 80:
        raise AccountingError("BAD_BANK_BRANCH", "Bank branch name is too long.")
    if len(holder_name) > 120:
        raise AccountingError("BAD_BANK_HOLDER", "Account holder name is too long.")
    return {"bank_name": bank_name, "account_number": account_number, "ifsc": ifsc,
            "branch": branch, "holder_name": holder_name}


def _save_bank_details(conn: sqlite3.Connection, tenant_id: str, account_id: str,
                       details: dict) -> str:
    cleaned = _clean_bank_details(details)
    conn.execute(
        "INSERT INTO bank_account (id, tenant_id, account_id, bank_name, account_number,"
        " ifsc, branch, holder_name, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (db.new_id(), tenant_id, account_id, cleaned["bank_name"],
         cleaned["account_number"], cleaned["ifsc"], cleaned["branch"],
         cleaned["holder_name"], db.now()),
    )
    return cleaned["bank_name"]


def _update_party_from_profile(conn: sqlite3.Connection, tenant_id: str, party_type: str,
                               party_id: str, profile: dict) -> None:
    table = party_type if party_type in ("customer", "vendor") else ""
    if not table or not party_id:
        return
    conn.execute(
        f"UPDATE {table} SET name=?, phone=?, gstin=?, email=?, address=?, state_code=?,"
        " credit_days=?, credit_limit_paise=? WHERE id=? AND tenant_id=?",
        ((profile.get("legal_name") or "")[:120] or
         conn.execute(f"SELECT name FROM {table} WHERE id=?", (party_id,)).fetchone()["name"],
         profile.get("phone", "")[:20], profile.get("gstin", "")[:15],
         profile.get("email", "")[:120], profile.get("address", "")[:240],
         (profile.get("state_code") or "27")[:2], profile.get("credit_days", 0),
         profile.get("credit_limit_paise", 0), party_id, tenant_id),
    )


def create_account(conn: sqlite3.Connection, tenant_id: str, code: str, name: str,
                   account_type: str, created_by: str | None = None,
                   group_code: str = "", profile: dict | None = None,
                   opening: dict | None = None, bank_details: dict | None = None) -> str:
    """Create a postable ledger account plus its optional 360-degree profile.

    ``opening`` posts a balanced opening journal in the same transaction as the
    account. ``profile`` stores company/contact/tax/credit/loan details, and a
    Sundry Debtors or Sundry Creditors account also gets a linked customer or
    vendor sub-ledger. Nothing is written if any step fails.
    """
    code = (code or "").strip().upper()
    name = (name or "").strip()
    account_type = (account_type or "").strip().lower()
    group_code = (group_code or "").strip().lower()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]{0,11}", code):
        raise AccountingError(
            "BAD_ACCOUNT_CODE",
            "Account code must start with a letter or digit and use up to 12 letters, digits or hyphens.",
        )
    if len(name) < 2 or len(name) > 80:
        raise AccountingError("BAD_ACCOUNT_NAME", "Account name must be between 2 and 80 characters.")
    if account_type not in ACCOUNT_TYPES:
        raise AccountingError("BAD_ACCOUNT_TYPE", "Choose a valid account type.")
    if not group_code:
        group_code = default_group_for_type(account_type)
    if group_code not in ACCOUNT_GROUPS:
        raise AccountingError("BAD_ACCOUNT_GROUP", "Choose a valid account group.")
    if ACCOUNT_GROUPS[group_code]["type"] != account_type:
        raise AccountingError(
            "ACCOUNT_GROUP_TYPE",
            f"{ACCOUNT_GROUPS[group_code]['label']} belongs under "
            f"{ACCOUNT_GROUPS[group_code]['type'].title()}, not {account_type.title()}.",
        )
    if conn.execute("SELECT 1 FROM account WHERE tenant_id=? AND code=?",
                    (tenant_id, code)).fetchone():
        raise AccountingError("ACCOUNT_CODE_TAKEN", f"Account code {code} already exists.")

    cleaned = _clean_profile(profile, group_code)
    if group_code == "bank":
        if not bank_details or not bank_details.get("bank_name") or not bank_details.get("account_number"):
            raise AccountingError("BANK_DETAILS_REQUIRED",
                                  "Enter the bank name and account number for a bank account.")

    own_tx = not conn.in_transaction
    if own_tx:
        conn.execute("BEGIN IMMEDIATE")
    try:
        account_id = db.new_id()
        conn.execute(
            "INSERT INTO account (id, tenant_id, code, name, type, group_code, is_postable)"
            " VALUES (?,?,?,?,?,?,1)",
            (account_id, tenant_id, code, name, account_type, group_code),
        )
        party = _ensure_party(conn, tenant_id, account_id, name, group_code, cleaned, created_by)
        party_type, party_id = party if party else ("", None)
        _save_profile(conn, tenant_id, account_id, group_code, cleaned, created_by,
                      party_type=party_type, party_id=party_id)
        if bank_details:
            _save_bank_details(conn, tenant_id, account_id, bank_details)

        opening_entry = None
        if opening and opening.get("amount") is not None:
            opening_entry = set_opening_balance(
                conn, tenant_id, account_id, opening.get("as_of", ""),
                int(opening["amount"]), opening.get("side", ""), created_by=created_by,
            )
        audit(conn, tenant_id, created_by, "account.create", "account", account_id,
              meta={"code": code, "name": name, "type": account_type, "group": group_code,
                    "opening_entry": opening_entry, "party_type": party_type or None})
        if own_tx:
            conn.execute("COMMIT")
        return account_id
    except Exception:
        if own_tx:
            conn.execute("ROLLBACK")
        raise


def account_profile(conn: sqlite3.Connection, tenant_id: str, account_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM account_profile WHERE tenant_id=? AND account_id=?",
        (tenant_id, account_id),
    ).fetchone()
    return dict(row) if row else None


def update_account_profile(conn: sqlite3.Connection, tenant_id: str, account_id: str,
                           name: str, profile: dict, bank_details: dict | None = None,
                           updated_by: str | None = None) -> None:
    """Update identity/profile details without changing code, type or group."""
    account = conn.execute(
        "SELECT * FROM account WHERE id=? AND tenant_id=?", (account_id, tenant_id)
    ).fetchone()
    if not account:
        raise AccountingError("ACCOUNT_NOT_FOUND", "Account not found in this business.")
    name = (name or "").strip()
    if len(name) < 2 or len(name) > 80:
        raise AccountingError("BAD_ACCOUNT_NAME", "Account name must be between 2 and 80 characters.")
    cleaned = _clean_profile(profile, account["group_code"])
    existing = account_profile(conn, tenant_id, account_id) or {}
    party_type = existing.get("party_type", "")
    party_id = existing.get("party_id")
    bank_cleaned = None
    if bank_details and account["group_code"] == "bank":
        bank_cleaned = _clean_bank_details(bank_details)

    own_tx = not conn.in_transaction
    if own_tx:
        conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("UPDATE account SET name=? WHERE id=?", (name, account_id))
        _save_profile(conn, tenant_id, account_id, account["group_code"], cleaned,
                      updated_by, party_type=party_type, party_id=party_id)
        _update_party_from_profile(conn, tenant_id, party_type, party_id, cleaned)
        if account["group_code"] == "bank" and bank_cleaned:
            row = conn.execute("SELECT id FROM bank_account WHERE account_id=? AND tenant_id=?",
                               (account_id, tenant_id)).fetchone()
            if row:
                conn.execute(
                    "UPDATE bank_account SET bank_name=?, account_number=?, ifsc=?, branch=?,"
                    " holder_name=? WHERE id=?",
                    (bank_cleaned["bank_name"], bank_cleaned["account_number"],
                     bank_cleaned["ifsc"], bank_cleaned["branch"],
                     bank_cleaned["holder_name"], row["id"]),
                )
            else:
                _save_bank_details(conn, tenant_id, account_id, bank_cleaned)
        audit(conn, tenant_id, updated_by, "account.update", "account", account_id,
              meta={"name": name, "group": account["group_code"]})
        if own_tx:
            conn.execute("COMMIT")
    except Exception:
        if own_tx:
            conn.execute("ROLLBACK")
        raise


# Accounts used by code by the posting engine or by report/control lookups. They
# stay active so an archive or merge can never break invoices, GST, cash or the
# opening-balance control account.
SYSTEM_ACCOUNT_CODES = frozenset({
    "1000",  # Cash
    "1100",  # Accounts Receivable fallback
    "1200",  # Inventory
    "2000",  # Accounts Payable
    "2100", "2101", "2102",  # GST output
    "2200", "2201", "2202",  # GST input
    "5000",  # Cost of goods sold
    "5100",  # Purchases
    "5900",  # Rounding off
})
SYSTEM_ACCOUNT_GROUPS = frozenset({"opening_equity"})


def account_is_system(account: sqlite3.Row | dict) -> bool:
    """True for a control ledger whose code is used by the posting engine."""
    return (account["code"] in SYSTEM_ACCOUNT_CODES
            or account["group_code"] in SYSTEM_ACCOUNT_GROUPS)


def _clean_account_reason(reason: str, required: bool = True) -> str:
    value = (reason or "").strip()
    if required and not value:
        raise AccountingError("REASON_REQUIRED", "A reason is required for this account change.")
    if len(value) > 200:
        raise AccountingError("REASON_TOO_LONG", "Keep the reason to 200 characters or fewer.")
    return value


def _account_or_error(conn: sqlite3.Connection, tenant_id: str, account_id: str) -> sqlite3.Row:
    account = conn.execute(
        "SELECT * FROM account WHERE id=? AND tenant_id=?", (account_id, tenant_id)
    ).fetchone()
    if not account:
        raise AccountingError("ACCOUNT_NOT_FOUND", "Account not found in this business.")
    return account


def account_balance(conn: sqlite3.Connection, tenant_id: str, account_id: str,
                    as_of: str | None = None) -> int:
    """Signed all-time or as-of balance for one account (debit positive)."""
    if as_of:
        row = conn.execute(
            """SELECT COALESCE(SUM(l.debit_paise - l.credit_paise),0) AS bal
               FROM journal_line l JOIN journal_entry e ON e.id=l.entry_id
               WHERE l.tenant_id=? AND l.account_id=? AND e.entry_date <= ?""",
            (tenant_id, account_id, as_of),
        ).fetchone()
    else:
        row = conn.execute(
            """SELECT COALESCE(SUM(debit_paise - credit_paise),0) AS bal
               FROM journal_line WHERE tenant_id=? AND account_id=?""",
            (tenant_id, account_id),
        ).fetchone()
    return int(row["bal"] or 0)


def _account_party(conn: sqlite3.Connection, tenant_id: str,
                   account_id: str) -> tuple[str, str] | None:
    row = conn.execute(
        "SELECT party_type, party_id FROM account_profile WHERE tenant_id=? AND account_id=?",
        (tenant_id, account_id),
    ).fetchone()
    if row and row["party_type"] in ("customer", "vendor") and row["party_id"]:
        return (row["party_type"], row["party_id"])
    # Legacy ledgers may predate account_profile. The customer/vendor pointer is
    # still authoritative and must never be archived or merged into another party.
    for table, party_type in (("customer", "customer"), ("vendor", "vendor")):
        ref = conn.execute(
            f"SELECT id FROM {table} WHERE tenant_id=? AND account_id=? LIMIT 1",
            (tenant_id, account_id),
        ).fetchone()
        if ref:
            return (party_type, ref["id"])
    return None


def _account_bank_link(conn: sqlite3.Connection, tenant_id: str, account_id: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM bank_account WHERE tenant_id=? AND account_id=?",
        (tenant_id, account_id),
    ).fetchone())


def _compatible_merge_targets(conn: sqlite3.Connection, tenant_id: str,
                              source: sqlite3.Row) -> list[sqlite3.Row]:
    source_party = _account_party(conn, tenant_id, source["id"])
    source_bank = source["group_code"] == "bank"
    rows = conn.execute(
        """SELECT a.*
           FROM account a
           WHERE a.tenant_id=? AND a.status='active' AND a.is_postable=1
             AND a.type=? AND a.id<>?
           ORDER BY a.code""",
        (tenant_id, source["type"], source["id"]),
    ).fetchall()
    out = []
    for row in rows:
        if row["group_code"] == "opening_equity":
            continue
        if account_is_system(row):
            continue
        target_party = _account_party(conn, tenant_id, row["id"])
        if source_party != target_party:
            continue
        if source_bank != (row["group_code"] == "bank"):
            continue
        out.append(row)
    return out


def merge_targets(conn: sqlite3.Connection, tenant_id: str, source_id: str) -> list[dict]:
    """Active ledgers that may receive the source ledger's balance."""
    source = _account_or_error(conn, tenant_id, source_id)
    if not source["is_postable"] or source["status"] != "active" or account_is_system(source):
        return []
    balances = {row["id"]: row["balance"] for row in account_balances(conn, tenant_id)}
    return [{**dict(row), "balance": balances.get(row["id"], 0),
             "group_label": account_group_label(row["group_code"], row["type"])}
            for row in _compatible_merge_targets(conn, tenant_id, source)]


def archive_account(conn: sqlite3.Connection, tenant_id: str, account_id: str,
                    reason: str, archived_by: str | None = None) -> dict:
    """Archive a zero-balance, non-control ledger without touching its history."""
    reason = _clean_account_reason(reason)
    own_tx = not conn.in_transaction
    if own_tx:
        conn.execute("BEGIN IMMEDIATE")
    try:
        account = _account_or_error(conn, tenant_id, account_id)
        if account["status"] == "archived":
            raise AccountingError("ACCOUNT_ALREADY_ARCHIVED", "This account is already archived.")
        if account_is_system(account):
            raise AccountingError(
                "SYSTEM_ACCOUNT",
                "This is a system or control ledger. It cannot be archived.",
            )
        if _account_party(conn, tenant_id, account_id):
            raise AccountingError(
                "PARTY_ACCOUNT",
                "This ledger is linked to a customer or vendor. Merge it into another ledger "
                "for the same party instead of archiving it.",
            )
        item_refs = conn.execute(
            "SELECT COUNT(*) AS c FROM item WHERE tenant_id=? AND revenue_code=?",
            (tenant_id, account["code"]),
        ).fetchone()["c"]
        if item_refs:
            raise AccountingError(
                "ACCOUNT_IN_USE",
                f"This sales ledger is used by {item_refs} product(s). Choose another sales "
                f"ledger for those products before archiving it.",
            )
        balance = account_balance(conn, tenant_id, account_id)
        if balance:
            side = "Dr" if balance > 0 else "Cr"
            raise AccountingError(
                "ACCOUNT_HAS_BALANCE",
                f"This account still has a balance of {money.fmt(abs(balance))} {side}. "
                f"Merge it into another ledger or post a zeroing journal first.",
            )
        conn.execute(
            "UPDATE account SET status='archived', archived_at=?, archived_by=?,"
            " merged_into_id=NULL WHERE id=? AND tenant_id=?",
            (db.now(), archived_by, account_id, tenant_id),
        )
        audit(conn, tenant_id, archived_by, "account.archive", "account", account_id,
              meta={"code": account["code"], "name": account["name"],
                    "group": account["group_code"], "reason": reason, "balance": 0})
        if own_tx:
            conn.execute("COMMIT")
        return {"account_id": account_id, "reason": reason, "balance": 0}
    except Exception:
        if own_tx:
            conn.execute("ROLLBACK")
        raise


def restore_account(conn: sqlite3.Connection, tenant_id: str, account_id: str,
                    reason: str = "", restored_by: str | None = None) -> dict:
    """Re-activate an archived ledger. Its history and zero/transfer balance remain."""
    reason = _clean_account_reason(reason, required=False)
    own_tx = not conn.in_transaction
    if own_tx:
        conn.execute("BEGIN IMMEDIATE")
    try:
        account = _account_or_error(conn, tenant_id, account_id)
        if account["status"] != "archived":
            raise AccountingError("ACCOUNT_NOT_ARCHIVED", "This account is already active.")
        previous_target = account["merged_into_id"]
        conn.execute(
            "UPDATE account SET status='active', archived_at=NULL, archived_by=NULL,"
            " merged_into_id=NULL WHERE id=? AND tenant_id=?",
            (account_id, tenant_id),
        )
        audit(conn, tenant_id, restored_by, "account.restore", "account", account_id,
              meta={"code": account["code"], "name": account["name"],
                    "reason": reason, "merged_into": previous_target})
        if own_tx:
            conn.execute("COMMIT")
        return {"account_id": account_id, "reason": reason,
                "merged_into": previous_target}
    except Exception:
        if own_tx:
            conn.execute("ROLLBACK")
        raise


def merge_accounts(conn: sqlite3.Connection, tenant_id: str, source_id: str, target_id: str,
                   reason: str, merged_by: str | None = None) -> dict:
    """Post a reclassification journal, then archive the source ledger.

    The source keeps all of its history. Only its net balance moves to the target,
    so the trial balance and all reports remain balanced. Party-linked ledgers can
    only merge into a target linked to the same customer/vendor; bank ledgers can
    only merge into another bank ledger.
    """
    reason = _clean_account_reason(reason)
    if source_id == target_id:
        raise AccountingError("SAME_ACCOUNT", "Choose a different target ledger.")
    own_tx = not conn.in_transaction
    if own_tx:
        conn.execute("BEGIN IMMEDIATE")
    else:
        conn.execute("SAVEPOINT sp_merge_account")
    try:
        source = _account_or_error(conn, tenant_id, source_id)
        target = _account_or_error(conn, tenant_id, target_id)
        if source["status"] != "active" or target["status"] != "active":
            raise AccountingError("ACCOUNT_ARCHIVED", "Both ledgers must be active to merge.")
        if not source["is_postable"] or not target["is_postable"]:
            raise AccountingError(
                "ACCOUNT_NOT_POSTABLE",
                "Merge accepts postable ledgers only, so the transfer can be journalised.",
            )
        if account_is_system(source) or account_is_system(target):
            raise AccountingError(
                "SYSTEM_ACCOUNT",
                "System or control ledgers cannot be merged. Choose ordinary ledgers.",
            )
        if source["type"] != target["type"]:
            raise AccountingError(
                "TYPE_MISMATCH",
                "Merge ledgers with the same accounting type only "
                f"({source['type'].title()} here).",
            )
        if target["group_code"] == "opening_equity":
            raise AccountingError("TARGET_NOT_ALLOWED",
                                  "Opening Balance Equity cannot be a merge target.")
        if _account_party(conn, tenant_id, source_id) != _account_party(conn, tenant_id, target_id):
            raise AccountingError(
                "PARTY_MISMATCH",
                "A customer/vendor ledger can only merge into another ledger linked to the "
                "same party, and an ordinary ledger cannot merge into a party ledger.",
            )
        source_bank = source["group_code"] == "bank"
        target_bank = target["group_code"] == "bank"
        if source_bank != target_bank:
            raise AccountingError(
                "BANK_MISMATCH",
                "A bank ledger can only merge into another bank ledger.",
            )
        future = conn.execute(
            """SELECT MAX(e.entry_date) AS d
               FROM journal_entry e JOIN journal_line l ON l.entry_id=e.id
               WHERE e.tenant_id=? AND l.account_id=? AND e.entry_date>?""",
            (tenant_id, source_id, _today_iso()),
        ).fetchone()["d"]
        if future:
            raise AccountingError(
                "FUTURE_ACTIVITY",
                f"This ledger has an entry dated {future}. Merge after that date so no balance "
                f"is left behind.",
            )

        balance = account_balance(conn, tenant_id, source_id)
        party = _account_party(conn, tenant_id, source_id)
        party_id = party[1] if party else None
        entry_id = None
        if balance:
            if balance > 0:
                lines = [
                    {"account_id": source_id, "debit": 0, "credit": balance,
                     "party_id": party_id, "memo": "Merge-out reclassification"},
                    {"account_id": target_id, "debit": balance, "credit": 0,
                     "party_id": party_id, "memo": "Merge-in reclassification"},
                ]
            else:
                lines = [
                    {"account_id": source_id, "debit": -balance, "credit": 0,
                     "party_id": party_id, "memo": "Merge-out reclassification"},
                    {"account_id": target_id, "debit": 0, "credit": -balance,
                     "party_id": party_id, "memo": "Merge-in reclassification"},
                ]
            narration = (f"Merge {source['code']} {source['name']} into "
                         f"{target['code']} {target['name']}: {reason}")
            entry_id = post_journal(
                conn, tenant_id, _today_iso(), narration, lines,
                source_type="merge", source_id=source_id, created_by=merged_by,
            )
            if account_balance(conn, tenant_id, source_id) != 0:
                raise AccountingError(
                    "MERGE_INCOMPLETE",
                    "The source ledger did not reach zero. Nothing was merged.",
                )
        conn.execute(
            "UPDATE account SET status='archived', archived_at=?, archived_by=?,"
            " merged_into_id=? WHERE id=? AND tenant_id=?",
            (db.now(), merged_by, target_id, source_id, tenant_id),
        )
        item_count = 0
        if source["type"] == "income":
            cur = conn.execute(
                "UPDATE item SET revenue_code=? WHERE tenant_id=? AND revenue_code=?",
                (target["code"], tenant_id, source["code"]),
            )
            item_count = cur.rowcount
        party_repointed = 0
        if party:
            table = "customer" if party[0] == "customer" else "vendor"
            cur = conn.execute(
                f"UPDATE {table} SET account_id=? WHERE tenant_id=? AND id=?"
                f" AND (account_id=? OR account_id IS NULL OR account_id='')",
                (target_id, tenant_id, party[1], source_id),
            )
            party_repointed = cur.rowcount
        entry_no = None
        if entry_id:
            entry_no = conn.execute(
                "SELECT entry_no FROM journal_entry WHERE id=?", (entry_id,)
            ).fetchone()["entry_no"]
        audit(conn, tenant_id, merged_by, "account.merge", "account", source_id,
              meta={"source_code": source["code"], "source_name": source["name"],
                    "target_id": target_id, "target_code": target["code"],
                    "target_name": target["name"], "reason": reason,
                    "balance": balance, "entry_id": entry_id, "entry_no": entry_no,
                    "items_repointed": item_count, "party_repointed": party_repointed})
        if own_tx:
            conn.execute("COMMIT")
        else:
            conn.execute("RELEASE sp_merge_account")
        return {"source_id": source_id, "target_id": target_id, "balance": balance,
                "entry_id": entry_id, "entry_no": entry_no, "item_count": item_count,
                "party_repointed": party_repointed}
    except Exception:
        if own_tx:
            conn.execute("ROLLBACK")
        else:
            conn.execute("ROLLBACK TO sp_merge_account")
            conn.execute("RELEASE sp_merge_account")
        raise


OPENING_EQUITY_NAME = "Opening Balance Equity"


def opening_equity_account(conn: sqlite3.Connection, tenant_id: str,
                           created_by: str | None = None) -> str:
    """Return the tenant's Opening Balance Equity account, creating it if needed."""
    row = conn.execute(
        "SELECT id FROM account WHERE tenant_id=? AND type='equity' AND name=?",
        (tenant_id, OPENING_EQUITY_NAME),
    ).fetchone()
    if row:
        return row["id"]
    used = {r["code"] for r in conn.execute(
        "SELECT code FROM account WHERE tenant_id=?", (tenant_id,)).fetchall()}
    for number in range(3200, 3300):
        code = str(number)
        if code not in used:
            return create_account(conn, tenant_id, code, OPENING_EQUITY_NAME, "equity",
                                  created_by=created_by, group_code="opening_equity")
    raise AccountingError("NO_CODE",
                         "No free equity code remains for the Opening Balance Equity account.")


def opening_balance_entry(conn: sqlite3.Connection, tenant_id: str, account_id: str) -> dict | None:
    """Latest posted opening-balance entry for one account, if any."""
    row = conn.execute(
        """SELECT e.id, e.entry_no, e.entry_date, e.narration,
                  l.debit_paise, l.credit_paise
           FROM journal_entry e
           JOIN journal_line l ON l.entry_id=e.id AND l.account_id=?
           WHERE e.tenant_id=? AND e.source_type='opening' AND e.source_id=?
             AND e.status='posted'
           ORDER BY e.entry_date DESC, e.entry_no DESC LIMIT 1""",
        (account_id, tenant_id, account_id),
    ).fetchone()
    return dict(row) if row else None


def set_opening_balance(conn: sqlite3.Connection, tenant_id: str, account_id: str,
                        as_of: str, amount: int, side: str,
                        created_by: str | None = None, note: str = "") -> str:
    """Post one opening balance against Opening Balance Equity.

    Opening balances are journals, not editable account fields: the account line
    and the equity line are always equal and can never become an unbalanced
    starting figure. A posted opening entry must be reversed before it can be
    replaced. ``note`` is an optional import/migration note appended to the
    journal narration; it never changes the amounts.
    """
    if not isinstance(amount, int) or amount <= 0:
        raise AccountingError("BAD_OPENING_AMOUNT", "Opening balance must be greater than zero.")
    side = (side or "").strip().lower()
    if side not in ("debit", "credit"):
        raise AccountingError("BAD_OPENING_SIDE", "Choose Debit or Credit for the opening balance.")
    try:
        as_of = date.fromisoformat((as_of or "").strip()).isoformat()
    except ValueError as exc:
        raise AccountingError("BAD_OPENING_DATE", "Choose a valid opening balance date.") from exc
    if as_of > _today_iso():
        raise AccountingError("BAD_OPENING_DATE", "Opening balance date cannot be in the future.")

    account = conn.execute(
        "SELECT * FROM account WHERE id=? AND tenant_id=?", (account_id, tenant_id)
    ).fetchone()
    if not account:
        raise AccountingError("ACCOUNT_NOT_FOUND", "Account not found in this business.")
    if not account["is_postable"]:
        raise AccountingError("ACCOUNT_NOT_POSTABLE", "This account cannot receive postings.")
    if account["status"] != "active":
        raise AccountingError(
            "ACCOUNT_ARCHIVED",
            "This account is archived. Restore it before posting an opening balance.",
        )

    equity_id = opening_equity_account(conn, tenant_id, created_by=created_by)
    if account_id == equity_id:
        raise AccountingError(
            "OPENING_EQUITY_ACCOUNT",
            "Opening balances are posted against Opening Balance Equity; choose another account.",
        )

    existing = conn.execute(
        "SELECT entry_no FROM journal_entry WHERE tenant_id=? AND source_type='opening'"
        " AND source_id=? AND status='posted' ORDER BY entry_no DESC LIMIT 1",
        (tenant_id, account_id),
    ).fetchone()
    if existing:
        raise AccountingError(
            "OPENING_EXISTS",
            f"Opening balance is already set by {existing['entry_no']}. Reverse that entry first to replace it.",
        )

    earliest = conn.execute(
        """SELECT MIN(e.entry_date) AS d
           FROM journal_entry e JOIN journal_line l ON l.entry_id=e.id
           WHERE e.tenant_id=? AND l.account_id=? AND e.status='posted'
             AND e.source_type!='opening'""",
        (tenant_id, account_id),
    ).fetchone()["d"]
    if earliest and as_of > earliest:
        raise AccountingError(
            "OPENING_AFTER_ACTIVITY",
            f"Opening balance must be dated on or before the first posted entry ({earliest}).",
        )

    party = conn.execute(
        "SELECT party_id, party_type FROM account_profile WHERE tenant_id=? AND account_id=?",
        (tenant_id, account_id),
    ).fetchone()
    party_id = party["party_id"] if party and party["party_type"] in ("customer", "vendor") else None
    if side == "debit":
        lines = [
            {"account_id": account_id, "debit": amount, "credit": 0, "party_id": party_id},
            {"account_id": equity_id, "debit": 0, "credit": amount},
        ]
    else:
        lines = [
            {"account_id": account_id, "debit": 0, "credit": amount, "party_id": party_id},
            {"account_id": equity_id, "debit": amount, "credit": 0},
        ]

    narration = f"Opening balance - {account['name']}"
    note = (note or "").strip()[:160]
    if note:
        narration += f" - {note}"
    entry_id = post_journal(
        conn, tenant_id, as_of, narration, lines,
        source_type="opening", source_id=account_id, created_by=created_by,
    )
    entry = conn.execute("SELECT entry_no FROM journal_entry WHERE id=?", (entry_id,)).fetchone()
    audit(conn, tenant_id, created_by, "opening_balance.set", "account", account_id,
          meta={"entry_id": entry_id, "entry_no": entry["entry_no"], "date": as_of,
                "amount": amount, "side": side, "note": note})
    return entry_id


# --------------------------------------------------------------------------
# journal posting
# --------------------------------------------------------------------------

def post_journal(conn: sqlite3.Connection, tenant_id: str, entry_date: str, narration: str,
                 lines: list[dict], source_type: str, source_id: str | None = None,
                 idempotency_key: str | None = None, created_by: str | None = None) -> str:
    """Post a balanced journal entry atomically. Returns entry id.

    lines: [{"account_id":..., "debit": paise, "credit": paise, "memo":...}]
    """
    if len(lines) < 2:
        raise AccountingError("TOO_FEW_LINES", "A journal entry needs at least two lines")

    total_debit = total_credit = 0
    clean = []
    for ln in lines:
        d = int(ln.get("debit", 0))
        c = int(ln.get("credit", 0))
        if d < 0 or c < 0:
            raise AccountingError("NEGATIVE_AMOUNT", "Debit/credit must be >= 0")
        if (d == 0) == (c == 0):
            raise AccountingError("LINE_SIDE", "Exactly one of debit/credit must be non-zero")
        total_debit += d
        total_credit += c
        clean.append((ln["account_id"], d, c, ln.get("memo"), ln.get("party_id")))

    if total_debit != total_credit:
        raise AccountingError(
            "UNBALANCED",
            f"Entry does not balance: debit {total_debit} != credit {total_credit}",
        )
    if total_debit == 0:
        raise AccountingError("ZERO_ENTRY", "Entry has no value")

    _assert_accounts(conn, tenant_id, {c[0] for c in clean})
    _assert_period_open(conn, tenant_id, entry_date)

    own_tx = not conn.in_transaction
    if own_tx:
        conn.execute("BEGIN IMMEDIATE")
    else:
        conn.execute("SAVEPOINT sp_post_journal")
    try:
        if idempotency_key:
            row = conn.execute(
                "SELECT id FROM journal_entry WHERE tenant_id=? AND idempotency_key=?",
                (tenant_id, idempotency_key),
            ).fetchone()
            if row:
                if own_tx:
                    conn.execute("COMMIT")
                else:
                    conn.execute("RELEASE sp_post_journal")
                return row["id"]

        entry_id = db.new_id()
        entry_no = db.next_number(conn, tenant_id, "journal", "JV")
        conn.execute(
            "INSERT INTO journal_entry (id, tenant_id, entry_no, entry_date, narration, source_type,"
            " source_id, idempotency_key, status, posted_at, created_by)"
            " VALUES (?,?,?,?,?,?,?,?, 'posted', ?, ?)",
            (entry_id, tenant_id, entry_no, entry_date, narration, source_type,
             source_id, idempotency_key, db.now(), created_by),
        )
        for i, (aid, d, c, memo, party) in enumerate(clean, start=1):
            conn.execute(
                "INSERT INTO journal_line (id, tenant_id, entry_id, line_no, account_id, party_id,"
                " debit_paise, credit_paise, memo) VALUES (?,?,?,?,?,?,?,?,?)",
                (db.new_id(), tenant_id, entry_id, i, aid, party, d, c, memo),
            )
        audit(conn, tenant_id, created_by, "ledger.post", "journal_entry", entry_id,
              meta={"amount": total_debit, "lines": len(clean), "source": source_type})
        if own_tx:
            conn.execute("COMMIT")
        else:
            conn.execute("RELEASE sp_post_journal")
        return entry_id
    except Exception:
        if own_tx:
            conn.execute("ROLLBACK")
        else:
            conn.execute("ROLLBACK TO sp_post_journal")
            conn.execute("RELEASE sp_post_journal")
        raise


def reverse_entry(conn: sqlite3.Connection, tenant_id: str, entry_id: str, reason: str,
                  created_by: str | None = None) -> str:
    if not reason or not reason.strip():
        raise AccountingError("REASON_REQUIRED", "A reversal reason is required")
    entry = conn.execute(
        "SELECT * FROM journal_entry WHERE id=? AND tenant_id=?", (entry_id, tenant_id)
    ).fetchone()
    if not entry:
        raise AccountingError("ENTRY_NOT_FOUND", "Journal entry not found")
    if entry["status"] == "reversed":
        raise AccountingError("ALREADY_REVERSED", "Entry is already reversed")

    lines = conn.execute(
        "SELECT * FROM journal_line WHERE entry_id=? ORDER BY line_no", (entry_id,)
    ).fetchall()
    mirrored = [{"account_id": l["account_id"], "debit": l["credit_paise"],
                 "credit": l["debit_paise"], "party_id": l["party_id"],
                 "memo": f"Reversal: {reason}"} for l in lines]

    conn.execute("BEGIN IMMEDIATE")
    try:
        new_id = post_journal(conn, tenant_id, entry["entry_date"],
                              f"Reversal of {entry['entry_no']}: {reason}",
                              mirrored, source_type="reversal", source_id=entry_id,
                              created_by=created_by)
        conn.execute("UPDATE journal_entry SET status='reversed' WHERE id=?", (entry_id,))
        conn.execute("UPDATE journal_entry SET reversal_of=? WHERE id=?", (entry_id, new_id))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return new_id

# --------------------------------------------------------------------------
# invoicing
# --------------------------------------------------------------------------

def create_invoice(conn: sqlite3.Connection, tenant_id: str, customer_id: str, invoice_date: str,
                   place_of_supply_state: str, items: list[dict],
                   idempotency_key: str | None = None, round_to_rupee: bool = False,
                   created_by: str | None = None) -> dict:
    """Create + post an invoice. items: [{item_id, qty, unit_price, discount, tax_rate_bp}]"""
    if not items:
        raise AccountingError("NO_ITEMS", "An invoice needs at least one line")

    tenant = conn.execute("SELECT * FROM tenant WHERE id=?", (tenant_id,)).fetchone()
    if not tenant:
        raise AccountingError("TENANT_NOT_FOUND", "Tenant not found")
    customer = conn.execute(
        "SELECT * FROM customer WHERE id=? AND tenant_id=?", (customer_id, tenant_id)
    ).fetchone()
    if not customer:
        raise AccountingError("CUSTOMER_NOT_FOUND", "Customer not in this tenant")
    _assert_period_open(conn, tenant_id, invoice_date)

    intra = place_of_supply_state == tenant["state_code"]

    computed = []
    sub_total = tax_total = cogs_total = 0
    revenue_by_account: dict[str, int] = {}
    for ln in items:
        item = conn.execute(
            "SELECT * FROM item WHERE id=? AND tenant_id=?", (ln["item_id"], tenant_id)
        ).fetchone()
        if not item:
            raise AccountingError("ITEM_NOT_FOUND", f"Item {ln['item_id']} not in this tenant")

        qty_milli = int(ln["qty"])
        price = int(ln.get("unit_price", item["sale_price_paise"]))
        discount = int(ln.get("discount", 0))
        rate_bp = int(ln.get("tax_rate_bp", item["tax_rate_bp"]))
        if qty_milli <= 0:
            raise AccountingError("BAD_QTY", "Quantity must be positive")
        if price < 0 or discount < 0 or rate_bp < 0:
            raise AccountingError("BAD_AMOUNT", "Negative price/discount/rate")

        gross = mul_qty_price(qty_milli, price)
        if discount > gross:
            raise AccountingError("BAD_DISCOUNT", "Discount cannot exceed line value")
        taxable = gross - discount
        tax = tax_on(taxable, rate_bp)
        line_total = taxable + tax

        if item["track_stock"]:
            if item["stock_milli"] < qty_milli:
                raise AccountingError(
                    "INSUFFICIENT_STOCK",
                    f"Not enough stock for {item['name']}: have {item['stock_milli']/1000:.3f}, need {qty_milli/1000:.3f}",
                )
            cogs_total += (item["cost_paise"] * qty_milli + 500) // 1000

        sub_total += taxable
        tax_total += tax
        revenue_by_account[item["revenue_code"]] = revenue_by_account.get(item["revenue_code"], 0) + taxable
        computed.append({
            "item_id": item["id"], "description": ln.get("description", item["name"]),
            "qty_milli": qty_milli, "unit_price_paise": price, "gross_paise": gross,
            "discount_paise": discount, "taxable_paise": taxable, "tax_rate_bp": rate_bp,
            "tax_paise": tax, "line_total_paise": line_total,
            "track_stock": bool(item["track_stock"]),
        })

    base_total = sub_total + tax_total
    if round_to_rupee:
        total = ((base_total + 50) // 100) * 100
    else:
        total = base_total
    round_off = total - base_total

    acct = db.account_id
    # A customer may have its own Sundry Debtors sub-ledger. In that case the
    # invoice must post to it so the customer statement and ledger agree.
    ar = customer["account_id"] or acct(conn, tenant_id, AR_ACCOUNT)
    cogs = acct(conn, tenant_id, "5000")
    inventory = acct(conn, tenant_id, "1200")
    round_acc = acct(conn, tenant_id, "5900")

    if intra:
        cgst, sgst = split_tax(tax_total)
        tax_lines = [(acct(conn, tenant_id, "2100"), cgst), (acct(conn, tenant_id, "2101"), sgst)]
    else:
        tax_lines = [(acct(conn, tenant_id, "2102"), tax_total)]

    lines = [{"account_id": ar, "debit": total, "credit": 0, "party_id": customer_id,
              "memo": "Invoice receivable"}]
    for code, amount in revenue_by_account.items():
        if not amount:
            continue
        try:
            revenue_account = acct(conn, tenant_id, code)
        except KeyError as exc:
            raise AccountingError("REVENUE_ACCOUNT_NOT_FOUND",
                                  f"Revenue account {code} is missing from the chart of accounts") from exc
        lines.append({"account_id": revenue_account, "debit": 0, "credit": amount,
                      "memo": "Revenue"})
    for acc, amt in tax_lines:
        if amt:
            lines.append({"account_id": acc, "debit": 0, "credit": amt, "memo": "GST output"})
    if cogs_total:
        lines.append({"account_id": cogs, "debit": cogs_total, "credit": 0, "memo": "COGS"})
        lines.append({"account_id": inventory, "debit": 0, "credit": cogs_total, "memo": "Inventory out"})
    if round_off > 0:
        lines.append({"account_id": round_acc, "debit": 0, "credit": round_off, "memo": "Round off"})
    elif round_off < 0:
        lines.append({"account_id": round_acc, "debit": -round_off, "credit": 0, "memo": "Round off"})

    conn.execute("BEGIN IMMEDIATE")
    try:
        if idempotency_key:
            existing = conn.execute(
                "SELECT * FROM invoice WHERE tenant_id=? AND idempotency_key=?",
                (tenant_id, idempotency_key),
            ).fetchone()
            if existing:
                conn.execute("COMMIT")
                return dict(existing)

        entry_id = post_journal(conn, tenant_id, invoice_date,
                                f"Invoice for {customer['name']}", lines,
                                source_type="invoice", idempotency_key=idempotency_key,
                                created_by=created_by)
        invoice_id = db.new_id()
        invoice_no = db.next_number(conn, tenant_id, "invoice", "INV")
        conn.execute(
            "INSERT INTO invoice (id, tenant_id, invoice_no, invoice_date, customer_id,"
            " place_of_supply_state, sub_total_paise, tax_paise, round_off_paise, total_paise,"
            " status, idempotency_key, journal_entry_id, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?, 'posted', ?,?,?)",
            (invoice_id, tenant_id, invoice_no, invoice_date, customer_id, place_of_supply_state,
             sub_total, tax_total, round_off, total, idempotency_key, entry_id, db.now()),
        )
        for c in computed:
            conn.execute(
                "INSERT INTO invoice_line (id, tenant_id, invoice_id, item_id, description, qty_milli,"
                " unit_price_paise, gross_paise, discount_paise, taxable_paise, tax_rate_bp,"
                " tax_paise, line_total_paise) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (db.new_id(), tenant_id, invoice_id, c["item_id"], c["description"], c["qty_milli"],
                 c["unit_price_paise"], c["gross_paise"], c["discount_paise"], c["taxable_paise"],
                 c["tax_rate_bp"], c["tax_paise"], c["line_total_paise"]),
            )
            if c["track_stock"]:
                conn.execute(
                    "UPDATE item SET stock_milli = stock_milli - ? WHERE id=?",
                    (c["qty_milli"], c["item_id"]),
                )
        conn.execute("UPDATE journal_entry SET source_id=? WHERE id=?", (invoice_id, entry_id))
        audit(conn, tenant_id, created_by, "invoice.create", "invoice", invoice_id,
              meta={"total": total, "invoice_no": invoice_no})
        conn.execute("COMMIT")
        return dict(conn.execute("SELECT * FROM invoice WHERE id=?", (invoice_id,)).fetchone())
    except Exception:
        conn.execute("ROLLBACK")
        raise


# --------------------------------------------------------------------------
# receivables / payables: receipts, vendor payments, bills, credit notes
# --------------------------------------------------------------------------

CASH_ACCOUNT = "1000"
BANK_ACCOUNT = "1010"
AR_ACCOUNT = "1100"
AP_ACCOUNT = "2000"


def _doc_or_raise(conn: sqlite3.Connection, tenant_id: str, table: str, doc_id: str,
                  label: str) -> sqlite3.Row:
    row = conn.execute(
        f"SELECT * FROM {table} WHERE id=? AND tenant_id=?", (doc_id, tenant_id)
    ).fetchone()
    if not row:
        raise AccountingError("DOC_NOT_FOUND", f"{label} not found in this business")
    return row


def invoice_outstanding(conn: sqlite3.Connection, tenant_id: str, invoice_id: str) -> int:
    inv = _doc_or_raise(conn, tenant_id, "invoice", invoice_id, "Invoice")
    allocated = conn.execute(
        "SELECT COALESCE(SUM(amount_paise),0) a FROM payment_allocation"
        " WHERE tenant_id=? AND doc_type='invoice' AND doc_id=?",
        (tenant_id, invoice_id),
    ).fetchone()["a"]
    credited = conn.execute(
        "SELECT COALESCE(SUM(total_paise),0) c FROM credit_note"
        " WHERE tenant_id=? AND invoice_id=?",
        (tenant_id, invoice_id),
    ).fetchone()["c"]
    return inv["total_paise"] - allocated - credited


def bill_outstanding(conn: sqlite3.Connection, tenant_id: str, bill_id: str) -> int:
    bill = _doc_or_raise(conn, tenant_id, "bill", bill_id, "Bill")
    allocated = conn.execute(
        "SELECT COALESCE(SUM(amount_paise),0) a FROM payment_allocation"
        " WHERE tenant_id=? AND doc_type='bill' AND doc_id=?",
        (tenant_id, bill_id),
    ).fetchone()["a"]
    debited = conn.execute(
        "SELECT COALESCE(SUM(total_paise),0) d FROM debit_note"
        " WHERE tenant_id=? AND bill_id=?",
        (tenant_id, bill_id),
    ).fetchone()["d"]
    return bill["total_paise"] - allocated - debited


def record_payment(conn: sqlite3.Connection, tenant_id: str, direction: str, party_id: str,
                   payment_date: str, amount_paise: int, mode: str = "bank",
                   allocations: list[dict] | None = None, reference: str = "", notes: str = "",
                   idempotency_key: str | None = None, created_by: str | None = None) -> dict:
    """Record a customer receipt or a vendor payment, optionally allocating it to documents."""
    if direction not in ("receipt", "payment"):
        raise AccountingError("BAD_DIRECTION", "Direction must be receipt or payment")
    if amount_paise <= 0:
        raise AccountingError("BAD_AMOUNT", "Payment amount must be greater than zero")
    if mode not in ("cash", "bank", "upi", "cheque", "card"):
        raise AccountingError("BAD_MODE", "Unknown payment mode")

    if idempotency_key:
        existing = conn.execute(
            "SELECT * FROM payment WHERE tenant_id=? AND idempotency_key=?",
            (tenant_id, idempotency_key),
        ).fetchone()
        if existing:
            return dict(existing)

    party_type = "customer" if direction == "receipt" else "vendor"
    table = "customer" if direction == "receipt" else "vendor"
    party = _doc_or_raise(conn, tenant_id, table, party_id, party_type.title())
    _assert_period_open(conn, tenant_id, payment_date)

    allocations = allocations or []
    total_alloc = 0
    for al in allocations:
        doc_type = al["doc_type"]
        expected = "invoice" if direction == "receipt" else "bill"
        if doc_type != expected:
            raise AccountingError("BAD_ALLOCATION", f"{direction} can only allocate to {expected}s")
        if int(al["amount"]) <= 0:
            raise AccountingError("BAD_ALLOCATION", "Allocation amount must be positive")
        if doc_type == "invoice":
            outstanding = invoice_outstanding(conn, tenant_id, al["doc_id"])
        else:
            outstanding = bill_outstanding(conn, tenant_id, al["doc_id"])
        if int(al["amount"]) > outstanding:
            raise AccountingError(
                "OVER_ALLOCATION",
                f"Allocation {al['amount']} exceeds outstanding {outstanding} for {doc_type}",
            )
        total_alloc += int(al["amount"])
    if total_alloc > amount_paise:
        raise AccountingError("OVER_ALLOCATION", "Allocations exceed the payment amount")

    cash_or_bank = db.account_id(
        conn, tenant_id, CASH_ACCOUNT if mode == "cash" else BANK_ACCOUNT
    )
    if direction == "receipt":
        ar = party["account_id"] or db.account_id(conn, tenant_id, AR_ACCOUNT)
        lines = [
            {"account_id": cash_or_bank, "debit": amount_paise, "credit": 0,
             "memo": f"Receipt from {party['name']}"},
            {"account_id": ar, "debit": 0, "credit": amount_paise, "party_id": party_id,
             "memo": f"Receipt from {party['name']}"},
        ]
        narration = f"Receipt from {party['name']}" + (f" ({reference})" if reference else "")
        prefix, doc_type = "RCPT", "receipt"
    else:
        ap = party["account_id"] or db.account_id(conn, tenant_id, AP_ACCOUNT)
        lines = [
            {"account_id": ap, "debit": amount_paise, "credit": 0, "party_id": party_id,
             "memo": f"Payment to {party['name']}"},
            {"account_id": cash_or_bank, "debit": 0, "credit": amount_paise,
             "memo": f"Payment to {party['name']}"},
        ]
        narration = f"Payment to {party['name']}" + (f" ({reference})" if reference else "")
        prefix, doc_type = "PYMT", "payment"

    conn.execute("BEGIN IMMEDIATE")
    try:
        if idempotency_key:
            existing = conn.execute(
                "SELECT * FROM payment WHERE tenant_id=? AND idempotency_key=?",
                (tenant_id, idempotency_key),
            ).fetchone()
            if existing:
                conn.execute("COMMIT")
                return dict(existing)

        entry_id = post_journal(conn, tenant_id, payment_date, narration, lines,
                                source_type=doc_type, idempotency_key=idempotency_key,
                                created_by=created_by)
        payment_id = db.new_id()
        voucher_no = db.next_number(conn, tenant_id, doc_type, prefix)
        conn.execute(
            "INSERT INTO payment (id, tenant_id, voucher_no, payment_date, direction, party_type,"
            " party_id, mode, account_id, amount_paise, reference, notes, journal_entry_id,"
            " idempotency_key, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (payment_id, tenant_id, voucher_no, payment_date, direction, party_type, party_id,
             mode, cash_or_bank, amount_paise, reference[:120], notes[:500], entry_id,
             idempotency_key, db.now()),
        )
        for al in allocations:
            conn.execute(
                "INSERT INTO payment_allocation (id, tenant_id, payment_id, doc_type, doc_id,"
                " amount_paise) VALUES (?,?,?,?,?,?)",
                (db.new_id(), tenant_id, payment_id, al["doc_type"], al["doc_id"], int(al["amount"])),
            )
        conn.execute("UPDATE journal_entry SET source_id=? WHERE id=?", (payment_id, entry_id))
        audit(conn, tenant_id, created_by, f"payment.{direction}", "payment", payment_id,
              meta={"amount": amount_paise, "mode": mode, "allocations": len(allocations)})
        conn.execute("COMMIT")
        return dict(conn.execute("SELECT * FROM payment WHERE id=?", (payment_id,)).fetchone())
    except Exception:
        conn.execute("ROLLBACK")
        raise


def create_bill(conn: sqlite3.Connection, tenant_id: str, vendor_id: str, bill_date: str,
                vendor_bill_no: str, place_of_supply_state: str, items: list[dict],
                idempotency_key: str | None = None, round_to_rupee: bool = False,
                created_by: str | None = None) -> dict:
    """Post a purchase bill: input GST, inventory/purchases, and accounts payable."""
    if not items:
        raise AccountingError("NO_ITEMS", "A bill needs at least one line")
    tenant = conn.execute("SELECT * FROM tenant WHERE id=?", (tenant_id,)).fetchone()
    if not tenant:
        raise AccountingError("TENANT_NOT_FOUND", "Tenant not found")
    vendor = _doc_or_raise(conn, tenant_id, "vendor", vendor_id, "Vendor")
    _assert_period_open(conn, tenant_id, bill_date)

    intra = place_of_supply_state == tenant["state_code"]
    computed = []
    sub_total = tax_total = 0
    stock_value = 0
    purchase_value = 0

    for ln in items:
        item = _doc_or_raise(conn, tenant_id, "item", ln["item_id"], "Item")
        qty_milli = int(ln["qty"])
        price = int(ln.get("unit_price", item["cost_paise"]))
        discount = int(ln.get("discount", 0))
        rate_bp = int(ln.get("tax_rate_bp", item["tax_rate_bp"]))
        if qty_milli <= 0:
            raise AccountingError("BAD_QTY", "Quantity must be positive")
        if price < 0 or discount < 0 or rate_bp < 0:
            raise AccountingError("BAD_AMOUNT", "Negative price/discount/rate")
        gross = mul_qty_price(qty_milli, price)
        if discount > gross:
            raise AccountingError("BAD_DISCOUNT", "Discount cannot exceed line value")
        taxable = gross - discount
        tax = tax_on(taxable, rate_bp)

        if item["track_stock"]:
            stock_value += taxable
            old_qty = item["stock_milli"]
            old_cost = item["cost_paise"]
            new_qty = old_qty + qty_milli
            # old_qty is in thousandths; taxable is paise for the purchased quantity.
            # Convert taxable to milli-paise so both sides share the same unit.
            new_cost = ((old_qty * old_cost + taxable * 1000) + new_qty // 2) // new_qty if new_qty else price
        else:
            purchase_value += taxable

        sub_total += taxable
        tax_total += tax
        computed.append({
            "item_id": item["id"], "description": ln.get("description", item["name"]),
            "qty_milli": qty_milli, "unit_price_paise": price, "gross_paise": gross,
            "discount_paise": discount, "taxable_paise": taxable, "tax_rate_bp": rate_bp,
            "tax_paise": tax, "line_total_paise": taxable + tax,
            "new_qty": item["stock_milli"] + qty_milli if item["track_stock"] else None,
            "new_cost": new_cost if item["track_stock"] else None,
        })

    base_total = sub_total + tax_total
    total = ((base_total + 50) // 100) * 100 if round_to_rupee else base_total
    round_off = total - base_total

    acct = db.account_id
    ap = vendor["account_id"] or acct(conn, tenant_id, AP_ACCOUNT)
    inventory = acct(conn, tenant_id, "1200")
    purchases = acct(conn, tenant_id, "5100")
    round_acc = acct(conn, tenant_id, "5900")

    if intra:
        cgst, sgst = split_tax(tax_total)
        tax_lines = [(acct(conn, tenant_id, "2200"), cgst), (acct(conn, tenant_id, "2201"), sgst)]
    else:
        tax_lines = [(acct(conn, tenant_id, "2202"), tax_total)]

    lines = [{"account_id": ap, "debit": 0, "credit": total, "party_id": vendor_id,
              "memo": "Bill payable"}]
    if stock_value:
        lines.append({"account_id": inventory, "debit": stock_value, "credit": 0,
                      "memo": "Inventory in"})
    if purchase_value:
        lines.append({"account_id": purchases, "debit": purchase_value, "credit": 0,
                      "memo": "Purchases"})
    for acc, amt in tax_lines:
        if amt:
            lines.append({"account_id": acc, "debit": amt, "credit": 0, "memo": "GST input"})
    if round_off > 0:
        lines.append({"account_id": round_acc, "debit": round_off, "credit": 0, "memo": "Round off"})
    elif round_off < 0:
        lines.append({"account_id": round_acc, "debit": 0, "credit": -round_off, "memo": "Round off"})

    conn.execute("BEGIN IMMEDIATE")
    try:
        if idempotency_key:
            existing = conn.execute(
                "SELECT * FROM bill WHERE tenant_id=? AND idempotency_key=?",
                (tenant_id, idempotency_key),
            ).fetchone()
            if existing:
                conn.execute("COMMIT")
                return dict(existing)

        entry_id = post_journal(conn, tenant_id, bill_date, f"Bill from {vendor['name']}", lines,
                                source_type="bill", idempotency_key=idempotency_key,
                                created_by=created_by)
        bill_id = db.new_id()
        bill_no = db.next_number(conn, tenant_id, "bill", "BILL")
        conn.execute(
            "INSERT INTO bill (id, tenant_id, bill_no, vendor_bill_no, bill_date, vendor_id,"
            " place_of_supply_state, sub_total_paise, tax_paise, round_off_paise, total_paise,"
            " status, idempotency_key, journal_entry_id, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?, 'posted', ?,?,?)",
            (bill_id, tenant_id, bill_no, (vendor_bill_no or "")[:60], bill_date, vendor_id,
             place_of_supply_state, sub_total, tax_total, round_off, total, idempotency_key,
             entry_id, db.now()),
        )
        for c in computed:
            conn.execute(
                "INSERT INTO bill_line (id, tenant_id, bill_id, item_id, description, qty_milli,"
                " unit_price_paise, gross_paise, discount_paise, taxable_paise, tax_rate_bp,"
                " tax_paise, line_total_paise) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (db.new_id(), tenant_id, bill_id, c["item_id"], c["description"], c["qty_milli"],
                 c["unit_price_paise"], c["gross_paise"], c["discount_paise"], c["taxable_paise"],
                 c["tax_rate_bp"], c["tax_paise"], c["line_total_paise"]),
            )
            if c["new_qty"] is not None:
                conn.execute(
                    "UPDATE item SET stock_milli=?, cost_paise=? WHERE id=?",
                    (c["new_qty"], c["new_cost"], c["item_id"]),
                )
        conn.execute("UPDATE journal_entry SET source_id=? WHERE id=?", (bill_id, entry_id))
        audit(conn, tenant_id, created_by, "bill.create", "bill", bill_id,
              meta={"total": total, "bill_no": bill_no})
        conn.execute("COMMIT")
        return dict(conn.execute("SELECT * FROM bill WHERE id=?", (bill_id,)).fetchone())
    except Exception:
        conn.execute("ROLLBACK")
        raise


def create_credit_note(conn: sqlite3.Connection, tenant_id: str, invoice_id: str, note_date: str,
                       reason: str, lines: list[dict], idempotency_key: str | None = None,
                       created_by: str | None = None) -> dict:
    """Sales return / credit note against an invoice. Restores stock at current cost."""
    if not reason or not reason.strip():
        raise AccountingError("REASON_REQUIRED", "A credit note needs a reason")
    if not lines:
        raise AccountingError("NO_ITEMS", "A credit note needs at least one line")
    invoice = _doc_or_raise(conn, tenant_id, "invoice", invoice_id, "Invoice")
    if invoice["status"] != "posted":
        raise AccountingError("INVOICE_NOT_POSTED", "Only posted invoices can be credited")
    _assert_period_open(conn, tenant_id, note_date)

    computed = []
    sub_total = tax_total = cost_total = 0
    revenue_by_account: dict[str, int] = {}

    for ln in lines:
        inv_line = conn.execute(
            "SELECT * FROM invoice_line WHERE id=? AND invoice_id=? AND tenant_id=?",
            (ln["invoice_line_id"], invoice_id, tenant_id),
        ).fetchone()
        if not inv_line:
            raise AccountingError("LINE_NOT_FOUND", "Invoice line not found")
        qty_milli = int(ln["qty"])
        if qty_milli <= 0:
            raise AccountingError("BAD_QTY", "Quantity must be positive")
        already = conn.execute(
            "SELECT COALESCE(SUM(l.qty_milli),0) q FROM credit_note_line l"
            " JOIN credit_note n ON n.id=l.credit_note_id"
            " WHERE n.tenant_id=? AND n.invoice_id=? AND l.invoice_line_id=?",
            (tenant_id, invoice_id, inv_line["id"]),
        ).fetchone()["q"]
        if qty_milli > inv_line["qty_milli"] - already:
            raise AccountingError(
                "OVER_CREDIT",
                f"Cannot credit {qty_milli/1000:.3f}; only {(inv_line['qty_milli']-already)/1000:.3f} returnable",
            )

        gross = mul_qty_price(qty_milli, inv_line["unit_price_paise"])
        disc = (inv_line["discount_paise"] * qty_milli + inv_line["qty_milli"] // 2) // inv_line["qty_milli"]
        taxable = max(0, gross - disc)
        tax = tax_on(taxable, inv_line["tax_rate_bp"])

        item = conn.execute("SELECT * FROM item WHERE id=?", (inv_line["item_id"],)).fetchone()
        cost = 0
        if item and item["track_stock"]:
            cost = (item["cost_paise"] * qty_milli + 500) // 1000
            revenue_code = item["revenue_code"]
        else:
            revenue_code = item["revenue_code"] if item else "4000"
        revenue_by_account[revenue_code] = revenue_by_account.get(revenue_code, 0) + taxable
        sub_total += taxable
        tax_total += tax
        cost_total += cost
        computed.append({
            "invoice_line_id": inv_line["id"], "item_id": inv_line["item_id"],
            "description": inv_line["description"], "qty_milli": qty_milli,
            "unit_price_paise": inv_line["unit_price_paise"], "taxable_paise": taxable,
            "tax_rate_bp": inv_line["tax_rate_bp"], "tax_paise": tax, "cost_paise": cost,
            "line_total_paise": taxable + tax, "track_stock": bool(item and item["track_stock"]),
        })

    total = sub_total + tax_total
    intra = invoice["place_of_supply_state"] == conn.execute(
        "SELECT state_code FROM tenant WHERE id=?", (tenant_id,)).fetchone()["state_code"]

    acct = db.account_id
    customer = _doc_or_raise(conn, tenant_id, "customer", invoice["customer_id"], "Customer")
    ar = customer["account_id"] or acct(conn, tenant_id, AR_ACCOUNT)
    inventory = acct(conn, tenant_id, "1200")
    cogs = acct(conn, tenant_id, "5000")

    if intra:
        cgst, sgst = split_tax(tax_total)
        tax_lines = [(acct(conn, tenant_id, "2100"), cgst), (acct(conn, tenant_id, "2101"), sgst)]
    else:
        tax_lines = [(acct(conn, tenant_id, "2102"), tax_total)]

    lines_j = [{"account_id": ar, "debit": 0, "credit": total, "party_id": invoice["customer_id"],
                "memo": "Credit note"}]
    for code, amount in revenue_by_account.items():
        if amount:
            lines_j.append({"account_id": acct(conn, tenant_id, code), "debit": amount, "credit": 0,
                            "memo": "Sales return"})
    for acc, amt in tax_lines:
        if amt:
            lines_j.append({"account_id": acc, "debit": amt, "credit": 0, "memo": "GST output reversal"})
    if cost_total:
        lines_j.append({"account_id": inventory, "debit": cost_total, "credit": 0, "memo": "Stock in"})
        lines_j.append({"account_id": cogs, "debit": 0, "credit": cost_total, "memo": "COGS reversal"})

    conn.execute("BEGIN IMMEDIATE")
    try:
        if idempotency_key:
            existing = conn.execute(
                "SELECT * FROM credit_note WHERE tenant_id=? AND idempotency_key=?",
                (tenant_id, idempotency_key),
            ).fetchone()
            if existing:
                conn.execute("COMMIT")
                return dict(existing)

        entry_id = post_journal(conn, tenant_id, note_date, f"Credit note: {reason}", lines_j,
                                source_type="credit_note", idempotency_key=idempotency_key,
                                created_by=created_by)
        note_id = db.new_id()
        note_no = db.next_number(conn, tenant_id, "credit_note", "CN")
        conn.execute(
            "INSERT INTO credit_note (id, tenant_id, note_no, note_date, customer_id, invoice_id,"
            " place_of_supply_state, sub_total_paise, tax_paise, round_off_paise, total_paise,"
            " reason, journal_entry_id, idempotency_key, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,0,?,?,?,?,?)",
            (note_id, tenant_id, note_no, note_date, invoice["customer_id"], invoice_id,
             invoice["place_of_supply_state"], sub_total, tax_total, total, reason[:200],
             entry_id, idempotency_key, db.now()),
        )
        for c in computed:
            conn.execute(
                "INSERT INTO credit_note_line (id, tenant_id, credit_note_id, item_id,"
                " invoice_line_id, description, qty_milli, unit_price_paise, taxable_paise,"
                " tax_rate_bp, tax_paise, cost_paise, line_total_paise)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (db.new_id(), tenant_id, note_id, c["item_id"], c["invoice_line_id"],
                 c["description"], c["qty_milli"], c["unit_price_paise"], c["taxable_paise"],
                 c["tax_rate_bp"], c["tax_paise"], c["cost_paise"], c["line_total_paise"]),
            )
            if c["track_stock"]:
                conn.execute("UPDATE item SET stock_milli=stock_milli+? WHERE id=?",
                             (c["qty_milli"], c["item_id"]))
        conn.execute("UPDATE journal_entry SET source_id=? WHERE id=?", (note_id, entry_id))
        audit(conn, tenant_id, created_by, "credit_note.create", "credit_note", note_id,
              meta={"total": total, "invoice_id": invoice_id})
        conn.execute("COMMIT")
        return dict(conn.execute("SELECT * FROM credit_note WHERE id=?", (note_id,)).fetchone())
    except Exception:
        conn.execute("ROLLBACK")
        raise


def create_debit_note(conn: sqlite3.Connection, tenant_id: str, bill_id: str, note_date: str,
                      reason: str, lines: list[dict], idempotency_key: str | None = None,
                      created_by: str | None = None) -> dict:
    """Purchase return / debit note against a bill.

    Reverses the original purchase value and input GST, and reduces the vendor
    payable. Stock is taken out at the bill line's purchase value, so the
    weighted-average cost is restated without inventing a gain or loss.
    """
    if not reason or not reason.strip():
        raise AccountingError("REASON_REQUIRED", "A debit note needs a reason")
    if not lines:
        raise AccountingError("NO_ITEMS", "A debit note needs at least one line")
    bill = _doc_or_raise(conn, tenant_id, "bill", bill_id, "Bill")
    if bill["status"] != "posted":
        raise AccountingError("BILL_NOT_POSTED", "Only posted bills can be debited")
    _assert_period_open(conn, tenant_id, note_date)
    tenant = conn.execute("SELECT * FROM tenant WHERE id=?", (tenant_id,)).fetchone()
    intra = bill["place_of_supply_state"] == tenant["state_code"]

    computed: list[dict] = []
    sub_total = tax_total = stock_value = purchase_value = 0
    stock_out: dict[str, int] = {}
    stock_value_out: dict[str, int] = {}

    for ln in lines:
        bill_line = conn.execute(
            "SELECT * FROM bill_line WHERE id=? AND bill_id=? AND tenant_id=?",
            (ln["bill_line_id"], bill_id, tenant_id),
        ).fetchone()
        if not bill_line:
            raise AccountingError("LINE_NOT_FOUND", "Bill line not found")
        qty_milli = int(ln["qty"])
        if qty_milli <= 0:
            raise AccountingError("BAD_QTY", "Quantity must be positive")
        already = conn.execute(
            "SELECT COALESCE(SUM(l.qty_milli),0) q FROM debit_note_line l"
            " JOIN debit_note n ON n.id=l.debit_note_id"
            " WHERE n.tenant_id=? AND n.bill_id=? AND l.bill_line_id=?",
            (tenant_id, bill_id, bill_line["id"]),
        ).fetchone()["q"]
        if qty_milli > bill_line["qty_milli"] - already:
            raise AccountingError(
                "OVER_DEBIT",
                f"Cannot return {qty_milli/1000:.3f}; only "
                f"{(bill_line['qty_milli']-already)/1000:.3f} returnable",
            )

        gross = mul_qty_price(qty_milli, bill_line["unit_price_paise"])
        disc = (bill_line["discount_paise"] * qty_milli
                + bill_line["qty_milli"] // 2) // bill_line["qty_milli"]
        taxable = max(0, gross - disc)
        tax = tax_on(taxable, bill_line["tax_rate_bp"])

        item = None
        if bill_line["item_id"]:
            item = conn.execute("SELECT * FROM item WHERE id=? AND tenant_id=?",
                                (bill_line["item_id"], tenant_id)).fetchone()
        track = bool(item and item["track_stock"])
        if track:
            stock_value += taxable
            stock_out[item["id"]] = stock_out.get(item["id"], 0) + qty_milli
            stock_value_out[item["id"]] = stock_value_out.get(item["id"], 0) + taxable
        else:
            purchase_value += taxable

        sub_total += taxable
        tax_total += tax
        computed.append({
            "bill_line_id": bill_line["id"], "item_id": bill_line["item_id"],
            "description": bill_line["description"], "qty_milli": qty_milli,
            "unit_price_paise": bill_line["unit_price_paise"], "taxable_paise": taxable,
            "tax_rate_bp": bill_line["tax_rate_bp"], "tax_paise": tax,
            "cost_paise": taxable if track else 0, "line_total_paise": taxable + tax,
            "track_stock": track,
        })

    # Validate stock quantity and restated average cost before posting anything.
    cost_updates: dict[str, tuple[int, int]] = {}
    for item_id, qty_out in stock_out.items():
        item = conn.execute("SELECT * FROM item WHERE id=?", (item_id,)).fetchone()
        if item["stock_milli"] < qty_out:
            raise AccountingError(
                "INSUFFICIENT_STOCK",
                f"Cannot return {qty_out/1000:.3f} of {item['name']}; only "
                f"{item['stock_milli']/1000:.3f} in stock",
            )
        new_qty = item["stock_milli"] - qty_out
        new_value_milli = item["stock_milli"] * item["cost_paise"] - stock_value_out[item_id] * 1000
        if new_qty > 0 and new_value_milli < 0:
            raise AccountingError(
                "COST_UNDERFLOW",
                f"Inventory value is lower than the purchase value being returned for {item['name']}."
                " Post an inventory revaluation journal first.",
            )
        new_cost = ((new_value_milli + new_qty // 2) // new_qty) if new_qty > 0 else item["cost_paise"]
        cost_updates[item_id] = (new_qty, max(0, new_cost))

    total = sub_total + tax_total

    acct = db.account_id
    vendor = _doc_or_raise(conn, tenant_id, "vendor", bill["vendor_id"], "Vendor")
    ap = vendor["account_id"] or acct(conn, tenant_id, AP_ACCOUNT)
    inventory = acct(conn, tenant_id, "1200")
    purchases = acct(conn, tenant_id, "5100")

    if intra:
        cgst, sgst = split_tax(tax_total)
        tax_lines = [(acct(conn, tenant_id, "2200"), cgst), (acct(conn, tenant_id, "2201"), sgst)]
    else:
        tax_lines = [(acct(conn, tenant_id, "2202"), tax_total)]

    lines_j = [{"account_id": ap, "debit": total, "credit": 0, "party_id": bill["vendor_id"],
                "memo": "Debit note / purchase return"}]
    if stock_value:
        lines_j.append({"account_id": inventory, "debit": 0, "credit": stock_value,
                        "memo": "Stock returned"})
    if purchase_value:
        lines_j.append({"account_id": purchases, "debit": 0, "credit": purchase_value,
                        "memo": "Purchase return"})
    for acc, amt in tax_lines:
        if amt:
            lines_j.append({"account_id": acc, "debit": 0, "credit": amt,
                            "memo": "GST input reversal"})

    conn.execute("BEGIN IMMEDIATE")
    try:
        if idempotency_key:
            existing = conn.execute(
                "SELECT * FROM debit_note WHERE tenant_id=? AND idempotency_key=?",
                (tenant_id, idempotency_key),
            ).fetchone()
            if existing:
                conn.execute("COMMIT")
                return dict(existing)

        entry_id = post_journal(conn, tenant_id, note_date, f"Debit note: {reason}", lines_j,
                                source_type="debit_note", idempotency_key=idempotency_key,
                                created_by=created_by)
        note_id = db.new_id()
        note_no = db.next_number(conn, tenant_id, "debit_note", "DBN")
        conn.execute(
            "INSERT INTO debit_note (id, tenant_id, note_no, note_date, vendor_id, bill_id,"
            " place_of_supply_state, sub_total_paise, tax_paise, round_off_paise, total_paise,"
            " reason, journal_entry_id, idempotency_key, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,0,?,?,?,?,?)",
            (note_id, tenant_id, note_no, note_date, bill["vendor_id"], bill_id,
             bill["place_of_supply_state"], sub_total, tax_total, total, reason[:200],
             entry_id, idempotency_key, db.now()),
        )
        for c in computed:
            conn.execute(
                "INSERT INTO debit_note_line (id, tenant_id, debit_note_id, item_id,"
                " bill_line_id, description, qty_milli, unit_price_paise, taxable_paise,"
                " tax_rate_bp, tax_paise, cost_paise, line_total_paise)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (db.new_id(), tenant_id, note_id, c["item_id"], c["bill_line_id"],
                 c["description"], c["qty_milli"], c["unit_price_paise"], c["taxable_paise"],
                 c["tax_rate_bp"], c["tax_paise"], c["cost_paise"], c["line_total_paise"]),
            )
        for item_id, (new_qty, new_cost) in cost_updates.items():
            conn.execute("UPDATE item SET stock_milli=?, cost_paise=? WHERE id=?",
                         (new_qty, new_cost, item_id))
        conn.execute("UPDATE journal_entry SET source_id=? WHERE id=?", (note_id, entry_id))
        audit(conn, tenant_id, created_by, "debit_note.create", "debit_note", note_id,
              meta={"total": total, "bill_id": bill_id})
        conn.execute("COMMIT")
        return dict(conn.execute("SELECT * FROM debit_note WHERE id=?", (note_id,)).fetchone())
    except Exception:
        conn.execute("ROLLBACK")
        raise


def receivable_ageing(conn: sqlite3.Connection, tenant_id: str, as_of: str | None = None) -> dict:
    as_of = as_of or _today_iso()
    as_of_d = date.fromisoformat(as_of)
    rows = conn.execute(
        """SELECT i.id, i.invoice_no, i.invoice_date, i.total_paise, c.name AS customer
           FROM invoice i JOIN customer c ON c.id=i.customer_id
           WHERE i.tenant_id=? AND i.status='posted' AND i.invoice_date <= ?
           ORDER BY i.invoice_date""",
        (tenant_id, as_of),
    ).fetchall()
    out = []
    totals = {"current": 0, "31-60": 0, "61-90": 0, "90+": 0}
    for r in rows:
        outstanding = invoice_outstanding(conn, tenant_id, r["id"])
        if outstanding <= 0:
            continue
        days = (as_of_d - date.fromisoformat(r["invoice_date"])).days
        bucket = "current" if days <= 30 else "31-60" if days <= 60 else "61-90" if days <= 90 else "90+"
        totals[bucket] += outstanding
        out.append({"invoice_id": r["id"], "invoice_no": r["invoice_no"], "date": r["invoice_date"],
                    "customer": r["customer"], "total": r["total_paise"],
                    "outstanding": outstanding, "days": days, "bucket": bucket})
    return {"as_of": as_of, "rows": out, "totals": totals, "grand_total": sum(totals.values())}


def payable_ageing(conn: sqlite3.Connection, tenant_id: str, as_of: str | None = None) -> dict:
    as_of = as_of or _today_iso()
    as_of_d = date.fromisoformat(as_of)
    rows = conn.execute(
        """SELECT b.id, b.bill_no, b.bill_date, b.total_paise, v.name AS vendor
           FROM bill b JOIN vendor v ON v.id=b.vendor_id
           WHERE b.tenant_id=? AND b.status='posted' AND b.bill_date <= ?
           ORDER BY b.bill_date""",
        (tenant_id, as_of),
    ).fetchall()
    out = []
    totals = {"current": 0, "31-60": 0, "61-90": 0, "90+": 0}
    for r in rows:
        outstanding = bill_outstanding(conn, tenant_id, r["id"])
        if outstanding <= 0:
            continue
        days = (as_of_d - date.fromisoformat(r["bill_date"])).days
        bucket = "current" if days <= 30 else "31-60" if days <= 60 else "61-90" if days <= 90 else "90+"
        totals[bucket] += outstanding
        out.append({"bill_id": r["id"], "bill_no": r["bill_no"], "date": r["bill_date"],
                    "vendor": r["vendor"], "total": r["total_paise"],
                    "outstanding": outstanding, "days": days, "bucket": bucket})
    return {"as_of": as_of, "rows": out, "totals": totals, "grand_total": sum(totals.values())}


def day_book(conn: sqlite3.Connection, tenant_id: str, date_from: str, date_to: str) -> list[dict]:
    rows = conn.execute(
        """SELECT e.id, e.entry_no, e.entry_date, e.narration, e.source_type, e.source_id,
                  e.status, COALESCE(SUM(l.debit_paise),0) AS amount
           FROM journal_entry e LEFT JOIN journal_line l ON l.entry_id=e.id
           WHERE e.tenant_id=? AND e.entry_date BETWEEN ? AND ?
           GROUP BY e.id ORDER BY e.entry_date, e.entry_no""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    return [dict(r) for r in rows]


def gst_summary(conn: sqlite3.Connection, tenant_id: str, date_from: str, date_to: str) -> dict:
    def account_tax(code: str, debit_side: bool) -> int:
        row = conn.execute(
            """SELECT COALESCE(SUM(l.debit_paise),0) d, COALESCE(SUM(l.credit_paise),0) c
               FROM journal_line l JOIN journal_entry e ON e.id=l.entry_id
               JOIN account a ON a.id=l.account_id
               WHERE l.tenant_id=? AND a.code=? AND e.entry_date BETWEEN ? AND ?""",
            (tenant_id, code, date_from, date_to),
        ).fetchone()
        return (row["d"] - row["c"]) if debit_side else (row["c"] - row["d"])

    output = {
        "CGST": account_tax("2100", False),
        "SGST": account_tax("2101", False),
        "IGST": account_tax("2102", False),
    }
    input_tax = {
        "CGST": account_tax("2200", True),
        "SGST": account_tax("2201", True),
        "IGST": account_tax("2202", True),
    }
    sales = conn.execute(
        """SELECT i.invoice_no, i.invoice_date, i.sub_total_paise, i.tax_paise, i.total_paise,
                  c.name AS party
           FROM invoice i JOIN customer c ON c.id=i.customer_id
           WHERE i.tenant_id=? AND i.invoice_date BETWEEN ? AND ? AND i.status='posted'
           ORDER BY i.invoice_date, i.invoice_no""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    purchases = conn.execute(
        """SELECT b.bill_no, b.bill_date, b.sub_total_paise, b.tax_paise, b.total_paise,
                  v.name AS party
           FROM bill b JOIN vendor v ON v.id=b.vendor_id
           WHERE b.tenant_id=? AND b.bill_date BETWEEN ? AND ? AND b.status='posted'
           ORDER BY b.bill_date, b.bill_no""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    out_total = sum(output.values())
    in_total = sum(input_tax.values())
    return {"from": date_from, "to": date_to, "output": output, "input": input_tax,
            "output_total": out_total, "input_total": in_total,
            "net_payable": out_total - in_total,
            "sales": [dict(r) for r in sales], "purchases": [dict(r) for r in purchases]}


def invoice_tax_breakup(conn: sqlite3.Connection, tenant_id: str, invoice_id: str) -> dict:
    """Per-line and rate-wise GST split that always sums to the invoice tax total."""
    inv = conn.execute(
        "SELECT i.*, c.name AS customer_name, c.gstin AS customer_gstin,"
        " c.address AS customer_address, c.state_code AS customer_state"
        " FROM invoice i JOIN customer c ON c.id=i.customer_id"
        " WHERE i.id=? AND i.tenant_id=?", (invoice_id, tenant_id),
    ).fetchone()
    if not inv:
        raise AccountingError("DOC_NOT_FOUND", "Invoice not found in this business")
    tenant = conn.execute("SELECT * FROM tenant WHERE id=?", (tenant_id,)).fetchone()
    lines = conn.execute("SELECT * FROM invoice_line WHERE invoice_id=? ORDER BY rowid",
                         (invoice_id,)).fetchall()
    intra = inv["place_of_supply_state"] == tenant["state_code"]
    total_tax = sum(l["tax_paise"] for l in lines)

    splits: list[dict] = []
    if intra:
        target_cgst = total_tax // 2
        base = [l["tax_paise"] // 2 for l in lines]
        diff = target_cgst - sum(base)
        for i, l in enumerate(lines):
            cgst = base[i] + (1 if i < diff else 0)
            splits.append({"cgst": cgst, "sgst": l["tax_paise"] - cgst, "igst": 0})
    else:
        splits = [{"cgst": 0, "sgst": 0, "igst": l["tax_paise"]} for l in lines]

    groups: dict[int, dict] = {}
    out_lines = []
    for l, sp in zip(lines, splits):
        g = groups.setdefault(l["tax_rate_bp"], {"rate_bp": l["tax_rate_bp"], "taxable": 0,
                                                 "cgst": 0, "sgst": 0, "igst": 0})
        g["taxable"] += l["taxable_paise"]
        g["cgst"] += sp["cgst"]
        g["sgst"] += sp["sgst"]
        g["igst"] += sp["igst"]
        out_lines.append({**dict(l), **sp})

    return {"invoice": dict(inv), "tenant": dict(tenant), "lines": out_lines,
            "groups": sorted(groups.values(), key=lambda g: g["rate_bp"]),
            "intra": intra, "total_tax": total_tax,
            "cgst": sum(s["cgst"] for s in splits), "sgst": sum(s["sgst"] for s in splits),
            "igst": sum(s["igst"] for s in splits)}


def gstr1_data(conn: sqlite3.Connection, tenant_id: str, date_from: str, date_to: str) -> dict:
    """GSTR-1 style working data: B2B, B2C small, HSN summary and document counts.

    This is a preparation aid, not an uploaded/filed return. Amounts are integer paise.
    """
    tenant = conn.execute("SELECT * FROM tenant WHERE id=?", (tenant_id,)).fetchone()
    if not tenant:
        raise AccountingError("TENANT_NOT_FOUND", "Tenant not found")

    invoices = conn.execute(
        "SELECT i.*, c.name AS customer_name, c.gstin AS customer_gstin,"
        " c.state_code AS customer_state FROM invoice i JOIN customer c ON c.id=i.customer_id"
        " WHERE i.tenant_id=? AND i.status='posted' AND i.invoice_date BETWEEN ? AND ?"
        " ORDER BY i.invoice_date, i.invoice_no", (tenant_id, date_from, date_to),
    ).fetchall()

    b2b: list[dict] = []
    b2cs: dict[tuple[str, int], dict] = {}
    line_splits: dict[str, dict] = {}
    b2c_count = 0

    for inv in invoices:
        br = invoice_tax_breakup(conn, tenant_id, inv["id"])
        for ln in br["lines"]:
            line_splits[ln["id"]] = ln
        registered = bool((inv["customer_gstin"] or "").strip())
        if not registered:
            b2c_count += 1
        for idx, g in enumerate(br["groups"]):
            if registered:
                b2b.append({
                    "gstin": inv["customer_gstin"].strip().upper(),
                    "receiver": inv["customer_name"],
                    "invoice_no": inv["invoice_no"],
                    "invoice_date": inv["invoice_date"],
                    "invoice_value": inv["total_paise"] if idx == 0 else None,
                    "place_of_supply": inv["place_of_supply_state"],
                    "reverse_charge": "N",
                    "rate_bp": g["rate_bp"], "taxable": g["taxable"],
                    "cgst": g["cgst"], "sgst": g["sgst"], "igst": g["igst"], "cess": 0,
                })
            else:
                key = (inv["place_of_supply_state"], g["rate_bp"])
                agg = b2cs.setdefault(key, {"place_of_supply": key[0], "rate_bp": key[1],
                                            "taxable": 0, "cgst": 0, "sgst": 0, "igst": 0,
                                            "invoice_ids": set()})
                agg["taxable"] += g["taxable"]
                agg["cgst"] += g["cgst"]
                agg["sgst"] += g["sgst"]
                agg["igst"] += g["igst"]
                agg["invoice_ids"].add(inv["id"])

    hsn_rows = conn.execute(
        "SELECT l.*, i.invoice_date, i.place_of_supply_state, it.hsn, it.name AS item_name,"
        " it.unit FROM invoice_line l JOIN invoice i ON i.id=l.invoice_id"
        " JOIN item it ON it.id=l.item_id"
        " WHERE i.tenant_id=? AND i.status='posted' AND i.invoice_date BETWEEN ? AND ?",
        (tenant_id, date_from, date_to),
    ).fetchall()

    hsn: dict[tuple[str, int], dict] = {}
    for row in hsn_rows:
        sp = line_splits.get(row["id"])
        if not sp:
            continue
        code = (row["hsn"] or "").strip().upper()
        key = (code, row["tax_rate_bp"])
        agg = hsn.setdefault(key, {"hsn": code or "NOT SET", "description": row["item_name"],
                                   "uqc": row["unit"], "rate_bp": row["tax_rate_bp"],
                                   "qty_milli": 0, "taxable": 0,
                                   "cgst": 0, "sgst": 0, "igst": 0, "total_value": 0})
        agg["qty_milli"] += row["qty_milli"]
        agg["taxable"] += row["taxable_paise"]
        agg["cgst"] += sp["cgst"]
        agg["sgst"] += sp["sgst"]
        agg["igst"] += sp["igst"]
        agg["total_value"] += row["line_total_paise"]

    credit_notes = conn.execute(
        "SELECT COUNT(*) c, COALESCE(SUM(total_paise),0) t FROM credit_note"
        " WHERE tenant_id=? AND note_date BETWEEN ? AND ?",
        (tenant_id, date_from, date_to),
    ).fetchone()

    credit_rows = conn.execute(
        "SELECT n.*, c.name AS customer_name, c.gstin AS customer_gstin"
        " FROM credit_note n JOIN customer c ON c.id=n.customer_id"
        " WHERE n.tenant_id=? AND n.note_date BETWEEN ? AND ?"
        " ORDER BY n.note_date, n.note_no", (tenant_id, date_from, date_to),
    ).fetchall()
    credit_detail: list[dict] = []
    for n in credit_rows:
        intra = n["place_of_supply_state"] == tenant["state_code"]
        cgst = n["tax_paise"] // 2 if intra else 0
        sgst = n["tax_paise"] - cgst if intra else 0
        credit_detail.append({
            "section": "CDNR" if (n["customer_gstin"] or "").strip() else "CDNUR",
            "gstin": (n["customer_gstin"] or "").strip().upper(),
            "receiver": n["customer_name"], "note_no": n["note_no"],
            "note_date": n["note_date"], "note_value": n["total_paise"],
            "place_of_supply": n["place_of_supply_state"],
            "taxable": n["sub_total_paise"], "cgst": cgst, "sgst": sgst,
            "igst": 0 if intra else n["tax_paise"], "cess": 0,
        })
    credit_totals = {
        "taxable": sum(r["taxable"] for r in credit_detail),
        "cgst": sum(r["cgst"] for r in credit_detail),
        "sgst": sum(r["sgst"] for r in credit_detail),
        "igst": sum(r["igst"] for r in credit_detail),
    }

    warnings: list[str] = []
    if not (tenant["gstin"] or "").strip():
        warnings.append("Supplier GSTIN is not set. Add it in Settings before using this export for filing.")
    if b2c_count:
        warnings.append(f"{b2c_count} invoice(s) have no buyer GSTIN and are grouped as B2C small.")
    missing_hsn = sum(1 for h in hsn.values() if h["hsn"] == "NOT SET")
    if missing_hsn:
        warnings.append(f"{missing_hsn} HSN/SAC group(s) have no code. Add HSN/SAC on the item master.")

    totals = {
        "taxable": sum(r["taxable"] for r in b2b) + sum(r["taxable"] for r in b2cs.values()),
        "cgst": sum(r["cgst"] for r in b2b) + sum(r["cgst"] for r in b2cs.values()),
        "sgst": sum(r["sgst"] for r in b2b) + sum(r["sgst"] for r in b2cs.values()),
        "igst": sum(r["igst"] for r in b2b) + sum(r["igst"] for r in b2cs.values()),
    }
    b2cs_rows = []
    for r in b2cs.values():
        row = dict(r)
        row["invoices"] = len(row.pop("invoice_ids"))
        b2cs_rows.append(row)
    return {
        "period": {"from": date_from, "to": date_to},
        "supplier": {"gstin": (tenant["gstin"] or "").strip().upper(),
                     "name": tenant["name"], "state_code": tenant["state_code"]},
        "b2b": b2b,
        "b2cs": sorted(b2cs_rows, key=lambda r: (r["place_of_supply"], r["rate_bp"])),
        "hsn": sorted(hsn.values(), key=lambda r: (r["hsn"], r["rate_bp"])),
        "credit_notes": credit_detail,
        "credit_note_totals": credit_totals,
        "docs": {"invoices": len(invoices), "b2c_invoices": b2c_count,
                 "credit_notes": credit_notes["c"], "credit_note_value": credit_notes["t"],
                 "debit_notes": 0, "cancelled": 0},
        "totals": totals,
        "warnings": warnings,
    }


def month_bounds(month: str) -> tuple[str, str]:
    """Return (first_day, last_day) for a YYYY-MM month."""
    text = (month or "").strip()
    parts = text.split("-")
    if len(parts) != 2:
        raise AccountingError("BAD_MONTH", "Month must be YYYY-MM")
    try:
        year, mon = int(parts[0]), int(parts[1])
    except ValueError:
        raise AccountingError("BAD_MONTH", "Month must be YYYY-MM") from None
    if year < 2000 or year > 2100 or not 1 <= mon <= 12:
        raise AccountingError("BAD_MONTH", "Month must be YYYY-MM")
    last = monthrange(year, mon)[1]
    return f"{year:04d}-{mon:02d}-01", f"{year:04d}-{mon:02d}-{last:02d}"


def gstr3b_data(conn: sqlite3.Connection, tenant_id: str, month: str) -> dict:
    """GSTR-3B style working summary for one month.

    Output tax and ITC come from posted documents (invoices, credit notes, bills,
    debit notes). The ledger tax accounts are used only as an independent
    reconciliation check. This is a preparation aid, not a filed return.
    """
    tenant = conn.execute("SELECT * FROM tenant WHERE id=?", (tenant_id,)).fetchone()
    if not tenant:
        raise AccountingError("TENANT_NOT_FOUND", "Tenant not found")
    date_from, date_to = month_bounds(month)
    g1 = gstr1_data(conn, tenant_id, date_from, date_to)
    books = gst_summary(conn, tenant_id, date_from, date_to)
    heads = ("IGST", "CGST", "SGST")

    def head_key(head: str) -> str:
        return head.lower()

    # ---- outward supplies: gross invoices less credit notes ----
    taxable_gross = g1["totals"]["taxable"]
    cn_taxable = g1["credit_note_totals"]["taxable"]
    output_gross = {h: g1["totals"][head_key(h)] for h in heads}
    output_cn = {h: g1["credit_note_totals"][head_key(h)] for h in heads}
    output_net = {h: output_gross[h] - output_cn[h] for h in heads}
    outward = {
        "taxable_gross": taxable_gross,
        "credit_note_taxable": cn_taxable,
        "taxable_net": taxable_gross - cn_taxable,
        "output_gross": output_gross,
        "credit_note_tax": output_cn,
        "output_net": output_net,
        "output_total": sum(output_net.values()),
        "zero_rated": 0,
        "nil_exempt": 0,
        "rcm_inward": 0,
        "non_gst": 0,
    }

    # ---- eligible ITC: purchase bills less debit notes ----
    bills = conn.execute(
        "SELECT sub_total_paise, tax_paise, place_of_supply_state FROM bill"
        " WHERE tenant_id=? AND status='posted' AND bill_date BETWEEN ? AND ?",
        (tenant_id, date_from, date_to),
    ).fetchall()
    debit_notes = conn.execute(
        "SELECT sub_total_paise, tax_paise, place_of_supply_state FROM debit_note"
        " WHERE tenant_id=? AND note_date BETWEEN ? AND ?",
        (tenant_id, date_from, date_to),
    ).fetchall()
    bill_tot = conn.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(sub_total_paise),0) taxable,"
        " COALESCE(SUM(tax_paise),0) tax FROM bill"
        " WHERE tenant_id=? AND status='posted' AND bill_date BETWEEN ? AND ?",
        (tenant_id, date_from, date_to),
    ).fetchone()
    dn_tot = conn.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(sub_total_paise),0) taxable,"
        " COALESCE(SUM(tax_paise),0) tax FROM debit_note"
        " WHERE tenant_id=? AND note_date BETWEEN ? AND ?",
        (tenant_id, date_from, date_to),
    ).fetchone()

    itc_gross = {h: 0 for h in heads}
    itc_reversal = {h: 0 for h in heads}

    def add_tax(target: dict, tax: int, place_of_supply: str) -> None:
        if place_of_supply == tenant["state_code"]:
            cgst, sgst = split_tax(tax)
            target["CGST"] += cgst
            target["SGST"] += sgst
        else:
            target["IGST"] += tax

    for row in bills:
        add_tax(itc_gross, row["tax_paise"], row["place_of_supply_state"])
    for row in debit_notes:
        add_tax(itc_reversal, row["tax_paise"], row["place_of_supply_state"])

    itc_net = {h: itc_gross[h] - itc_reversal[h] for h in heads}
    itc_available = {h: max(0, itc_net[h]) for h in heads}
    itc_excess = {h: max(0, -itc_net[h]) for h in heads}
    itc = {
        "gross": itc_gross,
        "reversal": itc_reversal,
        "net": itc_net,
        "gross_total": sum(itc_gross.values()),
        "reversal_total": sum(itc_reversal.values()),
        "net_total": sum(itc_net.values()),
        "available": itc_available,
        "available_total": sum(itc_available.values()),
        "excess_reversal": itc_excess,
        "excess_reversal_total": sum(itc_excess.values()),
        "import_goods": 0,
        "import_services": 0,
        "rcm": 0,
    }

    # ---- payment: head-wise set-off, no cross-utilisation ----
    payment_heads = []
    for head in heads:
        output = output_net[head]
        output_for_payment = max(0, output)
        output_carry = max(0, -output)
        available = itc_available[head]
        used = min(output_for_payment, available)
        cash = output_for_payment - used + itc_excess[head]
        payment_heads.append({
            "head": head,
            "output": output,
            "output_for_payment": output_for_payment,
            "output_carry": output_carry,
            "itc_available": available,
            "itc_used": used,
            "cash_payable": cash,
            "itc_balance": available - used,
        })
    payment = {
        "heads": payment_heads,
        "output_total": sum(h["output"] for h in payment_heads),
        "output_for_payment_total": sum(h["output_for_payment"] for h in payment_heads),
        "output_carry_total": sum(h["output_carry"] for h in payment_heads),
        "itc_available_total": sum(h["itc_available"] for h in payment_heads),
        "itc_used_total": sum(h["itc_used"] for h in payment_heads),
        "cash_payable_total": sum(h["cash_payable"] for h in payment_heads),
        "itc_balance_total": sum(h["itc_balance"] for h in payment_heads),
        "excess_reversal_total": itc["excess_reversal_total"],
    }

    # ---- reconciliation: GSTR-1 documents vs GSTR-3B vs ledger ----
    def check(key: str, label: str, expected: int, actual: int) -> dict:
        difference = actual - expected
        return {"key": key, "label": label, "expected": expected, "actual": actual,
                "difference": difference, "status": "ok" if difference == 0 else "check"}

    g1_taxable_net = g1["totals"]["taxable"] - g1["credit_note_totals"]["taxable"]
    g1_output_net = sum(g1["totals"][head_key(h)] - g1["credit_note_totals"][head_key(h)]
                        for h in heads)
    g1_cn_tax = sum(g1["credit_note_totals"][head_key(h)] for h in heads)
    checks = [
        check("gstr1_taxable", "GSTR-1 net taxable = GSTR-3B net taxable",
              g1_taxable_net, outward["taxable_net"]),
        check("gstr1_output", "GSTR-1 net output tax = GSTR-3B output tax",
              g1_output_net, outward["output_total"]),
        check("gstr1_cn", "GSTR-1 credit-note tax = GSTR-3B credit-note adjustment",
              g1_cn_tax, sum(output_cn.values())),
        check("ledger_output", "Document output tax = output tax ledger",
              outward["output_total"], books["output_total"]),
        check("ledger_itc", "Document ITC = input tax ledger",
              itc["net_total"], books["input_total"]),
        check("itc_docs", "Bill GST minus debit-note GST = ITC net",
              bill_tot["tax"] - dn_tot["tax"], itc["net_total"]),
    ]

    warnings = list(g1["warnings"])
    failed = [c for c in checks if c["status"] != "ok"]
    if failed:
        warnings.append(f"{len(failed)} reconciliation check(s) need review before filing.")
    if itc["net_total"] < 0:
        warnings.append("ITC reversal exceeds ITC available this month; the excess is shown as "
                        "payable in this working view. Review the debit notes and ITC claim.")
    if outward["output_total"] < 0:
        warnings.append("Credit notes exceed invoices this month; net output tax is negative "
                        "and is carried forward in this working view.")
    negative_heads = [h for h in heads if output_net[h] < 0]
    if negative_heads:
        warnings.append("Negative output tax in " + ", ".join(negative_heads) +
                        "; it is carried forward head-wise and is not set off against other heads.")
    if g1["docs"]["invoices"] == 0:
        warnings.append("No posted invoices in this month.")

    return {
        "period": {"month": month, "from": date_from, "to": date_to},
        "supplier": {"gstin": (tenant["gstin"] or "").strip().upper(),
                     "name": tenant["name"], "state_code": tenant["state_code"]},
        "outward": outward,
        "itc": itc,
        "payment": payment,
        "reconciliation": {
            "checks": checks,
            "failed": len(failed),
            "gstr1": {"totals": g1["totals"],
                      "credit_note_totals": g1["credit_note_totals"],
                      "docs": g1["docs"]},
        },
        "docs": {
            "invoices": g1["docs"]["invoices"],
            "b2c_invoices": g1["docs"]["b2c_invoices"],
            "credit_notes": g1["docs"]["credit_notes"],
            "bills": bill_tot["n"],
            "debit_notes": dn_tot["n"],
        },
        "warnings": warnings,
        "note": ("Working GSTR-3B preparation aid, not a filed return. Output tax is net of "
                 "credit notes; ITC is net of debit notes. Set-off is head-wise only: IGST "
                 "credit is not cross-utilised against CGST/SGST, and RCM/zero-rated/exempt "
                 "supplies are not modelled yet. Verify with your tax professional."),
    }


def vendor_balances(conn: sqlite3.Connection, tenant_id: str, as_of: str | None = None) -> list[dict]:
    as_of = as_of or _today_iso()
    rows = conn.execute(
        """
        SELECT v.id, v.name, v.phone, v.state_code,
               COALESCE(SUM(p.credit_paise - p.debit_paise), 0) AS balance
        FROM vendor v
        LEFT JOIN (
            SELECT l.party_id, l.debit_paise, l.credit_paise
            FROM journal_line l JOIN journal_entry e ON e.id=l.entry_id
            WHERE l.tenant_id=? AND l.party_id IS NOT NULL AND e.entry_date <= ?
        ) p ON p.party_id = v.id
        WHERE v.tenant_id=? GROUP BY v.id ORDER BY v.name
        """,
        (tenant_id, as_of, tenant_id),
    ).fetchall()
    return [dict(r) for r in rows]


def vendor_statement(conn: sqlite3.Connection, tenant_id: str, vendor_id: str,
                     date_from: str, date_to: str) -> dict:
    vendor = _doc_or_raise(conn, tenant_id, "vendor", vendor_id, "Vendor")
    opening = conn.execute(
        """SELECT COALESCE(SUM(l.credit_paise - l.debit_paise),0) bal
           FROM journal_line l JOIN journal_entry e ON e.id=l.entry_id
           WHERE l.tenant_id=? AND l.party_id=? AND e.entry_date < ?""",
        (tenant_id, vendor_id, date_from),
    ).fetchone()["bal"] or 0
    rows = conn.execute(
        """SELECT e.entry_no, e.entry_date, e.narration, e.source_type, e.source_id,
                  l.debit_paise, l.credit_paise
           FROM journal_line l JOIN journal_entry e ON e.id=l.entry_id
           WHERE l.tenant_id=? AND l.party_id=? AND e.entry_date BETWEEN ? AND ?
           ORDER BY e.entry_date, e.entry_no, l.line_no""",
        (tenant_id, vendor_id, date_from, date_to),
    ).fetchall()
    running = opening
    out = []
    billed = paid = debited = 0
    for r in rows:
        running += (r["credit_paise"] or 0) - (r["debit_paise"] or 0)
        billed += r["credit_paise"] or 0
        if r["source_type"] == "debit_note":
            debited += r["debit_paise"] or 0
        else:
            paid += r["debit_paise"] or 0
        out.append({"date": r["entry_date"], "ref": r["entry_no"], "narration": r["narration"],
                    "source_type": r["source_type"], "source_id": r["source_id"],
                    "debit": r["debit_paise"], "credit": r["credit_paise"], "balance": running})
    return {"vendor": dict(vendor), "from": date_from, "to": date_to, "opening": opening,
            "rows": out, "closing": running, "billed": billed, "paid": paid,
            "debited": debited}


# --------------------------------------------------------------------------
# reports
# --------------------------------------------------------------------------

def account_balances(conn: sqlite3.Connection, tenant_id: str,
                     as_of: str | None = None) -> list[dict]:
    """All chart accounts with their signed balance as of a date (Dr positive)."""
    as_of = as_of or _today_iso()
    rows = conn.execute(
        """
        SELECT a.id, a.code, a.name, a.type, a.group_code, a.is_postable,
               a.status, a.archived_at, a.merged_into_id,
               COALESCE(SUM(CASE WHEN e.entry_date <= ? THEN
                    l.debit_paise - l.credit_paise ELSE 0 END), 0) AS balance
        FROM account a
        LEFT JOIN journal_line l
          ON l.account_id = a.id AND l.tenant_id = a.tenant_id
        LEFT JOIN journal_entry e ON e.id = l.entry_id
        WHERE a.tenant_id = ?
        GROUP BY a.id
        ORDER BY a.code
        """,
        (as_of, tenant_id),
    ).fetchall()
    return [{**dict(r), "group_label": account_group_label(r["group_code"], r["type"])}
            for r in rows]


def trial_balance(conn: sqlite3.Connection, tenant_id: str, as_of: str | None = None) -> dict:
    as_of = as_of or _today_iso()
    rows = conn.execute(
        """
        SELECT a.id, a.code, a.name, a.type, a.status,
               COALESCE(SUM(l.debit_paise),0)  AS debit,
               COALESCE(SUM(l.credit_paise),0) AS credit
        FROM account a
        LEFT JOIN journal_line l ON l.account_id = a.id AND l.tenant_id = a.tenant_id
        LEFT JOIN journal_entry e ON e.id = l.entry_id AND e.entry_date <= ?
        WHERE a.tenant_id = ?
        GROUP BY a.id
        ORDER BY a.code
        """,
        (as_of, tenant_id),
    ).fetchall()
    out = []
    for r in rows:
        debit = r["debit"] or 0
        credit = r["credit"] or 0
        out.append({"account_id": r["id"], "code": r["code"], "name": r["name"],
                    "type": r["type"], "status": r["status"],
                    "debit": debit, "credit": credit, "balance": debit - credit})
    total_debit = sum(r["debit"] for r in out)
    total_credit = sum(r["credit"] for r in out)
    return {"as_of": as_of, "rows": out, "total_debit": total_debit,
            "total_credit": total_credit, "balanced": total_debit == total_credit}


def general_ledger(conn: sqlite3.Connection, tenant_id: str, account_id: str,
                   date_from: str, date_to: str) -> dict:
    acct = conn.execute(
        "SELECT * FROM account WHERE id=? AND tenant_id=?", (account_id, tenant_id)
    ).fetchone()
    if not acct:
        raise AccountingError("ACCOUNT_NOT_FOUND", "Account not in this tenant")
    opening_row = conn.execute(
        """SELECT COALESCE(SUM(l.debit_paise - l.credit_paise),0) AS bal
           FROM journal_line l JOIN journal_entry e ON e.id=l.entry_id
           WHERE l.tenant_id=? AND l.account_id=? AND e.entry_date < ?""",
        (tenant_id, account_id, date_from),
    ).fetchone()
    opening = opening_row["bal"] or 0
    rows = conn.execute(
        """SELECT e.id AS entry_id, e.entry_no, e.entry_date, e.narration,
                  e.source_type, e.source_id, e.status, e.reversal_of,
                  l.debit_paise, l.credit_paise, l.memo
           FROM journal_line l JOIN journal_entry e ON e.id=l.entry_id
           WHERE l.tenant_id=? AND l.account_id=? AND e.entry_date BETWEEN ? AND ?
           ORDER BY e.entry_date, e.entry_no, l.line_no""",
        (tenant_id, account_id, date_from, date_to),
    ).fetchall()
    running = opening
    out = []
    for r in rows:
        running += (r["debit_paise"] or 0) - (r["credit_paise"] or 0)
        out.append({"date": r["entry_date"], "ref": r["entry_no"], "narration": r["narration"],
                    "debit": r["debit_paise"], "credit": r["credit_paise"], "balance": running,
                    "entry_id": r["entry_id"], "source_type": r["source_type"],
                    "source_id": r["source_id"], "status": r["status"],
                    "reversal_of": r["reversal_of"]})
    return {"account": dict(acct), "from": date_from, "to": date_to,
            "opening": opening, "rows": out, "closing": running}


def customer_balances(conn: sqlite3.Connection, tenant_id: str, as_of: str | None = None) -> list[dict]:
    """AR balance per customer, from party-tagged journal lines."""
    as_of = as_of or _today_iso()
    rows = conn.execute(
        """
        SELECT c.id, c.name, c.phone, c.state_code,
               COALESCE(SUM(p.debit_paise - p.credit_paise), 0) AS balance
        FROM customer c
        LEFT JOIN (
            SELECT l.party_id, l.debit_paise, l.credit_paise
            FROM journal_line l
            JOIN journal_entry e ON e.id = l.entry_id
            WHERE l.tenant_id = ? AND l.party_id IS NOT NULL AND e.entry_date <= ?
        ) p ON p.party_id = c.id
        WHERE c.tenant_id = ?
        GROUP BY c.id
        ORDER BY c.name
        """,
        (tenant_id, as_of, tenant_id),
    ).fetchall()
    return [dict(r) for r in rows]


def customer_statement(conn: sqlite3.Connection, tenant_id: str, customer_id: str,
                       date_from: str, date_to: str) -> dict:
    customer = conn.execute(
        "SELECT * FROM customer WHERE id=? AND tenant_id=?", (customer_id, tenant_id)
    ).fetchone()
    if not customer:
        raise AccountingError("CUSTOMER_NOT_FOUND", "Customer not in this tenant")

    opening = conn.execute(
        """SELECT COALESCE(SUM(l.debit_paise - l.credit_paise), 0) AS bal
           FROM journal_line l JOIN journal_entry e ON e.id = l.entry_id
           WHERE l.tenant_id=? AND l.party_id=? AND e.entry_date < ?""",
        (tenant_id, customer_id, date_from),
    ).fetchone()["bal"] or 0

    rows = conn.execute(
        """SELECT e.entry_no, e.entry_date, e.narration, e.source_type, e.source_id,
                  l.debit_paise, l.credit_paise
           FROM journal_line l JOIN journal_entry e ON e.id = l.entry_id
           WHERE l.tenant_id=? AND l.party_id=? AND e.entry_date BETWEEN ? AND ?
           ORDER BY e.entry_date, e.entry_no, l.line_no""",
        (tenant_id, customer_id, date_from, date_to),
    ).fetchall()

    running = opening
    out = []
    invoiced = received = 0
    for r in rows:
        running += (r["debit_paise"] or 0) - (r["credit_paise"] or 0)
        invoiced += r["debit_paise"] or 0
        received += r["credit_paise"] or 0
        out.append({"date": r["entry_date"], "ref": r["entry_no"], "narration": r["narration"],
                    "source_type": r["source_type"], "source_id": r["source_id"],
                    "debit": r["debit_paise"], "credit": r["credit_paise"], "balance": running})
    return {"customer": dict(customer), "from": date_from, "to": date_to,
            "opening": opening, "rows": out, "closing": running,
            "invoiced": invoiced, "received": received}


def profit_and_loss(conn: sqlite3.Connection, tenant_id: str, date_from: str, date_to: str) -> dict:
    rows = conn.execute(
        """SELECT a.type, a.code, a.name,
                  COALESCE(SUM(l.debit_paise),0) AS debit,
                  COALESCE(SUM(l.credit_paise),0) AS credit
           FROM account a
           JOIN journal_line l ON l.account_id=a.id AND l.tenant_id=a.tenant_id
           JOIN journal_entry e ON e.id=l.entry_id AND e.entry_date BETWEEN ? AND ?
           WHERE a.tenant_id=? AND a.type IN ('income','expense')
           GROUP BY a.id ORDER BY a.code""",
        (date_from, date_to, tenant_id),
    ).fetchall()
    income, expense = [], []
    for r in rows:
        if r["type"] == "income":
            amount = (r["credit"] or 0) - (r["debit"] or 0)
            income.append({"code": r["code"], "name": r["name"], "amount": amount})
        else:
            amount = (r["debit"] or 0) - (r["credit"] or 0)
            expense.append({"code": r["code"], "name": r["name"], "amount": amount})
    total_income = sum(i["amount"] for i in income)
    total_expense = sum(e["amount"] for e in expense)
    return {"from": date_from, "to": date_to, "income": income, "expense": expense,
            "total_income": total_income, "total_expense": total_expense,
            "net_profit": total_income - total_expense}


def balance_sheet(conn: sqlite3.Connection, tenant_id: str, as_of: str | None = None) -> dict:
    as_of = as_of or _today_iso()
    tb = trial_balance(conn, tenant_id, as_of)
    assets = liabilities = equity = 0
    a_rows, l_rows, e_rows = [], [], []
    for r in tb["rows"]:
        bal = r["balance"]  # debit positive
        if r["type"] == "asset":
            assets += bal
            a_rows.append({**r, "amount": bal})
        elif r["type"] == "liability":
            amt = -bal
            liabilities += amt
            l_rows.append({**r, "amount": amt})
        elif r["type"] == "equity":
            amt = -bal
            equity += amt
            e_rows.append({**r, "amount": amt})

    pnl = profit_and_loss(conn, tenant_id, "0000-01-01", as_of)
    retained = pnl["net_profit"]
    equity += retained
    return {"as_of": as_of, "assets": a_rows, "liabilities": l_rows, "equity": e_rows,
            "total_assets": assets, "total_liabilities": liabilities,
            "retained_earnings": retained, "total_equity": equity,
            "balanced": assets == liabilities + equity,
            "difference": assets - (liabilities + equity)}


def dashboard(conn: sqlite3.Connection, tenant_id: str, date_from: str, date_to: str) -> dict:
    pnl = profit_and_loss(conn, tenant_id, date_from, date_to)
    balances = account_balances(conn, tenant_id, date_to)
    by_code = {r["code"]: r["balance"] for r in balances}

    def group_total(group_code: str, fallback_code: str) -> int:
        rows = [r for r in balances if r["group_code"] == group_code]
        if rows:
            return sum(r["balance"] for r in rows)
        return by_code.get(fallback_code, 0)

    ar = group_total("receivable", AR_ACCOUNT)
    cash = group_total("cash", CASH_ACCOUNT) + group_total("bank", BANK_ACCOUNT)
    inventory = group_total("inventory", "1200")
    payable = -group_total("payable", AP_ACCOUNT)
    inv_count = conn.execute(
        "SELECT COUNT(*) c FROM invoice WHERE tenant_id=? AND invoice_date BETWEEN ? AND ?",
        (tenant_id, date_from, date_to),
    ).fetchone()["c"]
    ar_age = receivable_ageing(conn, tenant_id, date_to)
    ap_age = payable_ageing(conn, tenant_id, date_to)
    return {"revenue": pnl["total_income"], "expense": pnl["total_expense"],
            "profit": pnl["net_profit"], "receivable": ar, "cash": cash,
            "inventory": inventory, "invoice_count": inv_count, "payable": payable,
            "open_invoices": len(ar_age["rows"]), "open_bills": len(ap_age["rows"]),
            "overdue_receivable": ar_age["totals"]["61-90"] + ar_age["totals"]["90+"],
            "overdue_payable": ap_age["totals"]["61-90"] + ap_age["totals"]["90+"]}
