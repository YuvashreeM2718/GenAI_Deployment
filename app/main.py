
"""MCP server for the interior design company's quotation tool.

Exposes one tool, `create_quotation`, that takes client + line-item
data and returns a fully computed quotation as Markdown text plus a
generated PDF file path.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List
from datetime import date

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastmcp import FastMCP

from app.models import ClientInfo, PaymentStage, QuotationRequest, Section
from app.quotation.quotation import build_quotation
from app.quotation.formatter import to_markdown
from app.file_generator.pdf_generator import file_generation

mcp = FastMCP("interior-quotation-server")

@mcp.tool()
def create_quotation(
    client_name: str, 
    location: str,
    sections : List[Section],
    # sections: List[Dict[str, Any]],
    gst_percent: float = 18.0,
    transport_charge: float = 0.0,
    # payment_split: List[Dict[str, Any]] = [],
    payment_split: List[PaymentStage] = []
) -> Dict[str, Any]:
    """Create an interior design quotation for a client.

    Args:
        client_name: name of the client eg: "John"
        location: location of the client eg: "Chennai"
        sections: list of sections, each:
            {
              "name": "Living Area",
              "items": [
                {"description": "TV Base Unit", "width": 7.0, "height": 1.5,
                 "depth": 1.5, "qty": 1, "unit": "sft", "rate": 1565},
                ...
              ]
            }
            unit is one of "sft", "Nos", "LS".
        gst_percent: GST percentage applied to the overall total.
        transport_charge: Flat transportation/loading charge.
        payment_split: list of {"label": str, "percent": float} stages,
            percentages should sum to 100.

    Returns:
        A dict with the computed totals and the Markdown quotation text.
    """
    formatted_date = date.today().strftime("%d-%m-%Y")
    print("date",formatted_date)
    client = ClientInfo(name= client_name, location=location, date= formatted_date)

    request = QuotationRequest(
        client=client,
        sections=sections,
        gst_percent=gst_percent,
        transport_charge=transport_charge,
        payment_split=payment_split,
    )

    quotation = build_quotation(request)
    markdown = to_markdown(quotation)

    # safe_name = quotation["client"]["name"].replace(" ", "_")
    # pdf_path = generate_pdf(quotation, filename=f"Quotation_{safe_name}.pdf")

    # return {
    #     "overall_total": quotation["overall_total"],
    #     "gst_amount": quotation["gst_amount"],
    #     "final_total": quotation["final_total"],
    #     "round_off_total": quotation["round_off_total"],
    #     "payment_schedule": quotation["payment_schedule"],
    #     "markdown": markdown
    # }

    return {
            "quotation":quotation,
            "markdown": markdown
        }

@mcp.tool()
def generate_pdf(quotation: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a pdf file for the quotation information.
    
        Args:
            quotation : detailed information to write in pdf file
    
        Returns:
            A dict with the pdf file path.
        """
    safe_name = quotation["client"]["name"].replace(" ", "_")
    pdf_path = file_generation(quotation, filename=f"Quotation_{safe_name}.pdf")

    return { "pdf_path": pdf_path }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")  # stdio transport by default