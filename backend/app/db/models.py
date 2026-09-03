"""
Read-only mirror of the tables the Quotation MCP server owns and writes to
(leads, quotations). The backend never writes here -- it only queries, so the
frontend can fetch quotation details without re-running the graph.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Quotation(Base):
    __tablename__ = "quotations"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(100))
    lead_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    property_type: Mapped[str] = mapped_column(String(50))
    location: Mapped[str] = mapped_column(String(100))
    budget: Mapped[int] = mapped_column(Integer)
    style: Mapped[str] = mapped_column(String(50))

    breakdown: Mapped[dict] = mapped_column(JSON)
    total: Mapped[int] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(String(30))
    pdf_filename: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
