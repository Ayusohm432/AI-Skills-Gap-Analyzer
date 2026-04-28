import os
import re
import logging
from pathlib import Path
from typing import Any

import spacy

from nlp.config import NLPConfig
from nlp.semantic import extract_skills_semantic
from nlp.pdf_processor import extract_text_from_pdf   # noqa: F401 – re-exported
from nlp.docx_processor import extract_text_from_docx  # noqa: F401 – re-exported
from nlp.txt_processor import extract_text_from_txt    # noqa: F401 – re-exported

logger = logging.getLogger(__name__)

# ── MIME-type → file extension mapping used by the dispatcher ─────────────────
_MIME_TO_EXT: dict[str, str] = {
    "application/pdf":                                                              "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document":     "docx",
    "application/msword":                                                           "docx",
    "text/plain":                                                                   "txt",
}


def extract_text(file_bytes: bytes, content_type: str = "", filename: str = "") -> str:
    """
    Unified text-extraction dispatcher.

    Routes the raw file bytes to the correct processor based on *content_type*
    (MIME string).  When the MIME type is absent or unrecognised, the function
    falls back to guessing from the *filename* extension.

    Parameters
    ----------
    file_bytes   : Raw bytes of the uploaded file.
    content_type : MIME type string supplied by the HTTP client.
    filename     : Original filename (used as extension fallback).

    Returns
    -------
    Cleaned plain-text string, or "" when the format is unsupported.
    No exception is raised; errors are logged.
    """
    ext = _resolve_extension(content_type, filename)
    logger.info("extract_text: content_type=%r  filename=%r  resolved_ext=%r", content_type, filename, ext)

    if ext == "pdf":
        return extract_text_from_pdf(file_bytes)
    if ext == "docx":
        return extract_text_from_docx(file_bytes)
    if ext == "txt":
        return extract_text_from_txt(file_bytes)

    logger.warning(
        "extract_text: unsupported format (content_type=%r, filename=%r) – returning empty string",
        content_type, filename,
    )
    return ""


def _resolve_extension(content_type: str, filename: str) -> str:
    """Return a normalised extension string ('pdf', 'docx', 'txt', or '')."""
    # 1. Try MIME type first (most reliable)
    ext = _MIME_TO_EXT.get((content_type or "").strip().lower(), "")
    if ext:
        return ext

    # 2. Fallback: derive from filename extension
    if filename:
        suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if suffix in ("pdf", "docx", "doc", "txt"):
            return "docx" if suffix in ("doc", "docx") else suffix

    return ""

try:
    nlp = spacy.load("en_core_web_sm")
except Exception:
    pass # Needs to be python -m spacy download en_core_web_sm during docker image build

KNOWN_SKILLS = {
    "python", "java", "c++", "javascript", "typescript", "react", "angular", "vue", "next.js", "node.js",
    "express", "flask", "django", "spring boot", "sql", "mysql", "postgresql", "mongodb", "redis",
    "aws", "azure", "gcp", "docker", "kubernetes", "jenkins", "git", "github", "gitlab", "ci/cd",
    "machine learning", "deep learning", "tensorflow", "pytorch", "scikit-learn", "pandas", "numpy",
    "data analysis", "data science", "nlp", "computer vision", "statistics", "mathematics",
    "html", "css", "tailwind", "sass", "bootstrap", "rest api", "graphql", "agile", "scrum", "keras",
    "mlops", "feature engineering", "c#", ".net", "rust", "go", "ruby", "php"
}

# extract_text_from_pdf is imported from nlp.pdf_processor and re-exported above.
# The function signature is: extract_text_from_pdf(file_bytes: bytes) -> str

