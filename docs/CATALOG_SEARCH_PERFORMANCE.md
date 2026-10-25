# Catalog dimension query measurements

This is a reproducible, opt-in PostgreSQL experiment with synthetic data, not a production
latency promise. It exercises the same catalog_search predicates as the product endpoint,
but excludes HTTP, authentication, source-name hydration, response serialization, assistant
inference and price retrieval. It is a single-client warm-cache run without concurrent load.

## Reproduce

Use a separate local PostgreSQL database named with the suffix `_benchmark`, containing
no organizations. Apply the normal Alembic migrations to it first. Do not point the tool
at a business database or run destructive integration/browser fixtures against it.
From the repository root, with DATABASE_URL set to that database:

```sh
PYTHONPATH=apps/api .venv/bin/python apps/api/tests/benchmark_catalog_search.py \
  --rows-per-org 5000 --repeats 10 --output /tmp/catalog-query-benchmark.json
```

The tool seeds two organizations with5000 products each, distributed across mm/cm/m
categories with canonical Decimal attribute strings, unique lengths, and some inactive rows.
It runs exact, inclusive mixed-unit and empty-interior filters. Each measurement includes a
count plus a deterministic five-row page, with assertions for expected count, page size and
tenant identity. EXPLAIN ANALYZE/BUFFERS JSON plans accompany each query. It rejects another
database suffix or existing organizations, bounds seed/repeat sizes and imposes a15s SQL
statement timeout. A finally block rolls back all synthetic organizations/references/products;
post-rollback counts are verified. The database/schema itself remains available for reuse.
The benchmark is not collected by pytest or run in ordinary CI and has no timing pass/fail gate.

## Recorded experiment — 2026-10-24

Ten repeats per case,10000 total products,5000 in the queried organization. Values below
are combined count/page milliseconds; the JSON artifacts contain PostgreSQL version and
full plans. p95 with only ten samples is the maximum sample and is particularly noisy.

| Query | Baseline median / p95 | Selected CASE branch median / p95 |
| --- | --- | --- |
| Exact2mm |32.882 /45.220 |34.571 /46.133 |
| Inclusive2–3mm, lower bound0.2cm |190.272 /200.854 |173.702 /202.111 |
| Empty2.000001–2.999999mm |182.607 /194.002 |172.643 /192.291 |

A first attempt multiplied the stored quantity by a selected unit factor. It was slower
(263.692ms median for the inclusive case) and was discarded. Its artifact remains explicit
negative evidence. The selected implementation uses CASE to select one known unit before
checking bounds, retaining the nested regex-guarded numeric CASE and JSON string-type check.
There is no new index, schema, unit-conversion policy, financial arithmetic or infrastructure.

The observed medians improved modestly for ranges; inclusive p95 did not improve and exact
search was unchanged in code. These small sequential samples do not establish statistical
significance, production throughput or acceptable latency for a larger tenant. Tenant scans
remain possible. Query plans and representative larger/concurrent workloads should guide
any future indexed dimension projection; no such index is claimed here.

Evidence:

- [Baseline](evidence/catalog-query-baseline-2026-10-24.json)
- [Discarded normalization attempt](evidence/catalog-query-normalized-attempt-2026-10-24.json)
- [Selected branch implementation](evidence/catalog-query-benchmark-2026-10-24.json)

## Registered identifier search — baseline, 2026-10-25

The same opt-in tool now accepts --identifier-search. It seeds two identifiers (barcode and
vendor) per product with identical literal values containing %, _ and backslash; both tenants
have the same values. This adds direct name/SKU, identifier, missing-identifier and combined
identifier/range cases. The endpoint and benchmark share apply_text_search, so the experiment
uses the actual bound text predicate. All original dimension cases still run unchanged.

```sh
PYTHONPATH=apps/api .venv/bin/python apps/api/tests/benchmark_catalog_search.py \
  --rows-per-org 5000 --repeats 5 --identifier-search \
  --output /tmp/catalog-identifiers.json
```

This baseline used correlated EXISTS,10000 total products and20000 identifiers, with five
combined count/page samples per case. Median/p95 milliseconds: name199.787/700.045,
SKU222.238/238.641, literal identifier231.789/232.184, missing identifier221.519/222.720,
identifier plus2–3mm range635.917/653.403. Plans show a very high estimated outer cost and
substantial JIT compilation even for direct-name matches whose identifier subplan never ran.
PostgreSQL used a hashed identifier subplan, not one executed scan per product; no quadratic
execution claim is made. No PostgreSQL/JIT configuration was changed.

Count, five-row page size and tenant identity were asserted in every repetition, including
multiple aliases without count inflation. All synthetic organizations/products/identifiers
rolled back and absence was verified. This is query-only, single-client, small-sample evidence;
no API, concurrency or production SLO is measured. No new index is justified by this run.
Baseline plans: [catalog-identifiers-baseline-2026-10-25.json](evidence/catalog-identifiers-baseline-2026-10-25.json).
