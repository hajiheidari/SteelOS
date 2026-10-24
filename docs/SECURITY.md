# Security — implemented and pending controls

## Implemented M1

- Argon2id passwords; minimum 12 characters for new passwords; maximum 128. No public signup.
- Opaque 48-byte random session tokens, SHA-256 digest at rest, bounded expiry, single-use
  refresh rotation, logout revocation, all-session revocation on password change.
- Membership checked on every request; role changes effective immediately. Organization
  selected at login only after credentials and membership verification.
- Fixed permission matrix: viewer reads; editor reads and writes business data; admin also
  manages catalog definitions, warehouses/grants, pricing sources, price decisions, settings,
  users, audit access and master-data deletion. Warehouse reads/location writes additionally
  require explicit grant for non-admins. Managers have all warehouse access in their tenant.
- Tenant-scoped queries and composite foreign keys. Client organization_id rejected by
  domain input schemas. No cross-tenant lookup grants access.
- Persistent per-normalized-email login throttling: 10 failed attempts in a 15-minute window;
  row locking applies across workers. Generic credential errors avoid email enumeration.
- API errors exclude stack traces, SQL, secrets and rejected input values. Structured logs
  contain generated request ID, method, result and timing, without bodies/query strings/PII.
- Business writes and auth success/settings events audit in the same DB transaction.
- Server-side frontend proxy: HttpOnly, SameSite Strict, Secure in production cookie;
  browser never receives bearer token JSON. Exact configured origin required for mutations.
  Backend accepts bearer only, so no cookie CSRF on direct API routes.
- Loopback local ports, explicit CORS origins, no committed environment secrets. Next security
  headers include frame denial and CSP. Dev-only unsafe-eval supports React tooling; production
  CSP allows inline Next.js scripts/styles (nonce CSP remains a hardening opportunity).

## Operational limits and future work

No public deployment authorized. Before production: TLS/host/origin configuration, backup and
restore drills, database least privilege, audit export/immutable storage, proxy rate limiting,
monitoring, recovery process, penetration review and password recovery policy. Login throttling
can be abused to temporarily lock a known email; stronger edge controls/MFA can follow real needs.
No uploads, paid AI, external scraping, email messaging, tax filing or automatic financial posting.
No RLS policy is claimed: tenant isolation uses domain authorization plus composite FKs.
Database operators remain privileged; API audit history has no write endpoints but DB superusers
can modify tables. Role grants and source approval require authenticated administrators.

Future agents must use controlled APIs with explicit policy/audit and approvals for sensitive
stock ownership, approved pricing, accounting and tax actions; no direct database access.

Organization administration (enrollment, removal, role changes and organization settings)
is serialized with a PostgreSQL organization-row `FOR NO KEY UPDATE` lock. The actor's
membership role is queried again after acquiring the lock, because authorization checked
before waiting may have become stale. Combined with rejecting self-demotion/removal, this
prevents two concurrent admins from removing/demoting each other and leaving no admin.
The lock permits normal foreign-key key-share locks; it does not serialize unrelated tenants.

Browser session lifecycle: failed current-password verification is a 400 input error and does
not clear an otherwise valid cookie. Actual 401 responses from authenticated requests trigger
a full navigation to login, discarding tenant data, outstanding UI work and form secrets in the
old document. Logout/password-change success deletes the HttpOnly cookie and navigates to a
fresh document; no follow-up workspace load is issued after these actions. No business form
payload or password is stored in browser storage to restore it after logout.

Every domain create/update/delete and price decision locks the actor's membership row for
its transaction, refreshes the current role, and rechecks permission after waiting. Removed
memberships return 401; demoted actors return 403. Idempotency replays are checked under the
same current authorization before returning a stored result. The lock also serializes retries
for the same actor. Different actors/organizations remain independent except for domain locks
such as the category-rule invariant. Identity administration retains its organization-lock order.

## Approved warehouse operations extension

See [INVENTORY.md](INVENTORY.md) for the implemented M2 API, immutable ledger,
role/warehouse policy, concurrency rules, migration `0002_inventory` and test coverage.
M1 historical boundaries describe the foundation before this approved extension.

### Warehouse grant checks and cached creation responses