def extract_skills_from_text(text):
    text = text.lower()
    text = re.sub(r'[^\w\s\+\#\.]', ' ', text)
    doc = nlp(text)
    
    found_skills = set()
    for token in doc:
        if token.text in KNOWN_SKILLS:
            found_skills.add(token.text)
            
    for chunk in doc.noun_chunks:
        if chunk.text in KNOWN_SKILLS:
            found_skills.add(chunk.text)
            
    for skill in KNOWN_SKILLS:
        if skill in text.split():
            found_skills.add(skill)
            
    return list(found_skills)

def calculate_readiness_score(resume_skills, target_skills):
    if not target_skills:
        return 0
    match_count = sum(1 for skill in target_skills if skill in resume_skills)
    return round((match_count / len(target_skills)) * 100)

def match_role_and_skills(resume_skills, roles_db, user_given_role=None):
    resume_skills_set = set([s.lower() for s in resume_skills])
    
    # If the user selected a specific role, we calculate score against it directly
    if user_given_role and user_given_role != "Auto Detect":
        required_skills = roles_db.get(user_given_role, [])
        required_skills_set = set([s.lower() for s in required_skills])
        score = calculate_readiness_score(resume_skills_set, required_skills_set)
        gap = list(required_skills_set - resume_skills_set)
        return {
            "target_role": user_given_role,
            "readiness_score": score,
            "missing_skills": gap,
            "identified_skills": list(resume_skills_set)
        }

    # Auto Detect Mode: Iterate every role and find the highest match
    best_role = "General Developer"
    best_score = 0
    best_gap = ["python", "javascript", "sql"]
    
    for title, skills in roles_db.items():
        role_skills_set = set([s.lower() for s in skills])
        score = calculate_readiness_score(resume_skills_set, role_skills_set)
        if score > best_score:
            best_score = score
            best_role = title
            best_gap = list(role_skills_set - resume_skills_set)
            
    return {
        "target_role": best_role,
        "readiness_score": best_score,
        "missing_skills": best_gap,
        "identified_skills": list(resume_skills_set)
    }

import urllib.parse

def generate_roadmap(missing_skills_ranked):
    if not missing_skills_ranked:
        return []

    # Handle legacy lists of strings gracefully
    normalized = []
    for item in missing_skills_ranked:
        if isinstance(item, str):
            normalized.append({"skill": item, "likelihood": 0.5, "priority": "medium"})
        else:
            normalized.append(item)

    # Sort by likelihood (highest first) so high-likelihood skills appear in first weeks
    sorted_skills = sorted(normalized, key=lambda x: x.get("likelihood", 0.0), reverse=True)

    roadmap = []
    week = 1
    for item in sorted_skills:
        skill = item["skill"]
        encoded = urllib.parse.quote(skill)
        
        roadmap.append({
            "week": f"Week {week}-{week+1}",
            "focus": f"{skill.title()} Basics & Application",
            "resources": [
                f"Coursera: https://www.coursera.org/search?query={encoded}",
                f"YouTube: https://www.youtube.com/results?search_query={encoded}+crash+course"
            ]
        })
        week += 2
        
    return roadmap

from nlp.interview_bank import (
    BEHAVIORAL_QUESTIONS,
    SYSTEM_DESIGN_QUESTIONS,
    TECHNICAL_SKILL_QUESTIONS,
    get_role_domain,
)
import random

