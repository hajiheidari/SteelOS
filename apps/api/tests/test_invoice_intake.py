import io
import json
from uuid import UUID

import pytest
from app import models as m
from app.db import engine
from app.modules.invoices import ocr
from app.modules.invoices.parser import propose
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

TEXT = "Invoice number: 12345\nDate: 2026-10-25\nSeller: Synthetic Steel\nBuyer: Synthetic Buyer\nIRR\nSubtotal: 246.90\nTax total: 24.69\nGrand total: 271.59\nSheet | 2 | kg | 123.45 | 246.90"


def upload(client, token, data=b"synthetic-file", key="invoice-upload", media="image/png"):
    return client.post(
        "/api/v1/invoice-intakes/extract",
        headers={**token, "Content-Type": media, "Idempotency-Key": key},
        content=data,
    )


@pytest.fixture
def intake(world, monkeypatch):
    client, tokens, *_ = world
    monkeypatch.setattr(ocr, "extract", lambda data, media: (TEXT, 1, "test-fixture"))
    result = upload(client, tokens[0])
    assert result.status_code == 201, result.text
    return result.json()


def test_invoice_transcription_versions_scope_replay_and_no_business_posting(world, intake):
    client, tokens, *_ = world
    assert intake["fields"]["grand_total"] == "271.59"
    assert intake["fields"]["lines"][0]["unit_price"] == "123.45"
    assert intake["financial_approval"] is False and intake["business_posted"] is False
    assert upload(client, tokens[0]).json() == intake
    assert upload(client, tokens[0], key="duplicate-file").status_code == 409
    assert upload(client, tokens[0], data=b"another", key="invoice-upload").status_code == 409
    assert upload(client, tokens[2], key="viewer").status_code == 403
    assert upload(client, tokens[1], key="other-org").status_code == 201
    path = "/api/v1/invoice-intakes/" + intake["id"]
    assert client.get(path, headers=tokens[1]).status_code == 404
    assert client.get(path, headers=tokens[2]).status_code == 200
    assert client.get(path + "/revisions/1", headers=tokens[1]).status_code == 404
    payload = {
        "expected_version": 1,
        "corrected_text": "Human correction",
        "fields": {**intake["fields"], "invoice_number": "Human-123"},
        "mark_reviewed": True,
    }
    headers = {**tokens[0], "Idempotency-Key": "human-review"}
    reviewed = client.put(path, headers=headers, json=payload)
    assert reviewed.status_code == 200, reviewed.text
    reviewed = reviewed.json()
    assert reviewed["version"] == 2 and reviewed["status"] == "reviewed"
    assert reviewed["raw_text"] == intake["raw_text"]
    assert reviewed["extraction"] == intake["extraction"]
    assert client.put(path, headers=headers, json=payload).json() == reviewed
    assert (
        client.put(
            path, headers={**tokens[0], "Idempotency-Key": "stale"}, json=payload
        ).status_code
        == 409
    )
    assert (
        client.put(
            path, headers={**tokens[2], "Idempotency-Key": "denied"}, json=payload
        ).status_code
        == 403
    )
    changed = client.put(
        path,
        headers={**tokens[0], "Idempotency-Key": "edit"},
        json={**payload, "expected_version": 2, "mark_reviewed": False},
    )
    assert changed.status_code == 200 and changed.json()["status"] == "draft"
    assert client.get(path + "/revisions/1", headers=tokens[0]).json() == intake
    assert client.get(path + "/revisions?limit=1", headers=tokens[0]).json()["total"] == 3
    with Session(engine()) as db:
        for model in (m.StockEntry, m.PriceObservation, m.SalesDraft):
            assert db.scalar(select(func.count()).select_from(model)) == 0
        assert (
            db.scalar(
                select(func.count())
                .select_from(m.AuditEvent)
                .where(m.AuditEvent.resource == "invoice-intakes")
            )
            == 4
        )


