"""
nlp/llm_interview.py
====================
Conversational mock interview powered by Google Gemini (google-genai SDK).
"""
import os
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class InterviewLLM:
    """
    Wrapper for Google Gemini to conduct conversational mock interviews.
    Uses the current google-genai SDK (replaces the deprecated google-generativeai).
    """

    def __init__(self):
        try:
            from google import genai
            self._genai = genai
        except ImportError:
            logger.warning(
                "google-genai is not installed. "
                "Install it with: pip install google-genai"
            )
            self._genai = None
            self._client = None
            return

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY not set. LLM features will be unavailable.")
            self._client = None
        else:
            # Use default API version for these newer models
            self._client = self._genai.Client(api_key=api_key)
            logger.info("Gemini client initialized successfully.")

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _system_instruction(self, role: str, missing_skills: List[str]) -> str:
        skills_str = ", ".join(missing_skills) if missing_skills else "general technical skills"
        return (
            f"You are an expert technical interviewer conducting a mock interview for a {role} position.\n"
            f"The candidate's identified skill gaps are: {skills_str}.\n\n"
            "Your goals:\n"
            "1. Conduct a professional, realistic technical interview.\n"
            "2. Focus questions on the identified skill gaps to help the candidate prepare.\n"
            "3. Be encouraging but rigorous.\n"
            "4. Ask ONE question at a time.\n"
            "5. Provide brief, specific feedback on each answer before asking the next question.\n"
            "6. If the candidate asks for help, explain the concept concisely and continue.\n"
        )

    def _available(self) -> bool:
        return self._client is not None

    # ── Public API ─────────────────────────────────────────────────────────────

    async def start_session(self, role: str, missing_skills: List[str]) -> str:
        """Returns the interviewer's opening message and first question."""
        if not self._available():
            return (
                "[LLM unavailable — check GEMINI_API_KEY] "
                "Let's get started. Can you walk me through a recent project?"
            )

        prompt = (
            self._system_instruction(role, missing_skills)
            + "\n\nStart the interview now. Greet the candidate briefly and ask your first technical question."
        )

        # Try available models in order of likelihood
        models_to_try = [
            "gemini-2.5-flash", 
            "gemini-2.5-flash-lite", 
            "gemini-2.0-flash", 
            "gemini-2.0-flash-lite"
        ]
        
        for model_name in models_to_try:
            try:
                response = self._client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                return response.text.strip()
            except Exception as exc:
                if "429" in str(exc) and model_name != models_to_try[-1]:
                    logger.warning(f"Quota hit for {model_name}, trying next fallback...")
                    continue
                logger.error(f"Gemini start_session error ({model_name}): {exc}")
                return (
                    f"[API Error: {type(exc).__name__}] Welcome! "
                    "Can you describe a challenging technical project you've worked on recently?"
                )

    async def get_next_response(
        self,
        role: str,
        missing_skills: List[str],
        history: List[Dict[str, str]],
        user_message: str,
    ) -> str:
        """Returns the interviewer's next message."""
        if not self._available():
            return "[LLM unavailable] That's interesting. Can you elaborate on that further?"

        system = self._system_instruction(role, missing_skills)
        contents = []
        for turn in history:
            sdk_role = "user" if turn["role"] == "user" else "model"
            contents.append({"role": sdk_role, "parts": [{"text": turn["content"]}]})
        contents.append({"role": "user", "parts": [{"text": user_message}]})

        from google.genai import types
        
        models_to_try = [
            "gemini-2.5-flash", 
            "gemini-2.5-flash-lite", 
            "gemini-2.0-flash", 
            "gemini-2.0-flash-lite",
            "gemini-2.5-pro",
            "gemini-2.0-flash-001",
            "gemini-2.0-flash-lite-001",
            "gemini-2.5-flash-lite",
        ]

        for model_name in models_to_try:
            try:
                response = self._client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(system_instruction=system),
                )
                return response.text.strip()
            except Exception as exc:
                if "429" in str(exc) and model_name != models_to_try[-1]:
                    logger.warning(f"Quota hit for {model_name}, trying next fallback...")
                    continue
                logger.error(f"Gemini get_next_response error ({model_name}): {exc}")
                return (
                    f"[API Error: {type(exc).__name__}] That's a valid perspective. "
                    "Let's explore a different area — how do you approach learning new tech quickly?"
                )
