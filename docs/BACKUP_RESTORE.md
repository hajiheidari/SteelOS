# Synthetic PostgreSQL backup/restore drill

Implemented development/CI verification uses the real PostgreSQL17 pg_dump custom format and
pg_restore in the explicitly selected local test service container. It is not an operational
backup tool: never point this command at business data, even if a database is named *_test.
The world fixture truncates its disposable source and seeds only synthetic data through APIs.

Run after migrations, without any other backend/browser run sharing the database:

```sh
POSTGRES_TEST_CONTAINER=<local-test-container-name-or-id> \
DATABASE_URL=postgresql+psycopg://steelos:steelos@localhost:5432/steelos_test \
PYTHONPATH=apps/api .venv/bin/pytest -q apps/api/tests/test_backup_restore.py
```

The role needs CREATEDB and pg_control_system access on the disposable test cluster. CI
supplies its own PostgreSQL service ID; local Docker socket is selected explicitly, ignoring
remote daemon/context selectors. No Docker image is pulled or service provisioned by this test.
The container system identifier must equal DATABASE_URL's cluster before archive/restore work.
A random restore database is exclusively created; an existing database is never cleaned or
reused. Four negative regressions reject ordinary/unsafe source names. Without the explicit
container variable, the real drill is skipped locally; CI always supplies it.

The fixture covers two organizations/users/memberships/sessions; Persian catalog/parties and
JSON attributes; ownership-aware posted stock receipt/ledger; exact six-place pricing;
internal sales snapshot/revision; manual CRM due dates and invoice transcription/revision.
The OCR fixture is labelled synthetic; this test measures database recovery, not OCR accuracy.

The test compares every model table's rows, table/column types and numeric precision/scale,
nullability, indexes, FK/unique definitions, constraint metadata and trigger definitions.
CHECK expressions may deparse with equivalent cast syntax after pg_restore, so their textual
spelling is not treated as an invariant. Representative invalid tax/status/ownership/price
writes, cross-tenant FK insertion and ledger/sales/invoice-history mutations must actually fail
on the restored database. Restored tokens read through the real API, including foreign-tenant
404 and exact sales amounts. Alembic revision is checked and the source stays unchanged.

The archive is synthetic, mode0600, stays in pytest's private temporary directory and is deleted
in cleanup, including failure paths. It is never uploaded as a CI artifact. The restored DB is
dropped after connections close; failure to clean up fails the test. pg_dump/pg_restore have
60-second deadlines; restore uses one transaction and exits on error. No --clean or --create is
accepted. --no-owner/--no-acl intentionally exclude role/ACL recovery from this rehearsal.

## Remaining production work

No scheduled backup, encryption/key lifecycle, off-host storage, WAL/PITR, retention, monitoring,
production restore automation, role/grant recovery, RPO/RTO or disaster-recovery certification is
implemented by this drill. Dumps containing real data would include sensitive text/session hashes;
they require separately approved storage/access/retention policy. Native invoice originals are
not archived by SteelOS and cannot be recovered from its database. Production recovery needs
business acceptance, infrastructure-specific policies and repeatable exercises on approved data.

Failure-path coverage also runs real pg_restore against an intentionally corrupted synthetic
archive and verifies nonzero failure, archive/destination cleanup and unchanged source rows.
A separately injected mismatched cluster identifier must stop before dump or DB creation.
These are failure regressions, not an exercise of production failover or mid-transaction outage.