def generate_interview_questions(missing_skills: list, role: str = "General Developer"):
    """
    Generate a categorized list of 10-15 interview questions based on the role and missing skills.
    Returns a list of dicts with 'question', 'category', and 'difficulty'.
    """
    questions = []
    
    # 1. Behavioral (always include 3-4)
    num_behavioral = min(4, len(BEHAVIORAL_QUESTIONS))
    questions.extend(random.sample(BEHAVIORAL_QUESTIONS, num_behavioral))
    
    # 2. System Design (include 2-3 based on role domain)
    domain = get_role_domain(role)
    sys_design_pool = SYSTEM_DESIGN_QUESTIONS.get(domain, SYSTEM_DESIGN_QUESTIONS["general"])
    num_sys_design = min(3, len(sys_design_pool))
    questions.extend(random.sample(sys_design_pool, num_sys_design))
    
    # 3. Technical (include 6-8 based on missing skills to probe gaps)
    # Extract skill strings (handling both string lists and ranked dicts)
    skill_names = [s["skill"].lower() if isinstance(s, dict) else str(s).lower() for s in missing_skills]
    tech_pool = []
    
    for skill in skill_names:
        if skill in TECHNICAL_SKILL_QUESTIONS:
            tech_pool.extend(TECHNICAL_SKILL_QUESTIONS[skill])
            
    # If not enough missing-skill-specific questions, pad with general python/javascript/sql
    if len(tech_pool) < 6:
        for fallback in ["python", "javascript", "sql"]:
            if fallback not in skill_names:
                tech_pool.extend(TECHNICAL_SKILL_QUESTIONS[fallback])
                
    num_tech = min(8, len(tech_pool))
    if tech_pool:
        questions.extend(random.sample(tech_pool, num_tech))
        
    # Shuffle the final list so it doesn't always start with behavioral
    random.shuffle(questions)
    
    return questions[:15]


def _merge_results(
    keyword_skills: list[str],
    semantic_results: list[dict[str, Any]],
    strategy: str = "union",
) -> list[dict[str, Any]]:
    """
    Merge Phase 1 keyword matches with Phase 2 semantic results.

    Strategies:
      - "union": Combine both, keyword hits get confidence=1.0
      - "semantic_only": Only return semantic results
      - "keyword_only": Only return keyword results (with confidence=1.0)

    Returns list of {"skill": str, "confidence": float, "category": str}
    """
    if strategy == "keyword_only":
        return [
            {"skill": s, "confidence": 1.0, "category": "keyword_match"}
            for s in keyword_skills
        ]

    if strategy == "semantic_only":
        return semantic_results

    # Default: "union" — merge both
    merged: dict[str, dict[str, Any]] = {}

    # Keyword results as baseline (confidence = 1.0)
    for skill_name in keyword_skills:
        key = skill_name.lower()
        merged[key] = {
            "skill": skill_name,
            "confidence": 1.0,
            "category": "keyword_match",
        }

    # Layer semantic results on top — add new discoveries,
    # but don't overwrite keyword hits (they already have confidence=1.0)
    for result in semantic_results:
        key = result["skill"].lower()
        if key not in merged:
            merged[key] = result

    return sorted(merged.values(), key=lambda x: x["confidence"], reverse=True)


def extract_skills_combined(
    text: str,
    config: NLPConfig | None = None,
) -> list[dict[str, Any]]:
    """
    Phase 2 skill extraction: combines keyword matching with semantic similarity.

    Returns list of dicts with keys:
      - "skill": str — skill name
      - "confidence": float — confidence score (1.0 for keyword matches)
      - "category": str — skill category
    """
    config = config or NLPConfig()

    # Phase 1: keyword matching (always runs as baseline)
    keyword_skills = extract_skills_from_text(text)
    logger.info("Keyword extraction found %d skills", len(keyword_skills))

    # Phase 2: semantic matching
    semantic_results = []
    if config.USE_SEMANTIC_EXTRACTION:
        try:
            semantic_results = extract_skills_semantic(text, config)
            logger.info("Semantic extraction found %d skills", len(semantic_results))
        except Exception as e:
            logger.error("Semantic extraction failed, falling back to keyword-only: %s", e)

    # Merge results
    return _merge_results(keyword_skills, semantic_results, config.MERGE_STRATEGY)


# ── Skill categorization (Step 4 integration) ─────────────────────────────────

# Output domain keys — these are the four canonical buckets the API exposes.
_OUTPUT_DOMAINS: tuple[str, ...] = ("frontend", "backend", "devops", "data")

