"""
Quotation Generation MCP server.

Exposes 5 tools over MCP (streamable-http transport):
  create_quotation, generate_pdf, send_email,
  schedule_design_consultation, save_lead

Each tool is a plain function with type hints -- FastMCP derives the tool's
JSON schema from the signature + docstring automatically. No heavy logic:
each tool does one DB read/write plus, where relevant, one service call.
"""

import os
import uuid
from dotenv import load_dotenv
load_dotenv()
from mcp.server import MCPServer
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse

from config import settings
from db.models import Consultation, Lead, Quotation
from db.session import get_session, init_db
from services.email_service import send_quotation_email
from services.pdf_service import generate_quotation_pdf

mcp = MCPServer(
    name="quotation-server"
)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def create_quotation(
    session_id: str,
    property_type: str,
    location: str,
    budget: int,
    style: str,
    breakdown: dict,
    total: int,
) -> dict:
    """Create a new quotation record from a computed cost breakdown and return its ID.

        Args:
            session_id (str): The session ID associated with the quotation.
            property_type (str): The type of property (e.g., "apartment", "house").
            location (str): The location of the property.
            budget (int): The budget for the quotation.
            style (str): The design style for the quotation. (e.g., "modern", "minimal", "traditional", "contemporary").
            breakdown (dict): A dictionary containing the cost breakdown. (eg., {"flooring": 5000, "painting": 2000, "lighting": 1500}).
            total (int): The total cost of the quotation. (eg., 300000).

        Returns:
            dict: A dictionary containing the quotation ID, status, and total cost.
    
    """
    quotation_id = f"Q-{uuid.uuid4().hex[:8].upper()}"

    with get_session() as session:
        quotation = Quotation(
            id=quotation_id,
            session_id=session_id,
            property_type=property_type,
            location=location,
            budget=budget,
            style=style,
            breakdown=breakdown,
            total=total,
            status="created",
        )
        session.add(quotation)

    return {"quotation_id": quotation_id, "status": "created", "total": total}


@mcp.tool()
def generate_pdf(quotation_id: str) -> dict:
    """Generate a PDF for an existing quotation and return its download URL.
        Args:
            quotation_id (str): The ID of the quotation for which to generate a PDF.

        Returns:
            dict: A dictionary containing the quotation ID and the URL to download the generated PDF.    
    """
    with get_session() as session:
        quotation = session.get(Quotation, quotation_id)
        if quotation is None:
            return {"error": f"quotation {quotation_id} not found"}

        filename = generate_quotation_pdf(quotation)
        quotation.pdf_filename = filename
        quotation.status = "pdf_ready"
        session.add(quotation)

    return {
        "quotation_id": quotation_id,
        "url": f"{settings.public_base_url}/pdfs/{filename}",
    }


@mcp.tool()
def send_email(quotation_id: str, to_email: str) -> dict:
    """Email the generated PDF quotation to the given address.
        Args:
            quotation_id (str): The ID of the quotation to email.
            to_email (str): The recipient's email address.

        Returns:
            dict: A dictionary containing the status of the email sending operation.   
    """
    with get_session() as session:
        quotation = session.get(Quotation, quotation_id)
        if quotation is None:
            return {"error": f"quotation {quotation_id} not found"}

        if not quotation.pdf_filename:
            return {"error": "PDF not generated yet -- call generate_pdf first"}

        pdf_path = os.path.join(settings.pdf_output_dir, quotation.pdf_filename)
        result = send_quotation_email(
            to_email=to_email,
            quotation_id=quotation_id,
            total=quotation.total,
            pdf_path=pdf_path,
        )

        quotation.status = "emailed"
        session.add(quotation)

    return result


@mcp.tool()
def save_lead(name: str, phone: str, email: str = "", city: str = "") -> dict:
    """Save (or update) a lead's contact details, keyed by phone number.
        Args:
            name (str): The name of the lead.
            phone (str): The phone number of the lead.
            email (str, optional): The email address of the lead. Defaults to an empty string.
            city (str, optional): The city of the lead. Defaults to an empty string.

        Returns:
            dict: A dictionary containing the lead ID and status of the operation.
    """
    with get_session() as session:
        lead = session.query(Lead).filter(Lead.phone == phone).one_or_none()
        if lead is None:
            lead = Lead(name=name, phone=phone, email=email or None, city=city or None)
            session.add(lead)
            session.flush()
        else:
            lead.name = name
            lead.email = email or lead.email
            lead.city = city or lead.city

    return {"lead_id": lead.id, "status": "saved"}


@mcp.tool()
def schedule_design_consultation(
    lead_name: str,
    phone: str,
    preferred_date: str,
    preferred_time: str,
    notes: str = "",
) -> dict:
    """Schedule a design consultation, creating the lead if it doesn't exist yet.
        Args:
            lead_name (str): The name of the lead.
            phone (str): The phone number of the lead.
            preferred_date (str): The preferred date for the consultation (YYYY-MM-DD).
            preferred_time (str): The preferred time for the consultation (HH:MM).
            notes (str, optional): Additional notes for the consultation. Defaults to an empty string.

        Returns:
            dict: A dictionary containing the consultation ID, status, and scheduled date and time.
    """
    with get_session() as session:
        lead = session.query(Lead).filter(Lead.phone == phone).one_or_none()
        if lead is None:
            lead = Lead(name=lead_name, phone=phone)
            session.add(lead)
            session.flush()

        consultation = Consultation(
            lead_id=lead.id,
            preferred_date=preferred_date,
            preferred_time=preferred_time,
            notes=notes or None,
            status="scheduled",
        )
        session.add(consultation)
        session.flush()

    return {
        "consultation_id": consultation.id,
        "status": "scheduled",
        "date": preferred_date,
        "time": preferred_time,
    }


# ---------------------------------------------------------------------------
# Static PDF serving (so generate_pdf's returned URL is actually fetchable)
# ---------------------------------------------------------------------------

@mcp.custom_route("/pdfs/{filename}", methods=["GET"])
async def serve_pdf(request: Request):
    filename = request.path_params["filename"]
    filepath = os.path.join(settings.pdf_output_dir, filename)

    if not os.path.isfile(filepath):
        return JSONResponse({"error": "not found"}, status_code=404)

    return FileResponse(filepath, media_type="application/pdf")


if __name__ == "__main__":
    init_db()
    mcp.run(transport="streamable-http", host=settings.mcp_host, port=settings.mcp_port)
