# Roadmap

M1 foundation: local setup/migrations, identity, tenant authorization, validated catalog,
parties, warehouse/location master data and grants, pricing intake/history/approval, audit,
Persian RTL workspace. Implementation/acceptance results in DEVELOPMENT_STATUS.md.
Acceptance remains gated by actual CI execution and review; do not infer completion from scope.

M2 approved warehouse scope: append-only stock/ownership/reservation operations and
transactional availability; implemented contracts in INVENTORY.md. Internal non-binding sales drafts with price snapshots/revisions are implemented (SALES_DRAFTS.md).
Version-bound administrator internal reviews are implemented; financial approval/issuance,
purchases/sales contracts and trading settlement remain future
work; Iranian invoices use IRR and two-place ROUND_HALF_UP (founder clarified); exclusive tax with configurable default10% is implemented for internal drafts.
M3: proprietary double-entry accounting, official requirements research and parallel reconciliation.
M4: deeper CRM, quoting and controlled sales agent workflows.
M5: approved research/market/education/marketing assistance.
M6: approved external integrations, official tax validation and operational hardening.

No paid services, main merge or public deployment without founder authorization. No sensitive
agent database writes. New infrastructure requires a concrete validated need.

AI readiness is tracked in AGENT_READINESS.md. A limited local-model read-only sales search
assistant is implemented/tested; broader/writable agents remain future work (SALES_ASSISTANT.md).

The local sales assistant now has deterministic explicit dimension extraction and exact
length-equivalent catalog filters, with clarification rather than dropping constraints.
Broader dimension grammar, inferred/synonymous names and large-scale evaluation
remain future work; current details/evidence are in SALES_ASSISTANT.md.

Founder-approved local invoice transcription is implemented at the API layer and its Persian
UI is being verified. It is separate from financial sales/stock/accounting; current evidence,
limits and delivery status are in INVOICE_INTAKE.md and DEVELOPMENT_STATUS.md.
