"""Turns a computed quotation dict into a Markdown string.

String building only - no calculations happen in this file.
"""

from typing import Any, Dict

from app.config import COMPANY_NAME, COMPANY_TAGLINE, CURRENCY_SYMBOL


def _money(value: float) -> str:
    """Format a number as currency with thousands separators."""
    return f"{CURRENCY_SYMBOL}{value:,.0f}"


def to_markdown(quotation: Dict[str, Any]) -> str:
    """Build the full Markdown quotation document."""
    client = quotation["client"]
    lines = []

    lines.append(f"# {COMPANY_NAME}")
    lines.append(f"*{COMPANY_TAGLINE}*")
    lines.append("")
    lines.append(f"**Client:** {client['name']}  ")
    lines.append(f"**Location:** {client['location']}  ")
    lines.append(f"**Date:** {client['date']}")
    lines.append("")

    for section in quotation["sections"]:
        lines.append(f"## {section['name']}")
        lines.append("")
        lines.append("| S.No | Description | W | H | D | Qty/Area | Unit | Amount |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for i, item in enumerate(section["items"], start=1):
            lines.append(
                f"| {i} | {item['description']} | {item['width']} | "
                f"{item['height']} | {item['depth']} | {item['area']} | "
                f"{item['unit']} | {_money(item['amount'])} |"
            )
        lines.append("")
        lines.append(f"**Section Total: {_money(section['section_total'])}**")
        lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Overall Total: **{_money(quotation['overall_total'])}**")
    lines.append(
        f"- GST ({quotation['gst_percent']}%): "
        f"**{_money(quotation['gst_amount'])}**"
    )
    lines.append(
        f"- Transportation Charges: **{_money(quotation['transport_charge'])}**"
    )
    lines.append(f"- Final Total: **{_money(quotation['final_total'])}**")
    lines.append(f"- Round-off Total: **{_money(quotation['round_off_total'])}**")
    lines.append("")

    if quotation["payment_schedule"]:
        lines.append("## Payment Schedule")
        lines.append("")
        lines.append("| Stage | % | Amount |")
        lines.append("|---|---|---|")
        for stage in quotation["payment_schedule"]:
            lines.append(
                f"| {stage['label']} | {stage['percent']}% | "
                f"{_money(stage['amount'])} |"
            )
        lines.append("")

    return "\n".join(lines)