# ── Rule-based fallback map (keyword → domain) ────────────────────────────────
# Used when skill_clusterer is unavailable OR for skills the KMeans cannot embed.
_RULE_BASED_CATEGORY_MAP: dict[str, str] = {
    # Frontend
    "react": "frontend", "angular": "frontend", "vue": "frontend",
    "next.js": "frontend", "nuxt": "frontend", "svelte": "frontend",
    "html": "frontend", "css": "frontend", "sass": "frontend", "scss": "frontend",
    "tailwindcss": "frontend", "tailwind": "frontend", "bootstrap": "frontend",
    "webpack": "frontend", "vite": "frontend", "parcel": "frontend",
    "typescript": "frontend", "javascript": "frontend",
    "figma": "frontend", "adobe xd": "frontend", "responsive design": "frontend",
    # Backend / APIs
    "node.js": "backend", "express": "backend", "fastapi": "backend",
    "django": "backend", "flask": "backend", "spring boot": "backend",
    "spring": "backend", "rails": "backend", "ruby on rails": "backend",
    "asp.net": "backend", ".net": "backend", "laravel": "backend",
    "graphql": "backend", "rest api": "backend", "grpc": "backend",
    "postgresql": "backend", "mysql": "backend", "sqlite": "backend",
    "mongodb": "backend", "redis": "backend", "elasticsearch": "backend",
    "cassandra": "backend", "dynamodb": "backend", "rabbitmq": "backend",
    "kafka": "backend", "java": "backend", "go": "backend",
    "python": "backend", "ruby": "backend", "php": "backend", "c#": "backend",
    "rust": "backend", "c++": "backend", "scala": "backend", "kotlin": "backend",
    "sql": "backend",
    # DevOps / Cloud / Infra
    "docker": "devops", "kubernetes": "devops", "k8s": "devops",
    "aws": "devops", "azure": "devops", "gcp": "devops",
    "terraform": "devops", "ansible": "devops", "chef": "devops", "puppet": "devops",
    "jenkins": "devops", "github actions": "devops", "gitlab ci": "devops",
    "circleci": "devops", "ci/cd": "devops", "argocd": "devops",
    "linux": "devops", "bash": "devops", "nginx": "devops", "apache": "devops",
    "prometheus": "devops", "grafana": "devops", "helm": "devops",
    "vagrant": "devops", "packer": "devops", "cloudformation": "devops",
    # Data / ML / AI
    "machine learning": "data", "deep learning": "data", "data science": "data",
    "tensorflow": "data", "pytorch": "data", "keras": "data",
    "scikit-learn": "data", "scikit learn": "data", "sklearn": "data",
    "pandas": "data", "numpy": "data", "matplotlib": "data", "seaborn": "data",
    "nlp": "data", "computer vision": "data", "statistics": "data",
    "data analysis": "data", "data visualization": "data",
    "tableau": "data", "power bi": "data", "looker": "data",
    "spark": "data", "hadoop": "data", "airflow": "data",
    "mlops": "data", "mlflow": "data", "kubeflow": "data",
    "feature engineering": "data", "model deployment": "data",
    "xgboost": "data", "lightgbm": "data", "a/b testing": "data",
}


def _rule_based_categorize(skills: list[str]) -> dict[str, list[str]]:
    """
    Fallback: categorize skills using the keyword lookup table.
    Always returns all four domain keys (empty list for absent domains).
    """
    result: dict[str, list[str]] = {d: [] for d in _OUTPUT_DOMAINS}
    for skill in skills:
        domain = _RULE_BASED_CATEGORY_MAP.get(skill.lower(), "data")  # default → data
        if domain in result:
            result[domain].append(skill)
        else:
            result["data"].append(skill)
    return result


