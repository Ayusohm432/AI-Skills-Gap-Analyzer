import spacy
import pdfplumber
import re
import io
import logging
from typing import Any

from nlp.config import NLPConfig
from nlp.semantic import extract_skills_semantic

logger = logging.getLogger(__name__)

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

def extract_text_from_pdf(file_bytes):
    text = ""
    # We use io.BytesIO to simulate a file for pdfplumber because FastAPI UploadFile gives bytes
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
    return text

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

def generate_roadmap(missing_skills):
    roadmap = []
    week = 1
    for skill in missing_skills:
        roadmap.append({
            "week": f"Week {week}-{week+1}",
            "focus": f"{skill.title()} Basics & Application",
            "resources": [
                f"Coursera: Modern {skill.title()}",
                f"YouTube: {skill.title()} Crash Course"
            ]
        })
        week += 2
    return roadmap

def generate_interview_questions(missing_skills):
    questions = []
    for skill in missing_skills[:5]:
        questions.append(f"Can you explain the core concepts of {skill.title()} and how you'd use it in a production project?")
    if not questions:
        questions.append("Can you walk us through your most complex project, including the architecture and challenges?")
    return questions


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
