# ARTHIVIO — Accounting Rules

| Field | Value |
|---|---|
| Version | 1.1 |
| Date | 2026-10-28 |
| Status | Draft for owner + professional review |
| Applies to | Phase 2 onward |
| Jurisdiction default | India (configurable per legal entity) |

> These rules are the specification the engine must satisfy. The core double-entry, posting,
> reversal, ledger and reporting rules are implemented through Build 0.12 and covered by the
> automated tests; they are still **not** a substitute for review by a qualified accountant or tax
> professional. Tax specifics marked ⚠️ must be validated against current official sources before
> any tax output is produced.

---

## 1. Money representation

| Rule | Detail |
|---|---|
| Storage | `BIGINT` minor units (paise for INR, cents for USD/EUR) + `CHAR(3)` currency |
| Arithmetic | Python `Decimal` with an explicit context; **no `float` anywhere** on a financial path |
| Intermediate precision | 4 decimal places, then quantise to the currency's minor unit |
| Scale | Per-currency: INR/USD/EUR = 2; configured per entity, not hard-coded globally |
| Negative amounts | Not used as a shortcut for credit. A line has `debit_minor` **or** `credit_minor`, both ≥ 0 |
| Mixed currency | A journal entry is single-currency; translation happens in a separate, explicit step |

**Why:** `0.1 + 0.2 != 0.3` in binary floating point. On a ledger that becomes a trial balance that does not balance. This is the single most common source of silent financial corruption.

---

## 2. Rounding policy

| Rule | Detail |
|---|---|
| Mode | `ROUND_HALF_UP` at the currency's minor unit, unless the entity configures otherwise |
| Where applied | Per calculated component (line tax, line discount, line total), then summed |
| Residual allocation | When a document-level amount must be distributed across lines, use the **largest remainder method** so the sum of parts equals the whole **exactly** |
| Document rounding | Optional whole-unit rounding (e.g. nearest ₹1); the difference posts to a dedicated `Rounding Off` account — never silently absorbed |
| Test requirement | Sum of allocated parts == total, for every allocation, including adversarial remainders |

### Worked rounding example (verify against tests)

Split ₹100.00 across 3 equal parts:

```
exact share = 100.00 / 3 = 33.3333…
floors      = 33.33, 33.33, 33.33  → 99.99
remainder   = 0.01
allocate 1 minor unit to the largest fractional remainder (line 1)
result      = 33.34 + 33.33 + 33.33 = 100.00  ✓
```

Naive rounding (`33.33 × 3`) loses one paisa. That paisa is exactly the kind of defect that makes a trial balance fail by 0.01 and wastes days.

---

## 3. Double-entry conventions

| Account type | Normal balance | Increases with |
|---|---|---|
| Asset | Debit | Debit |
| Expense / Cost | Debit | Debit |
| Liability | Credit | Credit |
| Equity | Credit | Credit |
| Income / Revenue | Credit | Credit |

Signed balance used internally: `signed_minor = Σ debit − Σ credit`. A debit-normal account has a positive signed balance when it looks "normal"; presentation flips sign for credit-normal types.

### Posting rules

1. `Σ debit == Σ credit` per entry, at posting precision — otherwise **block**.
2. Minimum two lines.
3. Each line: exactly one of debit/credit is non-zero.
4. Every line references a postable account belonging to the same tenant and entity.
5. Posting is atomic: header + lines + balances commit together or not at all.
6. Posting date must fall inside an **open** fiscal period.
7. Posted entries are immutable. Correction = reversal (+ optional replacement), both linked and audited.
8. Every entry carries provenance: `source_type`, `source_id`, `created_by`, rule version.

### Worked example — credit sale with perpetual inventory

Invoice: goods ₹3,150.00 net, GST 18% = ₹567.00, total ₹3,717.00; cost of goods ₹2,100.00.

```
Dr  Accounts Receivable            3,717.00
    Cr  Sales Revenue                          3,150.00
    Cr  GST Output Payable                       567.00
Dr  Cost of Goods Sold             2,100.00
    Cr  Inventory                              2,100.00
```

Debits 5,817.00 = Credits 5,817.00 ✓

Receipt later:

```
Dr  Bank                           3,717.00
    Cr  Accounts Receivable                    3,717.00
```
✓

---

## 4. Document numbering

- Sequence per `(tenant, document_type, fiscal_year)`, allocated transactionally.
- Gaps are recorded, never silently filled.
- Duplicate document numbers rejected by a unique constraint, not just a UI check.
- Offline/multi-device numbering (Phase 5) uses a reserved block strategy with the same uniqueness guarantee.
- Statutory numbering rules ⚠️ must be verified before go-live.

