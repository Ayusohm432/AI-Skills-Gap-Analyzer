"""
nlp/llm_providers.py
====================
Pluggable LLM provider system for the mock interview feature.

Supported providers:
  - gemini  (default) — Google Gemini via google-genai SDK
  - ollama            — Local Ollama server via its REST API

Configuration via environment variables:
  LLM_PROVIDER      = "gemini" | "ollama"   (default: "gemini")
  GEMINI_API_KEY    = <your key>             (required for gemini)
  OLLAMA_BASE_URL   = "http://localhost:11434" (default for ollama)
  OLLAMA_MODEL      = "llama3.2"             (default for ollama)

Adding a new provider:
  1. Subclass BaseLLMProvider and implement start_session() and get_next_response()
  2. Register it in get_llm_provider()
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("nlp.llm_providers")


# ── Shared utilities (reused from llm_interview.py) ──────────────────────────

import textwrap

_MAX_USER_MSG_CHARS = 6_000
_MAX_HISTORY_TURNS  = 10


def chunk_and_clean(text: str, chunk_size: int = 1_000) -> str:
    """Normalise and truncate a user message before sending to any LLM."""
    text = text.strip()
    if not text:
        return ""
    if len(text) > _MAX_USER_MSG_CHARS:
        logger.warning("Message truncated: %d → %d chars", len(text), _MAX_USER_MSG_CHARS)
        text = text[:_MAX_USER_MSG_CHARS] + "… [truncated]"
    return " ".join(textwrap.wrap(text, width=chunk_size, break_long_words=True))


def trim_history(history: list[dict]) -> list[dict]:
    """Keep only the last _MAX_HISTORY_TURNS conversation turns."""
    max_messages = _MAX_HISTORY_TURNS * 2
    if len(history) <= max_messages:
        return history
    trimmed = history[-max_messages:]
    logger.info("History trimmed: %d → %d messages", len(history), len(trimmed))
    return trimmed


# ── Abstract base ─────────────────────────────────────────────────────────────

class BaseLLMProvider(ABC):
    """All interview LLM providers must implement this interface."""

    @abstractmethod
    async def start_session(self, role: str, missing_skills: list[str]) -> str:
        """Return the interviewer's opening greeting and first question."""

    @abstractmethod
    async def get_next_response(
        self,
        role: str,
        missing_skills: list[str],
        history: list[dict[str, str]],
        user_message: str,
    ) -> str:
        """Return the interviewer's next message given the conversation so far."""

    # Shared prompt builder
    def system_instruction(self, role: str, missing_skills: list[str]) -> str:
        skills_str = ", ".join(missing_skills) if missing_skills else "general technical skills"
        return (
            f"You are an expert technical interviewer conducting a mock interview for a {role} position.\n"
            f"The candidate's identified skill gaps are: {skills_str}.\n\n"
            "Your goals:\n"
            "1. Conduct a professional, realistic technical interview.\n"
            "2. Focus questions on the identified skill gaps.\n"
            "3. Be encouraging but rigorous.\n"
            "4. Ask ONE question at a time.\n"
            "5. Provide brief, specific feedback on each answer before asking the next question.\n"
            "6. If the candidate asks for help, explain concisely and continue.\n"
        )


# ── Gemini Provider ───────────────────────────────────────────────────────────

class GeminiProvider(BaseLLMProvider):
    """Google Gemini via the google-genai SDK."""

    _MODELS = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    ]

    def __init__(self):
        try:
            from google import genai
            from google.genai import types as genai_types
            self._genai       = genai
            self._types       = genai_types
            api_key           = os.getenv("GEMINI_API_KEY")
            self._client      = genai.Client(api_key=api_key) if api_key else None
            if not api_key:
                logger.warning("[GeminiProvider] GEMINI_API_KEY not set.")
        except ImportError:
            logger.warning("[GeminiProvider] google-genai not installed.")
            self._client = None
            self._types  = None

    def _available(self) -> bool:
        return self._client is not None

    async def start_session(self, role: str, missing_skills: list[str]) -> str:
        if not self._available():
            return "[Gemini unavailable] Let's get started. Walk me through a recent project."

        prompt = self.system_instruction(role, missing_skills) + (
            "\n\nStart the interview now. Greet the candidate briefly and ask your first question."
        )
        return self._call(prompt)

    async def get_next_response(
        self,
        role: str,
        missing_skills: list[str],
        history: list[dict[str, str]],
        user_message: str,
    ) -> str:
        if not self._available():
            return "[Gemini unavailable] Interesting — can you elaborate?"

        safe_msg = chunk_and_clean(user_message)
        trimmed  = trim_history(history)
        system   = self.system_instruction(role, missing_skills)

        contents = []
        for turn in trimmed:
            sdk_role = "user" if turn["role"] == "user" else "model"
            contents.append({"role": sdk_role, "parts": [{"text": turn["content"]}]})
        contents.append({"role": "user", "parts": [{"text": safe_msg}]})

        return self._call_chat(contents, system)

    def _call(self, prompt: str) -> str:
        """Simple single-turn call (used for session start)."""
        for model in self._MODELS:
            try:
                resp = self._client.models.generate_content(model=model, contents=prompt)
                return resp.text.strip()
            except Exception as exc:
                if "429" in str(exc):
                    continue
                logger.error("[GeminiProvider] %s: %s", model, exc)
                return f"[API Error] Welcome! Tell me about a recent challenge."
        return "[Gemini quota exhausted] Let's begin — what project are you most proud of?"

    def _call_chat(self, contents: list, system: str) -> str:
        """Multi-turn chat call with system instruction."""
        for model in self._MODELS:
            try:
                resp = self._client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=self._types.GenerateContentConfig(system_instruction=system),
                )
                return resp.text.strip()
            except Exception as exc:
                if "429" in str(exc):
                    continue
                logger.error("[GeminiProvider] %s: %s", model, exc)
                return "[API Error] That's interesting — let's explore another area."
        return "[Gemini quota exhausted] How do you approach learning new tech quickly?"


