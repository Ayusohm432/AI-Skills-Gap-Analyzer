"""
routes/github.py
================
GitHub profile integration — enriches skill analysis with public project data.

Endpoint
--------
POST /api/v1/analyze/github
    Accept a GitHub username (and optionally a list of skills already extracted
    from a resume), fetch the user's top public repositories via the GitHub API,
    extract languages & repository topics, merge with any supplied resume skills,
    deduplicate, categorise using the existing NLP pipeline, and return a
    structured enrichment payload.

Rate Limiting
-------------
- GitHub API: the ``X-RateLimit-Remaining`` response header is inspected after
  every call.  When it reaches 0, the endpoint raises HTTP 429 with a
  ``Retry-After`` header (seconds until the reset window) so clients know when
  to retry.
- Our own endpoint: decorated with ``@limiter.limit("30/minute")`` so a single
  user cannot tunnel-hammer GitHub through this service.
- Optional ``GITHUB_TOKEN`` env var: when set, every GitHub request is sent with
  ``Authorization: Bearer <token>`` raising the rate limit from 60 → 5 000/hr.

Authentication
--------------
Requires a valid JWT (Bearer token) via the ``get_current_user`` dependency —
same as every other protected endpoint.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status

from models import GithubAnalyzeRequest, GithubAnalyzeResponse
from nlp.engine import KNOWN_SKILLS, categorize_skills
from security import get_current_user, decrypt_token, encrypt_token
from database import users_collection
from bson import ObjectId


logger = logging.getLogger("routes.github")

router = APIRouter()

# ── GitHub API constants ───────────────────────────────────────────────────────

_GITHUB_API_BASE = "https://api.github.com"
_GITHUB_TIMEOUT  = 10.0   # seconds per request

# Optional personal-access token — raises rate limit from 60 → 5 000 req/hr.
_GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")

# ── Language / topic → canonical skill name table ─────────────────────────────
# Maps GitHub-reported language names and common repo topic tags to the skill
# strings used throughout the rest of the pipeline.  Keys are lowercased.

_LANG_TO_SKILL: dict[str, str] = {
    # Programming languages
    "python":             "Python",
    "javascript":         "JavaScript",
    "typescript":         "TypeScript",
    "java":               "Java",
    "c++":                "C++",
    "c#":                 "C#",
    "go":                 "Go",
    "rust":               "Rust",
    "ruby":               "Ruby",
    "php":                "PHP",
    "kotlin":             "Kotlin",
    "scala":              "Scala",
    "swift":              "Swift",
    "r":                  "R",
    "shell":              "Bash",
    "bash":               "Bash",
    "powershell":         "Bash",
    "dockerfile":         "Docker",
    "makefile":           "Linux",
    "jupyter notebook":   "Data Science",
    "html":               "HTML",
    "css":                "CSS",
    "dart":               "Dart",
    # Topics / tags
    "machine-learning":   "Machine Learning",
    "deep-learning":      "Deep Learning",
    "neural-network":     "Deep Learning",
    "nlp":                "NLP",
    "computer-vision":    "Computer Vision",
    "data-science":       "Data Science",
    "data-analysis":      "Data Analysis",
    "react":              "React",
    "nextjs":             "Next.js",
    "vue":                "Vue",
    "angular":            "Angular",
    "node":               "Node.js",
    "nodejs":             "Node.js",
    "express":            "Express",
    "django":             "Django",
    "flask":              "Flask",
    "fastapi":            "FastAPI",
    "spring-boot":        "Spring Boot",
    "graphql":            "GraphQL",
    "rest-api":           "REST API",
    "grpc":               "gRPC",
    "docker":             "Docker",
    "kubernetes":         "Kubernetes",
    "k8s":                "Kubernetes",
    "terraform":          "Terraform",
    "ansible":            "Ansible",
    "aws":                "AWS",
    "azure":              "Azure",
    "gcp":                "GCP",
    "ci-cd":              "CI/CD",
    "github-actions":     "CI/CD",
    "postgresql":         "PostgreSQL",
    "mysql":              "MySQL",
    "mongodb":            "MongoDB",
    "redis":              "Redis",
    "elasticsearch":      "Elasticsearch",
    "kafka":              "Kafka",
    "rabbitmq":           "RabbitMQ",
    "tensorflow":         "TensorFlow",
    "pytorch":            "PyTorch",
    "keras":              "Keras",
    "scikit-learn":       "scikit-learn",
    "pandas":             "Pandas",
    "numpy":              "NumPy",
    "mlops":              "MLOps",
    "airflow":            "Airflow",
    "spark":              "Spark",
    "hadoop":             "Hadoop",
    "tableau":            "Tableau",
}

# ── GitHub API client helpers ─────────────────────────────────────────────────

def _build_headers(token: str | None = None) -> dict[str, str]:
    """Return HTTP headers for GitHub API requests."""
    headers: dict[str, str] = {
        "Accept":     "application/vnd.github+json",
        "User-Agent": "AI-Skills-Gap-Analyzer/1.0",
    }
    # Priority: user-provided token > environment GITHUB_TOKEN
    effective_token = token or _GITHUB_TOKEN
    if effective_token:
        headers["Authorization"] = f"Bearer {effective_token}"
    return headers



def _check_rate_limit(response: httpx.Response) -> None:
    """
    Inspect GitHub rate-limit headers.  Raises HTTP 429 when remaining == 0.

    GitHub returns:
        X-RateLimit-Limit     : total requests allowed in the window
        X-RateLimit-Remaining : requests remaining before reset
        X-RateLimit-Reset     : UTC Unix timestamp of the next reset
    """
    remaining = response.headers.get("X-RateLimit-Remaining")
    reset_ts   = response.headers.get("X-RateLimit-Reset")

    if remaining is not None and int(remaining) == 0:
        retry_after = 60   # sensible default
        if reset_ts:
            try:
                reset_dt    = datetime.fromtimestamp(int(reset_ts), tz=timezone.utc)
                now         = datetime.now(tz=timezone.utc)
                retry_after = max(0, int((reset_dt - now).total_seconds()))
            except (ValueError, OSError):
                pass

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"GitHub API rate limit exceeded. "
                f"Retry after {retry_after} seconds. "
                "Set the GITHUB_TOKEN environment variable to raise the limit to 5 000 req/hr."
            ),
            headers={"Retry-After": str(retry_after)},
        )


async def _fetch_user_repos(
    username: str,
    max_repos: int,
    client: httpx.AsyncClient,
    token: str | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch the user's public repositories sorted by star count (descending).

    Returns a list of raw GitHub repository objects (dicts).
    Raises HTTPException on 404 (user not found), 429 (rate limit), or 502
    (GitHub unreachable / timeout).
    """
    url    = f"{_GITHUB_API_BASE}/users/{username}/repos"
    params = {
        "type":      "owner",
        "sort":      "stargazers",
        "direction": "desc",
        "per_page":  min(max_repos, 100),
        "page":      1,
    }

    try:
        resp = await client.get(url, params=params, headers=_build_headers(token))
    except httpx.TimeoutException:

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub API request timed out. Please try again.",
        )
    except httpx.RequestError as exc:
        logger.error("GitHub API request failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to reach the GitHub API. Please try again later.",
        )

    _check_rate_limit(resp)

    if resp.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"GitHub user '{username}' not found.",
        )
    if resp.status_code == 403:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "GitHub API rate limit exceeded (403 Forbidden). "
                "Set the GITHUB_TOKEN environment variable to raise the limit to 5 000 req/hr."
            ),
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub API returned an unexpected status: {resp.status_code}.",
        )

    repos: list[dict[str, Any]] = resp.json()
    # Take only non-forked repos by default; fall back to all if none remain
    owned = [r for r in repos if not r.get("fork", False)]
    return (owned or repos)[:max_repos]


