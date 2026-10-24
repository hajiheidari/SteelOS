# Read-only local sales assistant

Implemented: a Persian question becomes a validated product search term/currency through
one local-model call. A fixed registry reads the current user's organization catalog and
approved, valid prices through existing domain APIs. The UI shows source cards, not free-form
model claims. This is a limited interactive search assistant, not an autonomous sales closer,
financial approver, research agent or messaging integration.

## Local setup (optional and free)

Default ASSISTANT_PROVIDER=disabled keeps clean M1 setup/CI independent of model software.
The Persian page explains when no model is configured. No paid provider/key is supported.
The optional Compose profile uses a pinned Ollama0.40.10 image, CPU2/memory4GiB, one loaded
model and parallel inference1. Model downloads need approximately1.4GB in addition to the
Docker image (about5GB); allow sufficient local disk/RAM. Nothing is published publicly.

From the repository root after the ordinary local setup:

```sh
docker compose --profile assistant-local up -d ollama
docker compose exec -e OLLAMA_HOST=http://127.0.0.1:11434 ollama ollama pull qwen3:1.7b
ASSISTANT_PROVIDER=ollama docker compose up -d --build api
```

For a host Python API using an already running local Ollama:

```sh
ASSISTANT_PROVIDER=ollama ASSISTANT_OLLAMA_URL=http://127.0.0.1:11434 \
  uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000
```

Compose uses http://ollama:11434 internally; host Python defaults to127.0.0.1:11434.
Only local HTTP hosts are accepted (loopback, ollama, host.docker.internal), without userinfo,
path, query or fragment; redirects are disabled. Model selection is restricted to qwen3:1.7b
in this first version. Cloud features are disabled on the optional Ollama service. API requests
never install/download models or activate services. A missing/invalid provider returns503.
A TLS-inspecting development proxy may require a read-only CA mount and SSL_CERT_FILE on
the model container. Keep TLS verification enabled; do not commit session certificates.

