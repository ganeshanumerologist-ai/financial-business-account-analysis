# ARTHIVIO — OpenCode Master Build Prompt
## Primary instruction file for developing the ARTHIVIO business finance, accounting and analytics platform

> **How to use:** Open this file in the root of the ARTHIVIO project repository and give it to OpenCode as the governing project instruction. If OpenCode supports project rules/instructions, configure this file as the primary project instruction. Keep this file in the repository so it remains available throughout development.

## OpenCode execution contract

These execution rules apply in addition to the complete product requirements below.

1. **Treat the full specification in this file as the source of truth.** Do not silently omit, weaken, reinterpret, or replace requirements. If two requirements conflict or a requirement is ambiguous, document the conflict and choose the safest reversible approach; ask the owner only when a decision is genuinely blocking.
2. **Start by inspecting the actual repository and environment.** Check existing files, Git status, package managers, runtimes, dependencies, database configuration, tests, and available commands before changing anything. Never assume the repository is empty or that a tool is installed.
3. **Plan before coding.** Create or update the documentation and traceability artifacts required below. Map each requirement to a planned module, acceptance criteria, and tests. Identify assumptions, dependencies, external services, costs, and legal/accounting/security review needs.
4. **Work in small, reviewable phases.** Do not generate the whole product in one pass. Implement the smallest useful step in the current phase, run relevant checks, inspect the resulting diff, and report the outcome before continuing.
5. **Protect existing work.** Do not delete, overwrite, reset, or migrate user data or existing project files without first inspecting their purpose and making a safe backup where appropriate. Do not run destructive commands without explicit approval.
6. **Never fake completion.** Do not claim code, tests, integrations, backups, security controls, tax compliance, payment confirmation, or deployment works unless it has actually been implemented and verified. Clearly label mock/demo data and unimplemented features.
7. **Do not invent secrets or paid access.** Never hard-code credentials, expose secrets, enable paid services, create paid resources, or incur charges without explicit owner approval. Use documented environment-variable examples and safe local defaults.
8. **Financial correctness is a release gate.** Use deterministic accounting calculations, decimal-safe monetary arithmetic, explicit rounding rules, balanced double-entry postings, idempotency, audit history, reconciliation, and tests. If a critical invariant fails, block the affected posting or output rather than guessing or silently correcting it.
9. **Security is a release gate.** Enforce authorization and tenant isolation on the server for every applicable operation. Add tests that attempt cross-tenant access and privilege escalation. Never rely only on frontend hiding.
10. **Verify every change.** Run the relevant formatter, linter, type checks, unit/integration/end-to-end tests, migrations checks, and build commands that are available. If a check cannot run, state exactly why; never fabricate a passing result.
11. **Keep documentation synchronized with code.** Update the README, architecture, database, security, accounting, compliance, testing, roadmap, decision log, and requirements traceability documents as appropriate.
12. **Finish every work session with a concise report:** what changed, files created/modified, commands and tests actually run, pass/fail results, known limitations, security/accounting risks, any owner action required, and the single next recommended step.
13. **Do not expose confidential business data to external AI or other services** unless the integration is configured, authorized, consented to where required, and reviewed for data protection.
14. **Do not launch to production by implication.** Production deployment, domain changes, public exposure, real payment/tax/banking integrations, destructive migrations, and other high-impact actions require explicit owner approval and the relevant readiness checks.

## Mandatory sequential rules for OpenCode — follow in order

**These three rules are mandatory execution gates. Follow Rule 1, then Rule 2, then Rule 3. Do not skip, combine, or silently advance past a gate.** The full product specification below remains in force.

### RULE NO. 1 — Repository inspection, requirements and planning only

> Inspect the current repository and prepare the complete requirements, architecture, database schema, security model, accounting validation strategy, development roadmap and test plan. Create or update the documentation files listed in the master instructions. Do not build all modules yet. Report the findings and proposed first implementation step.

**Acceptance gate:**
- Inspect the real repository, environment, existing files, dependencies, Git status and available tests before modifying anything.
- Create or update the documentation listed in the master instructions, including requirements, architecture, database design, security plan, backup/recovery, accounting rules, compliance matrix, API integrations, report catalogue, test plan, roadmap, decision log and requirements traceability.
- Record assumptions, unresolved decisions, external dependencies, potential costs, risks and acceptance criteria.
- Do not implement application modules during this rule. Documentation and safe inspection only.
- Report findings, files created/updated, commands actually run, known blockers, and the proposed first implementation step.
- Stop at the end of Rule 1 and wait for the owner's approval before implementing Rule 2.

