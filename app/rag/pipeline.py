"""The 'advanced RAG node' as one function: cache -> retrieve (hybrid+rerank) -> guarded vision answer.

Returns (answer, sources, cached). Used by the chat agent's RAG node and by the evals script."""
from .cache import lookup, store
from .retrieve import retrieve
# from .generate import generate
from ..guardrails.rules import load_guardrails


def _sources(context) -> list[str]:
    seen = {f'{p.payload["doc"]} p.{p.payload["page"]}' for p in context}
    return sorted(seen, key=lambda s: (s.rsplit(" p.", 1)[0], int(s.rsplit(" p.", 1)[1])))


async def answer_from_docs(question: str) -> tuple[str, list[str], bool]:
    # 1) semantic cache: similar question already answered? return instantly.
    hit = await lookup(question)
    if hit:
        answer, sources = hit
        return answer, sources, True

    # 2) retrieve: hybrid search + rerank
    context, primary = await retrieve(question)
    if not context:
        return "I couldn't find anything relevant in the company documents.", [], False

    # 3) generate a guarded answer with the vision LLM
    guardrails = load_guardrails()
    # answer = await generate(question, context, primary, guardrails)
    sources = _sources(context)

    # 4) remember it for next time
    await store(question, answer, sources)
    return answer, sources, False