# ── KMeans cluster → output domain map ───────────────────────────────────────
# Derived by probing representative skills through the clusterer.
# The model has 13 clusters (see models/ml_models/v1.0/metadata.json).
# Each cluster ID is mapped to one of the four output domains.
# Clusters not listed here fall back to "data" (safe default).
_CLUSTER_DOMAIN_MAP: dict[int, str] = {
    # These assignments are derived from centroid analysis:
    # clusters heavily weighted toward frontend / UI skill terms.
    0:  "frontend",
    1:  "data",
    2:  "backend",
    3:  "devops",
    4:  "data",
    5:  "frontend",
    6:  "backend",
    7:  "devops",
    8:  "data",
    9:  "backend",
    10: "devops",
    11: "data",
    12: "frontend",
}

# Embedding model shared across calls (lazy init to avoid import overhead)
_sentence_encoder = None
_encoder_lock_flag = False  # prevents recursive re-entry on import failure


def _get_encoder():
    """Lazily load the SentenceTransformer encoder (cached module-level)."""
    global _sentence_encoder, _encoder_lock_flag
    if _sentence_encoder is not None:
        return _sentence_encoder
    if _encoder_lock_flag:
        return None   # already tried and failed
    _encoder_lock_flag = True
    try:
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415
        _sentence_encoder = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("[categorize_skills] SentenceTransformer loaded OK")
    except Exception as exc:
        logger.warning("[categorize_skills] SentenceTransformer unavailable: %s", exc)
        _sentence_encoder = None
    return _sentence_encoder


def categorize_skills(
    skills_list: list[str],
    clusterer=None,
) -> dict[str, list[str]]:
    """
    Categorize a list of detected skills into four domain buckets using the
    trained KMeans skill clusterer, with an automatic rule-based fallback.

    This function is integrated at **pipeline Step 4** (post missing-skills
    prediction) so that every analysis result carries a structured domain
    breakdown without a separate pass over the skill list.

    Parameters
    ----------
    skills_list : list[str]
        Detected skills (strings) to categorize.
    clusterer : sklearn KMeans-compatible object | None
        The loaded ``skill_clusterer`` from ``app.state.ml_models``.  When
        ``None`` (model unavailable), falls back to rule-based categorization.

    Returns
    -------
    dict[str, list[str]]
        Always contains exactly these four keys (values may be empty lists)::

            {
                "frontend": [...],
                "backend":  [...],
                "devops":   [...],
                "data":     [...],
            }

    Notes
    -----
    - Unknown skills (not in either the rule map or the clusterer vocabulary)
      are placed in ``"data"`` as the safest default.
    - If ``sentence_transformers`` is not installed the ML path is skipped
      and the rule-based path is used transparently.
    """
    if not skills_list:
        return {d: [] for d in _OUTPUT_DOMAINS}

    # ── ML path: KMeans clusterer + sentence embeddings ────────────────
    if clusterer is not None:
        encoder = _get_encoder()
        if encoder is not None:
            try:
                import numpy as np  # noqa: PLC0415

                embeddings = encoder.encode(
                    skills_list,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
                cluster_ids = clusterer.predict(embeddings)  # shape: (n_skills,)

                result: dict[str, list[str]] = {d: [] for d in _OUTPUT_DOMAINS}
                for skill, cid in zip(skills_list, cluster_ids):
                    domain = _CLUSTER_DOMAIN_MAP.get(int(cid), "data")
                    result[domain].append(skill)

                logger.info(
                    "[categorize_skills] ML path: %d skills → %s",
                    len(skills_list),
                    {k: len(v) for k, v in result.items()},
                )
                return result

            except Exception as exc:
                logger.warning(
                    "[categorize_skills] ML path failed (%s: %s) – using rule-based fallback",
                    type(exc).__name__, exc,
                )
        else:
            logger.warning(
                "[categorize_skills] Encoder unavailable – using rule-based fallback"
            )

    # ── Rule-based fallback ────────────────────────────────────────────
    result = _rule_based_categorize(skills_list)
    logger.info(
        "[categorize_skills] Rule-based fallback: %d skills → %s",
        len(skills_list),
        {k: len(v) for k, v in result.items()},
    )
    return result
