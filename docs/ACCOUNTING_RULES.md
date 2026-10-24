# ARTHIVIO — Accounting Rules

| Field | Value |
|---|---|
| Version | 1.0 |
| Date | 2026-10-24 |
| Status | Draft for owner + professional review |
| Applies to | Phase 2 onward |
| Jurisdiction default | India (configurable per legal entity) |

> These rules are the specification the engine must satisfy. They are **not yet implemented**, and they are **not** a substitute for review by a qualified accountant or tax professional. Tax specifics marked ⚠️ must be validated against current official sources before any tax output is produced.

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
| Opening balances | Entered once per account per period; re-entry requires a correction workflow, not an overwrite |
| Closing | `closing = opening + Σ debits − Σ credits` (signed), asserted per account and per period |
| Carry-forward | Closing balance of period N becomes opening of N+1 for balance-sheet accounts; P&L accounts close to retained earnings per policy |
| Timezone | Business dates are `DATE`; a posting near midnight must not shift periods due to UTC conversion |

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
