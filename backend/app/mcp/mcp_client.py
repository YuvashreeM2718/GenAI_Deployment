"""
Client for the externally-built Quotation MCP server.
No tool logic lives here -- this just opens a session, calls one tool,
and returns its result as a plain dict. Kept deliberately stateless and simple.
"""

import json

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.config import settings


async def call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    """
    Call a single tool on the Quotation MCP server and return its result.
    Opens a fresh connection per call -- fine for this workload's volume.
    """
    async with streamable_http_client(settings.mcp_server_url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)

            for block in result.content:
                if hasattr(block, "text"):
                    try:
                        return json.loads(block.text)
                    except json.JSONDecodeError:
                        return {"raw": block.text}
            return {}