# ── Ollama Provider ───────────────────────────────────────────────────────────

class OllamaProvider(BaseLLMProvider):
    """
    Local Ollama server via its native REST API.

    Ollama Chat API endpoint: POST /api/chat
    Expected format:
      { "model": "...", "messages": [...], "stream": false }
    Response:
      { "message": { "role": "assistant", "content": "..." } }

    Requires Ollama to be running locally: https://ollama.ai
    Pull a model first: `ollama pull llama3.2`
    """

    def __init__(self):
        self._base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        self._model    = os.getenv("OLLAMA_MODEL", "llama3.2")
        self._timeout  = 120.0  # local model generation can be slow

        logger.info(
            "[OllamaProvider] base_url=%s  model=%s", self._base_url, self._model
        )

    async def _chat(self, messages: list[dict]) -> str:
        """Call Ollama's /api/chat endpoint."""
        url     = f"{self._base_url}/api/chat"
        payload = {"model": self._model, "messages": messages, "stream": False}

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data["message"]["content"].strip()
            except httpx.ConnectError:
                raise RuntimeError(
                    f"Ollama is not running at {self._base_url}. "
                    "Start it with: `ollama serve`"
                )
            except httpx.HTTPStatusError as e:
                raise RuntimeError(f"Ollama API error {e.response.status_code}: {e.response.text}")
            except KeyError:
                raise RuntimeError("Unexpected Ollama response format")

    async def start_session(self, role: str, missing_skills: list[str]) -> str:
        system = self.system_instruction(role, missing_skills)
        messages = [
            {"role": "system",  "content": system},
            {"role": "user",    "content": "Start the interview — greet me briefly and ask your first question."},
        ]
        try:
            return await self._chat(messages)
        except Exception as exc:
            logger.error("[OllamaProvider] start_session failed: %s", exc)
            return f"[Ollama Error: {exc}] Let's begin — walk me through a recent project."

    async def get_next_response(
        self,
        role: str,
        missing_skills: list[str],
        history: list[dict[str, str]],
        user_message: str,
    ) -> str:
        safe_msg = chunk_and_clean(user_message)
        trimmed  = trim_history(history)
        system   = self.system_instruction(role, missing_skills)

        messages = [{"role": "system", "content": system}]
        for turn in trimmed:
            ollama_role = "user" if turn["role"] == "user" else "assistant"
            messages.append({"role": ollama_role, "content": turn["content"]})
        messages.append({"role": "user", "content": safe_msg})

        try:
            return await self._chat(messages)
        except Exception as exc:
            logger.error("[OllamaProvider] get_next_response failed: %s", exc)
            return f"[Ollama Error: {exc}] Interesting — let's explore another area."


# ── Factory ───────────────────────────────────────────────────────────────────

_PROVIDERS: dict[str, type[BaseLLMProvider]] = {
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
}


def get_llm_provider() -> BaseLLMProvider:
    """
    Returns the configured LLM provider singleton.

    Set LLM_PROVIDER env var to switch:
      LLM_PROVIDER=gemini   → uses Gemini API (default)
      LLM_PROVIDER=ollama   → uses local Ollama server
    """
    provider_name = os.getenv("LLM_PROVIDER", "gemini").lower().strip()
    provider_cls  = _PROVIDERS.get(provider_name)

    if provider_cls is None:
        logger.warning(
            "Unknown LLM_PROVIDER=%r — falling back to 'gemini'. "
            "Valid options: %s", provider_name, list(_PROVIDERS.keys())
        )
        provider_cls = GeminiProvider

    logger.info("[LLM Factory] Using provider: %s", provider_name)
    return provider_cls()
