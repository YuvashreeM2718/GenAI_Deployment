"""Renders a computed quotation dict into a PDF file using reportlab.

Only layout code lives here - all numbers are taken as-is from the
already-computed quotation dict (see quotation.py).
"""

import os
from typing import Any, Dict

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
import sys
import tempfile
from pathlib import Path

from app.config import COMPANY_NAME, COMPANY_TAGLINE, OUTPUT_DIR

# Anchor OUTPUT_DIR to this file's own location, not the process cwd.
# This is the key fix: __file__ is stable regardless of who launches the server or from where.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

HEADER_GREEN = colors.HexColor("#2f5233")
LIGHT_GREEN = colors.HexColor("#e7efe8")

# The base Helvetica font used by reportlab has no Rupee sign (Unicode)
# glyph, so it renders as a black box. Use "Rs." for PDF output instead.
# (Markdown output still uses the real symbol via config.CURRENCY_SYMBOL.)
PDF_CURRENCY_PREFIX = "Rs. "


def _money(value: float) -> str:
    return f"{PDF_CURRENCY_PREFIX}{value:,.0f}"


def _section_table(section: Dict[str, Any]) -> Table:
    """Build one reportlab Table for a single section's line items."""
    header = ["S.No", "Description", "W", "H", "D", "Qty/Area", "Unit", "Amount"]
    rows = [header]
    for i, item in enumerate(section["items"], start=1):
        rows.append([
            str(i),
            item["description"],
            item["width"],
            item["height"],
            item["depth"],
            item["area"],
            item["unit"],
            _money(item["amount"]),
        ])
    rows.append(["", "", "", "", "", "", "Section Total", _money(section["section_total"])])

    table = Table(rows, colWidths=[1.2 * cm, 6.5 * cm, 1.3 * cm, 1.3 * cm, 1.3 * cm, 1.8 * cm, 1.5 * cm, 2.6 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_GREEN),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, -1), (-1, -1), LIGHT_GREEN),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return table


def _ensure_writable_output_dir(preferred: Path) -> Path:
    """Try the preferred directory; fall back to a temp dir if it's not writable."""
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        probe = preferred / ".write_test"
        probe.write_text("ok")
        probe.unlink()
        return preferred
    except (PermissionError, OSError) as e:
        fallback = Path(tempfile.gettempdir()) / "quotation_server_data"
        fallback.mkdir(parents=True, exist_ok=True)
        print(f"[warn] '{preferred}' not writable ({e}); using fallback '{fallback}'", file=sys.stderr)
        return fallback

def file_generation(quotation: Dict[str, Any], filename: str) -> str:
    """Write the quotation PDF to OUTPUT_DIR and return its full path."""
    output_dir = _ensure_writable_output_dir(BASE_DIR / OUTPUT_DIR)
    path = str(output_dir / filename)

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(path, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    story = []

    client = quotation["client"]
    story.append(Paragraph(COMPANY_NAME, styles["Title"]))
    story.append(Paragraph(COMPANY_TAGLINE, styles["Italic"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"<b>Client:</b> {client['name']}", styles["Normal"]))
    story.append(Paragraph(f"<b>Location:</b> {client['location']}", styles["Normal"]))
    story.append(Paragraph(f"<b>Date:</b> {client['date']}", styles["Normal"]))
    story.append(Spacer(1, 16))

    for section in quotation["sections"]:
        story.append(Paragraph(section["name"], styles["Heading2"]))
        story.append(_section_table(section))
        story.append(Spacer(1, 12))

    summary_rows = [
        ["Overall Total", _money(quotation["overall_total"])],
        [f"GST ({quotation['gst_percent']}%)", _money(quotation["gst_amount"])],
        ["Transportation Charges", _money(quotation["transport_charge"])],
        ["Final Total", _money(quotation["final_total"])],
        ["Round-off Total", _money(quotation["round_off_total"])],
    ]
    summary_table = Table(summary_rows, colWidths=[10 * cm, 5 * cm])
    summary_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), LIGHT_GREEN),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
    ]))
    story.append(Paragraph("Summary", styles["Heading2"]))
    story.append(summary_table)
    story.append(Spacer(1, 16))

    if quotation["payment_schedule"]:
        schedule_rows = [["Stage", "%", "Amount"]]
        for stage in quotation["payment_schedule"]:
            schedule_rows.append([stage["label"], f"{stage['percent']}%", _money(stage["amount"])])
        schedule_table = Table(schedule_rows, colWidths=[8 * cm, 3 * cm, 4 * cm])
        schedule_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HEADER_GREEN),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ]))
        story.append(Paragraph("Payment Schedule", styles["Heading2"]))
        story.append(schedule_table)

    try:
        doc.build(story)
    except PermissionError as e:
        raise RuntimeError(
            f"Could not write PDF to '{path}': access denied. "
            f"Check that the server process has write permission to '{output_dir}'."
        ) from e

    return path