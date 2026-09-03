"""
Config for the Quotation MCP server. Kept separate from the main backend's
config since this runs as an independent service.
"""
from dotenv import load_dotenv
load_dotenv()
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Server
    mcp_host: str = ""
    mcp_port: int = 9000
    # Base URL other services use to reach this server's HTTP routes (e.g. PDFs)
    public_base_url: str = "http://localhost:9000"

    # Database (separate DB/schema from the backend's own Postgres, or the
    # same instance with a different database name -- either works)
    database_url: str = ""

    # PDF storage
    pdf_output_dir: str = "generated_pdfs"

    # Email (SMTP) -- if unset, send_email() simulates instead of sending
    smtp_host: str | None = ""
    smtp_port: int = 587
    smtp_username: str | None = ""
    smtp_password: str | None = ""
    smtp_from_address: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