[Qwen3-1.7B model card](https://huggingface.co/Qwen/Qwen3-1.7B) declares Apache-2.0.
Weights are not committed/redistributed in this repository. Tested Ollama model manifest:
8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7 (Q4_K_M).
Tags can change: verify installed digest and rerun evaluation when updating weights/runtime.

## Request and evidence contract

Authenticated GET /api/v1/sales-assistant/status returns configured/provider/model,
availability=unchecked|disabled, fixed tool names, read_only=true, financial_approval=false.
Configured is a configuration flag, not proof that the model is installed/healthy.

POST /api/v1/sales-assistant/query accepts only {question:string,2–1000 characters}.
Model planning returns only product_query (≤120 chars or null) and explicit currency
IRR/IRT/USD/EUR (defaultIRR); extra keys/invalid responses are rejected. Model never receives
session credentials, organization IDs, domain results, contacts, history or pricing facts.
User-entered question text is processed locally. There is no conversation memory.

The fixed tool registry supports only:

- catalog.search: GET products, active=true, literal q, limit5,offset0.
- prices.current: GET price-observations for each returned product, approved_only=true,
  selected currency, observed_at descending, limit5,offset0.

At most one model call, six domain-data calls and a final GET auth/me recheck per request;
at most two concurrent requests per API worker,45-second total model deadline (plus HTTP timeouts),256 predicted
tokens, context2048 and provider response≤64KiB. Saturation returns429. The model cannot
choose HTTP methods, paths, tenants, IDs or page limits. Session authorization is rechecked
by every nested domain request and before returning results, including revocation during
model inference. Reads use the existing controlled APIs rather than model/database access.

Results include products, exact source amount strings, currency/unit, source name/ID,
provenance, observation/expiry timestamps, delivery and tax-inclusion indicators. Search
and price totals show when results were truncated to5. Unsupported intent returns no domain
results. No price/FX/quantity/tax/quotation calculation is performed by the model.
retrieval_started_at/finished_at describe the read interval, not an atomic market snapshot
or guarantee of continued validity. Current price rules must be rechecked before draft use.

No tool can create/update/review/approve a draft, post inventory/accounting, alter prices or
send messages. financial_approval is always false. Internal reads act with a bounded delegation
of the authenticated user's session; no separate agent credentials/admin service account or
background worker is provisioned. Token stays in the API/domain transport, never in the model.
Successful reads add an assistant_query audit event with actor/org, not question/answer text.
Application HTTP-client INFO URL and raw Uvicorn access logs are disabled; structured
request events omit search text.
Keep model prompt/request debug logging off for business data.

## Validation and limits

Default automated tests mock only model extraction and exercise actual PostgreSQL/domain
APIs. CI browser tests use a disposable local HTTP provider fixture guarded by a _test database;
this fixture is explicitly not an AI model and is not used for product results. No model
weights, downloads, paid endpoints or external API secrets are required by CI.

Opt-in actual local-model tests (disposable database; do not run alongside browser tests):

```sh
DATABASE_URL=postgresql+psycopg://steelos:steelos@localhost:5432/steelos_test \
  STEELOS_TEST_LOCAL_MODEL=1 PYTHONPATH=apps/api \
  python -m pytest -q apps/api/tests/test_sales_assistant.py
PYTHONPATH=apps/api python apps/api/tests/evaluate_local_assistant.py
```

On the tested CPU environment, all7 synthetic Persian extraction cases matched (steel terms,
USD/IRT, unrelated greeting and request to approve/send invoices). Cold inference5.33s,
warm1.13–1.48s. An actual-model API integration test returned the exact approved DB price
123456.123456 for the correct tenant. Raw synthetic evidence: [local-assistant-2026-10-24.json](evidence/local-assistant-2026-10-24.json).
These small tests establish connectivity/basic extraction,
not broad Persian accuracy, production load capacity or immunity to misinterpreted intent.
Read-only hard limits still apply even if a model produces a misleading search term.

Pending: ranges and broader natural-language dimension grammar, broader quality/abuse evaluation, organization-specific
operating limits, optional citation-based prose, agent service-principal lifecycle if needed,
and separately authorized proposal/write workflows. OCR/research/marketing/channel agents
are not implemented. No production deployment is included.

## Exact technical dimensions (implemented)

The server extracts explicit named linear dimensions before model inference: thickness/ضخامت,
width/عرض, length/طول, diameter/قطر and height/ارتفاع. Supported syntax is a name followed
by a positive decimal number and mm/cm/m (also میلیمتر/میلی‌متر, سانتیمتر, متر), with optional
colon/equal separator. Persian/Arabic digits and valid Persian grouping/decimal separators
are normalized exactly. The remaining product-name question goes to the model; numeric
constraints never depend on a model retaining or reconstructing them.

The public product API accepts an optional attributes JSON query (≤4096 characters), e.g.:
`{"thickness":{"value":"2","unit":"mm"},"width":{"value":"1.2","unit":"m"}}`.
At most8 extensible attribute keys, AND semantics, positive Decimal(20,6) values, no floats/
booleans/duplicate JSON keys. The generic catalog filter supports every valid catalog Code
key and the existing Dimension units, not only the five assistant names. mm/cm/m compare
exact physical equivalence; kg/none require the same unit. No tolerance/ranges, guessed
unit, price-unit conversion or inventory mutation occurs. Comparisons use canonical catalog
JSON strings and exact Decimal-derived alternatives, not unsafe casts of arbitrary JSON.
Wrong/absent attributes return no matches; filters are never dropped to produce an answer.
Other resource endpoints reject the attributes filter with422.

Unknown/missing units, repeated dimensions, unsupported ranges or number-word forms outside the finite grammar or bare
measurements without an attribute name yield needs_clarification=true and no product/price
reads or model call. This is a conservative explicit grammar, not a general natural-language
measurement parser. General questions about available dimensions without numeric constraints
are not turned into exact filters. Clarification responses do not establish a price/currency
selection. Valid responses include dimensions (user-derived filters) and needs_clarification;
the Persian UI displays understood constraints alongside the actual product attributes.

Model-generated product terms must copy a substring from the remaining question (case/space
normalization only); spelling changes, invented synonyms or translation produce a sanitized503,
not a different catalog lookup. Initial actual-model evaluation matched10/12 scenarios: two
misspelled ورق as وارق. Exact-copy enforcement and prompt examples corrected the evaluated
cases; the rerun matched12/12. Both initial/final synthetic artifacts are retained under
[evidence](evidence/local-assistant-dimensions-2026-10-24.json), alongside the initial artifact.
An opt-in actual-model API test also matches0.2cm against stored2mm and returns the exact
approved DB price. These results do not establish general language accuracy or production readiness.

### Persian number words

Named dimensions also accept یک through ده, نیم, and an integer from that set followed
by و نیم, including ZWNJ separators. For example ضخامت دو و نیم میلی‌متر becomes
exactly2.5mm before inference. Values are explicit Decimal constants; the model does not
interpret number words. Unsupported compound numbers (such as بیست or دو و سه), fractions
and ranges request clarification. Catalog API contracts remain decimal strings.
