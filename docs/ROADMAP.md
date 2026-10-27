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
M3 accounting is explicitly deferred to last by the founder on2026-10-27; reference-process input is not a blocker for the current agents.
M4 current priority: controlled internal sales drafts/assistance and CRM.
M5 current priority: internal research/development, education and marketing drafts before accounting.
M6: approved external integrations, official tax validation and operational hardening.

No paid services, main merge or public deployment without founder authorization. No sensitive
agent database writes. New infrastructure requires a concrete validated need.

AI readiness is tracked in AGENT_READINESS.md. A limited local-model read-only sales search
assistant is implemented/tested; broader/writable agents remain future work (SALES_ASSISTANT.md).

The local sales assistant now has deterministic explicit dimension extraction and exact
length-equivalent catalog filters, with clarification rather than dropping constraints.
Broader dimension grammar, inferred/synonymous names and large-scale evaluation
remain future work; current details/evidence are in SALES_ASSISTANT.md.

Founder-approved local invoice transcription is implemented with its Persian
UI and native/API/desktop/mobile tests. It is separate from financial sales/stock/accounting; current evidence,
limits and delivery status are in INVOICE_INTAKE.md and DEVELOPMENT_STATUS.md.

The founder explicitly deferred unavailable invoice samples; FOUNDER_INPUTS.md tracks them as
future input, not a blocker for independent development. Manual CRM follow-ups and their
party/status/overdue workspace filters are implemented (CRM_FOLLOW_UPS.md); accounting/financial
issuance, outbound communication and writable agents remain outside this delivery.

A synthetic PostgreSQL custom-archive recovery drill, including corruption/mismatch cleanup
regressions, is implemented in CI (BACKUP_RESTORE.md). Operational backup policies, off-host
retention, role/ACL restoration and production recovery acceptance remain future work.
The accounting reference-process input is tracked as F-002 in FOUNDER_INPUTS.md for parallel
reconciliation design; it does not authorize a financial posting engine or tax integration.

The approved internal four-role workbench and its exact boundaries are in INTERNAL_AGENTS.md.
External research retrieval/publishing/messaging remain separate future authorization.

Founder priority2026-10-27: research, education, marketing and sales precede accounting. The internal four-role draft/source/review workbench is implemented; model content quality remains unaccepted after actual local4B evaluation. Documented education has three authored lessons and six deterministic self-check questions without a model dependency. Generative tutoring, learner progress, autonomous external research, campaigns/channels and accounting remain separate future work; see INTERNAL_AGENTS.md and AGENT_READINESS.md.
