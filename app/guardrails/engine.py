"""The topical guardrail that runs BEFORE the router.

Primary path: NVIDIA **NeMo Guardrails** — an input rail ('self check input', configured in ./config)
decides whether the message is on-topic (orders / cart / products / tickets / company documents).
If it's off-topic the rail returns a FIXED refusal message and we never reach the router/LLM agents.

Fallback: if `nemoguardrails` isn't installed in the environment, we use a small OpenAI topical
classifier with the SAME allowed topics, so the app still runs and behaves the same way.
"""
import json
import os

from ..config import get_settings

settings = get_settings()

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "config")
REFUSAL = (
    "I can only help with your questions answered by "
    "our company documents. Please ask me something about one of those."
)

_rails = None            # cached LLMRails instance
_use_nemo: bool | None = None


def _ensure_openai_key():
    if settings.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key


def get_rails():
    """Load (once) the NeMo LLMRails from ./config. Returns None if NeMo isn't available."""
    global _rails, _use_nemo
    if _use_nemo is False:
        return None
    print("get_rails",_rails)
    if _rails is None:
        try:
            _ensure_openai_key()
            from nemoguardrails import LLMRails, RailsConfig
            cfg = RailsConfig.from_path(CONFIG_DIR)
            _rails = LLMRails(cfg)
            _use_nemo = True
            print("[guardrails] NeMo Guardrails loaded.")
        except Exception as exc:
            print(f"[guardrails] NeMo unavailable, using fallback classifier: {exc}")
            _use_nemo = False
            _rails = None
    return _rails


def reload_rails():
    """Drop the cached rails so the next call picks up a freshly regenerated prompts.yml."""
    global _rails
    _rails = None


def _current_topics() -> list[str]:
    try:
        with open(settings.guardrails_path) as f:
            topics = json.load(f).get("topics")
            if topics:
                return topics
    except Exception:
        pass
    return [
        # "client information as name, location, address, date",
        # "quotation calculated in table as S.No, Description, Width(W), Height(H), Dimension(D), Qty/Area, Unit, Reference, Amountcompany policies: material specifications, warranty, services, timelines (from company documents)",
        # "company policies: material specifications, warranty, services, timelines, note"
        "attention mechanisms",
        "transformer architecture",
        "neural networks",
        "machine reading"   
    ]


_REFUSAL_MARK = "i can only help with your questions"   # distinctive slice of the fixed refusal


async def _nemo_guard(rails, question: str) -> tuple[bool, str]:
    # run ONLY the input rails (no dialog/answer generation) — pure gate.
    print('question',question)
    result = await rails.generate_async(
        messages=[{"role": "user", "content": question}],
        options={"rails": {"input": True, "dialog": False, "output": False, "retrieval": False}},
    )
    print("_nemo_guard result", result)
    resp = getattr(result, "response", result)
    content = ""
    if isinstance(resp, list) and resp:
        last = resp[-1]
        content = last.get("content", "") if isinstance(last, dict) else str(last)
    elif isinstance(resp, dict):
        content = resp.get("content", "")
    elif isinstance(resp, str):
        content = resp
    # BLOCKED only when the rail returned our fixed refusal. For allowed input, NeMo (with dialog off)
    # returns the original/empty message — which must NOT be treated as a block.
    print("content",content)
    blocked = _REFUSAL_MARK in content.lower()
    return (not blocked), (REFUSAL if blocked else "")


async def _fallback_guard(question: str) -> tuple[bool, str]:
    print("_fallback_guard called")
    from ..rag.clients import openai_client
    topics = "\n".join(f"- {t}" for t in _current_topics())
    print('topics',topics)
    client = openai_client()
    resp = await client.chat.completions.create(
        model=settings.router_model, temperature=0,
        messages=[
            {"role": "system", "content":
                "You are a topic gate for a company act as a assistant. Allowed topics:\n"
                f"{topics}\n"
                "If the user message is NOT about any allowed topic, answer exactly 'BLOCK'. Otherwise answer 'OK'."},
            {"role": "user", "content": question},
        ],
    )
    verdict = resp.choices[0].message.content.strip().upper()
    return (False, REFUSAL) if verdict.startswith("BLOCK") else (True, "")


async def guard_input(question: str) -> tuple[bool, str]:
    """Return (allowed, refusal_message). Off-topic -> (False, fixed message)."""
    try:
        rails = get_rails()
        if rails is not None:
            return await _nemo_guard(rails, question)
        return await _fallback_guard(question)
    except Exception as exc:
        print(f"[guardrails] check errored, allowing through: {exc}")
        return True, ""
