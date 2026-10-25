# Local invoice intake — approved transcription scope

Founder approved local invoice OCR into an editable draft with human checking on2026-10-25.
This module records an **untrusted transcription**, not a sales draft, legal invoice, approved
price, stock movement, ownership transfer, journal or tax filing. It has no posting, export,
customer-send or conversion endpoint and no LLM/paid API. Human transcription review is not
financial approval. Existing IRR/two-place HALF_UP/exclusive-tax sales rules are unchanged.

## Implemented API

All routes use /api/v1/invoice-intakes and current organization membership. Admin/editor may
extract/edit/review transcription; viewer reads. Organization IDs cannot be supplied in fields.

- GET /status: native availability (tools plus fas/eng data), accepted media,5MiB,3-page limits.
- POST /extract: raw PNG/JPEG/PDF bytes with actual Content-Type and Idempotency-Key;201.
  The Persian browser workspace/proxy supports this bounded binary endpoint. Server/proxy bound upload
  bytes independently.415 unsupported type;413 over5MiB;422 empty/invalid/unsupported document;
  429 per-worker OCR saturation;503 missing native tools/data;504 processing deadline.
- GET collection: paginated summaries only, limit25,max100,offset; no large text/history blobs.
- GET /{id}: original extraction, corrected text, structured candidates, source SHA256/media,
  engine/page count, actor/timestamps/version and financial_approval=false/business_posted=false.
- PUT /{id}: expected_version, corrected_text≤100000 characters, fields, mark_reviewed=false.
  Idempotency-Key required.409 stale version; explicit true records a human transcription check.
  Subsequent ordinary editing returns status to draft. Review does not assert completeness,
  financial correctness, tax compliance, price approval or readiness for customer use.
- GET /{id}/revisions: paginated metadata; GET /{id}/revisions/{version}: immutable snapshot.

Opaque session/current membership is rechecked after native processing before any persistence.
No actor/DB locks are held through OCR. Mutations and replays use existing membership locks and
actor-scoped idempotency, with a second replay check after processing. Same file hash is unique
within an organization: another create key returns409; same actor/key/payload replays original
snapshot. Identical bytes in another organization are independent. Tenant lookups return404.

## Evidence, validation and retention

Migration0006_invoice_intake adds invoice_intakes and invoice_intake_revisions with UUIDs,
TIMESTAMPTZ, tenant composite FKs, source-hash uniqueness and version/status/page checks.
Triggers retain the source/hash/media/page/engine/raw text/original candidate evidence and
prevent header deletion, invalid version jumps and revision mutation/deletion. Each edit
creates a new immutable snapshot with audit/idempotency in the same transaction. Privileged
DB operators can bypass controls; this is not RLS or immutable external archive storage.

Original bytes and filenames are **not persisted**. A private temporary directory is removed
on success/error/timeout; the operator must retain the original outside this module. SHA256
identifies bytes but is not a digital signature. Raw/corrected text, source evidence, fields,
revisions and idempotent snapshots can contain sensitive invoice data and are retained without
an automatic deletion endpoint/job. No legal retention period is invented; reviewed retention,
backup/access policy and original-document archival remain operator/product decisions.
Audit contains actor/action/resource/time, never invoice text or money. Native diagnostics are
suppressed; API errors contain no file contents, paths, subprocess output or stack trace.

Fields include printed invoice number/date text, seller/buyer names, explicit currency,
subtotal/tax/grand total and up to100 transcription lines (description, quantity, unit, price,
line total). Dates printed on documents remain text: no guessed Jalali/UTC conversion.
Money is exact decimal strings with at most2 places; unit prices allow6 and quantities6 places.
Floats/booleans, extra fields and excessive precision are rejected. Nothing is automatically
recalculated, rounded, netted, currency-converted or compared with approved business prices.
Tax is transcribed as printed; the organization's internal10% default is not guessed onto OCR.

The deterministic labelled-v1 parser recognizes explicit colon-labelled Persian/English fields,
unique currency mentions and five-cell pipe-separated rows. Duplicate labels/ambiguous currency,
malformed grouping, unsupported precision or unrecognized tables leave fields empty/warned;
raw text remains available. It is not a general invoice/table-layout interpreter. Manually add
or correct rows/units. No automatic catalog/party matching or confidence score is claimed.

## Native runtime and bounded processing

Docker API installs free Tesseract, fas/eng language packages, Poppler and prlimit; Pillow13.0.0
is pinned. Host Debian/Ubuntu setup: install tesseract-ocr, tesseract-ocr-fas, tesseract-ocr-eng,
poppler-utils and util-linux, then pip install the pinned requirements. Verify tesseract
--list-langs includes fas and eng. No OCR model/data is downloaded by an API request.

