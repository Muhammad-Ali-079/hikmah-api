"""Hikmah Life API: sign up, email code, sign in, account. (Phase 1)

Run on your PC:   uvicorn app.main:app --reload
Docs page:        http://127.0.0.1:8000/docs
"""
import hmac
import re
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import config, datastore, mailer, ocr, pages, rag, retrieval, security
from .db import ChatUse, ContactMsg, DailyReaction, EmailCode, User, get_db, init_db, utcnow


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Hikmah Life API", version="2.0.0", lifespan=lifespan)
bearer = HTTPBearer(auto_error=False)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ------------------------------------------------------------------ helpers
def fail(status: int, code: str, message: str, **extra) -> HTTPException:
    """Every error has the same shape:  {"detail": {"code": "...", "message": "...", ...}}"""
    return HTTPException(status_code=status, detail={"code": code, "message": message, **extra})


def clean_email(raw: str) -> str:
    e = (raw or "").strip().lower()
    if len(e) > 254 or not EMAIL_RE.match(e):
        raise fail(422, "invalid_email", "Enter a valid email address.")
    return e


def check_password(pw: str) -> None:
    if len(pw) < config.MIN_PASSWORD:
        raise fail(422, "weak_password", f"Use at least {config.MIN_PASSWORD} characters.")
    if len(pw) > 128:
        raise fail(422, "weak_password", "Password is too long.")


def user_json(u: User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email, "verified": u.is_verified, "lang": u.lang}


def by_email(db: Session, email: str) -> Optional[User]:
    return db.scalar(select(User).where(User.email == email))


def send_code(db: Session, user: User, purpose: str) -> int:
    """Emails a fresh code. Returns 0 when sent, or the seconds to wait when asked too soon."""
    now = utcnow()
    last = db.scalar(
        select(EmailCode).where(EmailCode.user_id == user.id, EmailCode.purpose == purpose).order_by(EmailCode.id.desc()).limit(1)
    )
    if last is not None:
        wait = config.RESEND_SECONDS - int((now - last.created_at).total_seconds())
        if wait > 0:
            return wait
    sent_last_hour = db.scalar(
        select(func.count()).select_from(EmailCode).where(
            EmailCode.user_id == user.id, EmailCode.purpose == purpose, EmailCode.created_at > now - timedelta(hours=1)
        )
    ) or 0
    if sent_last_hour >= config.MAX_CODES_PER_HOUR:
        raise fail(429, "too_many_codes", "Too many codes were sent. Try again in an hour.")

    code = security.make_code()
    row = EmailCode(
        user_id=user.id,
        purpose=purpose,
        code_hash=security.hash_code(code, user.id, purpose),
        created_at=now,
        expires_at=now + timedelta(minutes=config.CODE_MINUTES),
    )
    db.add(row)
    db.commit()
    if not mailer.send_code(user.email, user.name, code, purpose):
        db.delete(row)  # so the user can try again at once
        db.commit()
        raise fail(502, "email_failed", "We could not send the email. Please try again in a minute.")
    return 0


def check_code(db: Session, user: User, purpose: str, code: str) -> None:
    """Raises an error unless `code` is the newest, unused, unexpired code for this user."""
    now = utcnow()
    row = db.scalar(
        select(EmailCode)
        .where(EmailCode.user_id == user.id, EmailCode.purpose == purpose, EmailCode.used == False)  # noqa: E712
        .order_by(EmailCode.id.desc())
        .limit(1)
    )
    if row is None or row.expires_at < now:
        raise fail(400, "code_expired", "This code has expired. Ask for a new one.")
    if row.attempts >= config.CODE_MAX_TRIES:
        raise fail(429, "too_many_attempts", "Too many wrong tries. Ask for a new code.")
    if not security.codes_match(row.code_hash, security.hash_code(code.strip(), user.id, purpose)):
        row.attempts += 1
        db.commit()
        left = config.CODE_MAX_TRIES - row.attempts
        raise fail(400, "wrong_code", "That code is not correct.", tries_left=left)
    row.used = True
    db.commit()


def current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer), db: Session = Depends(get_db)) -> User:
    data = security.read_token(creds.credentials) if creds else None
    if not data:
        raise fail(401, "not_logged_in", "Please sign in again.")
    user = db.get(User, int(data["sub"]))
    if user is None or not user.is_verified or user.token_version != data.get("ver"):
        raise fail(401, "not_logged_in", "Please sign in again.")
    return user


