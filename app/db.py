# app/db.py
import datetime as dt
import os

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sentinel.db")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()


def _now():
    return dt.datetime.now(dt.UTC)


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    idempotency_key = Column(String, unique=True, index=True, nullable=False)
    time_seconds = Column(Float, nullable=False)
    amount = Column(Float, nullable=False)
    hour_of_day = Column(Integer, nullable=False)
    bucket = Column(Integer, nullable=False)  # score decile 0-9
    features = Column(JSON, nullable=False)
    score = Column(Float, nullable=False)
    source = Column(String, nullable=False)  # "model" or "fallback_rules"
    flagged = Column(Boolean, nullable=False, index=True)
    explanation = Column(JSON)
    summary = Column(String)
    created_at = Column(DateTime, default=_now)


class Review(Base):  # append-only audit trail
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), index=True, nullable=False)
    decision = Column(String, nullable=False)
    note = Column(String)
    reviewer_role = Column(String, nullable=False)
    created_at = Column(DateTime, default=_now)