Only PNG/JPEG single-frame images up to12MP and unencrypted PDFs of1–3 pages are accepted.
PDF embedded text is used when≥20 characters; otherwise Poppler rasterizes each page to≤2400px
and Tesseract eng+fas reads it. Embedded text can also be wrong/untrusted. No original filename,
shell command, URL, custom engine/model or executable path is supplied by the client.
Native processing has a30s overall deadline,2 active slots per API worker,512MiB address-space,
15 CPU-second and20MiB per-output-file process limits. Extracted text≤100000 characters.
prlimit/start timeouts bound local commands; this is not a hardened hostile-file sandbox or a
claim of production upload security. Keep OS/native decoder packages patched and apply
production edge/request limits before any deployment. Cancellation waits for bounded native
processing so a slot is not released while its command still runs.

## Actual synthetic evaluation and known numeric risk

Native tests exercise real PNG, scanned PDF, embedded-text PDF and corrupt/type-mismatched/
4-page rejection. Other API tests replace only OCR text to test deterministic scope/history/
revocation/permission/error behavior. CI installs native tools; no OCR provider mock is used
for native tests. The broader optional sales assistant's existing fixture remains separate.

A three-case synthetic local evaluation is recorded in
[evidence/local-invoice-ocr-2026-10-25.json](evidence/local-invoice-ocr-2026-10-25.json).
English PNG/scanned PDF matched the checked number/total. Persian names/number were read,
but the Persian decimal separator in1234.56 was dropped and the proposed total became123456.
This failure is deliberately retained; no guessed numeric repair was added. An earlier English
fas+eng order read12345 as5; eng+fas corrected that fixture. These tiny samples do not establish
general Persian, table, financial or production accuracy. **Always compare every number and
separator with the original document before recording a human transcription check.**

Reproduce (disposable *_test DB for integration tests, native language data installed):

```sh
DATABASE_URL=postgresql+psycopg://steelos:steelos@localhost:5432/steelos_test \
  PYTHONPATH=apps/api .venv/bin/pytest -q apps/api/tests/test_invoice_intake.py
PYTHONPATH=apps/api .venv/bin/python apps/api/tests/evaluate_invoice_ocr.py
```

The local executor lacked root/apt indexes; for this test only, official tessdata_fast4.1.0
fas.traineddata was placed in a temporary TESSDATA_PREFIX alongside the existing eng data.
SHA256:db1c0a91208aff00d3cf1ed2c1d23f76419afd5f024688b4f71adc3f2ce4a505.
Nothing was committed from model/language binaries. Docker/CI use OS packages instead.

Native command environments are allowlisted; database/proxy/auth secrets are not inherited.
Working/home/temp/cache directories point to the private temporary workspace during processing.
Native readiness uses the same environment restriction. These controls do not turn native
parsers into a hardened hostile-file sandbox; OS/package maintenance remains necessary.

## Persian workspace (implemented)

The authenticated dashboard page uses the actual API for bounded file upload, text/field/row
correction, explicit human-transcription checkbox, paginated lists/history and read-only old
versions. Normal edits invalidate the current transcription-review state. User-entered Persian/
Arabic digits remain strings and normalize before submission. A successful image upload can
show the original local image only while its hash matches the selected intake; Blob URLs are
revoked on file change/unmount. PDFs are not embedded as active browser content. Original
bytes stay out of browser storage/server persistence; the user retains the original.

The same-origin proxy forwards raw bytes only to invoice-intakes/extract, caps streaming bytes
independently and gives bounded native processing45s; ordinary JSON routes retain15s. It keeps
the HttpOnly credential/CSRF checks and no-store responses. CSP adds blob: only to img-src for
local image preview; script/frame/connect policies are unchanged. Desktop/mobile browser tests
exercise real PDF text extraction, actual PNG OCR/preview, Persian monetary corrections, human
check/edit invalidation, immutable historical view, duplicate/oversize/origin rejection and
unchanged stock/price/sales counts. Earlier browser selector failures led to explicit accessible
labels for the currency/text controls; the final workflows passed on both viewports.

Compose bounds the API's volatile /tmp workspace to128MiB with nosuid/nodev/noexec. The
non-root native pipeline was verified with the same tmpfs options in a network-disabled
container. A local executor check without tmpfs failed from an almost-full container root
filesystem; that failed attempt is not success evidence. No PostgreSQL volume was pruned.
Temporary-storage/native I/O failures return a sanitized retryable503 and create no intake;
an injected full-disk regression checks that private paths do not escape in the error.