### RULE NO. 2 — Phase 1 only: secure foundation

> Implement Phase 1 only: authentication, tenant isolation, roles and permissions, database migrations, audit logs, secrets management and a tested backup/restore foundation. Add automated security tests. Do not start billing or accounting modules until the foundation passes its critical tests.

**Acceptance gate:**
- Implement only the Phase 1 secure foundation described in the approved architecture.
- Include authentication and secure session handling; server-side tenant isolation; role-based and least-privilege permissions; safe database migrations; audit logs; environment-based secrets management; and a backup/restore foundation.
- Test backup restoration and data integrity. A backup file existing is not proof that restoration works.
- Add and run automated security tests, including attempts at cross-tenant access and unauthorized actions. Add migration and authorization tests as appropriate.
- Run available formatting, linting, type checks, unit/integration tests and build checks. Report exact commands and actual results.
- Fix critical failures before declaring Phase 1 complete. If a critical test cannot run or fails, state why, do not claim the foundation passed, and do not begin billing or accounting.
- Do not implement billing, invoicing, the accounting engine, journals, ledgers, or financial statements during this rule.
- At the end, report changed files, tests and results, unresolved risks, and whether every critical Phase 1 gate passed. Stop and wait for the owner's approval before starting Rule 3.

### RULE NO. 3 — Phase 2 only: accounting core

> Implement Phase 2 only according to the approved architecture. Build the double-entry accounting engine, ledger, trial balance and financial statements with reconciliation invariants, source traceability and automated tests. Do not claim financial correctness unless the relevant tests pass.

**Prerequisites:**
- Rule 1 planning must be documented and approved.
- Phase 1 must be implemented, and its critical security, migration, tenant-isolation and backup/restore tests must pass.
- If any prerequisite is not satisfied, stop and report the blocker instead of proceeding.

**Acceptance gate:**
- Implement only Phase 2 accounting-core features defined in the approved architecture: chart of accounts where required, balanced double-entry journals, general ledger, trial balance, profit and loss, balance sheet and cash flow statement as scoped in the approved plan.
- Use decimal-safe monetary arithmetic and documented precision, currency and rounding policies. Do not use binary floating-point arithmetic for authoritative monetary calculations.
- Enforce balanced journal entries and atomic posting. Use controlled reversal/correction entries for posted transactions; never silently edit posted financial records.
- Provide source-document references, audit history, reporting-period filters, rule/version traceability and drill-down to source records where applicable.
- Add automated unit, integration, property/invariant and regression tests for journal balancing, ledger totals, trial-balance equality, financial-statement reconciliation, balance-sheet equation, period boundaries, rounding, duplicate/idempotent posting and unauthorized access.
- Independently recalculate critical totals where appropriate and compare them with the primary calculation path.
- Block critical postings or reports when a required invariant fails. Never silently correct a discrepancy or fabricate missing figures.
- Run all available relevant checks and report exact commands, actual results, untested areas and remaining professional-review needs.
- Do not claim financial correctness unless the relevant tests have actually passed. Passing automated tests does not replace qualified accounting/tax review.
- Do not start later phases or unrelated modules during this rule. Stop after Phase 2 and report the outcome; wait for the owner's approval before proceeding further.

### Rule enforcement and stop conditions

- The rule number is the current scope limit. Do not implement later rules or phases early.
- If repository conditions make a rule unsafe or impossible, stop, explain the evidence and propose a safe alternative.
- Never mark an acceptance gate as passed based on code inspection alone when execution/testing is required.
- Keep a checklist of every acceptance criterion with `PASS`, `FAIL`, or `NOT RUN`, plus evidence.
- A feature is complete only when implementation, relevant tests, documentation and acceptance criteria agree.
- Do not promise zero errors. Minimize risk through verification, reconciliation, independent checks and safe blocking of critical failures.

---

## First action required

