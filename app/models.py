"""Data models for the interior design quotation MCP server.

Kept intentionally simple: plain Pydantic models with basic field
validation only. No nested business logic lives here.
"""

from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class Unit(str, Enum):
    """Unit of measurement for a line item, as seen in the reference quote."""

    SFT = "sft"   # square feet, amount = width * height * qty * rate
    NOS = "Nos"   # count based, amount = qty * rate
    LS = "LS"     # lump sum, amount = rate


class ClientInfo(BaseModel):
    """Basic client / project details shown in the quotation header."""

    name: str
    location: str
    date: str  # e.g. "07-03-2026" - kept as string, no date logic needed


class LineItem(BaseModel):
    """A single row in the quotation table.

    width/height are in feet. For SFT items, area = width * height.
    For Nos/LS items, width/height/depth are simply left at 0.
    """

    description: str
    width: float = 0
    height: float = 0
    depth: float = 0
    qty: float = 1
    unit: Unit = Unit.SFT
    rate: float = 0


class Section(BaseModel):
    """A named group of line items, e.g. 'Living Area', 'Bedroom 1'."""

    name: str
    items: List[LineItem] = Field(default_factory=list)


class PaymentStage(BaseModel):
    """One row of the payment schedule, e.g. 'Booking Advance', 30%."""

    label: str
    percent: float


class QuotationRequest(BaseModel):
    """Full input payload for creating a quotation."""

    client: ClientInfo
    sections: List[Section]
    gst_percent: float = 18.0
    transport_charge: float = 0.0
    payment_split: List[PaymentStage] = Field(default_factory=list)
