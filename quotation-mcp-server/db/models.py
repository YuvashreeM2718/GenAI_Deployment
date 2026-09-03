"""
Database models for the Quotation MCP server.
Three simple tables: leads, quotations, consultations. No heavy ORM logic --
plain columns, plain relationships.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(20), unique=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Quotation(Base):
    __tablename__ = "quotations"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)  # e.g. "Q-3F9A2B1C"
    session_id: Mapped[str] = mapped_column(String(100))
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id"), nullable=True)

    property_type: Mapped[str] = mapped_column(String(50))
    location: Mapped[str] = mapped_column(String(100))
    budget: Mapped[int] = mapped_column(Integer)
    style: Mapped[str] = mapped_column(String(50))

    breakdown: Mapped[dict] = mapped_column(JSON)
    total: Mapped[int] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(String(30), default="created")  # created | pdf_ready | emailed
    pdf_filename: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Consultation(Base):
    __tablename__ = "consultations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id"), nullable=True)
    quotation_id: Mapped[str | None] = mapped_column(ForeignKey("quotations.id"), nullable=True)

    preferred_date: Mapped[str] = mapped_column(String(20))   # "2026-09-15"
    preferred_time: Mapped[str] = mapped_column(String(20))   # "10:00 AM"
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="scheduled")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
