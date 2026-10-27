import asyncio
from typing import Annotated
from uuid import UUID

from app.config import settings
from app.db import database
from app.idempotency import finish, replay
from app.modules.agent_workbench import provider
from app.modules.agent_workbench.learning import LESSONS, VERSION, catalog
from app.modules.agent_workbench.learning import CheckInput as LearningCheck
from app.modules.agent_workbench.models import AgentEvidence, AgentReview, AgentRun, AgentSource
from app.modules.agent_workbench.schemas import Kind, ReviewInput, RunInput, SourceInput
from app.modules.resources import audit, scoped, serialize
from app.schemas import StoredText
from app.security import Context, authorize_write, bearer, context
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/agent-workbench", tags=["internal agent drafts"])
Key = Header(..., min_length=1, max_length=100)
slots = asyncio.Semaphore(1)


def get(db, ctx, model, record_id, *, lock=False):
    stmt = scoped(model, ctx).where(model.id == record_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(stmt)
    if row is None:
        raise HTTPException(404, "Record not found")
    return row


def read_run(db, ctx, run):
    evidence = db.scalars(
        scoped(AgentEvidence, ctx)
        .where(AgentEvidence.run_id == run.id)
        .order_by(AgentEvidence.alias)
    ).all()
    source_ids = [row.source_id for row in evidence]
    active = (
        set(
            db.scalars(
                scoped(AgentSource, ctx).where(
                    AgentSource.id.in_(source_ids), AgentSource.active.is_(True)
                )
            ).all()
        )
        if source_ids
        else set()
    )
    review = db.scalar(scoped(AgentReview, ctx).where(AgentReview.run_id == run.id))
    return {
        **serialize(run),
        "evidence": [serialize(row) for row in evidence],
        "evidence_current": len(active) == len(evidence),
        "grounding": "cited_draft" if evidence else "no_sources_plan_only",
        "review": serialize(review) if review else None,
        "financial_approval": False,
        "published": False,
        "external_actions": False,
        "claim_verification": "human_required",
    }


def active_sources(db, ctx, ids):
    if not ids:
        return []
    rows = db.scalars(
        scoped(AgentSource, ctx)
        .where(AgentSource.id.in_(ids))
        .order_by(AgentSource.id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    ).all()
    if len(rows) != len(ids):
        raise HTTPException(404, "Source not found")
    if any(not row.active for row in rows):
        raise HTTPException(409, "Source revoked; choose current evidence")
    by_id = {row.id: row for row in rows}
    return [by_id[id_] for id_ in ids]


@router.get("/status")
def status(ctx: Context = Depends(context)):
    config = settings()
    return {
        "configured": config.agent_workbench_provider == "ollama",
        "provider": config.agent_workbench_provider,
        "model": config.agent_workbench_model
        if config.agent_workbench_provider == "ollama"
        else None,
        "kinds": list(provider.TASKS),
        "policy_version": provider.POLICY_VERSION,
        "tools": [],
        "external_actions": False,
        "financial_approval": False,
        "source_mode": "human_approved_manual_text",
        "generation_readiness": "experimental_not_quality_accepted",
    }


@router.get("/sources")
def sources(
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    q: Annotated[StoredText, Query(max_length=200)] = "",
    active: bool | None = None,
    ctx: Context = Depends(context),
    db: Session = Depends(database),
):
    stmt = scoped(AgentSource, ctx)
    if q:
        stmt = stmt.where(AgentSource.name.icontains(q, autoescape=True))
    if active is not None:
        stmt = stmt.where(AgentSource.active == active)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(
        stmt.order_by(AgentSource.created_at.desc(), AgentSource.id).offset(offset).limit(limit)
    ).all()
    return {
        "items": [serialize(row) for row in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.post("/sources", status_code=201)
def create_source(
    payload: SourceInput,
    idempotency_key: str = Key,
    ctx: Context = Depends(context),
    db: Session = Depends(database),
):
    authorize_write(db, ctx, admin=True)
    prior, fingerprint = replay(
        db, ctx, idempotency_key, "agent-source", payload.model_dump(mode="json")
    )
    if prior:
        return serialize(get(db, ctx, AgentSource, UUID(prior["id"])))
    row = AgentSource(
        organization_id=ctx.organization_id,
        created_by=ctx.user_id,
        **payload.model_dump(exclude={"rights_confirmed"}),
    )
    db.add(row)
    db.flush()
    audit(db, ctx, "create", "agent-sources", row.id)
    finish(db, ctx, idempotency_key, fingerprint, {"id": str(row.id)})
    return serialize(row)


@router.post("/sources/{source_id}/revoke")
def revoke(
    source_id: UUID,
    idempotency_key: str = Key,
    ctx: Context = Depends(context),
    db: Session = Depends(database),
):
    authorize_write(db, ctx, admin=True)
    prior, fingerprint = replay(
        db, ctx, idempotency_key, "agent-source-revoke", {"id": str(source_id)}
    )
    row = get(db, ctx, AgentSource, source_id, lock=True)
    if prior:
        return serialize(row)
    if row.active:
        row.active = False
        db.flush()
        audit(db, ctx, "revoke", "agent-sources", row.id)
    finish(db, ctx, idempotency_key, fingerprint, {"id": str(row.id)})
    return serialize(row)


@router.get("/runs")
def runs(
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    kind: Kind | None = None,
    ctx: Context = Depends(context),
    db: Session = Depends(database),
):
    stmt = scoped(AgentRun, ctx)
    if kind:
        stmt = stmt.where(AgentRun.kind == kind)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(
        stmt.order_by(AgentRun.created_at.desc(), AgentRun.id).offset(offset).limit(limit)
    ).all()
    return {
        "items": [{**serialize(row), "output": {"title": row.output["title"]}} for row in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/runs/{run_id}")
def read(run_id: UUID, ctx: Context = Depends(context), db: Session = Depends(database)):
    return read_run(db, ctx, get(db, ctx, AgentRun, run_id))


@router.post("/runs", status_code=201)
async def generate(
    payload: RunInput,
    idempotency_key: str = Key,
    ctx: Context = Depends(context),
    credentials=Depends(bearer),
    db: Session = Depends(database),
):
    authorize_write(db, ctx)
    data = payload.model_dump(mode="json")
    prior, fingerprint = replay(db, ctx, idempotency_key, "agent-run", data)
    if prior:
        return read_run(db, ctx, get(db, ctx, AgentRun, UUID(prior["id"])))
    config = settings()
    if config.agent_workbench_provider != "ollama":
        raise HTTPException(503, "Local drafting model not configured")
    rows = active_sources(db, ctx, payload.source_ids)
    snapshots = [
        {
            "alias": f"S{i + 1}",
            "id": str(row.id),
            "name": row.name,
            "content": row.content,
            "kind": row.kind,
            "attribution": row.attribution,
            "source_url": row.source_url,
        }
        for i, row in enumerate(rows)
    ]
    # No DB connections/actor locks are held during inference. The model gets aliases, not IDs or credentials.
    db.rollback()
    if slots.locked():
        raise HTTPException(429, "Internal agent is busy; retry shortly")
    async with slots:
        output = await provider.generate(
            payload.kind,
            payload.brief,
            [{"alias": row["alias"], "content": row["content"]} for row in snapshots],
            config,
        )
    # Validate even if a provider adapter changes; inferencing never authorizes a write.
    try:
        output = provider.validate_output(output, snapshots, payload.kind)
    except (ValueError, KeyError, TypeError):
        raise HTTPException(503, "Invalid generated evidence") from None
    ctx = context(credentials, db)
    authorize_write(db, ctx)
    prior, fingerprint = replay(db, ctx, idempotency_key, "agent-run", data)
    if prior:
        return read_run(db, ctx, get(db, ctx, AgentRun, UUID(prior["id"])))
    active_sources(db, ctx, payload.source_ids)
    row = AgentRun(
        organization_id=ctx.organization_id,
        created_by=ctx.user_id,
        kind=payload.kind,
        brief=payload.brief,
        output=output,
        model_name=config.agent_workbench_model,
        policy_version=provider.POLICY_VERSION,
    )
    db.add(row)
    db.flush()
    for snapshot in snapshots:
        db.add(
            AgentEvidence(
                organization_id=ctx.organization_id,
                run_id=row.id,
                source_id=UUID(snapshot["id"]),
                alias=snapshot["alias"],
                snapshot=snapshot,
            )
        )
    db.flush()
    audit(db, ctx, "generate", "agent-runs", row.id)
    finish(db, ctx, idempotency_key, fingerprint, {"id": str(row.id)})
    return read_run(db, ctx, row)


@router.post("/runs/{run_id}/review")
def review(
    run_id: UUID,
    payload: ReviewInput,
    idempotency_key: str = Key,
    ctx: Context = Depends(context),
    db: Session = Depends(database),
):
    authorize_write(db, ctx, admin=True)
    prior, fingerprint = replay(
        db, ctx, idempotency_key, "agent-review", {"id": str(run_id), **payload.model_dump()}
    )
    row = get(db, ctx, AgentRun, run_id, lock=True)
    if prior:
        return read_run(db, ctx, row)
    if db.scalar(scoped(AgentReview, ctx).where(AgentReview.run_id == row.id)):
        raise HTTPException(409, "Run already reviewed; generate a new draft for changes")
    if payload.decision == "accepted":
        ids = db.scalars(
            scoped(AgentEvidence, ctx)
            .where(AgentEvidence.run_id == row.id)
            .with_only_columns(AgentEvidence.source_id)
        ).all()
        active_sources(db, ctx, ids)
    decision = AgentReview(
        organization_id=ctx.organization_id,
        run_id=row.id,
        created_by=ctx.user_id,
        **payload.model_dump(),
    )
    db.add(decision)
    db.flush()
    audit(db, ctx, "review", "agent-runs", row.id)
    finish(db, ctx, idempotency_key, fingerprint, {"id": str(row.id)})
    return read_run(db, ctx, row)


@router.get("/lessons")
def lessons(ctx: Context = Depends(context)):
    return catalog()


@router.post("/lessons/{lesson_id}/check")
def check_lesson(lesson_id: str, body: LearningCheck, ctx: Context = Depends(context)):
    lesson = next((row for row in LESSONS if row["id"] == lesson_id), None)
    if lesson is None:
        raise HTTPException(404, "Lesson not found")
    questions = lesson["questions"]
    if set(body.answers) != {row["id"] for row in questions} or any(
        not 0 <= body.answers[row["id"]] < len(row["options"]) for row in questions
    ):
        raise HTTPException(422, "Answer every lesson question with a listed option")
    feedback = [
        {
            "question_id": row["id"],
            "correct": body.answers[row["id"]] == row["answer"],
            "correct_option": row["answer"],
            "explanation": row["explanation"],
        }
        for row in questions
    ]
    return {
        "lesson_id": lesson_id,
        "version": VERSION,
        "correct_count": sum(row["correct"] for row in feedback),
        "question_count": len(questions),
        "feedback": feedback,
        "progress_persisted": False,
        "generated_by_model": False,
        "financial_approval": False,
    }
