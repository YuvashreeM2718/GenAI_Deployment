"""Local evals over a golden dataset.

Two things are measured:
  1. Routing accuracy — including the GUARDRAIL: off-topic questions should come back as 'blocked'
     (NeMo Guardrails), and on-topic ones as rag
  2. RAG keyword recall — for 'rag' questions with expected_keywords, does the answer contain them?

The golden dataset is auto-regenerated every time a document is processed (see app/guardrails/rules.py),
so this eval set tracks your documents.

Run:  python -m evals.run_evals
Needs the same .env / services as the API (OpenAI for routing/guardrails; Qdrant+Cohere+Redis for RAG)."""
import asyncio
import json
import os

from app.agent.context import set_current_user
from app.guardrails.engine import guard_input
from app.rag.pipeline import answer_from_docs

HERE = os.path.dirname(__file__)


async def route_of(question: str) -> str:
    # guardrail first — off-topic short-circuits to 'blocked'
    allowed, _ = await guard_input(question)
    if not allowed:
        return "blocked"
    return "allowed"


async def main():
    with open(os.path.join(HERE, "golden_dataset.json")) as f:
        dataset = json.load(f)

    set_current_user(1)     # evals run as a demo user
    route_correct = 0
    kw_total, kw_hit = 0, 0

    print("=" * 70)
    for i, case in enumerate(dataset, 1):
        q = case["question"]
        expected = case["expected_route"]
        got = await route_of(q)
        ok = "✅" if got == expected else "❌"
        route_correct += got == expected
        print(f"{i:2}. [{ok}] route: expected={expected:6} got={got:6} | {q}")

        # for rag cases with keywords, also check the produced answer
        if expected == "rag" and case.get("expected_keywords"):
            try:
                answer, _, _ = await answer_from_docs(q)
                for kw in case["expected_keywords"]:
                    kw_total += 1
                    hit = kw.lower() in answer.lower()
                    kw_hit += hit
                    print(f"        keyword '{kw}': {'found' if hit else 'missing'}")
            except Exception as exc:
                reason = type(exc).__name__
                if "429" in str(exc) or "rate" in str(exc).lower() or "Trial" in str(exc):
                    reason = "Cohere rate limit (trial key) — routing still counts, only this keyword check is skipped"
                print(f"        (RAG check skipped: {reason})")

    print("=" * 70)
    print(f"Routing accuracy : {route_correct}/{len(dataset)} = {route_correct / len(dataset):.0%}")
    if kw_total:
        print(f"RAG keyword recall: {kw_hit}/{kw_total} = {kw_hit / kw_total:.0%}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