def test_invoice_database_guards(world, intake):
    _, _, orgs, _ = world
    with Session(engine()) as db:
        for statement in (
            "UPDATE invoice_intakes SET raw_text='rewritten',version=version+1 WHERE id=:id",
            "DELETE FROM invoice_intakes WHERE id=:id",
            "UPDATE invoice_intake_revisions SET snapshot='{}' WHERE intake_id=:id",
            "DELETE FROM invoice_intake_revisions WHERE intake_id=:id",
        ):
            with pytest.raises(IntegrityError):
                db.execute(text(statement), {"id": UUID(intake["id"])})
            db.rollback()
        with pytest.raises(IntegrityError):
            db.add(
                m.InvoiceIntakeRevision(
                    organization_id=UUID(orgs[1]),
                    intake_id=UUID(intake["id"]),
                    version=1,
                    actor_id=UUID(intake["created_by"]),
                    snapshot={},
                )
            )
            db.commit()
        db.rollback()


def test_invoice_upload_bounds_and_processing_failure_leave_no_records(world, monkeypatch):
    from fastapi import HTTPException

    client, tokens, *_ = world
    assert upload(client, tokens[0], media="text/html").status_code == 415
    assert upload(client, tokens[0], data=b"").status_code == 422
    assert upload(client, tokens[0], data=b"x" * (ocr.MAX_BYTES + 1)).status_code == 413

    def unavailable(*args):
        raise HTTPException(503, "Local OCR unavailable")

    monkeypatch.setattr(ocr, "extract", unavailable)
    assert upload(client, tokens[0]).status_code == 503
    with Session(engine()) as db:
        for model in (m.InvoiceIntake, m.InvoiceIntakeRevision, m.IdempotencyRecord):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_invoice_rechecks_revoked_session_after_ocr(world, monkeypatch):
    client, tokens, *_ = world

    def revoke(data, media):
        assert client.post("/api/v1/auth/logout", headers=tokens[0]).status_code == 200
        return TEXT, 1, "test-fixture"

    monkeypatch.setattr(ocr, "extract", revoke)
    assert upload(client, tokens[0]).status_code == 401
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(m.InvoiceIntake)) == 0


def test_invoice_parser_preserves_ambiguity_and_exact_persian_numbers():
    result = propose(
        "شماره فاکتور: ۱۲۳\nفروشنده: فولاد\nخریدار: آزمون\nمبلغ کل: ۱٬۲۳۴٫۵۶\nریال\nورق | ۲ | kg | ۱۲۳٫۴۵ | ۲۴۶٫۹۰"
    )
    assert result["fields"]["invoice_number"] == "۱۲۳"
    assert result["fields"]["grand_total"] == "1234.56"
    assert result["fields"]["lines"][0]["quantity"] == "2"
    ambiguous = propose("Seller: First\nSeller: Second\nSubtotal: 12,34\nIRR USD")
    assert ambiguous["fields"]["seller_name"] is None and ambiguous["fields"]["currency"] is None
    assert "ambiguous_seller_name" in ambiguous["warnings"]
    assert ambiguous["fields"]["subtotal"] is None
    assert propose("Grand total: 123.456")["fields"]["grand_total"] is None


def image_bytes(format="PNG", pages=1):
    image = Image.new("RGB", (1400, 850), "white")
    ImageDraw.Draw(image).multiline_text(
        (40, 40), TEXT, fill="black", font=ImageFont.load_default(size=32), spacing=16
    )
    output = io.BytesIO()
    if format == "PDF":
        image.save(output, format=format, save_all=True, append_images=[image] * (pages - 1))
    else:
        image.save(output, format=format)
    return output.getvalue()


def test_native_local_ocr_image_pdf_and_rejection():
    assert ocr.availability(), "Install native OCR tools with eng+fas data for this test"
    for format, media in (("PNG", "image/png"), ("PDF", "application/pdf")):
        raw, pages, provider = ocr.extract(image_bytes(format), media)
        assert pages == 1
        assert propose(raw)["fields"]["invoice_number"] == "12345", raw
        assert provider == "tesseract/eng+fas"
    from fastapi import HTTPException

    for data, media in (
        (b"invalid", "image/png"),
        (image_bytes(), "image/jpeg"),
        (image_bytes("PDF", pages=4), "application/pdf"),
    ):
        with pytest.raises(HTTPException) as rejected:
            ocr.extract(data, media)
        assert rejected.value.status_code == 422