# ------------------------------------------------------------------ request bodies
class SignUp(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    email: str
    password: str
    lang: str = "en"


class Verify(BaseModel):
    email: str
    code: str = Field(min_length=6, max_length=6)


class EmailOnly(BaseModel):
    email: str


class Login(BaseModel):
    email: str
    password: str


class Reset(BaseModel):
    email: str
    code: str = Field(min_length=6, max_length=6)
    new_password: str


class Confirm(BaseModel):
    password: str


# ------------------------------------------------------------------ routes
@app.get("/health")
def health():
    return {"ok": True}


@app.post("/auth/signup")
def signup(body: SignUp, db: Session = Depends(get_db)):
    email = clean_email(body.email)
    check_password(body.password)
    name = body.name.strip()
    if not name:
        raise fail(422, "invalid_name", "Enter your name.")
    lang = body.lang if body.lang in ("en", "ur", "de") else "en"

    user = by_email(db, email)
    if user is not None and user.is_verified:
        raise fail(409, "email_taken", "This email already has an account. Please sign in.")
    pw_hash = security.hash_password(body.password)
    if user is None:
        user = User(email=email, name=name, pw_hash=pw_hash, lang=lang)
        db.add(user)
    else:  # started before but never verified: let them start again with new details
        user.name = name
        user.pw_hash = pw_hash
        user.lang = lang
    try:
        db.commit()
    except IntegrityError:  # two sign-ups with the same email at the same moment
        db.rollback()
        raise fail(409, "email_taken", "This email already has an account. Please sign in.")
    wait = send_code(db, user, "verify")
    return {"ok": True, "email": email, "resend_in": wait or config.RESEND_SECONDS}


@app.post("/auth/verify")
def verify(body: Verify, db: Session = Depends(get_db)):
    user = by_email(db, clean_email(body.email))
    if user is None:
        raise fail(400, "wrong_code", "That code is not correct.")
    check_code(db, user, "verify", body.code)
    user.is_verified = True
    user.last_login_at = utcnow()
    db.commit()
    return {"token": security.make_token(user.id, user.token_version), "user": user_json(user)}


@app.post("/auth/resend")
def resend(body: EmailOnly, db: Session = Depends(get_db)):
    user = by_email(db, clean_email(body.email))
    wait = 0
    if user is not None and not user.is_verified:  # never tells whether an email is registered
        wait = send_code(db, user, "verify")
    return {"ok": True, "resend_in": wait or config.RESEND_SECONDS}


@app.post("/auth/login")
def login(body: Login, db: Session = Depends(get_db)):
    email = clean_email(body.email)
    user = by_email(db, email)
    bad = fail(401, "invalid_credentials", "Email or password is not correct.")
    if user is None:
        security.verify_password(body.password, security.hash_password("x"))  # same time as a real check
        raise bad
    now = utcnow()
    if user.locked_until and user.locked_until > now:
        mins = int((user.locked_until - now).total_seconds() // 60) + 1
        raise fail(429, "locked", f"Too many wrong tries. Try again in {mins} minutes.", minutes=mins)
    if not security.verify_password(body.password, user.pw_hash):
        user.failed_logins += 1
        if user.failed_logins >= config.MAX_FAILED_LOGINS:
            user.locked_until = now + timedelta(minutes=config.LOCK_MINUTES)
            user.failed_logins = 0
        db.commit()
        raise bad
    user.failed_logins = 0
    user.locked_until = None
    if not user.is_verified:
        db.commit()
        try:
            send_code(db, user, "verify")
        except HTTPException:
            pass  # the app still opens the code page; the user can press "Send again"
        raise fail(403, "not_verified", "Please verify your email first. We sent you a code.")
    user.last_login_at = now
    db.commit()
    return {"token": security.make_token(user.id, user.token_version), "user": user_json(user)}


@app.post("/auth/forgot")
def forgot(body: EmailOnly, db: Session = Depends(get_db)):
    user = by_email(db, clean_email(body.email))
    wait = 0
    if user is not None and user.is_verified:
        wait = send_code(db, user, "reset")
    return {"ok": True, "resend_in": wait or config.RESEND_SECONDS}


@app.post("/auth/reset")
def reset(body: Reset, db: Session = Depends(get_db)):
    check_password(body.new_password)
    user = by_email(db, clean_email(body.email))
    if user is None or not user.is_verified:
        raise fail(400, "wrong_code", "That code is not correct.")
    check_code(db, user, "reset", body.code)
    user.pw_hash = security.hash_password(body.new_password)
    user.token_version += 1  # signs the account out everywhere
    user.failed_logins = 0
    user.locked_until = None
    db.commit()
    return {"ok": True}


@app.get("/me")
def me(user: User = Depends(current_user)):
    return {"user": user_json(user)}


@app.post("/me/delete")
def delete_me(body: Confirm, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Play Store rule: people must be able to delete their account and data."""
    if not security.verify_password(body.password, user.pw_hash):
        raise fail(401, "invalid_credentials", "Password is not correct.")
    db.delete(user)  # its codes go with it
    db.commit()
    return {"ok": True}


@app.get("/admin/users")
def admin_users(x_admin_key: str = Header(default=""), db: Session = Depends(get_db)):
    """For you only. Shows who registered. Passwords are hashed, so they can never be shown."""
    if not config.ADMIN_KEY or not hmac.compare_digest(x_admin_key, config.ADMIN_KEY):
        raise HTTPException(status_code=404)
    rows = db.scalars(select(User).order_by(User.id.desc())).all()
    return {
        "count": len(rows),
        "verified": sum(1 for u in rows if u.is_verified),
        "users": [
            {
                "id": u.id,
                "name": u.name,
                "email": u.email,
                "verified": u.is_verified,
                "lang": u.lang,
                "created_at": u.created_at.isoformat(),
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            }
            for u in rows
        ],
    }


@app.get("/privacy", response_class=HTMLResponse)
def privacy():
    return pages.privacy()


@app.get("/account-deletion", response_class=HTMLResponse)
def account_deletion():
    return pages.deletion()


# ------------------------------------------------------------------ knowledge library + chat (Phase 3)
DAILY_QUESTIONS = 60


def need_library():
    d = datastore.get_db()
    if d is None:
        raise fail(503, "library_unavailable", "The library is not loaded on the server yet.")
    return d


class Ask(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    lang: str = Field(default="en", max_length=8)


@app.post("/chat")
def chat(body: Ask, user: User = Depends(current_user), db: Session = Depends(get_db)):
    lib = need_library()
    day = utcnow().strftime("%Y-%m-%d")
    row = db.scalar(select(ChatUse).where(ChatUse.user_id == user.id, ChatUse.day == day))
    if row is None:
        row = ChatUse(user_id=user.id, day=day, count=0)
        db.add(row)
    if row.count >= DAILY_QUESTIONS:
        raise fail(429, "daily_limit", "You reached today's question limit. Please come back tomorrow.")
    row.count += 1
    db.commit()
    return rag.answer(lib, body.question)


class Photo(BaseModel):
    image_b64: str = Field(min_length=100, max_length=7_000_000)


@app.post("/chat/ocr")
def chat_ocr(body: Photo, user: User = Depends(current_user)):
    """Turns a photo (a page, a screenshot) into text. The app puts that text in the question box for the person to check."""
    text = ocr.read_text(body.image_b64)
    if text is None:
        raise fail(422, "bad_image", "This picture could not be read. Use a clear JPG or PNG photo.")
    return {"text": text}


@app.get("/library/stats")
def library_stats(user: User = Depends(current_user)):
    return datastore.stats()


@app.get("/library/search")
def library_search(q: str, kind: str = "", user: User = Depends(current_user)):
    lib = need_library()
    q = q.strip()[:200]
    ref = retrieval.find_reference(q)
    if ref and ref[0] == "hadith":
        h = retrieval.get_hadith(lib, ref[1])
        return {"results": [rag._source(h, 1)] if h else []}
    query = retrieval.build_query(q)
    kinds = [kind] if kind in ("quran", "hadith", "tafsir") else None
    hits = retrieval.search(lib, query, 20, kinds)
    return {"results": [rag._source(h, i + 1) for i, h in enumerate(hits)]}


@app.get("/library/hadith/{no}")
def library_hadith(no: int, user: User = Depends(current_user)):
    h = retrieval.get_hadith(need_library(), no)
    if not h:
        raise fail(404, "not_found", "This hadith number is not in the data.")
    return rag._source(h, 1)


@app.get("/library/quran/{surah}/{ayah}")
def library_quran(surah: int, ayah: int, user: User = Depends(current_user)):
    v = retrieval.get_verses(need_library(), surah, ayah, ayah)
    if not v:
        raise fail(404, "not_found", "This verse is not in the data.")
    return rag._source(v[0], 1)


# ------------------------------------------------------------------ ayah / hadith of the day: counters

DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ITEM_RE = re.compile(r"^(q\d{1,3}:\d{1,3}|h\d{1,5}(\.\d{1,2})?)$")


class DailyAct(BaseModel):
    day: str
    key: str
    action: str   # like | unlike | download | share


@app.get("/daily/{day}/stats")
def daily_stats(day: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """How many people liked / downloaded / shared each image of that day (numbers only, no names)."""
    if not DAY_RE.match(day):
        raise fail(422, "invalid_input", "Bad date.")
    rows = db.execute(
        select(DailyReaction.item, DailyReaction.action, func.count()).where(DailyReaction.day == day).group_by(DailyReaction.item, DailyReaction.action)
    ).all()
    counts: dict = {}
    for item, action, n in rows:
        counts.setdefault(item, {})[action] = n
    mine: dict = {}
    for item, action in db.execute(select(DailyReaction.item, DailyReaction.action).where(DailyReaction.day == day, DailyReaction.user_id == user.id)).all():
        mine.setdefault(item, []).append(action)
    return {"counts": counts, "mine": mine}


@app.post("/daily/act")
def daily_act(body: DailyAct, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not DAY_RE.match(body.day) or not ITEM_RE.match(body.key) or body.action not in ("like", "unlike", "download", "share"):
        raise fail(422, "invalid_input", "Bad request.")
    action = "like" if body.action == "unlike" else body.action
    existing = db.execute(
        select(DailyReaction).where(DailyReaction.user_id == user.id, DailyReaction.day == body.day, DailyReaction.item == body.key, DailyReaction.action == action)
    ).scalar_one_or_none()
    if body.action == "unlike":
        if existing:
            db.delete(existing)
            db.commit()
    elif existing is None:           # a person counts once per image and action
        db.add(DailyReaction(user_id=user.id, day=body.day, item=body.key, action=action))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
    return {"ok": True}


# ------------------------------------------------------------------ Contact us


class ContactIn(BaseModel):
    kind: str = Field(max_length=12)
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(max_length=254)
    phone: str = Field(min_length=7, max_length=30)
    message: str = Field(min_length=10, max_length=3000)
    info: str = Field(default="", max_length=300)


@app.post("/contact")
def contact(body: ContactIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.kind not in ("like", "problem", "mistake", "idea", "other"):
        raise fail(422, "invalid_input", "Bad type.")
    email = clean_email(body.email)
    digits = re.sub(r"\D", "", body.phone)
    if not re.fullmatch(r"[0-9+()\-\s]{7,30}", body.phone) or not 7 <= len(digits) <= 15:
        raise fail(422, "bad_phone", "Please enter a valid phone number.")
    since = utcnow() - timedelta(hours=1)
    recent = db.execute(select(func.count()).select_from(ContactMsg).where(ContactMsg.user_id == user.id, ContactMsg.created_at > since)).scalar() or 0
    if recent >= 5:
        raise fail(429, "too_many", "Too many messages. Please try again in an hour.")
    rec = ContactMsg(user_id=user.id, kind=body.kind, name=body.name.strip(), email=email, phone=body.phone.strip(), message=body.message.strip(), info=body.info.strip())
    db.add(rec)
    db.commit()
    sent = mailer.send_contact({"user_id": user.id, "kind": rec.kind, "name": rec.name, "email": rec.email, "phone": rec.phone, "message": rec.message,
                                "account_email": user.email, "info": rec.info, "when": rec.created_at.strftime("%Y-%m-%d %H:%M")})
    rec.mailed = sent
    db.commit()
    return {"ok": True, "mailed": sent}
