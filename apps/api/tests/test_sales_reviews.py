"""Internal review is versioned evidence, never financial or customer issuance."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from app import models as m
from app.db import engine
from app.modules.sales import service
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_sales_drafts import create_draft
from test_sales_drafts import sales as sales_fixture

sales = sales_fixture


def review(env, draft, *, decision="accepted", note="", token=0, key=None, version=None):
    client, tokens, *_ = env
    return client.post(
        f"/api/v1/sales-drafts/{draft['id']}/review",
        headers={**tokens[token], "Idempotency-Key": key or str(uuid4())},
        json={"expected_version": version or draft["version"], "decision": decision, "note": note},
    )


def test_review_scope_permissions_replay_version_and_immutable_evidence(sales):
    client, tokens, orgs, users, *_, payload = sales
    draft = create_draft(sales)
    assert review(sales, draft, token=2).status_code == 403
    assert (
        client.put(
            f"/api/v1/organization/members/{users[2]}",
            headers=tokens[0],
            json={"role": "editor"},
        ).status_code
        == 200
    )
    assert review(sales, draft, token=2).status_code == 403
    assert review(sales, draft, token=1).status_code == 404
    response = review(sales, draft, key="review-once", note="بازبینی داخلی")
    assert response.status_code == 201, response.text
    accepted = response.json()
    assert accepted["snapshot"]["grand_total"] == "288307.09"
    assert accepted["reviewer_id"] == users[0]
    assert accepted["financial_approval"] is False
    assert review(sales, draft, key="review-once", note="بازبینی داخلی").json() == accepted
    assert review(sales, draft, key="review-once", note="different").status_code == 409
    assert review(sales, draft).status_code == 409
    read = client.get(f"/api/v1/sales-drafts/{draft['id']}", headers=tokens[0]).json()
    assert read["internal_review"]["id"] == accepted["id"]
    assert read["internal_review_usable"] is True
    assert read["financial_approval"] is False
    listed = client.get("/api/v1/sales-drafts", headers=tokens[0]).json()["items"][0]
    assert listed["internal_review"] == read["internal_review"]
    assert "snapshot" not in listed["internal_review"]
    for suffix in ("reviews", f"reviews/{accepted['id']}"):
        assert (
            client.get(
                f"/api/v1/sales-drafts/{draft['id']}/{suffix}", headers=tokens[1]
            ).status_code
            == 404
        )
    changed = client.put(
        f"/api/v1/sales-drafts/{draft['id']}",
        headers={**tokens[0], "Idempotency-Key": str(uuid4())},
        json={**payload, "expected_version": 1, "note": "نسخهٔ تازه"},
    )
    assert changed.status_code == 200, changed.text
    newer = changed.json()
    assert newer["internal_review"] is None and newer["internal_review_usable"] is False
    assert review(sales, draft).status_code == 409
    assert review(sales, newer, decision="rejected", note=" ").status_code == 422
    rejected = review(sales, newer, decision="rejected", note="اصلاح شرایط تحویل")
    assert rejected.status_code == 201, rejected.text
    history = client.get(
        f"/api/v1/sales-drafts/{draft['id']}/reviews?limit=1", headers=tokens[0]
    ).json()
    assert history["total"] == 2 and len(history["items"]) == 1
    assert history["items"][0]["decision"] == "rejected"
    evidence = client.get(
        f"/api/v1/sales-drafts/{draft['id']}/reviews/{accepted['id']}", headers=tokens[0]
    ).json()
    assert evidence["snapshot"] == accepted["snapshot"]
    with Session(engine()) as db:
        for sql in (
            "UPDATE sales_draft_reviews SET note='changed' WHERE id=:id",
            "DELETE FROM sales_draft_reviews WHERE id=:id",
        ):
            with pytest.raises(IntegrityError):
                db.execute(text(sql), {"id": accepted["id"]})
                db.commit()
            db.rollback()
        assert db.scalar(select(func.count()).select_from(m.StockEntry)) == 0
        assert (
            db.scalar(
                select(func.count())
                .select_from(m.AuditEvent)
                .where(
                    m.AuditEvent.organization_id == orgs[0],
                    m.AuditEvent.action.in_(["review_accepted", "review_rejected"]),
                )
            )
            == 2
        )


def test_review_rechecks_current_validity_and_rejection_can_record_invalid_prices(
    sales, monkeypatch
):
    client, tokens, *_, payload = sales
    draft = create_draft(sales)
    accepted = review(sales, draft)
    assert accepted.status_code == 201
    real_now = service.now
    monkeypatch.setattr(service, "now", lambda db: real_now(db) + timedelta(days=1))
    read = client.get(f"/api/v1/sales-drafts/{draft['id']}", headers=tokens[0]).json()
    assert read["internal_review"]["decision"] == "accepted"
    assert not read["internal_review_usable"] and not read["prices_usable"]
    monkeypatch.setattr(service, "now", real_now)
    second = create_draft(sales, {**payload, "code": "EXPIRED-REVIEW"})
    monkeypatch.setattr(service, "now", lambda db: real_now(db) + timedelta(days=1))
    assert review(sales, second).status_code == 409
    assert review(sales, second, decision="rejected", note="قیمت منقضی است").status_code == 201
    response = client.post(
        f"/api/v1/sales-drafts/{second['id']}/cancel",
        headers={**tokens[0], "Idempotency-Key": str(uuid4())},
        json={"expected_version": 1},
    )
    assert response.status_code == 200
    assert review(sales, response.json()).status_code == 409
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(m.SalesDraftReview)) == 2
        assert (
            db.scalar(
                select(func.count())
                .select_from(m.AuditEvent)
                .where(
                    m.AuditEvent.action == "review_accepted",
                )
            )
            == 1
        )


def test_review_rejects_non_irr_or_legacy_unconfigured_policy(sales):
    client, tokens, orgs, users, *_, payload = sales
    # Simulated legacy/non-domestic headers are rejected before accepting any monetary snapshot.
    with Session(engine()) as db:
        ids = []
        for currency, rate, rounding in (("USD", "10", "half_up_2"), ("IRR", None, None)):
            draft = m.SalesDraft(
                organization_id=UUID(orgs[0]),
                customer_id=UUID(payload["customer_id"]),
                code=f"POLICY-{currency}",
                currency=currency,
                created_by=UUID(users[0]),
                updated_by=UUID(users[0]),
                tax_rate_percent=rate,
                amount_rounding=rounding,
            )
            db.add(draft)
            db.flush()
            ids.append(str(draft.id))
        db.commit()
    for draft_id in ids:
        assert review(sales, {"id": draft_id, "version": 1}).status_code == 409


def test_concurrent_review_decisions_have_one_winner_and_no_orphan_audit(sales):
    client, tokens, _, users, *_ = sales
    assert (
        client.put(
            f"/api/v1/organization/members/{users[2]}",
            headers=tokens[0],
            json={"role": "admin"},
        ).status_code
        == 200
    )
    draft = create_draft(sales)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda index: review(sales, draft, token=index).status_code, [0, 2])
        )
    assert sorted(results) == [201, 409]
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(m.SalesDraftReview)) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(m.AuditEvent)
                .where(
                    m.AuditEvent.action == "review_accepted",
                )
            )
            == 1
        )


def test_review_expiring_during_snapshot_is_not_accepted(sales, monkeypatch):
    draft = create_draft(sales)
    with Session(engine()) as db:
        at = service.now(db)
    checks = iter((at, at + timedelta(days=1)))
    monkeypatch.setattr(service, "now", lambda db: next(checks))
    response = review(sales, draft, key="last-second")
    assert response.status_code == 409, response.text
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(m.SalesDraftReview)) == 0
        assert (
            db.scalar(
                select(func.count())
                .select_from(m.IdempotencyRecord)
                .where(
                    m.IdempotencyRecord.key == "last-second",
                )
            )
            == 0
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(m.AuditEvent)
                .where(
                    m.AuditEvent.action == "review_accepted",
                )
            )
            == 0
        )