def embedded_pdf(text_value):
    stream = f"BT /F1 18 Tf 40 750 Td ({text_value}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    document, positions = b"%PDF-1.4\n", []
    for index, body in enumerate(objects, 1):
        positions.append(len(document))
        document += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(document)
    document += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    document += b"".join(f"{position:010d} 00000 n \n".encode() for position in positions)
    return (
        document
        + f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    )


def test_native_pdf_embedded_text_uses_no_ocr_guess():
    raw, pages, provider = ocr.extract(
        embedded_pdf("Invoice number: Embedded-98765"), "application/pdf"
    )
    assert pages == 1 and provider == "poppler/embedded-text"
    assert propose(raw)["fields"]["invoice_number"] == "Embedded-98765"


def test_invoice_rechecks_demotion_and_does_not_persist(world, monkeypatch):
    client, tokens, _, users = world
    member_path = "/api/v1/organization/members/" + users[2]
    assert client.put(member_path, headers=tokens[0], json={"role": "editor"}).status_code == 200

    def demote(data, media):
        assert (
            client.put(member_path, headers=tokens[0], json={"role": "viewer"}).status_code == 200
        )
        return TEXT, 1, "test-fixture"

    monkeypatch.setattr(ocr, "extract", demote)
    assert upload(client, tokens[2]).status_code == 403
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(m.InvoiceIntake)) == 0


def test_invoice_ocr_concurrency_and_input_contract(world, intake, monkeypatch):
    from app.modules.invoices import router

    client, tokens, *_ = world

    class Busy:
        def acquire(self, **kwargs):
            return False

    monkeypatch.setattr(router, "slots", Busy())
    assert upload(client, tokens[0], data=b"new-file", key="busy").status_code == 429
    base = {"expected_version": 1, "corrected_text": "Review", "fields": intake["fields"]}
    for override in (
        {"grand_total": True},
        {"subtotal": 12.34},
        {"grand_total": "123.456"},
        {"organization_id": "foreign"},
    ):
        result = client.put(
            "/api/v1/invoice-intakes/" + intake["id"],
            headers={**tokens[0], "Idempotency-Key": "invalid-update"},
            json={**base, "fields": {**intake["fields"], **override}},
        )
        assert result.status_code == 422
    assert (
        client.get("/api/v1/invoice-intakes/" + intake["id"], headers=tokens[0]).json()["version"]
        == 1
    )


def test_ocr_timeout_and_invalid_input_always_delete_temporary_files(tmp_path, monkeypatch):
    import subprocess

    from fastapi import HTTPException

    created = []
    original = ocr.tempfile.TemporaryDirectory

    def directory(**kwargs):
        temporary = original(dir=tmp_path, **kwargs)
        created.append(temporary.name)
        return temporary

    monkeypatch.setattr(ocr.tempfile, "TemporaryDirectory", directory)
    monkeypatch.setattr(ocr, "availability", lambda: True)
    with pytest.raises(HTTPException) as invalid:
        ocr.extract(b"invalid", "image/png")
    assert invalid.value.status_code == 422

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("native", 30)

    monkeypatch.setattr(ocr.subprocess, "run", timeout)
    with pytest.raises(HTTPException) as expired:
        ocr.extract(image_bytes(), "image/png")
    assert expired.value.status_code == 504
    from pathlib import Path

    assert created and all(not Path(path).exists() for path in created)