Before implementing application features, inspect the repository and environment, then follow **“24. REQUIRED FIRST RESPONSE FROM OPENCODE”** in the specification below. Create or update the planning documents and propose the first small, testable step. Do not skip directly to a large code dump.

---

## Complete product specification

The specification below is preserved from the owner's supplied master instructions. Treat every section as a requirement unless a limitation or conflict is explicitly documented.

---

# ARTHIVIO — SUPER MASTER PROJECT INSTRUCTIONS
## Global Business Management, Accounting, Financial Intelligence & Analytics Platform

### 1. YOUR ROLE

Act as a senior enterprise software architect, full-stack developer, accounting-system specialist, financial data engineer, cybersecurity engineer, UX/UI designer, QA automation engineer, and technical project manager.

Build a secure, modern, scalable business platform named **ARTHIVIO**.

Provisional brand tagline: **Smarter Finance. Stronger Business.**

The brand name is provisional until domain, company-name and trademark checks are completed.

The platform must be suitable for businesses of different sizes worldwide, beginning with India-specific accounting, taxation and business workflows and expanding internationally through jurisdiction-specific modules.

The owner is a complete programming beginner. Explain important actions in simple language, maintain clear documentation, and never assume that the owner understands terminal commands or deployment.

### 2. NON-NEGOTIABLE DEVELOPMENT RULES

1. Do not attempt to build the entire production system in one enormous code-generation step.
2. First inspect the existing repository, files, installed tools, framework, dependencies and available environment.
3. Preserve existing working functionality. Do not overwrite or delete important files without checking them.
4. Create a complete requirements document, architecture plan, database model, security plan, development roadmap and test plan before implementing the core modules.
5. After preparing the plan, explain it briefly and begin implementation phase by phase.
6. Do not wait for the owner to repeat requirements already stated in this document.
7. Do not claim a feature works until it has been implemented and tested.
8. Do not fabricate successful tests, security certifications, financial results, payment confirmations, government approvals or API connectivity.
9. Do not use placeholder data in a way that can be mistaken for actual customer or financial data.
10. Use stable, supported dependencies and document why important technology choices are made.
11. Use environment variables or a suitable secrets manager for credentials. Never expose secrets in source code or commit them to version control.
12. Never weaken authentication, authorization, accounting validation or data protection merely to make a demonstration work.
13. For every phase, report completed work, files changed, tests performed, remaining risks and the next recommended step.
14. When a critical requirement cannot be safely implemented, explain the limitation and provide a controlled alternative.
15. Maintain a project decision log and a requirements-to-test traceability matrix.

Governing principles:

- No Silent Failure.
- No Silent Financial Correction.
- No Unsupported Financial Claim.
- No Unverified Critical Output.
- No Unauthorized Cross-Tenant Data Access.
- No False Payment or Government-Verification Status.

Absolute zero-error operation cannot be promised. The system must instead minimize errors through independent validation, reconciliation, testing, auditability and safe blocking of critical failures.

### 3. PRODUCT OBJECTIVE

Create one integrated platform for:

- Accounting and bookkeeping.
- Financial statements and financial analysis.
- Sales, purchases and universal billing.
- Customer and supplier management.
- Inventory, barcode scanning and warehouse operations.
- Manufacturing and raw-material tracking.
- Cash, bank, receivables and payables.
- Business budgets, costing, projects and assets.
- Tax preparation and authorized compliance integrations.
- Industry-specific reports and interactive charts.
- AI-assisted business analysis and forecasting.
- Multi-company and multi-branch management.
- Online and carefully controlled offline operations.
- Secure storage, audit trails, backups and disaster recovery.

A business should activate only the modules relevant to its legal structure, industry, permissions and available data.

### 4. BRAND AND VISUAL DESIGN

Create a contemporary, premium, multinational-grade enterprise SaaS interface.

Brand: ARTHIVIO  
Tagline: Smarter Finance. Stronger Business.

Mandatory design constraints:

- Do not use a black-and-blue combination.
- Use a refined warm-ivory, emerald-green, soft-sage and muted-gold palette.
- Suggested starting colors:
  - Warm ivory: #F7F5EF
  - Emerald green: #176B4D
  - Soft sage: #DCE8D9
  - Muted gold: #C6A15B
  - Dark green-teal for text: #183E35
