"""The chat runs on behalf of ONE logged-in user. We stash that user's id in a ContextVar so the
SQL tools can read it themselves — the LLM never gets to choose the user_id."""
from contextvars import ContextVar

current_user_id: ContextVar[int] = ContextVar("current_user_id", default=0)


def set_current_user(user_id: int) -> None:
    current_user_id.set(user_id)


def get_current_user_id() -> int:
    return current_user_id.get()
