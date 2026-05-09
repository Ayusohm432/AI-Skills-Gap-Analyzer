"""
nlp/llm_interview.py
====================
Thin adapter layer for the conversational mock interview.

All provider logic (Gemini, Ollama, etc.) lives in nlp/llm_providers.py.
This module exists for backwards compatibility with routes/interview.py.

To switch providers, set the LLM_PROVIDER environment variable:
  LLM_PROVIDER=gemini   (default)
  LLM_PROVIDER=ollama
"""

from __future__ import annotations

import logging
from typing import List, Dict

from nlp.llm_providers import get_llm_provider, BaseLLMProvider

logger = logging.getLogger(__name__)


class InterviewLLM:
    """
    Backwards-compatible wrapper.
    Delegates all calls to the active LLM provider selected by LLM_PROVIDER env var.
    """

    def __init__(self):
        self._provider: BaseLLMProvider = get_llm_provider()

    async def start_session(self, role: str, missing_skills: List[str]) -> str:
        """Returns the interviewer's opening greeting and first question."""
        return await self._provider.start_session(role, missing_skills)

    async def get_next_response(
        self,
        role: str,
        missing_skills: List[str],
        history: List[Dict[str, str]],
        user_message: str,
    ) -> str:
        """Returns the interviewer's next message."""
        return await self._provider.get_next_response(
            role, missing_skills, history, user_message
        )