- Maintain strong readable contrast and accessibility.
- Use precise typography, clean spacing, subtle borders, restrained shadows and consistent iconography.
- Avoid clutter, oversized headlines, excessive decorative photography and giant background images.
- Do not use a large city image as the main visual element. Business dashboards, modern data visualizations and a restrained growth motif should be the main visual focus.
- Use vector logos and icons where appropriate.
- Build actual responsive interface components, not a static screenshot pretending to be a working website.
- Target crisp, high-resolution visual quality comparable to premium enterprise products. “8K” is not a substitute for responsive design, sharp assets or accessible text.
- The interface must work on desktop, tablet and mobile.
- Provide appropriate loading, empty, error, permission-denied and offline states.

### 5. PUBLIC WEBSITE AND NAVIGATION

Build a public marketing homepage separate from the authenticated business dashboard.

Suggested public navigation:

- Platform
- Solutions
- Industries
- Reports & Analytics
- Resources
- Pricing
- Log in
- Get Started

Suggested dashboard navigation:

- Dashboard
- Accounting
- Sales & Purchase
- Inventory
- Banking & Cash
- Reports & Analytics
- Business Intelligence
- AI Insights
- Documents
- Compliance
- Users & Permissions
- Settings

Adapt navigation to screen size, user role, enabled modules and business type. Do not display irrelevant menu items.

Homepage headline:

“Smarter Finance. Stronger Business.”

Supporting message:

“Accounting, financial clarity and intelligent business analysis — connected in one secure platform.”

Provide a clear product overview, interactive-style dashboard preview, business-growth charts, feature summaries, security information and a prominent Get Started action.

Do not publish unsupported customer counts, uptime percentages, certifications or performance claims.

### 6. USERS, TENANTS AND ORGANIZATION STRUCTURE

Support multiple independent users and businesses.

Required hierarchy:

User → Workspace/Tenant → Legal Entity → Branch/Location → Warehouse/Stock Location → Department/Cost Centre/Project.

Requirements:

- One user may have authorized access to multiple businesses.
- Each business can have multiple authorized users.
- Strict server-side tenant isolation on every data request.
- Separate roles and permissions for owner, administrator, manager, accountant, cashier, sales staff, inventory staff and read-only users.
- Branch-, warehouse-, department- and project-level restrictions where required.
- Consolidated multi-company reports only when explicitly authorized and configured.
- Correct handling of intercompany transactions and eliminations when applicable.
- Keep legal entity type separate from industry type.
- Support configurable business profiles and industry-specific modules.

Never rely solely on hiding interface elements for security.

### 7. INDUSTRY TEMPLATES

Design configurable templates for:

1. General trading and wholesale.
2. Retail and POS.
3. Manufacturing.
4. E-commerce and marketplaces.
5. Services and consultancy.
6. Construction and contracting.
7. Agriculture and agri-business.
8. Pharmaceutical, medical and healthcare businesses.
9. Food, restaurant and hospitality.
10. Transport and logistics.
11. Import and export.
12. Real estate and property.
13. Professional firms and agencies.
14. Education and training.
15. Nonprofit organizations, trusts and societies.

These are starting templates, not a claim that every legal or regulatory requirement is covered.

Regulated sectors such as banking, insurance, securities and NBFCs require additional specialist design and review.

### 8. ONBOARDING WORKFLOW

Implement the following sequence:

1. Registration and login.
2. Secure account setup and optional MFA where supported.
3. Language selection.
4. Create business workspace.
5. Enter business identity and contact information.
6. Select legal structure and industry.
7. Configure financial year, currency and accounting settings.
8. Configure GST/tax status conditionally.
9. Set up chart of accounts and opening balances.
10. Add products, services, units, SKU and barcode.
11. Configure branches, warehouses, departments and projects.
12. Add authorized users and roles.
13. Import customers, suppliers, opening stock and balances.
14. Run setup validation.
15. Resolve errors and revalidate.
16. Open the role-based dashboard only when critical setup requirements pass.

Do not assume GST registration is compulsory for every business.

### 9. ACCOUNTING ENGINE

Implement accounting using deterministic, tested business rules.

Core features:

