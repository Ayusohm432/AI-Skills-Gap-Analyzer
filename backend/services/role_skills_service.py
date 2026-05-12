"""
services/role_skills_service.py
================================
Fetches the canonical required-skill list for ANY job role, including
custom roles that are not in the database or the ML model's training set.

Resolution order:
  1. MongoDB jobs_collection  – exact role_name match (zero network cost)
  2. _DEFAULT_ROLES_DB        – five hard-coded roles (zero network cost)
  3. Gemini generative AI     – asks the model for the top skills (async, <2 s)
  4. Adzuna job listings      – frequency-analyse live job descriptions (<3 s)
  5. Hard fallback            – generic software-engineering skills

The result is cached in memory for the process lifetime so repeated
analyses of the same custom role pay no additional latency.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("services.role_skills")

# ── In-process cache: {role_lower: [skills]} ──────────────────────────────────
_role_skills_cache: dict[str, list[str]] = {}

# ── Hard-coded known-role table (mirrors _DEFAULT_ROLES_DB in ml_inference) ───
_DEFAULT_ROLES_DB: dict[str, list[str]] = {
    "data scientist":            ["Python", "SQL", "Machine Learning", "Statistics", "Pandas", "TensorFlow", "NumPy", "Data Visualization", "Scikit-Learn"],
    "machine learning engineer": ["Python", "Docker", "Machine Learning", "TensorFlow", "MLOps", "AWS", "PyTorch", "Kubernetes", "MLflow"],
    "backend developer":         ["Node.js", "Python", "SQL", "Docker", "AWS", "API Design", "MongoDB", "FastAPI", "PostgreSQL", "Redis"],
    "frontend developer":        ["React", "JavaScript", "HTML", "CSS", "TypeScript", "TailwindCSS", "Next.js", "GraphQL", "Webpack"],
    "cyber security analyst":    ["Linux", "Networking", "Python", "SIEM", "Firewalls", "Cryptography", "Penetration Testing", "Incident Response", "OWASP"],
    "devops engineer":           ["Docker", "Kubernetes", "Terraform", "CI/CD", "AWS", "Ansible", "Linux", "Python", "Monitoring", "Helm"],
    "full-stack developer":      ["React", "Node.js", "TypeScript", "PostgreSQL", "Docker", "AWS", "REST APIs", "MongoDB", "Next.js", "GraphQL"],
    "full stack developer":      ["React", "Node.js", "TypeScript", "PostgreSQL", "Docker", "AWS", "REST APIs", "MongoDB", "Next.js", "GraphQL"],
    "data engineer":             ["Python", "Spark", "Kafka", "Airflow", "SQL", "AWS", "ETL", "dbt", "Data Warehouse", "Hadoop"],
    "data analyst":              ["SQL", "Python", "Tableau", "Power BI", "Excel", "Statistics", "Data Visualization", "Pandas", "Reporting"],
    "mobile developer":          ["Flutter", "Dart", "React Native", "iOS", "Android", "Swift", "Kotlin", "REST APIs", "Firebase"],
    "android developer":         ["Kotlin", "Java", "Android SDK", "Jetpack Compose", "REST APIs", "Firebase", "MVVM", "Coroutines"],
    "ios developer":             ["Swift", "SwiftUI", "UIKit", "Xcode", "Core Data", "REST APIs", "Combine", "Firebase"],
    "cloud architect":           ["AWS", "Azure", "GCP", "Terraform", "Docker", "Kubernetes", "Microservices", "System Design", "Networking"],
    "product manager":           ["Roadmapping", "Agile", "Scrum", "User Research", "Data Analysis", "Stakeholder Management", "SQL", "A/B Testing"],
    "qa engineer":               ["Selenium", "Pytest", "Jest", "Test Automation", "API Testing", "CI/CD", "JIRA", "Postman", "Load Testing"],
    "software architect":        ["System Design", "Microservices", "Design Patterns", "Docker", "Kubernetes", "Cloud Architecture", "API Design", "Scalability"],
}

# ── Adzuna skill vocabulary (for description mining) ─────────────────────────
_TECH_SKILLS_VOCAB: list[str] = [
    "Python", "Java", "JavaScript", "TypeScript", "Go", "Rust", "C++", "C#",
    "Ruby", "PHP", "Swift", "Kotlin", "Scala", "R", "Bash",
    "FastAPI", "Django", "Flask", "Spring Boot", "Express.js", "Node.js",
    "React", "Next.js", "Vue.js", "Angular", "Svelte", "Tailwind CSS",
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "Cassandra",
    "AWS", "Azure", "GCP", "Docker", "Kubernetes", "Terraform", "Ansible",
    "CI/CD", "Jenkins", "GitHub Actions", "Linux",
    "TensorFlow", "PyTorch", "Scikit-Learn", "Pandas", "NumPy", "Machine Learning",
    "Deep Learning", "NLP", "Computer Vision", "MLOps", "MLflow", "Statistics",
    "Spark", "Kafka", "Airflow", "dbt", "ETL", "Data Warehouse",
    "SIEM", "Penetration Testing", "Network Security", "Incident Response",
    "SOC", "OWASP", "Zero Trust", "Firewalls", "Cryptography",
    "System Design", "Microservices", "API Design", "GraphQL", "REST APIs",
    "Git", "Agile", "Scrum", "Design Patterns", "OOP",
    "Selenium", "Jest", "Pytest", "Playwright", "Unit Testing",
    "Flutter", "Dart", "React Native", "iOS", "Android", "Swift",
    "Tableau", "Power BI", "Excel", "SQL", "Data Visualization",
]
_SKILL_PATTERNS: list[tuple[str, re.Pattern]] = [
    (s, re.compile(r"\b" + re.escape(s) + r"\b", re.IGNORECASE))
    for s in _TECH_SKILLS_VOCAB
]

# ── Gemini model ──────────────────────────────────────────────────────────────
_GEMINI_MODEL = os.getenv("GEMINI_ROLE_SKILLS_MODEL", "gemini-2.0-flash")

try:
    from google import genai as _genai
    from google.genai import types as _genai_types
    _GEMINI_AVAILABLE = True
except ImportError:
    _genai = None
    _genai_types = None
    _GEMINI_AVAILABLE = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_skills_from_text(text: str) -> list[str]:
    """Return skills found in text (deduplicated, preserving order)."""
    seen: set[str] = set()
    out: list[str] = []
    for skill, pat in _SKILL_PATTERNS:
        if pat.search(text) and skill not in seen:
            seen.add(skill)
            out.append(skill)
    return out


def _normalize(role: str) -> str:
    return role.strip().lower()


# ── Source 1: Gemini ──────────────────────────────────────────────────────────

async def _fetch_skills_from_gemini(role: str) -> list[str] | None:
    """Ask Gemini for the top required skills for `role`. Returns None on failure."""
    if not _GEMINI_AVAILABLE:
        return None

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None

    prompt = (
        f"List exactly 12 technical skills required for a '{role}' job role in 2024-2025.\n"
        "Return ONLY a JSON array of skill name strings, no explanation, no markdown:\n"
        '["Skill 1", "Skill 2", ...]'
    )

    def _call_gemini() -> str:
        """Synchronous SDK call — runs in a thread pool via asyncio.to_thread."""
        client = _genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=prompt,
            config=_genai_types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=512,
            ),
        )
        return response.text.strip()

    try:
        raw = await asyncio.to_thread(_call_gemini)

        # Strip markdown fences if present
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.lower().startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        skills = json.loads(raw)
        if isinstance(skills, list) and skills:
            # Keep only non-empty strings, cap at 15
            clean = [str(s).strip() for s in skills if str(s).strip()][:15]
            logger.info(
                "Gemini returned %d skills for role=%r: %s",
                len(clean), role, clean[:5],
            )
            return clean if clean else None

    except json.JSONDecodeError as exc:
        logger.warning("Gemini skills JSON parse error for role=%r: %s", role, exc)
    except Exception as exc:
        logger.warning("Gemini skills fetch failed for role=%r: %s", role, exc)

    return None


# ── Source 2: Adzuna ──────────────────────────────────────────────────────────

async def _fetch_skills_from_adzuna(role: str) -> list[str]:
    """Mine Adzuna job descriptions for the most frequently required skills."""
    app_id  = os.getenv("ADZUNA_APP_ID",  "").strip()
    app_key = os.getenv("ADZUNA_APP_KEY", "").strip()
    country = os.getenv("ADZUNA_COUNTRY", "in")

    if not (app_id and app_key):
        return []

    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
    params = {
        "app_id":           app_id,
        "app_key":          app_key,
        "results_per_page": 30,
        "what":             role,
        "sort_by":          "relevance",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        results: list[dict] = data.get("results", [])
        if not results:
            return []

        # Aggregate descriptions
        descriptions = [
            f"{r.get('title', '')} {r.get('description', '')}"
            for r in results
        ]
        from collections import Counter
        counter: Counter = Counter()
        for desc in descriptions:
            for s in set(_extract_skills_from_text(desc)):
                counter[s] += 1

        top = [skill for skill, _ in counter.most_common(15)]
        logger.info(
            "Adzuna returned %d job listings → top skills for role=%r: %s",
            len(results), role, top[:5],
        )
        return top

    except httpx.HTTPStatusError as exc:
        logger.warning("Adzuna HTTP %d for role=%r: %s", exc.response.status_code, role, exc)
    except Exception as exc:
        logger.warning("Adzuna fetch failed for role=%r: %s", role, exc)

    return []


# ── Source 3: Static fallback ─────────────────────────────────────────────────

_GENERIC_FALLBACK = [
    "Python", "SQL", "Git", "REST APIs", "Docker",
    "Problem Solving", "System Design", "Agile", "Communication", "Unit Testing",
]


# ── Public API ────────────────────────────────────────────────────────────────

async def get_required_skills_for_role(
    role: str,
    roles_db: dict[str, list[str]] | None = None,
) -> tuple[list[str], str]:
    """
    Return the required skills for *role* and the data source used.

    Parameters
    ----------
    role     : Target role name (e.g. "Blockchain Developer", "Backend Developer")
    roles_db : The jobs_collection dict {role_name: [skills]} from MongoDB.
               Pass None to skip the DB lookup.

    Returns
    -------
    (skills: list[str], source: str)
      source is one of: "db", "builtin", "gemini", "adzuna", "fallback"
    """
    key = _normalize(role)

    # ── 0. In-process cache ───────────────────────────────────────────────────
    if key in _role_skills_cache:
        return _role_skills_cache[key], "cache"

    # ── 1. MongoDB jobs_collection ────────────────────────────────────────────
    if roles_db:
        # Try exact match first, then case-insensitive
        skills = roles_db.get(role, [])
        if not skills:
            for db_role, db_skills in roles_db.items():
                if db_role.strip().lower() == key:
                    skills = db_skills
                    break
        if skills:
            logger.info("Role skills for %r resolved from DB (%d skills)", role, len(skills))
            _role_skills_cache[key] = skills
            return skills, "db"

    # ── 2. Built-in table ─────────────────────────────────────────────────────
    builtin = _DEFAULT_ROLES_DB.get(key)
    if builtin:
        logger.info("Role skills for %r resolved from built-in table (%d skills)", role, len(builtin))
        _role_skills_cache[key] = builtin
        return builtin, "builtin"

    logger.info("Role %r not in DB or built-ins — fetching from external sources", role)

    # ── 3. Gemini ─────────────────────────────────────────────────────────────
    gemini_skills = await _fetch_skills_from_gemini(role)
    if gemini_skills and len(gemini_skills) >= 5:
        _role_skills_cache[key] = gemini_skills
        return gemini_skills, "gemini"

    # ── 4. Adzuna ─────────────────────────────────────────────────────────────
    adzuna_skills = await _fetch_skills_from_adzuna(role)
    if adzuna_skills and len(adzuna_skills) >= 5:
        # Blend with Gemini partial result if available
        if gemini_skills:
            seen = {s.lower() for s in adzuna_skills}
            for s in gemini_skills:
                if s.lower() not in seen:
                    adzuna_skills.append(s)
                    seen.add(s.lower())
        _role_skills_cache[key] = adzuna_skills
        return adzuna_skills, "adzuna"

    # ── 5. Hard fallback ──────────────────────────────────────────────────────
    logger.warning(
        "All sources failed for role=%r — using generic fallback skills", role
    )
    _role_skills_cache[key] = _GENERIC_FALLBACK
    return _GENERIC_FALLBACK, "fallback"