def test_concurrent_transcription_edits_keep_one_current_revision(world, intake, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from app.modules.invoices import router

    client, tokens, _, users = world
    assert (
        client.put(
            "/api/v1/organization/members/" + users[2], headers=tokens[0], json={"role": "editor"}
        ).status_code
        == 200
    )
    reached = Barrier(2)
    original = router.record

    def synchronize(db, ctx, intake_id, lock=False):
        if lock:
            reached.wait(timeout=5)
        return original(db, ctx, intake_id, lock)

    monkeypatch.setattr(router, "record", synchronize)

    def change(index):
        return client.put(
            "/api/v1/invoice-intakes/" + intake["id"],
            headers={**tokens[index], "Idempotency-Key": f"concurrent-{index}"},
            json={
                "expected_version": 1,
                "corrected_text": f"Human edit {index}",
                "fields": intake["fields"],
            },
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(change, [0, 2]))
    assert sorted(r.status_code for r in results) == [200, 409]
    assert (
        client.get("/api/v1/invoice-intakes/" + intake["id"], headers=tokens[0]).json()["version"]
        == 2
    )
    assert (
        client.get(
            "/api/v1/invoice-intakes/" + intake["id"] + "/revisions", headers=tokens[0]
        ).json()["total"]
        == 2
    )


def test_native_processing_receives_no_database_or_other_runtime_secrets(monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace

    monkeypatch.setenv("OCR_TEST_SECRET", "synthetic-private-value")

    def native(arguments, **kwargs):
        assert "DATABASE_URL" not in kwargs["env"]
        assert "OCR_TEST_SECRET" not in kwargs["env"]
        assert "HTTP_PROXY" not in kwargs["env"]
        assert kwargs["env"]["OMP_THREAD_LIMIT"] == "1"
        if "--list-langs" in arguments:
            return SimpleNamespace(returncode=0, stdout=b"eng\nfas\n")
        assert kwargs["env"]["HOME"] == kwargs["cwd"]
        target = arguments[arguments.index("-l") - 1]
        Path(target + ".txt").write_text("Invoice number: Safe-123")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(ocr.subprocess, "run", native)
    raw, _, _ = ocr.extract(image_bytes(), "image/png")
    assert "Safe-123" in raw


def test_native_temporary_storage_failure_is_sanitized_and_retryable(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(ocr, "availability", lambda: True)

    def full_disk(**kwargs):
        raise OSError(28, "synthetic-private-path: no space")

    monkeypatch.setattr(ocr.tempfile, "TemporaryDirectory", full_disk)
    with pytest.raises(HTTPException) as failure:
        ocr.extract(b"image", "image/png")
    assert failure.value.status_code == 503
    assert "synthetic-private-path" not in failure.value.detail


@pytest.mark.parametrize("invalid", ["Private\x00text", "Private\ud800text"])
@pytest.mark.parametrize("field", ["corrected_text", "seller_name", "description"])
def test_invoice_invalid_text_corrections_rejected_without_writes(world, intake, field, invalid):
    client, tokens, *_ = world
    payload = {
        "expected_version": 1,
        "corrected_text": "Valid",
        "fields": {"seller_name": "Valid", "lines": [{"description": "Valid"}]},
    }
    import copy

    bad = copy.deepcopy(payload)
    if field == "corrected_text":
        bad[field] = invalid
    elif field == "description":
        bad["fields"]["lines"][0][field] = invalid
    else:
        bad["fields"][field] = invalid
    path = "/api/v1/invoice-intakes/" + intake["id"]
    headers = {**tokens[0], "Idempotency-Key": "nul-correction"}
    models = (m.InvoiceIntakeRevision, m.AuditEvent, m.IdempotencyRecord)
    with Session(engine()) as db:
        before = tuple(db.scalar(select(func.count()).select_from(model)) for model in models)
    result = client.put(
        path,
        headers={**headers, "Content-Type": "application/json"},
        content=json.dumps(bad, ensure_ascii=True).encode("ascii"),
    )
    assert result.status_code == 422
    assert "Private" not in result.text
    assert client.get(path, headers=tokens[0]).json() == intake
    with Session(engine()) as db:
        assert (
            tuple(db.scalar(select(func.count()).select_from(model)) for model in models) == before
        )
    assert client.put(path, headers=headers, json=payload).status_code == 200


@pytest.mark.parametrize("invalid", ["Private\x00text", "Private\ud800text"])
def test_invoice_invalid_extraction_text_rejected_without_records(world, monkeypatch, invalid):
    client, tokens, *_ = world
    monkeypatch.setattr(ocr, "extract", lambda *args: (invalid, 1, "test-fixture"))
    models = (m.InvoiceIntake, m.InvoiceIntakeRevision, m.AuditEvent, m.IdempotencyRecord)
    with Session(engine()) as db:
        before = tuple(db.scalar(select(func.count()).select_from(model)) for model in models)
    result = upload(client, tokens[0], key="nul-extract")
    assert result.status_code == 422 and "Private" not in result.text
    with Session(engine()) as db:
        assert (
            tuple(db.scalar(select(func.count()).select_from(model)) for model in models) == before
        )
    monkeypatch.setattr(ocr, "extract", lambda *args: (TEXT, 1, "test-fixture"))
    assert upload(client, tokens[0], key="nul-extract").status_code == 201