- Configurable chart of accounts.
- Double-entry journal engine.
- General ledger.
- Customer and supplier subledgers.
- Trial balance.
- Profit and loss statement.
- Balance sheet.
- Cash flow statement.
- Accounts receivable and payable ageing.
- Bank and cash reconciliation.
- Budgets and actual-versus-budget comparisons.
- Fixed assets and depreciation.
- Loans, interest and EMI schedules.
- Cost centres, departments and project costing.
- Period closing and locking.
- Reversal and correction entries.
- Audit trails and source-document references.
- Configurable multicurrency support.
- Import and migration validation.

Every posted journal must balance according to the configured accounting precision and rounding policy.

Do not permit silent edits to posted financial records. Use controlled reversals or correction entries with reasons, approvals and audit history.

Financial statements must reconcile to the underlying ledger.

Accounting standards and policies must be configurable for the applicable jurisdiction and legal entity.

### 10. UNIVERSAL BILLING, POS AND PAYMENTS

Support businesses selling or purchasing goods, products, raw materials and services.

Invoice fields, where applicable:

- Invoice number, date and time.
- Seller's legal/business name and address.
- Logo, contact details and applicable GSTIN.
- Buyer name, mobile number, address and applicable GSTIN.
- Invoice type and place of supply.
- Product/service description.
- SKU/barcode, quantity, unit and rate.
- Discounts, tax mapping and totals.
- Payment terms, payment status and due date.
- Source order, delivery and related-document references.

Support customer lookup by name, mobile number, customer ID or GSTIN where applicable.

Provide authorized access to customer ledger history, previous bills, receipts, payments, advances, returns and outstanding amounts.

Previous items may be reused for convenience, but current prices, taxes, availability and stock must be revalidated.

Do not automatically merge customers merely because their mobile numbers match.

Support:

- Cash.
- UPI and payment QR.
- Debit and credit cards through supported payment providers.
- Online payments and authorized gateways.
- Bank transfers such as NEFT, RTGS and IMPS where supported.
- Credit sales and udhaar.
- Split payments across supported methods.
- Partial payments, advances, refunds and outstanding balances.

Never mark a payment confirmed without a valid confirmation source or an authorized, audited manual confirmation.

Distinguish a UPI payment QR from the statutory GST e-invoice signed QR and Invoice Reference Number (IRN). Never fabricate a statutory QR or IRN.

Support quotations, sales orders, dispatch/delivery, invoices, receipts, credit notes, debit notes, customer returns, supplier returns and payment reminders.

Support A4 invoice printing, 58 mm/80 mm thermal receipts where supported, PDF exports and color/black-and-white printing.

Validate invoice numbering, tax calculations, rounding, payment allocation, inventory movements, receivables, general-ledger postings and duplicate transactions.

### 11. COMPLETE INVENTORY AND BARCODE

Inventory must track all relevant stock movements, including:

- Opening stock.
- Purchases and goods receipts.
- Sales and dispatches.
- Customer returns.
- Supplier returns.
- Damage, wastage and expiry.
- Transfers between warehouses.
- Production and production consumption.
- Samples and internal use.
- Approved stock adjustments.

Each movement should record product, quantity, unit, date/time, source document, warehouse, user and approval where required.

Maintain a complete, traceable product movement history.

Support:

- Barcode scanning through compatible USB/Bluetooth scanners.
- Supported mobile-camera barcode scanning.
- EAN/UPC, Code 128 and other explicitly supported formats.
- Internal SKU and barcode generation.
- Barcode label printing.
- Product variants.
- Unit conversions.
- Batch, serial-number and expiry tracking where relevant.
- Physical stock counts.
- Reorder levels and purchase planning.
- Slow-moving and dead-stock analysis.
- Inventory valuation and margin analysis.
- Warehouse and branch transfers.
- Landed-cost allocation.
- Damaged/quarantine stock handling.

A barcode identifies a product; it does not automatically prove its current price, stock quantity or expiry.

Returned goods must not automatically become saleable stock until the applicable inspection process is completed.

Use the following stock reconciliation concept:

Closing Stock = Opening Stock + Receipts + Eligible Customer Returns + Transfers In + Production In − Sales/Issues − Supplier Returns − Damage/Wastage − Transfers Out − Production Consumption ± Approved Adjustments.

The actual formula must respect item status, units, timing and configured business rules.

