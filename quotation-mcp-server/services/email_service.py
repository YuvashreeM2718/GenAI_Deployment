"""
Sends the quotation email. If SMTP credentials aren't configured (typical
for local dev), it simulates the send and logs instead -- so the pipeline
still runs end-to-end without a real mail server.
"""

import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import settings


def send_quotation_email(to_email: str, quotation_id: str, total: int, pdf_path: str | None) -> dict:
    subject = f"Your Interior Design Quotation ({quotation_id})"
    body = (
        f"Hi,\n\nThanks for reaching out. Your estimated quotation total is "
        f"Rs. {total:,}.\n\nPlease find the detailed quotation attached.\n\n"
        f"Best,\nInterior Design Team"
    )

    if not settings.smtp_host:
        # No SMTP configured -- simulate so local/dev pipelines still work end-to-end.
        print(f"[email_service] SIMULATED send to {to_email}: {subject}")
        return {"status": "simulated", "to": to_email}

    message = MIMEMultipart()
    message["From"] = settings.smtp_from_address
    message["To"] = to_email
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain"))

    if pdf_path:
        with open(pdf_path, "rb") as f:
            attachment = MIMEApplication(f.read(), _subtype="pdf")
            attachment.add_header("Content-Disposition", "attachment", filename=f"{quotation_id}.pdf")
            message.attach(attachment)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        server.login(settings.smtp_username, settings.smtp_password)
        server.sendmail(settings.smtp_from_address, to_email, message.as_string())

    return {"status": "sent", "to": to_email}
