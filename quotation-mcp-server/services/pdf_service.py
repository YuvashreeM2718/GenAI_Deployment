"""
Generates a simple, clean quotation PDF using ReportLab.
One function, one table -- no fancy layout logic.
"""

import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from config import settings


def generate_quotation_pdf(quotation) -> str:
    """
    Build a PDF for the given Quotation row and save it to disk.
    Returns the filename (not full path) -- the caller builds the public URL.
    """
    os.makedirs(settings.pdf_output_dir, exist_ok=True)
    filename = f"{quotation.id}.pdf"
    filepath = os.path.join(settings.pdf_output_dir, filename)

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(filepath, pagesize=A4, topMargin=25 * mm, bottomMargin=20 * mm)

    elements = [
        Paragraph("Interior Design Quotation", styles["Title"]),
        Spacer(1, 6),
        Paragraph(f"Quotation ID: {quotation.id}", styles["Normal"]),
        Paragraph(f"Property: {quotation.property_type} — {quotation.location}", styles["Normal"]),
        Paragraph(f"Style: {quotation.style.title()}", styles["Normal"]),
        Paragraph(f"Stated Budget: Rs. {quotation.budget:,}", styles["Normal"]),
        Spacer(1, 16),
    ]

    table_data = [["Category", "Estimated Cost (Rs.)"]]
    for category, price in quotation.breakdown.items():
        table_data.append([category, f"{price:,}"])
    table_data.append(["Total", f"{quotation.total:,}"])

    table = Table(table_data, colWidths=[300, 150])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E4053")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EAECEE")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(table)
    elements.append(Spacer(1, 20))
    elements.append(
        Paragraph(
            "This is an estimate based on standard scope of work. "
            "Final pricing may vary after a design consultation.",
            styles["Italic"],
        )
    )

    doc.build(elements)
    return filename