---

## 5. Idempotency and duplicates

| Rule | Detail |
|---|---|
| Idempotency key | Required on all document-creating endpoints; unique per `(tenant, key)` |
| Replay | Same key + same payload → return the original result, no second posting |
| Same key + different payload | Reject with a conflict error |
| Duplicate detection | Same party + same amount + same date + same reference within a window → flagged `Needs Review`, never auto-merged |
| Customer merging | **Never** automatic on matching mobile numbers (spec §10) |

---

## 6. Periods, opening balances, closing

| Rule | Detail |
|---|---|
| Fiscal period | Defined by start/end dates; no overlapping periods |
| Status | `open` → `locked` → `closed`; reopening requires an audited, authorised action |
| Posting to locked/closed | Rejected at the service layer, with a clear error |
| Opening balances | Entered once when an account is brought into the books and carried forward by the normal closing process; re-entry requires reversal and a replacement journal, never an overwrite |
| Closing | `closing = opening + Σ debits − Σ credits` (signed), asserted per account and per period |
| Carry-forward | Closing balance of period N becomes opening of N+1 for balance-sheet accounts; P&L accounts close to retained earnings per policy |
| Timezone | Business dates are `DATE`; a posting near midnight must not shift periods due to UTC conversion |

### Implemented opening-balance workflow (Build 0.10)

- The **Set opening balance** form on an account ledger posts one balanced journal:
  - Debit opening: `Dr selected account` / `Cr Opening Balance Equity`;
  - Credit opening: `Dr Opening Balance Equity` / `Cr selected account`.
- `Opening Balance Equity` is created lazily with the next free code from `3200` upward. An existing
  account with a different name is never reused as the contra account.
