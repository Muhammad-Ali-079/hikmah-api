"""Database tables (SQLAlchemy 2.0). Works with SQLite on your PC and free Postgres (Neon) online."""
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from . import config


def utcnow() -> datetime:
    """Naive UTC time (the same in SQLite and Postgres)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(config.DATABASE_URL, pool_pre_ping=True, pool_recycle=300, connect_args=_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(60))
    pw_hash: Mapped[str] = mapped_column(String(200))
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0)   # +1 = every old login token stops working
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    lang: Mapped[str] = mapped_column(String(5), default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    codes: Mapped[List["EmailCode"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class EmailCode(Base):
    __tablename__ = "email_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(10))          # "verify" or "reset"
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)

    user: Mapped[User] = relationship(back_populates="codes")


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class ChatUse(Base):
    """How many questions a person asked today (keeps the free LLM quota safe)."""
    __tablename__ = "chat_use"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    day: Mapped[str] = mapped_column(String(10), index=True)   # YYYY-MM-DD (UTC)
    count: Mapped[int] = mapped_column(Integer, default=0)


class DailyReaction(Base):
    """One like / download / share of one ayah or hadith on one day. Only counted; names are never shown to anyone."""
    __tablename__ = "daily_reactions"
    __table_args__ = (UniqueConstraint("user_id", "day", "item", "action", name="uq_daily_reaction"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    day: Mapped[str] = mapped_column(String(10), index=True)      # 2026-11-08
    item: Mapped[str] = mapped_column(String(20))                 # q2:255  or  h1
    action: Mapped[str] = mapped_column(String(10))               # like | download | share
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ContactMsg(Base):
    """Every message sent from the Contact us page. Kept in the database too, so nothing is lost if the email fails."""
    __tablename__ = "contact_msgs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(12))
    name: Mapped[str] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(254))
    phone: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(String(3000))
    info: Mapped[str] = mapped_column(String(300), default="")      # app language, phone model / system
    mailed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
