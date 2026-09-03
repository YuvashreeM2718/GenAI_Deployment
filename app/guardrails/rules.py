"""Auto-updating guardrails + golden dataset.

Called after an admin processes a new document. From a sample of the document text we ask the LLM to:
  1. name the new allowed TOPICS  -> baked into NeMo's self_check_input prompt (config/prompts.yml)
  2. produce answering RULES       -> saved to guardrails.json and injected into the RAG answer prompt
  3. write fresh GOLDEN eval cases  -> evals/golden_dataset.json (RAG questions from the docs + fixed cases)

So both the guardrails and the eval set track the documents automatically.
"""
import json
import os

from ..config import get_settings
from ..rag.clients import openai_client
from ..rag.ingest import sample_document_text
from .engine import CONFIG_DIR, reload_rails

settings = get_settings()

PROMPTS_PATH = os.path.join(CONFIG_DIR, "prompts.yml")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))  
GOLDEN_PATH = os.path.join(PROJECT_ROOT, "evals", "golden_dataset.json")

FIXED_TOPICS = [
    # "client information as name, location, address, date",
    # "quotation calculated in table as S.No, Description, Width(W), Height(H), Dimension(D), Qty/Area, Unit, Reference, Amount",
    # "material specifications",
    # "product specifications",
    # "warranty information",
    # "service period details",
    # "customization options",
    # "payment schedule",
    # "installation checks",
    # "company policies",
    # "notes"
    "attention mechanisms",
    "transformer architecture",
    "neural networks",
    "machine reading"
]

DEFAULT_RULES = [
    "Answer only from the provided company documents; never invent policies, prices, or dates.",
    "If the answer is not in the documents, say you could not find it.",
    "Do not give legal, medical, or financial advice.",
]

# order/cart/ticket + off-topic cases are always part of the eval set
FIXED_CASES = [
    {"question": "What BLEU score did the Transformer achieve for English-to-German translation?", "expected_route": "allowed"},
    {"question": "How long did it take to train the big Transformer model?", "expected_route": "allowed"},
    {"question": "What is the training cost of the Transformer compared to previous models?", "expected_route": "allowed"},
    {"question": "What dropout rate was used for the big Transformer model in English-to-French translation?", "expected_route": "allowed"},
    {"question": "Which model achieved the highest BLEU score for English-to-French translation?", "expected_route": "allowed"},
    {"question": "Who won the football world cup in 2018?", "expected_route": "blocked"},
    {"question": "Who is the PM of India?", "expected_route": "blocked"},
    {"question": "Write a story about 'A Lion King'", "expected_route": "blocked"},
    {"question": "Write me a Python script to scrape a website", "expected_route": "blocked"},
]


def load_guardrails() -> str:
    """Answering rules (bullet string) used inside the RAG answer prompt."""
    rules = DEFAULT_RULES
    try:
        with open(settings.guardrails_path) as f:
            saved = json.load(f).get("rules")
            if saved:
                rules = saved
    except FileNotFoundError:
        pass
    return "\n".join(f"- {r}" for r in rules)


def _write_prompts_yml(topics: list[str]) -> None:
    bullets = "\n".join(f"      - {t}" for t in topics)
    content = (
        "prompts:\n"
        "  - task: self_check_input\n"
        "    content: |\n"
        "      You are the topic gate for a company act as a assistant.\n\n"
        "      The assistant may ONLY help with these topics:\n"
        f"{bullets}\n\n"
        "      Block the message if it is NOT about any of the allowed topics — for example general\n"
        "      knowledge, coding, math, politics, other companies, celebrities, jokes, or personal advice.\n\n"
        '      User message: "{{ user_input }}"\n\n'
        "      Question: Should the user message be blocked (answer Yes or No)?\n"
        "      Answer:\n"
    )
    with open(PROMPTS_PATH, "w") as f:
        f.write(content)


async def refresh_guardrails() -> tuple[list[str], list[str]]:
    """Regenerate topics (NeMo prompt) + answering rules (guardrails.json) from the current docs."""
    sample = await sample_document_text()
    topics = list(FIXED_TOPICS)
    rules = list(DEFAULT_RULES)

    if sample.strip():
        try:
            client = openai_client()
            resp = await client.chat.completions.create(
                model=settings.router_model, temperature=0,
                messages=[
                    {"role": "system", "content":
                        "From the company document sample, return ONLY a JSON object with two arrays:\n"
                        '  "topics": 4-8 short phrases naming subjects the assistant should now answer '
                        '(e.g. "return window", "international shipping", "warranty claims").\n'
                        '  "rules": 4-7 short imperative answering rules. Keep these baselines: only answer '
                        "from the documents, never hallucinate, no legal/medical/financial advice."},
                    {"role": "user", "content": sample},
                ],
            )
            text = resp.choices[0].message.content.strip()
            text = text[text.find("{"): text.rfind("}") + 1]
            data = json.loads(text)
            doc_topics = [str(t) for t in data.get("topics", []) if str(t).strip()]
            if doc_topics:
                topics = FIXED_TOPICS + doc_topics
            if data.get("rules"):
                rules = [str(r) for r in data["rules"]]
        except Exception as exc:
            print(f"[guardrails] topic/rule generation failed, using defaults: {exc}")

    os.makedirs(os.path.dirname(settings.guardrails_path) or ".", exist_ok=True)
    with open(settings.guardrails_path, "w") as f:
        json.dump({"topics": topics, "rules": rules}, f, indent=2)

    _write_prompts_yml(topics)     # update NeMo's input-rail prompt
    reload_rails()                 # next request reloads rails with the new topics
    return topics, rules


async def refresh_golden_dataset() -> int:
    """Rewrite evals/golden_dataset.json: doc-derived RAG questions + fixed db/ticket/off-topic cases."""
    cases: list[dict] = []
    sample = await sample_document_text()
    if sample.strip():
        try:
            client = openai_client()
            resp = await client.chat.completions.create(
                model=settings.router_model, temperature=0,
                messages=[
                    {"role": "system", "content":
                        "From the company document sample, write 5 realistic customer questions answerable "
                        "from these documents. Return ONLY a JSON array; each item: "
                        '{"question": str, "expected_keywords": [1-2 lowercase words expected in the answer]}.'},
                    {"role": "user", "content": sample},
                ],
            )
            text = resp.choices[0].message.content.strip()
            text = text[text.find("["): text.rfind("]") + 1]
            for c in json.loads(text):
                cases.append({
                    "question": str(c["question"]),
                    "expected_route": "rag",
                    "expected_keywords": [str(k).lower() for k in c.get("expected_keywords", [])],
                })
        except Exception as exc:
            print(f"[golden] generation failed, using fixed cases only: {exc}")

    cases = cases + FIXED_CASES
    os.makedirs(os.path.dirname(GOLDEN_PATH), exist_ok=True)
    with open(GOLDEN_PATH, "w") as f:
        json.dump(cases, f, indent=2)
    return len(cases)


async def refresh_all() -> None:
    """One call after a document is ingested: guardrails + golden dataset both updated."""
    await refresh_guardrails()
    await refresh_golden_dataset()