When perpetual inventory accounting applies, inventory and cost-of-goods-sold entries must reconcile with the accounting ledger.

### 12. OFFLINE OPERATIONS AND SYNCHRONIZATION

Offline billing is an essential requirement.

Provide an offline-capable workflow using an appropriate, tested architecture.

- Cache only necessary and authorized product, pricing, tax-configuration and customer data.
- Protect local data using supported device storage security.
- Save each offline transaction with a globally unique transaction ID.
- Show “Offline / Pending Sync” clearly.
- Print a local receipt only when the device and printer support it.
- Sync automatically or through an explicit user action when connectivity returns.
- Use idempotency keys and transaction constraints to prevent duplicate financial postings.
- Detect concurrent changes, stock conflicts and duplicate invoice risks.
- Record conflicts and require appropriate resolution and audit logging.
- Display offline stock as an estimate where other counters may be selling simultaneously.
- Use a safe invoice-number allocation strategy that works across multiple devices and branches.
- Never pretend that an offline system has obtained a fresh government IRN, online bank confirmation or gateway confirmation.

Do not overwrite conflicting transactions silently.

### 13. FINANCIAL ACCURACY AND SIX-LAYER VALIDATION

Implement six complementary validation layers.

Layer 1 — Transaction validation:
Required fields, permissions, dates, units, amounts, duplicate IDs and calculation checks.

Layer 2 — Cross-ledger reconciliation:
Subledgers against general ledger, inventory against inventory accounts, bank records against bank ledgers, receivables/payables against control accounts.

Layer 3 — Cross-report invariants:
Trial balance equality, balance-sheet equation, opening-plus-movements-to-closing, and report totals matching source data.

Layer 4 — Anomaly detection:
Unusual transactions, duplicate invoices, unexpected margins, negative stock, suspicious refunds and abnormal patterns. Flag for review without automatically alleging fraud.

Layer 5 — Independent recalculation:
Recalculate critical totals using an independent calculation path and compare results.

Layer 6 — Approval and audit:
Maker-checker controls, period locks, high-risk approvals, correction/reversal records and traceable evidence.

Use these validation states:

- Verified: configured checks passed; not a guarantee of absolute correctness.
- Needs Review.
- Blocked.
- Stale Data.

Critical failures must block posting or the affected report when safe operation requires it.

Implement rule versioning, effective dates, audit logs, data lineage, document provenance, concurrency controls, idempotency and regression testing.

Every important figure should be traceable to source transactions, formula, filters, reporting period and rule version.

### 14. REPORTS AND VISUAL ANALYTICS

Design a shared library of approximately 150 visualization/report templates across ten groups:

1. Financial statements and performance.
2. Accounting, ledgers and audit.
3. Sales and customer analysis.
4. Purchase and supplier analysis.
5. Inventory and warehouse.
6. Costing, manufacturing and operations.
7. Cash, credit and risk.
8. Tax, GST and compliance.
9. Strategy, organization and process.
10. AI, forecasting and cross-business analysis.

Do not display all charts to every user.

Select relevant charts based on industry, enabled modules, available data, role and reporting period.

Allow users to customize their dashboard and restore default layouts.

Each chart/report must have:

- Defined source data.
- Explicit formulas and calculation rules.
- Applicability conditions.
- Permissions and filters.
- Drill-down to underlying records.
- Export capability.
- Hindi/English labels.
- Data freshness information.
- Missing-data warnings.
- Clear separation of actual values, estimates and forecasts.

Do not fabricate data to fill empty charts.

### 15. AI BUSINESS INTELLIGENCE

AI may explain financial trends, summarize business performance, identify potential anomalies and help users explore authorized records.

AI must not replace deterministic accounting calculations.

Requirements:

- Use only data the current user is authorized to access.
- Ground financial statements in verified source records.
- Cite or link internal source records where appropriate.
- Explain assumptions and missing data.
- Distinguish actual results from estimates and forecasts.
- Avoid invented financial numbers or unsupported conclusions.
- Treat anomaly findings as indicators requiring review, not proof of misconduct.
- Keep AI access tenant-isolated.
- Log important AI actions where appropriate.
- Do not send confidential business data to external AI services without appropriate configuration, permissions, consent and data-protection review.

### 16. USER DATA STORAGE AND BACKUPS

