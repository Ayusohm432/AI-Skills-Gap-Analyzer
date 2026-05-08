"""
services/ai_interview_service.py
=================================
AI-powered interview question generator using Gemini.

This uses a RAG-style approach where the full resume-derived context
(role, found skills, missing skills, readiness score, seniority) is
injected directly into the Gemini prompt, producing questions that are
hyper-personalized to the specific candidate's profile.

Fallback Strategy:
  Gemini API success → returns AI-generated questions (list of dicts)
  Any failure        → returns None → worker falls back to static bank
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from dotenv import load_dotenv
load_dotenv()   # ensures .env is loaded even when called outside FastAPI context

logger = logging.getLogger("services.ai_interview")

# Gemini model to use
_GEMINI_MODEL = "gemini-2.0-flash"

try:
    from google import genai
    from google.genai import types as genai_types
    _GEMINI_AVAILABLE = True
except ImportError:
    genai = None
    genai_types = None
    _GEMINI_AVAILABLE = False


def _build_prompt(
    role: str,
    identified_skills: list[str],
    missing_skills: list[str],
    readiness_score: float,
    seniority: str,
) -> str:
    """
    Constructs a rich, context-aware prompt for Gemini.
    The resume context is injected as structured data, making
    the questions directly relevant to this candidate's gaps.
    """
    found_skills_str   = ", ".join(identified_skills[:25]) if identified_skills else "None detected"
    missing_skills_str = ", ".join(missing_skills[:15])    if missing_skills    else "None"

    return f"""You are a senior technical interviewer preparing questions for a job candidate.

## Candidate Profile (from resume analysis)
- **Target Role:** {role}
- **Seniority Level:** {seniority}
- **Readiness Score:** {readiness_score:.1f}/100
- **Skills Found in Resume:** {found_skills_str}
- **Skill Gaps (Missing Skills):** {missing_skills_str}

## Instructions
Generate exactly 12 interview questions tailored to this candidate's profile.
Focus **specifically** on:
1. Testing depth of their existing skills (probe what they already know).
2. Uncovering how they deal with their skill gaps (can they learn on the job?).
3. Role-specific technical scenarios for a {seniority} {role}.

## Question Distribution (must follow exactly):
- 3 Behavioral questions (STAR format, relevant to a {role})
- 3 Technical questions on the candidate's **found skills** (go deep)
- 4 Technical questions on the **missing skills** (test if they've self-learned or have adjacent knowledge)
- 2 System Design / Architecture questions for a {role}

## Output Format (strict JSON, no markdown fences, no extra text)
Return ONLY a raw JSON array of 12 objects, each with these exact keys:
[
  {{
    "question": "full question text here",
    "category": "Behavioral" | "Technical" | "System Design",
    "difficulty": "Easy" | "Medium" | "Hard",
    "skill_focus": "name of skill or concept being tested"
  }}
]"""


async def generate_ai_interview_questions(
    role: str,
    identified_skills: list[str],
    missing_skills: list[str],
    readiness_score: float,
    seniority: str = "Mid-level",
) -> list[dict[str, Any]] | None:
    """
    Calls Gemini to generate personalized interview questions.

    Returns a list of question dicts on success, or None on failure
    (so the caller can gracefully fall back to the static bank).
    """
    if not _GEMINI_AVAILABLE:
        logger.warning("google-genai not installed; skipping AI question generation")
        return None

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning(
            "GEMINI_API_KEY not set; skipping AI question generation. "
            "Set GEMINI_API_KEY in .env to enable this feature."
        )
        return None

    prompt = _build_prompt(role, identified_skills, missing_skills, readiness_score, seniority)

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=2048,
            ),
        )

        raw_text = response.text.strip()

        # Strip accidental markdown fences if model adds them
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()

        questions = json.loads(raw_text)

        if not isinstance(questions, list):
            raise ValueError("Gemini response was not a JSON array")

        # Sanitize: ensure all required keys are present
        clean = []
        for q in questions:
            if isinstance(q, dict) and "question" in q:
                clean.append({
                    "question":    q.get("question", ""),
                    "category":   q.get("category", "Technical"),
                    "difficulty":  q.get("difficulty", "Medium"),
                    "skill_focus": q.get("skill_focus", role),
                })
        
        if not clean:
            raise ValueError("No valid questions after sanitization")

        logger.info(
            "AI interview questions generated: %d questions for role=%r", len(clean), role
        )
        return clean

    except json.JSONDecodeError as e:
        logger.error("Failed to parse Gemini JSON response: %s", e)
        return None
    except Exception as e:
        logger.error("AI interview generation failed: %s", e)
        return None
