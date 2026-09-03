"""
Structured-output schemas for the LLM nodes.
Passed to get_structured_model() so LangChain/Ollama return validated
Pydantic objects instead of raw text we'd have to parse ourselves.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class IntentResult(BaseModel):
    intent: Literal["new_quotation", "faq", "unclear"] = Field(
        description=(
            "new_quotation: user wants interiors done / a quote, mentions BHK/budget/renovation. "
            "faq: general question about the service, not their own quote. "
            "unclear: greeting or small talk."
        )
    )


class SlotExtraction(BaseModel):
    property_type: Optional[str] = Field(
        default=None, description="e.g. '2BHK' or '3BHK', only if mentioned in this message"
    )
    budget: Optional[int] = Field(
        default=None,
        description="Budget in INR as an integer. Convert '15 lakh' -> 1500000, '1.2 crore' -> 12000000.",
    )
    location: Optional[str] = Field(default=None, description="City name, only if mentioned in this message")
    style: Optional[str] = Field(
        default=None,
        description="One of: modern, contemporary, traditional, minimal -- only if mentioned in this message",
    )