Every tenant's data must be securely isolated.

Implement:

- Primary data storage.
- A secondary backup copy in a separate protected storage location.
- Daily automated backups.
- Backup job status and failure alerts.
- Backup integrity verification.
- Regular restore testing.
- Documented backup retention.
- Encrypted backups and secure key management.
- Separate, least-privilege backup permissions.
- An additional isolated/off-site or immutable backup where feasible.
- Disaster-recovery procedures and rollback capability.
- Recovery targets for acceptable data loss and restoration time.

Two folders on the same disk or server do not count as independent disaster-recovery protection.

Do not claim a backup is recoverable merely because a backup file exists.

Test restoration and verify data integrity, tenant boundaries and related records.

Protect local offline data as well as cloud data.

Define retention, deletion, export and legal-hold procedures according to applicable law and business needs.

### 17. SECURITY AT EVERY LEVEL

Implement layered security:

1. Account authentication, strong password controls, MFA options and session management.
2. Server-side tenant isolation.
3. Role-based and least-privilege access.
4. Branch and warehouse permissions.
5. Additional authentication and approvals for high-risk financial actions.
6. Encryption in transit and at rest.
7. Secure secrets and encryption-key management.
8. Permission checks for exports, documents and downloads.
9. Restricted and audited administrator/support access.
10. Secure API credentials, scopes, rate limits and revocation.
11. Offline-device protection and safe synchronization.
12. Security monitoring, suspicious-activity alerts and incident response.
13. Protected backups, restore testing and disaster recovery.

Test for cross-tenant data leakage, authorization bypass, injection, session misuse, unsafe file uploads, exposed secrets, insecure APIs and improper export permissions.

Do not claim compliance or security certification without actual independent verification.

### 18. OFFICIAL INDIAN COMPLIANCE AND INTEGRATIONS

Use official sources as the starting point for implementation research:

- GST Portal: https://www.gst.gov.in/
- e-Invoice Portal: https://einvoice.gst.gov.in/
- e-Invoice API Sandbox: https://einv-apisandbox.nic.in/
- Income Tax e-Filing: https://www.incometax.gov.in/
- Income Tax API Specifications: https://www.incometax.gov.in/iec/foportal/api-specifications
- MCA: https://www.mca.gov.in/
- ICAI Accounting Standards: https://www.icai.org/post/accounting-standards
- ICAI Ind AS: https://www.icai.org/post/indian-accounting-standards-indas
- CBIC Tax Information: https://taxinformation.cbic.gov.in/
- MeitY: https://www.meity.gov.in/
- RBI: https://www.rbi.org.in/
- Udyam: https://udyamregistration.gov.in/
- EPFO: https://www.epfindia.gov.in/
- ESIC: https://www.esic.gov.in/

Verify the current law, notifications, thresholds, effective dates, API availability, onboarding, credentials, consent and eligibility before implementing each integration.

Do not assume that an official API is publicly available or that access is automatic.

Implement applicable invoice and tax rules only after validating them against current official sources and qualified professional review.

GSTR-2B is a reconciliation source, not automatic proof that every input tax credit is eligible.

Tax filing and regulated actions must require authorized integrations, appropriate permissions, verified inputs and human approval where required.

Check applicable privacy, data-protection and cybersecurity obligations for the actual launch date and jurisdictions served.

For international expansion, use jurisdiction-specific rule sets, currencies, accounting standards, tax calculations and compliance calendars. Never assume Indian rules apply globally.

### 19. LANGUAGES AND ACCESSIBILITY

Support Hindi and English initially, with architecture ready for additional languages.

Requirements:

- Language selector.
- Translated navigation, validation messages, reports and key help text.
- Accessible text sizes, keyboard navigation and readable contrast.
- Responsive layouts.
- Voice input and spoken responses as a planned capability, using supported speech services and selected language.
- Appropriate privacy notices and consent for speech processing.
- Do not claim every language or offline speech feature works until tested.

### 20. PROPOSED TECHNOLOGY ARCHITECTURE

Evaluate, rather than blindly assume, the following candidates:

