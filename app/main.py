from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from typing import Literal
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.config import settings
from app.db import Base, engine, get_db
from app.models import Identity, Message, PatchSeries, IdentityActivity, Trailer, ReplyTask
from app.ingest import import_mbox

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Contribution Hub API", version="0.1.0",
              description="Private, self-hosted open-source contribution tracker.")

class ReplyTaskStatusUpdate(BaseModel):
    status: Literal["suggested", "done", "dismissed"]

@app.get("/api/health")
def health():
    return {"status": "ok", "identities_configured": len(settings.identity_emails)}

@app.get("/api/identities")
def identities(db: Session = Depends(get_db)):
    rows = db.scalars(select(Identity).order_by(Identity.email)).all()
    return [{"id": r.id, "email": r.email, "label": r.label} for r in rows]

def identity_stats(db: Session, identity: Identity):
    series_count = db.scalar(select(func.count(func.distinct(IdentityActivity.series_id))).where(
        IdentityActivity.identity_id == identity.id)) or 0
    messages = db.scalar(select(func.count(Message.id)).where(Message.sender == identity.email)) or 0
    own_thread_ids = select(Message.thread_id).where(Message.sender == identity.email)
    trailers = db.scalar(select(func.count(Trailer.id)).join(
        Message, Trailer.message_id == Message.message_id).where(
        Message.thread_id.in_(own_thread_ids),
        Trailer.kind.in_(["Reviewed-by", "Acked-by", "Tested-by"]))) or 0
    replies = db.scalar(select(func.count(ReplyTask.id)).join(
        Message, ReplyTask.message_id == Message.message_id).where(
        Message.thread_id.in_(select(Message.thread_id).where(Message.sender == identity.email)))) or 0
    return {"email": identity.email, "patch_series": series_count,
            "messages_sent": messages, "review_trailers_in_own_threads": trailers,
            "reply_suggestions_in_own_threads": replies}

@app.get("/api/identities/{email}/statistics")
def stats_for_identity(email: str, db: Session = Depends(get_db)):
    normalized = email.lower()
    identity = db.scalar(select(Identity).where(Identity.email == normalized))
    if not identity:
        raise HTTPException(404, "Unknown identity")
    return identity_stats(db, identity)

@app.get("/api/dashboard/overview")
def overview(db: Session = Depends(get_db)):
    rows = db.scalars(select(Identity).order_by(Identity.email)).all()
    stats = [identity_stats(db, r) for r in rows]
    combined_series = db.scalar(select(func.count(PatchSeries.id))) or 0
    return {"identities": stats, "combined": {
        "unique_patch_series": combined_series,
        "unique_messages": db.scalar(select(func.count(Message.id))) or 0,
        "reply_suggestions": db.scalar(select(func.count(ReplyTask.id))) or 0
    }}

@app.get("/api/contributions")
def contributions(limit: int = 100, db: Session = Depends(get_db)):
    limit = max(1, min(limit, 500))
    rows = db.execute(select(PatchSeries).order_by(PatchSeries.created_at.desc()).limit(limit)).scalars()
    result = []
    for s in rows:
        emails = db.execute(select(Identity.email).join(
            IdentityActivity, IdentityActivity.identity_id == Identity.id
        ).where(IdentityActivity.series_id == s.id).distinct()).scalars().all()
        message_id = db.scalar(select(Message.message_id).where(
            Message.series_id == s.id).order_by(Message.sent_at.desc()).limit(1))
        latest_activity = db.scalar(select(func.max(Message.sent_at)).where(Message.series_id == s.id))
        message_count = db.scalar(select(func.count(Message.id)).where(Message.series_id == s.id)) or 0
        result.append({
            "id": s.id,
            "subject": s.normalized_subject,
            "project": s.project_hint,
            "identities": emails,
            "message_count": message_count,
            "last_activity": latest_activity.isoformat() if latest_activity else None,
            "lore_url": f"https://lore.kernel.org/all/{message_id}/" if message_id else None,
        })
    return result

@app.get("/api/reply-tasks")
def reply_tasks(db: Session = Depends(get_db)):
    rows = db.execute(select(ReplyTask, Message).join(
        Message, ReplyTask.message_id == Message.message_id
    ).order_by(ReplyTask.created_at.desc()).limit(200)).all()
    return [{"id": t.id, "message_id": t.message_id, "subject": m.subject,
             "sender": m.sender, "reason": t.reason, "confidence": t.confidence,
             "status": t.status,
             "lore_url": f"https://lore.kernel.org/all/{t.message_id}/"} for t, m in rows]

@app.patch("/api/reply-tasks/{task_id}")
def update_reply_task(task_id: int, payload: ReplyTaskStatusUpdate, db: Session = Depends(get_db)):
    task = db.get(ReplyTask, task_id)
    if not task:
        raise HTTPException(404, "Unknown reply task")
    task.status = payload.status
    db.commit()
    return {"id": task.id, "status": task.status}

@app.post("/api/import/mbox")
def import_file(path: str, db: Session = Depends(get_db)):
    candidate = (settings.import_path / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    if settings.import_path not in candidate.parents or not candidate.is_file():
        raise HTTPException(400, "File must exist inside IMPORT_DIR")
    try:
        result = import_mbox(db, candidate, settings.identity_emails)
    except Exception as exc:
        db.rollback()
        raise HTTPException(400, f"Import failed: {type(exc).__name__}: {exc}")
    return result
