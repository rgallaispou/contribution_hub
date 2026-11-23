import mailbox, re
from email.utils import parseaddr, parsedate_to_datetime
from email.header import decode_header, make_header
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import select
from backend.app.models import Identity, Thread, Message, PatchSeries, IdentityActivity, Trailer, ReplyTask

PATCH_RE = re.compile(r"\[PATCH(?:\s+v(?P<version>\d+))?(?:\s+(?P<idx>\d+)/(?: (?P<total>\d+))?)?\]", re.I)
PATCH_RE2 = re.compile(r"\[PATCH(?:\s+v(?P<version>\d+))?\s+(?P<idx>\d+)/(?P<total>\d+)\]", re.I)
TRAILER_RE = re.compile(r"(?m)^([A-Za-z][A-Za-z0-9-]+):\s*(.+?)\s*$")
ACTION_WORDS = re.compile(r"\b(please update|please fix|could you|can you|would you|please clarify|needs? changes?|please resend|what do you think|could you explain|why does)\b", re.I)

def decoded(value):
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)

def clean_msgid(value):
    return (value or "").strip().strip("<>").strip()

def normalize_subject(subject):
    s = re.sub(r"(?i)^\s*(re|fw|fwd):\s*", "", subject or "")
    s = re.sub(r"(?i)\[patch[^]]*\]", "", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s or "(no subject)"

def parse_patch(subject):
    m = PATCH_RE2.search(subject or "")
    if not m:
        # Single patch / cover letter / RFC patch subject
        if re.search(r"\[PATCH(?:\s|\])", subject or "", re.I):
            vm = re.search(r"(?i)\bv(\d+)\b", subject)
            return True, int(vm.group(1)) if vm else 1, None, None
        return False, None, None, None
    return True, int(m.group("version") or 1), int(m.group("idx")), int(m.group("total"))

def extract_body(msg):
    chunks = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_maintype() == "text" and part.get_content_subtype() in ("plain", "x-patch"):
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        chunks.append(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
                except Exception:
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                chunks.append(payload.decode(msg.get_content_charset() or "utf-8", errors="replace"))
            elif isinstance(msg.get_payload(), str):
                chunks.append(msg.get_payload())
        except Exception:
            pass
    return "\n".join(chunks)[:200000]

def root_for(db: Session, msgid: str, parent: str | None):
    if parent:
        parent_msg = db.scalar(select(Message).where(Message.message_id == parent))
        if parent_msg:
            return db.get(Thread, parent_msg.thread_id)
    thread = db.scalar(select(Thread).where(Thread.root_message_id == msgid))
    if not thread:
        thread = Thread(root_message_id=msgid)
        db.add(thread)
        db.flush()
    return thread

def import_mbox(db: Session, path: Path, identities: list[str]):
    identity_rows = {}
    for email in identities:
        row = db.scalar(select(Identity).where(Identity.email == email))
        if not row:
            row = Identity(email=email, label="Personal" if email.startswith("rgallaispou@") else "Professional")
            db.add(row); db.flush()
        identity_rows[email] = row

    imported = skipped = 0
    box = mailbox.mbox(str(path))
    for raw in box:
        msgid = clean_msgid(raw.get("Message-ID"))
        if not msgid or db.scalar(select(Message.id).where(Message.message_id == msgid)):
            skipped += 1
            continue
        sender_name, sender = parseaddr(raw.get("From", ""))
        sender = sender.lower()
        subject = decoded(raw.get("Subject", ""))
        parent = clean_msgid(raw.get("In-Reply-To"))
        refs = [clean_msgid(x) for x in re.findall(r"<([^>]+)>", raw.get("References", ""))]
        thread = root_for(db, msgid, parent or (refs[-1] if refs else None))
        if not thread.subject:
            thread.subject = subject
        thread.last_seen = thread.last_seen

        try:
            sent_at = parsedate_to_datetime(raw.get("Date")) if raw.get("Date") else None
            if sent_at and sent_at.tzinfo is None:
                from datetime import timezone
                sent_at = sent_at.replace(tzinfo=timezone.utc)
        except Exception:
            sent_at = None

        is_patch, version, idx, total = parse_patch(subject)
        series_id = None
        if is_patch:
            key = normalize_subject(subject)
            series = db.scalar(select(PatchSeries).where(PatchSeries.series_key == key))
            if not series:
                series = PatchSeries(series_key=key, normalized_subject=key)
                db.add(series); db.flush()
            series_id = series.id

        recipients = ", ".join(raw.get_all("To", []) + raw.get_all("Cc", []))
        body = extract_body(raw)
        row = Message(
            message_id=msgid, thread_id=thread.id, sender=sender,
            recipients=recipients, subject=subject, sent_at=sent_at,
            body=body, in_reply_to=parent, is_patch=is_patch,
            patch_version=version, patch_index=idx, patch_total=total,
            series_id=series_id, source_file=path.name
        )
        db.add(row)
        db.flush()

        if sender in identity_rows and series_id:
            db.add(IdentityActivity(identity_id=identity_rows[sender].id,
                                    series_id=series_id, activity_type="submission",
                                    message_id=msgid))

        for kind, person in TRAILER_RE.findall(body):
            if kind.lower() in {"signed-off-by", "reviewed-by", "acked-by", "tested-by",
                                "reported-by", "suggested-by", "co-developed-by",
                                "requested-by", "link", "fixes"}:
                db.add(Trailer(message_id=msgid, kind=kind, person=person,
                               provenance_message_id=msgid))

        if sender not in identity_rows and ACTION_WORDS.search(body):
            # Suggest only when the thread has already contained a message from one of our identities.
            own_seen = db.scalar(select(Message.id).where(
                Message.thread_id == thread.id, Message.sender.in_(identities)).limit(1))
            if own_seen:
                existing = db.scalar(select(ReplyTask.id).where(ReplyTask.message_id == msgid))
                if not existing:
                    db.add(ReplyTask(message_id=msgid, thread_id=thread.id,
                                     reason="Inbound message contains a question or change-request phrase.",
                                     confidence="medium"))
        imported += 1

    db.commit()
    return {"imported": imported, "skipped_duplicates_or_missing_id": skipped}
