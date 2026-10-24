import asyncio

from app.config import settings
from app.db import database
from app.modules.assistant import provider, tools
from app.modules.assistant.schemas import Question
from app.modules.resources import audit
from app.security import Context, context
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

router = APIRouter(prefix="/sales-assistant", tags=["read-only sales assistant"])
slots = asyncio.Semaphore(2)


@router.get("/status")
def status(ctx: Context = Depends(context)):
    configured = settings().assistant_provider == "ollama"
    return {
        "configured": configured,
        "provider": "ollama" if configured else "disabled",
        "availability": "unchecked" if configured else "disabled",
        "model": settings().assistant_model if configured else None,
        "tools": list(tools.TOOLS),
        "read_only": True,
        "financial_approval": False,
    }


@router.post("/query")
async def query(
    payload: Question,
    request: Request,
    ctx: Context = Depends(context),
    db: Session = Depends(database),
):
    config = settings()
    if config.assistant_provider != "ollama":
        raise HTTPException(503, "Local sales model is not configured")
    if slots.locked():
        raise HTTPException(429, "Sales assistant is busy; retry shortly")
    async with slots:
        plan = await provider.plan(payload.question, config)
        result = await tools.search(request.app, request.headers["authorization"], plan)
        audit(db, ctx, "assistant_query", "sales-assistant", ctx.user_id)
        db.commit()
        return {**result, "mode": "local_model", "model": config.assistant_model}
