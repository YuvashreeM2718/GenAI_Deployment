"""All quotation math lives here as small, pure functions.

Every function does one basic arithmetic operation. No frameworks,
no hidden state, easy to unit test line by line.
"""

from typing import List

from app.models import LineItem, PaymentStage, Section, Unit
from app.config import ROUND_OFF_STEP


def item_area(item: LineItem) -> float:
    """Return the measured quantity/area for a line item.

    - SFT items: width * height (matches the 'Qty/Area' column
      in the reference quote, e.g. 7.0 x 1.5 = 10.5 sft).
    - Nos / LS items: just the qty (e.g. 1, 2, 4 nos).
    """
    if item.unit == Unit.SFT:
        return round(item.width * item.height, 2)
    return item.qty


def item_amount(item: LineItem) -> float:
    """Return the amount for one line item.

    - SFT: width * height * qty * rate
    - Nos: qty * rate
    - LS : rate (a fixed lump sum, qty is ignored)
    """
    if item.unit == Unit.SFT:
        return round(item.width * item.height * item.qty * item.rate, 2)
    if item.unit == Unit.NOS:
        return round(item.qty * item.rate, 2)
    return round(item.rate, 2)  # LS


def section_total(section: Section) -> float:
    """Sum of all item amounts within a section."""
    return round(sum(item_amount(item) for item in section.items), 2)


def overall_total(sections: List[Section]) -> float:
    """Sum of all section totals."""
    return round(sum(section_total(s) for s in sections), 2)


def gst_amount(overall: float, gst_percent: float) -> float:
    """GST value on the overall total."""
    return round(overall * gst_percent / 100, 2)


def final_total(overall: float, gst: float, transport_charge: float) -> float:
    """Overall total + GST + transport charge."""
    return round(overall + gst + transport_charge, 2)


def round_off_total(amount: float, step: int = ROUND_OFF_STEP) -> float:
    """Round amount to the nearest `step` (default nearest 1000)."""
    return round(amount / step) * step


def payment_schedule(total: float, stages: List[PaymentStage]) -> List[dict]:
    """Split `total` across payment stages using each stage's percent.

    Returns a list of {label, percent, amount} dicts. Purely
    percent * total / 100, no rounding rules beyond 2 decimals.
    """
    schedule = []
    for stage in stages:
        amount = round(total * stage.percent / 100, 2)
        schedule.append({
            "label": stage.label,
            "percent": stage.percent,
            "amount": amount,
        })
    return schedule
