# Architecture

Modular monolith: Next.js TypeScript frontend, FastAPI Python backend, PostgreSQL, object storage. APIs under `/api/v1`. Organization scoped access; future tenant isolation. Use UTC timestamps, decimal numeric types, immutable posted ledgers, explicit approval for sensitive actions. Agent tools never bypass domain services. Queue/workers optional in M1.