- The amount is integer paise, the side is explicit (defaulted from the account's normal balance),
  and the date cannot be in the future.
- The opening date must be on or before the account's first posted transaction. This prevents a
  later "opening" figure from being inserted after activity has already changed the balance.
- One posted opening entry is allowed per account. Replacing it requires a permission-controlled
  reversal with a reason, then a new opening journal; both entries remain in the ledger and audit
  trail.
- Every set writes `opening_balance.set`; the regular period lock, tenant scope and balanced-posting
  checks still apply. Opening entries are never direct edits to the account row.
- An opening figure on an income or expense account is accepted for migration, but normal year-end
  closing still applies; it is not a substitute for a prior-period P&L close.
- When the account is linked to a customer or vendor, the opening line carries the same `party_id`
  as later documents, so the party statement and the control account agree.

### Bulk opening-balance import (Build 0.11; `.xlsx` added in Build 0.12)

- The CSV or server-side `.xlsx` import is a **validation and convenience layer**, not a second accounting path. `.xlsx` is converted to neutral CSV first; formulas are never evaluated, cached values are used, and the same preview/posting rules below still apply. Every row
  still becomes one balanced journal through the same opening-balance service:
  - a debit row posts `Dr selected account` / `Cr Opening Balance Equity`;
  - a credit row posts `Dr Opening Balance Equity` / `Cr selected account`.
- The importer does not require total debits to equal total credits. Each row is balanced on its own,
  and the net difference is carried by Opening Balance Equity. A file with only debit openings is
  valid; the equity account simply carries the corresponding credit.
- **Preview writes nothing.** Posting is allowed only when every row passes: known and postable
  account in the same tenant, unique code within the file, amount greater than zero, Dr/Cr side,
  valid non-future date, not in a locked period, on or before first posted activity, no existing
  opening, and not the Opening Balance Equity account itself.
- Posting is **all-or-nothing** in one outer transaction. If a later row fails, earlier rows are
  rolled back too, including a freshly created Opening Balance Equity account. A partial import is
  never left behind.
- A missing code is rejected; the importer never invents an account. An existing opening is rejected;
  correction requires a permission-controlled reversal with a reason and a replacement import.
- `account.manage` is required. The per-account `opening_balance.set` audit remains, plus one
  `opening_balance.bulk_import` event with the filename, row count, Dr/Cr totals and created entry
  IDs. The CSV file itself is not stored.
- A CSV `note` is appended to the journal narration and copied into the per-account audit metadata;
  it never changes amounts, dates or sides.
- No schema or account-row change is made. The journal entries, lines and audit log remain the
  record, and the normal period lock, reversal, tenant-scope and balanced-posting checks still apply.

### Account archive and merge (Build 0.11)

- **Archive is not deletion.** An archived ledger keeps its code, name and every posted
  `journal_entry`/`journal_line`. It becomes non-postable and is removed from new-posting selectors,
  Bank Book, opening-import and product revenue choices. Its full ledger and history remain
  reachable from the ledger hub's archived list.
- Archiving requires `account.manage`, a reason and an **all-time balance of exactly zero**. No
  journal is posted by the archive action. The account row gains `status='archived'`,
  `archived_at`, `archived_by` and a null `merged_into_id`; `account.archive` is audited.
- System/control ledgers are locked from archive/merge: cash 1000, receivable 1100, inventory 1200,
  payable 2000, GST control accounts 2100-2102 and 2200-2202, COGS 5000, purchases 5100, rounding
  5900, and the Opening Balance Equity group. These codes are used by posting and report logic.
- A customer/vendor-linked ledger cannot be archived. It can only be merged into another ledger
  linked to the same party, so the party pointer and statement stay consistent. A legacy
  `customer.account_id`/`vendor.account_id` pointer is treated the same as an `account_profile`
  party link.
- An income ledger referenced by a product cannot be archived until the product is repointed.
- **Merge never edits history.** The source's net balance is moved to a target of the same
  `account.type` by one balanced `source_type='merge'` journal dated today:
  - debit-normal source: `Dr target` / `Cr source`;
  - credit-normal source: `Dr source` / `Cr target`.
  Both lines carry the same `party_id` when the source is party-linked, so the party statement nets
  to the same balance. The source is then archived with `merged_into_id` set. A zero-balance merge
  posts no journal.
- Merge is refused for different types, different parties, bank-to-non-bank, system/control source
  or target, an archived source/target, a source with future-dated activity, or a locked date
  period (the journal posting path enforces the lock). Products using a merged income code and the
  customer/vendor account pointer are repointed in the same transaction.
- **Restore** clears the archive metadata and makes the ledger postable again. It does **not**
  reverse a merge journal. If a merge must be corrected, restore the source and post an explicit
  manual journal; the original merge entry and its audit remain visible.
- The trial balance, P&L and balance sheet remain derived from posted lines, so archiving a
  zero-balance ledger changes no total and merging moves a balance without changing the overall
  equation.

### Account classification and party sub-ledgers (Build 0.10)

- `account.type` remains the accounting rule: assets and expenses are normally debit; liabilities,
  equity and income are normally credit. `account.group_code` classifies **where** the account sits
  in the chart (debtor, creditor, bank, loan, sales, purchase, and so on) and never overrides the
  type's normal side.
- The new-account form presents one **Account type / group** selector and derives the internal type
  from the group. The available groups include cash, bank, Sundry Debtors / Accounts Receivable,
  Sundry Creditors / Accounts Payable, inventory, fixed assets, investments, loans and advances, GST
  input, loans, duties and taxes (GST/TDS), provisions, suspense, capital, drawings, retained
  earnings, Profit & Loss A/c, opening-balance equity, sales, service and other income, purchase,
  direct expenses, COGS, employee costs, finance costs, depreciation and other expenses.
- A group must belong to a compatible type. For example `receivable` is asset, `payable` is
  liability, `sales` is income and `purchase` is expense; incompatible combinations are rejected.
- Suspense is a temporary liability holding account for unidentified or unreconciled amounts; it is
  not automatically cleared and must be reviewed before closing. Profit & Loss A/c is an equity
  classification for workflows that keep a separate P&L account; it does not replace the P&L report
  or create year-end closing entries.
- Creating a `receivable` or `payable` account also creates or links one customer or vendor
  sub-ledger. If that party already has a linked ledger, the account form attaches to it instead of
  creating a duplicate. Linking by name preserves phone, GSTIN, address and credit terms that were
  left blank on the account form; clearing a field later requires an explicit profile edit.
- Invoices, bills, receipts, payments, credit notes and debit notes post to the linked party ledger
  when one exists; otherwise they keep using the control account (1100 receivable or 2100 payable).
  The party statement and the linked ledger are therefore two views of the same posted lines.
- Descriptive data (company name, GSTIN, address, credit terms, bank or loan details) lives in
  `account_profile`. Editing it changes no posted amount, cannot change code/type/group, and is
  audited as `account.update`.
- Product margin, MRP, HSN/SAC and GST are item-master attributes, not ledger attributes. A single
  sales ledger can contain many products with different margins and tax rates.
- Opening balance on a party ledger is tagged with the party id so it is not silently missing from
  the customer/vendor statement.

---

## 7. Tax rules ⚠️

⚠️ Everything in this section must be validated against current GST/CBIC notifications and reviewed by a professional before it produces a real filing or invoice.

| Rule | Detail |
|---|---|
| Tax determination | Per line, from item + place of supply + registration status |
| Rate source | Configured tax master with effective dates; versioned, never hard-coded |
| Computation | `taxable_value × rate`, rounded per line to minor units |
| Inclusive/exclusive | Both supported; inclusive price backed out deterministically |
| CGST/SGST vs IGST | Determined by place of supply vs registered state |
| Exempt/nil/zero-rated | Explicit flags; not inferred from a zero rate |
| Rounding | Per line, then summed; document-level rounding to `Rounding Off` account |
| e-Invoice IRN / statutory QR | **Not implemented. Never fabricated.** Requires verified official API access (Phase 9) |
| ITC | GSTR-2B is a reconciliation **source**, not proof of eligibility |

No tax figure may be presented as "filed", "verified" or "approved" by the system without an actual authorised filing confirmation.

---

## 8. Report derivations

All reports are derived views over posted journal lines — never independently maintained totals.

| Report | Derivation | Invariant |
|---|---|---|
| Trial Balance | Per account: `Σ debit`, `Σ credit`, closing signed balance | `Σ debit balances == Σ credit balances` |
| Profit & Loss | Income credit balances − expense debit balances for the period | `Net profit == Σ (income) − Σ (expense)` |
| Balance Sheet | Asset, liability, equity balances as at period end; equity includes retained earnings | `Assets == Liabilities + Equity` |
| Cash Flow (indirect) | Net profit + non-cash adjustments ± working-capital changes ± investing/financing | Closing cash == balance-sheet cash |
| General Ledger | Chronological lines per account with running balance | Last running balance == closing balance |
| AR/AP Ageing | Open items bucketed by due date (0-30/31-60/61-90/90+) | `Σ buckets == control account balance` |
| Bank Reconciliation | Statement lines vs ledger lines | Unexplained difference must be visible, never hidden |
| GSTR-3B working | Posted invoices − credit notes for outward supplies; posted bills − debit notes for ITC; head-wise set-off | GSTR-1/ledger differences shown, never hidden; preparation aid only, not a filed return |

Every report row must drill down to the source lines that produced it, and the report must display: period, filters, currency, rule version, data freshness.

---

## 9. Validation states

| State | Meaning | Behaviour |
|---|---|---|
| **Verified** | All configured checks passed | Normal display; not a guarantee of absolute correctness |
| **Needs Review** | Anomaly or mismatch detected | Visible flag; blocks nothing unless policy says so |
| **Blocked** | A critical invariant failed | Posting/report refused with a reason |
| **Stale** | Data older than the freshness threshold | Report shows a freshness warning |

Anomaly detection (Layer 4) flags patterns — duplicate invoices, abnormal margins, negative stock, unusual refunds. It must **never** label a user as fraudulent.

---

## 10. Reconciliation (Layer 2)

| Reconciliation | Rule |
|---|---|
| AR subledger ↔ GL control | Sum of open customer items == AR control balance |
| AP subledger ↔ GL control | Sum of open supplier items == AP control balance |
| Inventory ↔ GL | Perpetual inventory value == inventory account balance |
| Bank ↔ GL | Statement balance vs bank ledger, difference explained by timing items |
| Stock equation | `Closing = Opening + Receipts + Eligible Returns + Transfers In + Production In − Sales − Supplier Returns − Damage − Transfers Out − Production Consumption ± Approved Adjustments` |

A mismatch is surfaced with the exact difference and candidate causes. It is **never** silently corrected.

---

## 11. Reversal and correction policy

1. Posted entries cannot be edited or deleted.
2. A reversal creates a mirrored entry, linked by `reversal_of`, with a mandatory reason.
3. Reversal + replacement is allowed only with an audit trail and appropriate permission.
4. Reversals are subject to the same period rules — you cannot reverse into a locked period without reopening it.
5. Correction of opening balances uses a dedicated adjustment entry, not a re-import.

---

## 12. Test obligations (release gate)

Critical (must pass before any financial feature ships):

- ACC-001…015 in `docs/TEST_PLAN.md` (balancing, atomicity, TB, BS, opening/closing, Decimal-only, rounding, period lock, immutability, reversal).
- Property-based tests: random balanced entries must always produce a balanced trial balance.
- Independent recalculation: report totals recomputed by a second code path and compared.
- Regression fixtures: hand-computed expected values committed alongside the test.

**No claim of financial correctness will be made until these pass and the evidence is recorded.**

---

## 13. Requires professional review before production

- GST rates, HSN/SAC mapping, place-of-supply logic, e-invoice thresholds.
- Depreciation methods and asset capitalisation thresholds.
- Revenue recognition for services/construction.
- Multi-currency translation and gain/loss treatment.
- Payroll/statutory dues (not in current scope).
- Any jurisdiction outside India.
