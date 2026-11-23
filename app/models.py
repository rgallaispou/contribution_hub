from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Boolean, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base

def utcnow():
    return datetime.now(timezone.utc)

class Identity(Base):
    __tablename__ = "identities"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(80))

class Thread(Base):
    __tablename__ = "threads"
    id: Mapped[int] = mapped_column(primary_key=True)
    root_message_id: Mapped[str] = mapped_column(String(998), unique=True, index=True)
    subject: Mapped[str] = mapped_column(Text, default="")
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class PatchSeries(Base):
    __tablename__ = "patch_series"
    id: Mapped[int] = mapped_column(primary_key=True)
    series_key: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    normalized_subject: Mapped[str] = mapped_column(Text)
    project_hint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[str] = mapped_column(String(998), unique=True, index=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("threads.id"), index=True)
    sender: Mapped[str] = mapped_column(String(320), index=True)
    recipients: Mapped[str] = mapped_column(Text, default="")
    subject: Mapped[str] = mapped_column(Text, default="")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    body: Mapped[str] = mapped_column(Text, default="")
    in_reply_to: Mapped[str | None] = mapped_column(String(998), nullable=True)
    is_patch: Mapped[bool] = mapped_column(Boolean, default=False)
    patch_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    patch_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    patch_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    series_id: Mapped[int | None] = mapped_column(ForeignKey("patch_series.id"), nullable=True, index=True)
    source_file: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (Index("ix_messages_thread_date", "thread_id", "sent_at"),)

class IdentityActivity(Base):
    __tablename__ = "identity_activity"
    id: Mapped[int] = mapped_column(primary_key=True)
    identity_id: Mapped[int] = mapped_column(ForeignKey("identities.id"), index=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("patch_series.id"), index=True)
    activity_type: Mapped[str] = mapped_column(String(40), default="submission")
    message_id: Mapped[str] = mapped_column(String(998))
    __table_args__ = (UniqueConstraint("identity_id", "message_id", "activity_type"),)

class Trailer(Base):
    __tablename__ = "trailers"
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[str] = mapped_column(String(998), index=True)
    kind: Mapped[str] = mapped_column(String(80), index=True)
    person: Mapped[str] = mapped_column(String(512), default="")
    provenance_message_id: Mapped[str] = mapped_column(String(998), default="")

class ReplyTask(Base):
    __tablename__ = "reply_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[str] = mapped_column(String(998), unique=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("threads.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="suggested")
    reason: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[str] = mapped_column(String(16), default="low")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
