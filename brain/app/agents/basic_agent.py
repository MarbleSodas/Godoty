from __future__ import annotations

import os


def generate_reply(user_text: str) -> tuple[str, dict]:
    """MVP reply function.

    Next step: swap to Agno Agent routed through LiteLLM.
    For now, keep the server functional without external config.
    """
    base_url = os.getenv("GODOTY_LITELLM_BASE_URL")
    model = os.getenv("GODOTY_MODEL")

    if not base_url or not model:
        return (
            "Godoty brain is running. Set GODOTY_LITELLM_BASE_URL and GODOTY_MODEL to enable LLM replies.",
            {"token_usage": None},
        )

    # Placeholder until we wire Agno+LiteLLM properly.
    return (f"(stub) You said: {user_text}", {"token_usage": None})