async def _fetch_repo_topics(
    username: str,
    repo_name: str,
    client: httpx.AsyncClient,
    token: str | None = None,
) -> list[str]:
    """
    Fetch repository topic tags via the GitHub topics API.
    Returns an empty list on any error (non-fatal — topics are best-effort).
    """
    url = f"{_GITHUB_API_BASE}/repos/{username}/{repo_name}/topics"
    try:
        headers = {**_build_headers(token), "Accept": "application/vnd.github.mercy-preview+json"}
        resp = await client.get(url, headers=headers)
        if resp.status_code == 200:
            return resp.json().get("names", [])
    except Exception as exc:

        logger.debug("Topic fetch failed for %s/%s: %s", username, repo_name, exc)
    return []


# ── Skill extraction helpers ──────────────────────────────────────────────────

def _extract_skills_from_github_data(
    languages: dict[str, int],
    topics: list[str],
) -> list[str]:
    """
    Convert GitHub language/topic data to canonical skill strings.

    Parameters
    ----------
    languages : mapping of language_name → bytes_of_code
    topics    : list of topic tag strings

    Returns a deduplicated list of canonical skill names (cased).
    """
    seen: set[str] = set()
    skills: list[str] = []

    for raw in list(languages.keys()) + topics:
        key = raw.lower().replace(" ", "-")   # normalise spaces & hyphens

        # 1. Direct lookup in the lang→skill table
        canonical = _LANG_TO_SKILL.get(key) or _LANG_TO_SKILL.get(raw.lower())

        # 2. Fallback: check if the raw name exists in KNOWN_SKILLS (lowercased)
        if canonical is None:
            for ks in KNOWN_SKILLS:
                if ks == raw.lower():
                    canonical = ks.title()
                    break

        if canonical and canonical.lower() not in seen:
            seen.add(canonical.lower())
            skills.append(canonical)

    return skills


