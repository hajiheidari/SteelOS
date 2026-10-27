# Manual CRM follow-ups

The founder deferred unavailable invoice examples and asked to proceed with the next independent
stage. This limited CRM extension tracks internal human follow-up work against existing customer/
supplier parties. It never places calls, sends messages, schedules external workers, changes prices,
posts financial/stock records or adds AI tools. Deferred founder inputs are in FOUNDER_INPUTS.md.

## Implemented contract

/api/v1/crm-follow-ups uses the existing authenticated resource API: POST requires an actor-scoped
Idempotency-Key; GET collection/detail, full PUT and administrator-only DELETE. Admin/editor write,
viewer read, current membership rechecked/locked on writes and replay. Inputs: party_id, name≤200,
kind=call|meeting|document|other (default call), due_at with timezone, status=open|completed|cancelled
(default open), notes≤1000. Dates normalize to UTC; unknown fields/client organization IDs are rejected.

Lists support pagination (25/default,100/max), literal q in subject/notes, party_id/status/kind and
sort=due_at with asc/desc. overdue_only=true requires status open and due_at<current UTC, combined
with other filters using AND before count/page. Other resources reject overdue_only=true. It is a
live read projection, not a notification, delivery guarantee or background reminder job.

Migration0007_crm_follow_ups adds tenant FK and composite party FK, enum checks and organization/
due indexes. New/reassigned follow-ups require an active same-tenant party under shared master lock.
Existing records remain readable and may be completed/cancelled after that party is deactivated.
Referenced parties cannot be deleted while follow-ups exist. Admin may delete a follow-up under
existing resource policy; metadata audit remains. This is not an immutable interaction ledger:
ordinary edits use the existing full-replacement/last-committed-write semantics, with no version
conflict/history snapshot contract. Completed/cancelled records may be manually corrected/reopened.

The Persian RTL page uses real paginated/searchable APIs and active-party selectors, due-order
listing, status/overdue filters and ordinary forms. The datetime form is explicitly device-local,
converted to UTC on submission and converted back locally when editing; table dates display through
existing Persian/Jalali Intl formatting. No browser storage, new service/dependency or outbound
integration is introduced. Audit stores actor/action/resource/time, not notes/contact contents.

## Coverage and boundaries

API tests cover replay/conflict, view/write/delete roles, cross-tenant CRUD/FKs, UTC conversion,
pagination/labels/literal wildcard search, overdue excluding future/completed records, inactive-party
rules, validation and unchanged financial/stock tables. Desktop/mobile browser coverage checks real
party selection, creation, due-time roundtrip in Asia/Tehran, completion and overdue disappearance.
This is a shared organization task list, not individual assignment, CRM automation or financial approval.

The dashboard additionally reads the actual tenant overdue count through limit=1 plus
 overdue_only=true. Its card opens the follow-up page with that filter already selected;
it does not run notifications or mutate tasks. Browser coverage checks this navigation with
a real overdue record and then its disappearance after completion.

Timezone conversion outside the supported UTC datetime range returns422 before writes;
rejected inputs do not consume an idempotency key.

The follow-up page now combines the existing status/overdue filter with an optional
party_id filter. Its server-searched25-item party picker includes inactive parties so
historical follow-ups remain discoverable. Selecting/clearing the party resets the list
offset; navigation clears the filter, and its ID participates in stale-response guards.
It does not reassign tasks or change the active-party rule on creation.