Warehouse-scoped mutations hold a shared lock on the actor's grant through commit;
revocation that acquires its row first is awaited and denied after recheck. Grant revocation
waits for a write that already acquired permission. Idempotency responses carry no authority:
location creation replay must still resolve the existing record through current warehouse
scope and hold the grant. Inventory draft replay likewise revalidates warehouse scope.
Restoring access allows the same idempotency key to return its original result without
creating another record. Requests denied for revoked scope do not create audit/domain rows.

### CI action dependencies

Workflow actions are pinned to verified commit SHAs of official `actions/*` releases,
with a version comment for review. Their internal runtime is Node 24; application CI
still uses Python 3.12 and Node 22. Checkout does not persist credentials, and workflow
permissions remain `contents: read`. Update pins deliberately against official release
metadata and validate with the full CI workflow. No deployment or publishing job exists.

### Internal sales drafts

Sales drafts authorize current membership before every write/replay. Shared locks stabilize
customer eligibility, product activity and approved price/source checks; concurrent master
revocation that wins the row lock causes409 and leaves no partial draft/revision/audit/
idempotency result. Revision and cancellation guards preserve history in PostgreSQL.
Clients provide price IDs, decimal quantities and an optional validated tax percentage;
prices, base/tax amounts and totals are always derived server-side.
Historical and cached price checks carry their original as-of timestamp; fresh GET rechecks
current eligibility. Financial approval is always false and there is no customer issuance,
stock/accounting posting or external-send endpoint in this stage.

Organization tax-default updates use the existing serialized administrator lock and
post-lock authority recheck, plus expected_version to reject stale writes. Members cannot
supply another organization ID. Concurrent policy edits yield one200/one409; viewer writes
are403. Draft rates/rounding policies are version-specific snapshots; changing defaults
never changes historical amounts. Tax-inclusive prices are rejected to prevent double tax.
Two-place HALF_UP calculations use Decimal/SQL NUMERIC, never binary floating point.

Internal sales reviews are administrator-only with current membership locking/recheck,
expected-version validation and a draft-row lock. Acceptance revalidates price/customer/source/
product under shared locks and checks expiry again before saving evidence. Review snapshots
are append-only with tenant/version FKs and a current-draft PostgreSQL trigger; audit and
idempotency share the transaction. Accepted internal review is not financial approval and
cannot issue/send a quotation. There is no implemented agent identity/runtime yet; see
AGENT_READINESS.md. Do not give future agents human administrator session tokens.

The optional sales assistant has a fixed read-only tool registry and no model-executable HTTP
or SQL interface. Local Ollama URLs/model are server-configured/validated; no paid provider,
public endpoint URL, redirects, arbitrary model name or API keys are supported. Only question
text and a static extraction schema reach the model, never token/tenant/domain results. The
user's token remains in server-side domain API calls; current session is checked on every read
and finally before returning results, including revocation during inference. Only catalog and
approved/current price fields are projected; no CRM contacts, warehouse balances or journals.
One extraction call, bounded tokens/response/time/data calls, concurrency2 per worker; no
unbounded loops or automatic model pulls. Read-only is enforced structurally even for an
administrator's user session. No separate agent principal or background agent exists yet.
Queries/answers are not persisted in audits; HTTP-client URL INFO and raw Uvicorn access
logs are suppressed in favor of structured request metadata.
Local model debug request logging must remain disabled for business data. CI's loopback-only
mock provider refuses non-_test databases and is not application inference. See SALES_ASSISTANT.md.

Assistant numeric dimension constraints are extracted/validated by deterministic code before
inference; model omission cannot relax them. Typed filters pass only through the controlled
product API, scoped before filtering/count/pagination. Up to8 Code attributes, bounded JSON,
Decimal/units and duplicate-key checks; all values are SQLAlchemy JSONB bind data, never SQL
identifiers/expressions. Exact-match canonical alternatives avoid numeric casts. Range comparisons put numeric casts inside CASE guarded by a bounded decimal regex, and require JSON string values; malformed/oversized JSON values cannot trigger a cast failure.
Ambiguity yields no data reads/model call; no-match never broadens criteria. A model-generated
query not copied from the question is rejected with a generic provider error. UI renders original
attribute/price evidence as escaped text. No new mutable permissions, external service or model
access to tokens/domain data was introduced.

Unsupported comparison/approximation/negation markers on named dimensions stop inference
and domain retrieval. Regressions specifically cover missing-unit comparisons and negated
exact/range constraints, which previously could lose or invert the user's numeric intent.
This guard does not authorize or implement open/exclusive comparison operators.
