# ARTHIVIO — Compliance Matrix

| Field | Value |
|---|---|
| Version | 1.0 |
| Date | 2026-10-24 |
| Status | Draft — informational, not legal advice |
| Jurisdiction basis | India (default), international expansion TBD |

> **No compliance claim is made.** Nothing here states that ARTHIVIO is compliant with any law, standard or certification. Each row records applicability, current implementation status, and the action required. Legal/tax review is required before any regulated output.

---

## 1. Claim policy

| Rule | Detail |
|---|---|
| Certification claims | Prohibited without independent verification |
| Tax filing claims | Only after an authorised filing confirmation exists |
| "GST ready" / "compliant" marketing | Must not appear until verified for the specific jurisdiction and date |
| e-Invoice IRN / statutory QR | Never fabricated; not implemented |
| Customer counts / uptime stats | Prohibited in UI and marketing (defect B-005) |

---

## 2. India — tax and corporate

| Area | Requirement | Applies when | Status | Action needed |
|---|---|---|---|---|
| GST registration display | Show GSTIN on invoices where registered | GST-registered entity | ❌ Not implemented | Verify format/checksum; conditional display |
| GST rate & HSN/SAC | Correct rate per item, effective-dated | GST entity | ❌ Not implemented | Tax master with effective dates; professional review |
| Place of supply | CGST+SGST vs IGST determination | Inter/intra-state supply | ❌ Not implemented | Rules engine + tests |
| Invoice series | Sequential, per FY, no unauthorised gaps | All | ❌ Not implemented | Transactional numbering (Phase 3) |
| GSTR-1 / 3B working papers | Data export for filing | GST entity | ❌ Not implemented | Report + reconciliation; no direct filing |
| GSTR-2B reconciliation | ITC matching (2B is a source, not proof) | GST entity | ❌ Not implemented | Import + match + flag |
| e-Invoice (IRN) | Only via official API, with credentials | Above threshold, if applicable | ⛔ Out of scope (Phase 9) | Official onboarding, sandbox first |
| e-Way bill | Only via official portal/API | Goods movement as applicable | ⛔ Out of scope | Verify access |
| TDS/TCS | Deduction, deposit, certificates | Applicable payments | ⛔ Out of scope | Professional design |
| Companies Act (MCA) | Statutory books, formats, filings | Companies | ⛔ Out of scope | Legal review |
| Accounting standards (ICAI/Ind AS) | Presentation and measurement | Applicable entities | ⚠️ Partially reflected in ACCOUNTING_RULES | Professional review |
| Audit trail (Companies Act) | Audit trail for books of account | Companies | ❌ Not implemented | Audit log design covers intent; verify legal adequacy |

---

## 3. Data protection and privacy

| Area | Requirement | Status | Action needed |
|---|---|---|---|
| DPDP Act 2023 (India) | Consent, purpose limitation, data-principal rights, breach notification | ❌ Not implemented | Privacy notice, consent records, DSAR process |
| Privacy notice | Plain-language notice of what is collected and why | ❌ Not drafted | Owner + legal review |
| Data minimisation | Collect only necessary fields | ⚠️ Design intent only | Field-level justification in DATABASE_DESIGN |
| Retention & deletion | Defined retention; legal hold support | ❌ Not implemented | Policy + implementation |
| Cross-border transfer | Restrictions per applicable law | ❌ N/A currently (local only) | Review before hosting abroad |
| Breach response | Detect, contain, notify | ⚠️ Outline only | Formal runbook |
| AI data handling | No tenant data to external AI without consent/config | ⚠️ Policy only | Enforce at Phase 8 |

---

## 4. Security and payments

| Area | Requirement | Status | Action needed |
|---|---|---|---|
| Payment card data | Never store PAN/CVV | ✅ By design — payments via provider only | Enforce if cards are added (Phase 9) |
| PCI DSS | Applies to card handling | ⛔ Out of scope | Use a provider; scope minimisation review |
| Encryption in transit | TLS | ❌ Not configured (local dev only) | Phase 10 |
| Encryption at rest | DB + backups | ❌ Not implemented | Phase 1/10 |
| Access control | Least privilege, audited | ❌ Not implemented | Phase 1 |
| Security certification (ISO/SOC2) | Optional, costly | ⛔ None claimed | Do not claim |

---

## 5. Financial-record integrity obligations

| Requirement | Status | Note |
|---|---|---|
| Immutable posted entries | ❌ Not implemented | Spec + ACCOUNTING_RULES §11 define behaviour |
| Audit trail of changes | ❌ Not implemented | Phase 1 audit log is the base |
| Reconciliation evidence | ❌ Not implemented | Phase 2 |
| Reproducible reports (period + rule version) | ❌ Not implemented | Phase 2/6 |
| Backup restoration proof | ❌ Not implemented | Phase 1 gate |

---

## 6. Jurisdiction readiness

| Jurisdiction | Status | Requirement to enable |
|---|---|---|
| India | Designed, nothing implemented | Tax review + rules engine |
| UAE / GCC (VAT) | Not designed | Separate rule set, currency, e-invoicing |
| EU (VAT, e-invoicing) | Not designed | Country-specific rules; GDPR |
| US (sales tax) | Not designed | Nexus rules, state-level rates |
| UK | Not designed | VAT + MTD considerations |

**Rule:** never apply Indian rules globally. Each jurisdiction needs its own verified rule set, currency handling, and compliance calendar.

---

## 7. Owner actions required (before any public launch)

1. Decide launch jurisdiction(s) and entity structure (OQ-02).
2. Engage a qualified CA/tax professional to review `docs/ACCOUNTING_RULES.md` §7.
3. Obtain legal review of the privacy notice and data-retention policy.
4. Verify current thresholds, rates, and effective dates from official sources at build time — not from this document.
5. Do not publish any compliance, certification or customer-count claim until evidence exists.
6. Complete Phase 10 readiness (independent security review, restore drills, monitored launch).

---

## 8. Status summary

| Category | Rows | Implemented | Out of scope | Needs review |
|---|---|---|---|---|
| India tax/corporate | 12 | 0 | 4 | 8 |
| Data protection | 7 | 0 | 0 | 7 |
| Security/payments | 6 | 0 | 1 | 5 |
| Record integrity | 5 | 0 | 0 | 5 |
| **Total** | **30** | **0** | **5** | **25** |

Zero rows are implemented because zero application code exists. This table is the baseline for future audits.
