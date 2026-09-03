"""Builds the full computed quotation from a QuotationRequest.

This is the single place that calls the calculation functions in
order and assembles their results into one plain dict. Keeping this
separate from models/calculations keeps each file small and focused.
"""

from typing import Any, Dict

from app.models import QuotationRequest
import app.quotation.calculations as calc


def build_quotation(request: QuotationRequest) -> Dict[str, Any]:
    """Compute every figure needed for the quotation, section by section."""

    computed_sections = []
    for section in request.sections:
        items = []
        for item in section.items:
            items.append({
                "description": item.description,
                "width": item.width,
                "height": item.height,
                "depth": item.depth,
                "qty": item.qty,
                "unit": item.unit.value,
                "rate": item.rate,
                "area": calc.item_area(item),
                "amount": calc.item_amount(item),
            })
        computed_sections.append({
            "name": section.name,
            "items": items,
            "section_total": calc.section_total(section),
        })

    overall = calc.overall_total(request.sections)
    gst = calc.gst_amount(overall, request.gst_percent)
    final = calc.final_total(overall, gst, request.transport_charge)
    rounded = calc.round_off_total(final)
    schedule = calc.payment_schedule(rounded, request.payment_split)

    return {
        "client": request.client.model_dump(),
        "sections": computed_sections,
        "gst_percent": request.gst_percent,
        "overall_total": overall,
        "gst_amount": gst,
        "transport_charge": request.transport_charge,
        "final_total": final,
        "round_off_total": rounded,
        "payment_schedule": schedule,
    }