- Frontend: Next.js and TypeScript.
- Backend: Python and FastAPI.
- Database: PostgreSQL or an appropriately secured managed PostgreSQL service.
- Charts: Apache ECharts or a comparable maintained visualization library.
- Offline: an appropriate PWA/local-storage architecture with secure synchronization.
- Document generation: suitable maintained libraries for PDF, spreadsheet and CSV output.
- Hosting: a low-cost prototype first, with a separate production-readiness assessment.

Before choosing the final stack, test compatibility, mobile usability, deployment costs, persistent storage, background jobs, database limits, backups, security features and offline behavior.

Do not place sensitive business records in an insecure browser-only database as the only production source of truth.

### 21. DEVELOPMENT PHASES

Phase 0 — Requirements and architecture:
Inspect repository, document requirements, map dependencies, prepare database design, threat model, API boundaries, acceptance criteria and project plan.

Phase 1 — Secure foundation:
Authentication, tenant model, roles, database migrations, audit logs, secrets, backups and restore testing.

Phase 2 — Accounting core:
Chart of accounts, double-entry engine, journals, general ledger, trial balance and financial statements.

Phase 3 — Customers, suppliers and billing:
Invoices, receipts, credit sales, returns, printing and ledger integration.

Phase 4 — Inventory and barcode:
Stock movements, warehouses, stock count, barcode, batch/serial/expiry where applicable and inventory reconciliation.

Phase 5 — Offline and synchronization:
Offline queue, idempotency, conflict resolution and multi-counter testing.

Phase 6 — Reports and analytics:
Financial reports, industry-specific dashboards, charts, drill-down and exports.

Phase 7 — Industry modules:
Implement and test templates incrementally.

Phase 8 — AI insights:
Authorized data access, traceable explanations, missing-data handling and forecast labeling.

Phase 9 — External integrations:
Tax, payment, banking and other integrations only after technical and legal access is verified.

Phase 10 — Production readiness:
Independent accounting/tax/security review, regression tests, penetration testing, backup restoration, migration testing, rollback and monitored launch.

Do not skip phases simply to produce a visually impressive demo.

### 22. TESTING AND RELEASE GATES

Create automated tests for:

- Accounting invariants.
- Invoice calculations and tax mapping.
- Customer/supplier ledgers.
- Inventory movement reconciliation.
- Duplicate prevention and idempotent posting.
- Concurrent transactions.
- Offline synchronization and conflicts.
- Tenant isolation and authorization.
- Report-to-ledger traceability.
- API failures and invalid inputs.
- Backup restoration and data integrity.
- Permission-protected exports.
- Migration and rollback.
- Accessibility and responsive behavior.

Use unit, integration, end-to-end, regression, property-based and stress tests as appropriate.

Do not release critical financial functionality when critical tests fail.

Require independent professional review for significant accounting/tax rules and security review before production.

### 23. DOCUMENTATION AND COMMUNICATION

Maintain these project files:

- README.md
- docs/REQUIREMENTS.md
- docs/ARCHITECTURE.md
- docs/DATABASE_DESIGN.md
- docs/SECURITY_PLAN.md
- docs/BACKUP_AND_RECOVERY.md
- docs/ACCOUNTING_RULES.md
- docs/COMPLIANCE_MATRIX.md
- docs/API_INTEGRATIONS.md
- docs/REPORT_CATALOG.md
- docs/TEST_PLAN.md
- docs/DEVELOPMENT_ROADMAP.md
- docs/DECISION_LOG.md
- docs/REQUIREMENTS_TRACEABILITY.md

Adapt this list to the existing repository without overwriting useful files.

Explain commands in beginner-friendly language. Clearly distinguish completed work, proposed work, untested functionality and external services that still need setup.

### 24. REQUIRED FIRST RESPONSE FROM OPENCODE

Before implementing the complete platform:

1. Inspect the existing project and runtime.
2. Summarize the current repository and any existing functionality.
3. Identify important missing requirements or technical blockers.
4. Prepare the architecture and phase plan.
5. List the security and accounting risks that require attention.
6. Create or update the documentation files.
7. Propose the first small, testable implementation step.

Do not generate the entire application in one response.

After the plan is ready, implement only the first approved foundational phase, run its tests, explain the results and proceed incrementally.

The owner must be able to understand what has been built, what remains incomplete and how to test each feature.

END OF SUPER MASTER PROJECT INSTRUCTIONS