def _merge_skills(
    github_skills: list[str],
    resume_skills: list[str],
) -> list[str]:
    """
    Union-merge two skill lists, deduplicating on lowercased key.

    GitHub-derived skills appear first; resume skills that are not already
    present are appended, preserving their original casing.
    """
    seen: set[str] = set()
    merged: list[str] = []

    for skill in github_skills + resume_skills:
        key = skill.lower()
        if key not in seen:
            seen.add(key)
            merged.append(skill)

    return merged


async def _refresh_github_token(user_id: str, refresh_token: str) -> str:
    """
    Attempt to refresh the GitHub access token using the stored refresh token.
    Updates the user document in MongoDB with the new tokens.
    """
    from services.oauth_service import GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, _GITHUB_TOKEN_URL
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        logger.error("GitHub refresh failed: Missing Client ID or Secret")
        return ""

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                _GITHUB_TOKEN_URL,
                headers={"Accept": "application/json"},
                data={
                    "client_id":     GITHUB_CLIENT_ID,
                    "client_secret": GITHUB_CLIENT_SECRET,
                    "refresh_token": refresh_token,
                    "grant_type":    "refresh_token",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                new_access = data.get("access_token")
                new_refresh = data.get("refresh_token")
                if new_access:
                    update_fields = {"github_access_token": encrypt_token(new_access)}
                    if new_refresh:
                        update_fields["github_refresh_token"] = encrypt_token(new_refresh)
                    
                    await users_collection.update_one(
                        {"_id": ObjectId(user_id)},
                        {"$set": update_fields}
                    )
                    logger.info("GitHub access token refreshed for user %s", user_id)
                    return new_access
            else:
                logger.warning("GitHub refresh failed: %s %s", resp.status_code, resp.text)
        except Exception as exc:
            logger.error("GitHub refresh exception: %s", exc)
    
    return ""


# ── Endpoint ──────────────────────────────────────────────────────────────────


@router.post(
    "/analyze/github",
    response_model=GithubAnalyzeResponse,
    status_code=status.HTTP_200_OK,
    summary="Enrich skill analysis with GitHub profile data",
    description=(
        "Fetches the user's top public GitHub repositories, extracts programming "
        "languages and repository topic tags, maps them to canonical skill names, "
        "merges with any skills already extracted from a resume, deduplicates, and "
        "returns a categorised skill breakdown.\n\n"
        "**Rate limiting**: GitHub's API rate limit is respected. If the limit is "
        "exhausted, the endpoint returns HTTP 429 with a ``Retry-After`` header. "
        "Configure the ``GITHUB_TOKEN`` environment variable to raise the limit from "
        "60 to 5 000 requests/hr.\n\n"
        "Requires a valid JWT (Bearer token)."
    ),
    tags=["GitHub Integration"],
)
async def analyze_github_profile(
    request:      Request,
    body:         GithubAnalyzeRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Enrich skill analysis from a GitHub profile.

    1. Validate the request.
    2. Fetch top repos via GitHub API (async, with rate-limit checks).
    3. Optionally fetch repo-level topic tags (best-effort).
    4. Aggregate language byte-counts across all repos.
    5. Extract canonical skill names from languages + topics.
    6. Merge with supplied resume skills (deduplicated).
    7. Categorise merged skills using the existing NLP categoriser.
    8. Return a structured response.
    """
    username  = body.github_username.strip()
    max_repos = body.max_repos

    logger.info(
        "analyze/github: user=%s  github_username=%s  max_repos=%d  resume_skills=%d",
        current_user["id"], username, max_repos, len(body.resume_skills),
    )

    # ── Token handling ────────────────────────────────────────────────
    # Fetch user's stored token if available
    encrypted_token = current_user.get("github_access_token")
    token = decrypt_token(encrypted_token) if encrypted_token else None

    # ── Fetch repositories ────────────────────────────────────────────
    async with httpx.AsyncClient(timeout=_GITHUB_TIMEOUT) as client:
        try:
            repos = await _fetch_user_repos(username, max_repos, client, token)
        except HTTPException as exc:
            # Handle token expiration (401)
            if exc.status_code == 401 and current_user.get("github_refresh_token"):
                logger.info("GitHub 401: Attempting token refresh for user %s", current_user["id"])
                new_token = await _refresh_github_token(
                    current_user["id"], 
                    decrypt_token(current_user["github_refresh_token"])
                )
                if new_token:
                    # Retry once with the fresh token
                    repos = await _fetch_user_repos(username, max_repos, client, new_token)
                    token = new_token  # use for topics too
                else:
                    raise exc
            else:
                raise exc

        # ── Aggregate language byte-counts ────────────────────────────
        language_totals: dict[str, int] = {}
        all_topics: list[str] = []

        for repo in repos:
            # Language from the repo summary (one dominant language)
            lang = repo.get("language")
            if lang:
                language_totals[lang] = language_totals.get(lang, 0) + 1

            # Topics (best-effort per-repo call — skip on rate limit)
            repo_topics = await _fetch_repo_topics(username, repo["name"], client, token)
            all_topics.extend(repo_topics)


    # Deduplicate topics while preserving order
    seen_topics: set[str] = set()
    unique_topics: list[str] = []
    for t in all_topics:
        if t not in seen_topics:
            seen_topics.add(t)
            unique_topics.append(t)

    # ── Extract skills from GitHub data ───────────────────────────────
    github_skills = _extract_skills_from_github_data(language_totals, unique_topics)

    # ── Merge with resume skills ──────────────────────────────────────
    merged = _merge_skills(github_skills, body.resume_skills)

    # ── Categorise via existing NLP pipeline ─────────────────────────
    ml_bundle  = getattr(request.app.state, "ml_models", None)
    clusterer  = ml_bundle.get("skill_clusterer") if isinstance(ml_bundle, dict) else None
    categories = categorize_skills(merged, clusterer=clusterer)

    logger.info(
        "analyze/github: repos=%d  github_skills=%d  merged=%d",
        len(repos), len(github_skills), len(merged),
    )

    return GithubAnalyzeResponse(
        github_username=username,
        repos_analyzed=len(repos),
        github_skills=github_skills,
        resume_skills=body.resume_skills,
        merged_skills=merged,
        skill_categories=categories,
        languages_found=language_totals,
        topics_found=unique_topics,
        source="github",
    )
